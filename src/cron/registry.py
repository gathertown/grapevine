from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

CronFunc = Callable[[], Awaitable[None]]


@dataclass(frozen=True)
class CronJobDef:
    id: str
    func: CronFunc
    crontab: str | None = None  # e.g. "*/10 * * * *"
    name: str | None = None  # human-friendly display name
    tags: list[str] = field(default_factory=list)
    max_instances: int = 1
    misfire_grace_time: int = 300
    coalesce: bool = True
    enabled: bool = True  # env-gated at registration time


# Global in-process registry
CRON_REGISTRY: dict[str, CronJobDef] = {}


def should_run_this_pod() -> bool:
    """Gate all crons at the pod level (prevent duplicate firing across replicas)."""
    return True  # os.getenv("IS_SCHEDULER", "0") == "1"


def load_runtime_overrides() -> dict[str, str]:
    """
    Allow per-job schedule overrides without a deploy.
    Env: CRON_OVERRIDES_JSON='{"housekeeping":"*/5 * * * *","daily_refresh":"15 2 * * *"}'
    """
    raw = os.getenv("CRON_OVERRIDES_JSON", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def filter_jobs_by_tags(jobs: dict[str, CronJobDef]) -> dict[str, CronJobDef]:
    """
    Run only jobs whose tags intersect CRON_TAGS (comma-separated).
    Leave CRON_TAGS unset to run all registered jobs for this pod.
    """
    tag_str = os.getenv("CRON_TAGS", "").strip()
    if not tag_str:
        return jobs
    wanted = {t.strip() for t in tag_str.split(",") if t.strip()}
    if not wanted:
        return jobs
    out: dict[str, CronJobDef] = {}
    for jid, j in jobs.items():
        if any(t in wanted for t in j.tags):
            out[jid] = j
    return out
