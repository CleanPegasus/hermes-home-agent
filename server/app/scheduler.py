from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger("hermes.scheduler")

# A scheduled job receives a fresh session and runs to completion. The scheduler
# commits and closes the session for it, and swallows+logs any exception so one
# failing job never kills the loop. This mirrors the threading model used by
# run_agent_job in main.py (there is no asyncio loop owning background work).
JobFn = Callable[[Session], None]


@dataclass
class IntervalJob:
    name: str
    interval_seconds: float
    fn: JobFn
    last_run: float = 0.0


@dataclass
class DailyJob:
    name: str
    hour: int
    fn: JobFn
    last_run_date: str | None = None


@dataclass
class HermesScheduler:
    session_factory: sessionmaker[Session]
    tick_seconds: float = 30.0
    interval_jobs: list[IntervalJob] = field(default_factory=list)
    daily_jobs: list[DailyJob] = field(default_factory=list)
    _thread: threading.Thread | None = field(default=None, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False)

    def add_interval(self, name: str, interval_seconds: float, fn: JobFn) -> None:
        self.interval_jobs.append(IntervalJob(name=name, interval_seconds=interval_seconds, fn=fn))

    def add_daily(self, name: str, hour: int, fn: JobFn) -> None:
        self.daily_jobs.append(DailyJob(name=name, hour=hour, fn=fn))

    def start(self) -> None:
        if self._thread is not None:
            return
        if not self.interval_jobs and not self.daily_jobs:
            return
        self._thread = threading.Thread(target=self._loop, name="hermes-scheduler", daemon=True)
        self._thread.start()
        logger.info(
            "scheduler started with %d interval job(s) and %d daily job(s)",
            len(self.interval_jobs),
            len(self.daily_jobs),
        )

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            now = time.monotonic()
            today = datetime.now(timezone.utc)
            for job in self.interval_jobs:
                if now - job.last_run >= job.interval_seconds:
                    job.last_run = now
                    self._run(job.name, job.fn)
            for daily in self.daily_jobs:
                stamp = today.date().isoformat()
                if today.hour >= daily.hour and daily.last_run_date != stamp:
                    daily.last_run_date = stamp
                    self._run(daily.name, daily.fn)
            self._stop.wait(self.tick_seconds)

    def _run(self, name: str, fn: JobFn) -> None:
        session = self.session_factory()
        try:
            fn(session)
            session.commit()
            logger.info("scheduler job '%s' completed", name)
        except Exception:  # noqa: BLE001 - one bad job must not kill the loop
            session.rollback()
            logger.exception("scheduler job '%s' failed", name)
        finally:
            session.close()
