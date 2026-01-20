"""
Cron job worker entrypoint.

Runs cron-scheduled async jobs via APScheduler on the same asyncio event loop
as the worker. Health endpoints are served from a dedicated HTTP thread
(handled by BaseJobWorker).
"""

from __future__ import annotations

import asyncio
import contextlib
import signal
from pathlib import Path

# Initialize New Relic agent before any other imports
import newrelic.agent

# APScheduler + cron registry
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from src.cron import discover_and_register_jobs, setup_scheduler
from src.jobs.base_worker import BaseJobWorker
from src.utils.config import get_config_value, get_grapevine_environment
from src.utils.logging import get_logger

logger = get_logger(__name__)

current_dir = Path(__file__).parent
config_path = current_dir / "newrelic_cron_worker.toml"
grapevine_env = get_grapevine_environment()
newrelic.agent.initialize(str(config_path), environment=grapevine_env)


class CronJobWorker(BaseJobWorker):
    """
    Minimal worker that hosts a health HTTP server and runs APScheduler cron jobs.
    """

    def __init__(self, http_port: int | None = None):
        super().__init__(http_port)
        self.scheduler: AsyncIOScheduler | None = None

    def _get_default_http_port(self) -> int:
        # Separate port from ingest worker so they can run side-by-side if needed
        return int(get_config_value("CRON_HTTP_PORT", "8090"))

    def _register_custom_routes(self, app) -> None:
        # Optional: add endpoints to introspect scheduler/jobs
        @app.get("/jobs")
        async def list_jobs():
            jobs = []
            if self.scheduler:
                for j in self.scheduler.get_jobs():
                    jobs.append(
                        {
                            "id": j.id,
                            "name": j.name,
                            "next_run_time": str(j.next_run_time) if j.next_run_time else None,
                            "trigger": str(j.trigger),
                        }
                    )
            return {
                "jobs": jobs,
                "scheduler_running": bool(self.scheduler and self.scheduler.running),
            }

        @app.get("/ready")
        async def ready():
            # Mark ready if scheduler is created; you can tighten this if you need
            return {
                "ok": True,
                "scheduler_running": bool(self.scheduler and self.scheduler.running),
            }

    async def start_scheduler(self) -> None:
        """
        Create and start the AsyncIOScheduler, load job modules, and register jobs.
        Safe to call once at startup.
        """
        # Make sure NR app is registered since we have no web transactions
        newrelic.agent.register_application()

        # Create scheduler on current loop
        self.scheduler = AsyncIOScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce": True,
                "misfire_grace_time": int(get_config_value("CRON_MISFIRE_GRACE_SECONDS", "300")),
            },
        )

        # Import all job modules so their @cron decorators run and register
        discover_and_register_jobs()

        # Register jobs + listeners (respects IS_SCHEDULER, CRON_TAGS, CRON_OVERRIDES_JSON)
        setup_scheduler(self.scheduler)

        # Start the scheduler (noop if no jobs due to env gates)
        self.scheduler.start()
        logger.info("APScheduler started", extra={"job_count": len(self.scheduler.get_jobs())})

    async def shutdown_scheduler(self) -> None:
        if self.scheduler:
            try:
                self.scheduler.shutdown(wait=False)
                logger.info("APScheduler shut down")
            except Exception as e:
                logger.warning("APScheduler shutdown error", extra={"error": str(e)})


async def main() -> None:
    """
    Main entry point for cron job worker.
    Spins up HTTP server thread and runs the scheduler until cancelled.
    """
    worker = CronJobWorker()

    # A simple never-ending awaitable that we can cancel via signals
    stop_event = asyncio.Event()

    def _handle_sigterm():
        logger.info("Received termination signal; stopping cron worker")
        stop_event.set()

    # Register signal handlers (Unix)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _handle_sigterm)

    async def run_forever():
        try:
            await worker.start_scheduler()
            await stop_event.wait()
        finally:
            await worker.shutdown_scheduler()

    # Run with HTTP server in a dedicated thread (health endpoints, /jobs, etc.)
    await worker.run_with_dedicated_http_thread(run_forever())


if __name__ == "__main__":
    asyncio.run(main())
