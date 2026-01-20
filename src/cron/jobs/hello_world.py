from __future__ import annotations

from src.cron import cron
from src.utils.logging import get_logger

logger = get_logger(__name__)


# run a job every 1 hour
@cron(id="hello_world", crontab="0 * * * *", tags=["test"])
async def hello_world() -> None:
    logger.info("Running cron: hello_world")
