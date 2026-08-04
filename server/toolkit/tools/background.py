"""Background job manager — manages long-running shell commands in the background.

Provides a registry for background processes that can be queried for output
or killed by the agent.  Each job gets a unique ID and tracks its stdout/stderr
in memory.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BackgroundJob:
    """A background shell job with captured output."""

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

    def is_running(self) -> bool:
        return not self.done and self.process.returncode is None


class BackgroundJobManager:
    """Manages background shell jobs.

    Provides start, poll output, and kill operations.  Jobs are keyed by
    a short unique ID (8 hex chars).
    """

    def __init__(self) -> None:
        self._jobs: dict[str, BackgroundJob] = {}

    def start(
        self,
        command: str,
        workspace_root: str,
        description: str = "",
    ) -> BackgroundJob:
        """Start a command in the background and return a BackgroundJob handle."""
        job_id = uuid.uuid4().hex[:8]

        logger.info("Starting background job %s: %s", job_id, command)

        process = asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=workspace_root,
        )

        job = BackgroundJob(
            id=job_id,
            command=command,
            description=description,
            process=process,
            working_dir=workspace_root,
        )
        self._jobs[job_id] = job

        # Start a background task to collect output
        asyncio.create_task(self._collect_output(job))

        return job

    async def _collect_output(self, job: BackgroundJob) -> None:
        """Collect stdout/stderr from a background job."""
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
        """Get current output from a background job.

        Returns formatted output string, or None if job not found.
        """
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

    def kill(self, job_id: str) -> str:
        """Kill a background job. Returns a status message."""
        job = self._jobs.get(job_id)
        if job is None:
            return f"Job {job_id} not found"

        if job.done:
            return f"Job {job_id} already completed (exit code: {job.exit_code})"

        if job.process.returncode is None:
            job.process.kill()
            try:
                job.process.wait()
            except Exception:
                pass
            return f"Job {job_id} killed"

        return f"Job {job_id} already terminated"

    def remove(self, job_id: str) -> bool:
        """Remove a job from the manager. Returns True if found."""
        return self._jobs.pop(job_id, None) is not None

    def list_jobs(self) -> list[dict[str, Any]]:
        """List all tracked jobs with their status."""
        result = []
        for job_id, job in self._jobs.items():
            result.append(
                {
                    "id": job_id,
                    "command": job.command,
                    "description": job.description,
                    "done": job.done,
                    "exit_code": job.exit_code,
                }
            )
        return result

    def cleanup_completed(self) -> int:
        """Remove completed jobs. Returns count of removed jobs."""
        to_remove = [job_id for job_id, job in self._jobs.items() if job.done]
        for job_id in to_remove:
            del self._jobs[job_id]
        return len(to_remove)


# Singleton instance
_background_manager: BackgroundJobManager | None = None


def get_background_manager() -> BackgroundJobManager:
    """Get the global background job manager singleton."""
    global _background_manager
    if _background_manager is None:
        _background_manager = BackgroundJobManager()
    return _background_manager
