from __future__ import annotations

import functools

import newrelic.agent
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.utils.logging import get_logger

from .registry import (
    CRON_REGISTRY,
    filter_jobs_by_tags,
    load_runtime_overrides,
    should_run_this_pod,
)

logger = get_logger(__name__)


def setup_scheduler(
    scheduler: AsyncIOScheduler,
) -> None:
    """
    Adds all registered cron jobs to the given AsyncIOScheduler with consistent policies.
    Call this once after importing all job modules.
    """
    if not should_run_this_pod():
        logger.info(
            "APScheduler: pod-level disabled (IS_SCHEDULER != '1'); skipping job registration"
        )
        return

    overrides = load_runtime_overrides()
    jobs = filter_jobs_by_tags(CRON_REGISTRY)

    # Listener for success/failure
    def _job_listener(event: JobExecutionEvent) -> None:
        job = scheduler.get_job(event.job_id)
        job_name = job.name if job else event.job_id
        if event.exception:
            logger.error(
                "Cron job failed", extra={"job_name": job_name, "exception": str(event.exception)}
            )
            newrelic.agent.record_exception()
        else:
            logger.info(
                "Cron job succeeded",
                extra={"job_name": job_name, "scheduled_run": str(event.scheduled_run_time)},
            )

    scheduler.add_listener(_job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    # Register jobs
    registered = 0
    for jid, j in jobs.items():
        if not j.enabled:
            logger.info("Cron job disabled (env-gated)", extra={"job_id": jid, "name": j.name})
            continue

        crontab = overrides.get(jid, j.crontab)
        if not crontab:
            logger.warning(
                "Cron job missing crontab; skipping", extra={"job_id": jid, "name": j.name}
            )
            continue

        # Wrap with New Relic background task (keeps per-job naming)
        @functools.wraps(j.func)
        async def _nr_wrapped(func=j.func, name=j.name):
            @newrelic.agent.background_task(name=f"IngestWorker/cron/{name}")
            async def _inner():
                return await func()

            return await _inner()

        scheduler.add_job(
            _nr_wrapped,
            trigger=_make_trigger(crontab),
            id=jid,
            name=j.name,
            max_instances=j.max_instances,
            misfire_grace_time=j.misfire_grace_time,
            coalesce=j.coalesce,
            replace_existing=True,
        )
        registered += 1

    logger.info(f"APScheduler: registered {registered} cron job(s)")


def _make_trigger(crontab: str) -> CronTrigger:
    parts = crontab.split()
    if len(parts) == 5:
        # minute hour day month day_of_week
        return CronTrigger.from_crontab(crontab)
    # Note: second field is not supported by CronTrigger.from_crontab
    if len(parts) == 6:
        # second minute hour day month day_of_week
        sec, minute, hour, day, month, dow = parts
        return CronTrigger(
            second=sec, minute=minute, hour=hour, day=day, month=month, day_of_week=dow
        )
    raise ValueError(f"Invalid crontab '{crontab}': expected 5 or 6 fields")
