"""In-process async job manager with progress + cancellation.

Long-running work (backtests, optimizations) returns a job/run ID
immediately; the frontend polls GET endpoints for status. Results are
persisted in SQLite so they survive restarts.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

STATES = [
    "queued", "fetching_data", "preparing_data", "calculating_indicators",
    "running_backtest", "calculating_metrics", "completed", "failed", "cancelled",
]


class Job:
    def __init__(self, job_id: str) -> None:
        self.id = job_id
        self.cancel_event = asyncio.Event()
        self.task: asyncio.Task | None = None

    def cancel(self) -> None:
        self.cancel_event.set()
        if self.task and not self.task.done():
            self.task.cancel()

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    def start(self, job_id: str, coro_factory: Callable[[Job], Awaitable[None]]) -> Job:
        job = Job(job_id)
        job.task = asyncio.create_task(self._run(job, coro_factory))
        self._jobs[job_id] = job
        return job

    async def _run(self, job: Job, coro_factory: Callable[[Job], Awaitable[None]]) -> None:
        try:
            await coro_factory(job)
        except asyncio.CancelledError:
            logger.info("job %s cancelled", job.id)
        except Exception:
            logger.exception("job %s failed", job.id)
        finally:
            self._jobs.pop(job.id, None)

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job:
            job.cancel()
            return True
        return False

    def is_running(self, job_id: str) -> bool:
        return job_id in self._jobs


job_manager = JobManager()
