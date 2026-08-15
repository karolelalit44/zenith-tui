from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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


class BackgroundJobManager:
    def __init__(self) -> None:
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
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
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

    async def _collect_output(self, job: BackgroundJob) -> None:
        try:
            stdout, stderr = await job.process.communicate()
            job.stdout = stdout.decode("utf-8", errors="replace") if stdout else ""
            job.stderr = stderr.decode("utf-8", errors="replace") if stderr else ""
            job.exit_code = job.process.returncode
            job.done = True
            logger.info(
                "Background job %s completed: exit_code=%d, stdout_len=%d, stderr_len=%d",
                job.id,
                job.exit_code or 0,
                len(job.stdout),
                len(job.stderr),
            )
        except Exception as e:
            job.error = e
            job.done = True
            logger.error("Background job %s failed: %s", job.id, e)

    def get_output(self, job_id: str) -> str | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        parts: list[str] = []
        if job.done:
            parts.append(f"[Job {job_id}] Completed (exit code: {job.exit_code})")
        else:
            parts.append(f"[Job {job_id}] Still running...")
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
