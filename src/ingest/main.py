import asyncio

import uvicorn
from fastapi import FastAPI

from src.ingest.controllers import (
    health_router,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


app = FastAPI(
    title="Corporate Context Live Storage API",
    description="Real-time webhook processing for document storage and embedding generation",
    version="1.0.0",
)
app.include_router(health_router)


async def main():
    uvicorn.run("src.ingest.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    asyncio.run(main())
