from __future__ import annotations

import os

from .registry import CRON_REGISTRY, CronFunc, CronJobDef


def cron(
    *,
    id: str,
    crontab: str | None = None,
    name: str | None = None,
    tags: list[str] | None = None,
    enabled_env: str | None = None,  # if set, job runs only when this env var == "1"
    max_instances: int = 1,
    misfire_grace_time: int = 300,
    coalesce: bool = True,
):
    """
    Decorator to register an async cron job.

    Example:
        @cron(id="housekeeping", crontab="*/10 * * * *", tags=["ops"])
        async def housekeeping(): ...
    """

    def _wrap(func: CronFunc) -> CronFunc:
        job_enabled = True
        if enabled_env:
            job_enabled = os.getenv(enabled_env, "0") == "1"

        job_def = CronJobDef(
            id=id,
            func=func,
            crontab=crontab,
            name=name or id,
            tags=tags or [],
            max_instances=max_instances,
            misfire_grace_time=misfire_grace_time,
            coalesce=coalesce,
            enabled=job_enabled,
        )
        if id in CRON_REGISTRY:
            raise ValueError(f"Duplicate cron id: {id}")
        CRON_REGISTRY[id] = job_def
        return func

    return _wrap
