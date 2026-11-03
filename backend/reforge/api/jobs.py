"""Background jobs: a photo is processed while the client polls its real stage events.

One process, in memory. A job folder keeps ``request.json`` from the start, and ``report.json`` or ``error.json`` once
the job ends, so a finished job is read back from disk after a restart; a job that was running when the server stopped
has neither and is reported ``interrupted``. At most ``max_running`` jobs run at once and ``max_waiting`` more can
queue, so a burst of uploads can't exhaust the machine (or, through the AI calls, the daily budget).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from reforge.errors import ReforgeError
from reforge.pipeline import STAGES, Progress

FINISHED_TTL_S = 600.0  # finished jobs leave memory after this; their status is then read from disk


@dataclass
class Stage:
    id: str
    state: str = "pending"  # "pending" | "running" | "done"
    seconds: float | None = None


@dataclass
class Job:
    job_id: str
    created_at: str
    state: str = "queued"  # "queued" | "running" | "done" | "failed"
    stages: dict[str, Stage] = field(default_factory=lambda: {s: Stage(s) for s in STAGES})
    started: float | None = None  # monotonic
    finished: float | None = None
    error: dict | None = None
    exception: BaseException | None = None
    task: asyncio.Task | None = None

    def progress(self, stage: str, state: str, seconds: float | None) -> None:
        entry = self.stages.setdefault(stage, Stage(stage))
        entry.state, entry.seconds = state, seconds

    @property
    def elapsed_s(self) -> float:
        if self.started is None:
            return 0.0
        return round((self.finished or time.monotonic()) - self.started, 2)

    def stage_list(self) -> list[dict]:
        return [{"id": s.id, "state": s.state, "seconds": s.seconds} for s in self.stages.values()]


class JobRegistry:
    def __init__(self, max_running: int = 2, max_waiting: int = 8) -> None:
        self.max_running = max_running
        self.max_waiting = max_waiting
        self._jobs: dict[str, Job] = {}
        self._slots: asyncio.Semaphore | None = None

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def active(self) -> int:
        return sum(1 for j in self._jobs.values() if j.state in ("queued", "running"))

    def check_capacity(self) -> None:
        if self.active() >= self.max_running + self.max_waiting:
            raise ReforgeError("SERVER_BUSY", "Too many parts are being analysed right now.",
                               "Try again in a minute.")

    def submit(self, job_id: str, work: Callable[[Progress], Awaitable[dict]]) -> Job:
        self._prune()
        if self._slots is None:  # created lazily, inside the running event loop
            self._slots = asyncio.Semaphore(self.max_running)
        job = Job(job_id, datetime.now(UTC).isoformat(timespec="seconds"))
        self._jobs[job_id] = job
        job.task = asyncio.create_task(self._run(job, work), name=f"job-{job_id}")
        return job

    async def _run(self, job: Job, work: Callable[[Progress], Awaitable[dict]]) -> dict | None:
        assert self._slots is not None
        async with self._slots:
            job.state, job.started = "running", time.monotonic()
            try:
                report = await work(job.progress)
            except ReforgeError as exc:
                job.state, job.error, job.exception = "failed", exc.to_dict(), exc
                return None
            except Exception as exc:  # the job's own error.json records it; the status says it failed
                job.state, job.exception = "failed", exc
                job.error = {"code": "INTERNAL_ERROR", "message": "The analysis stopped on an unexpected error.",
                             "hint": "Try again; if it happens again, report the job id."}
                return None
            finally:
                job.finished = time.monotonic()
                for stage in job.stages.values():  # a stage that was running when the job stopped didn't finish
                    if stage.state == "running":
                        stage.state = "stopped"
            job.state = "done"
            return report

    def _prune(self) -> None:
        now = time.monotonic()
        for job_id in [j.job_id for j in self._jobs.values()
                       if j.finished is not None and now - j.finished > FINISHED_TTL_S]:
            del self._jobs[job_id]
