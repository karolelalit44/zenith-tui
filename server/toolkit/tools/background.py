from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Retention bounds. Without these a long-lived watcher or dev server accumulates
# its entire output in memory for the life of the process and finished jobs are
# never released: `remove()` only runs for jobs that exit inside the 1s grace
# period in bash._start_background.
MAX_RETAINED_JOBS = 32
MAX_RETAINED_OUTPUT_CHARS = 2_000_000
# Aggregate ceiling across every retained job. Per-stream limits alone admit
# 32 jobs x 2 streams x 2M chars, which is a hundred-plus MB of log text held for
# the life of the process.
MAX_RETAINED_TOTAL_CHARS = 8_000_000
_TRUNCATION_MARKER = "\n... [output truncated: {kept} of {total} chars retained]\n"


def _truncate(text: str, limit: int = MAX_RETAINED_OUTPUT_CHARS) -> str:
    """Keep the head and tail of *text*, dropping the middle.

    Head and tail because both ends carry signal: the command's opening context
    and its final errors. The middle is where a chatty build log lives and is the
    part the model can re-read by re-running with a narrower command.
    """
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    tail = limit - head
    return (
        text[:head]
        + _TRUNCATION_MARKER.format(kept=limit, total=len(text))
        + text[-tail:]
    )


@dataclass
class BackgroundJob:
    id: str
    command: str
    description: str
    process: asyncio.subprocess.Process
    working_dir: str
    stdout: str = ""
    stderr: str = ""
    done: bool = False
    exit_code: int | None = None
    error: Exception | None = None
    stdout_truncated: bool = False
    stderr_truncated: bool = False
    # True once output was dropped. Surfaced by job_output so the model is told
    # the slice it is reading is partial instead of inferring a short log.
    output_truncated: bool = False


class BackgroundJobManager:
    def __init__(self) -> None:
        # Insertion-ordered so eviction can drop the oldest job. Dicts preserve
        # insertion order, so this needs no OrderedDict.
        self._jobs: dict[str, BackgroundJob] = {}
        self._reported: set[str] = set()

    async def start(
        self,
        command: str,
        workspace_root: str,
        description: str = "",
        cwd: str | None = None,
    ) -> BackgroundJob:
        job_id = uuid.uuid4().hex[:8]
        cwd = cwd or workspace_root
        logger.info("Starting background job %s (cwd=%s): %s", job_id, cwd, command)
        from server.shell_runner import run_shell_command

        process = await run_shell_command(command, cwd=cwd)
        return self.register(command, workspace_root, description, process, job_id, cwd=cwd)

    def register(
        self,
        command: str,
        workspace_root: str,
        description: str,
        process: asyncio.subprocess.Process,
        job_id: str | None = None,
        cwd: str | None = None,
    ) -> BackgroundJob:
        job_id = job_id or uuid.uuid4().hex[:8]
        logger.info("Registering background job %s: %s", job_id, command)
        job = BackgroundJob(
            id=job_id,
            command=command,
            description=description,
            process=process,
            working_dir=cwd or workspace_root,
        )
        self._jobs[job_id] = job
        asyncio.create_task(self._collect_output(job))
        return job

    def _retained_chars(self) -> int:
        return sum(len(job.stdout) + len(job.stderr) for job in self._jobs.values())

    def _evict_if_over_capacity(self) -> None:
        """Drop the oldest finished jobs once a retention bound is reached.

        Bounded by both job count and total retained characters. Running jobs are
        never evicted: the model still has a live job id for them and an eviction
        would turn `job_output` into a lookup failure for a process that is
        genuinely still going. The bounds are therefore soft when many jobs are in
        flight at once, which is the correct trade — the alternative is killing
        work the model asked for.
        """
        while len(self._jobs) > MAX_RETAINED_JOBS or self._retained_chars() > MAX_RETAINED_TOTAL_CHARS:
            for job_id, job in list(self._jobs.items()):
                if job.done:
                    self._jobs.pop(job_id, None)
                    self._reported.discard(job_id)
                    logger.info("Evicted finished background job %s (retention cap)", job_id)
                    break
            else:
                return

    async def _collect_output(self, job: BackgroundJob) -> None:
        try:
            stdout, stderr = await job.process.communicate()
            # The truncation flag must come from the same decoded text _truncate
            # saw. Deriving it from len(raw_bytes) instead would raise the flag on
            # multi-byte output that was never cut, and job_output would then tell
            # the model its middle was dropped when nothing was.
            stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""
            job.stdout_truncated = len(stdout_text) > MAX_RETAINED_OUTPUT_CHARS
            job.stderr_truncated = len(stderr_text) > MAX_RETAINED_OUTPUT_CHARS
            job.stdout = _truncate(stdout_text)
            job.stderr = _truncate(stderr_text)
            job.output_truncated = job.stdout_truncated or job.stderr_truncated
            job.exit_code = job.process.returncode
            job.done = True
            logger.info(
                "Background job %s completed: exit_code=%d, stdout_len=%d, stderr_len=%d%s",
                job.id,
                job.exit_code or 0,
                len(job.stdout),
                len(job.stderr),
                " (truncated)" if job.output_truncated else "",
            )
        except Exception as e:
            job.error = e
            job.done = True
            logger.error("Background job %s failed: %s", job.id, e)
        finally:
            self._evict_if_over_capacity()

    def get_output(self, job_id: str) -> str | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        parts: list[str] = []
        if job.done:
            parts.append(f"[Job {job_id}] Completed (exit code: {job.exit_code})")
        else:
            parts.append(f"[Job {job_id}] Still running...")
        if job.output_truncated:
            parts.append(
                f"[Job {job_id}] Output exceeded the retained limit and its middle was "
                "dropped. Re-run the command with a narrower scope, or redirect to a "
                "file and read that."
            )
        if job.stdout.strip():
            parts.append(job.stdout.strip())
        if job.stderr.strip():
            parts.append(f"stderr: {job.stderr.strip()}")
        return "\n".join(parts)

    def get(self, job_id: str) -> BackgroundJob | None:
        return self._jobs.get(job_id)

    def pending_completions(self) -> list[BackgroundJob]:
        """Jobs that finished since the last poll, each returned exactly once.

        The agent loop polls this each turn and surfaces completions (especially
        failures) to the model, so a background job that exits non-zero is no
        longer silently invisible.
        """
        fresh = [j for j in self._jobs.values() if j.done and j.id not in self._reported]
        for job in fresh:
            self._reported.add(job.id)
        return fresh

    def kill(self, job_id: str) -> str:
        job = self._jobs.get(job_id)
        if job is None:
            return f"Job {job_id} not found"
        if job.done:
            return f"Job {job_id} already completed (exit code: {job.exit_code})"
        if job.process.returncode is None:
            job.process.kill()
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                loop.create_task(job.process.wait())
            return f"Job {job_id} killed"
        return f"Job {job_id} already terminated"

    def remove(self, job_id: str) -> bool:
        return self._jobs.pop(job_id, None) is not None


_background_manager: BackgroundJobManager | None = None


def get_background_manager() -> BackgroundJobManager:
    global _background_manager
    if _background_manager is None:
        _background_manager = BackgroundJobManager()
    return _background_manager
