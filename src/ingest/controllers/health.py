"""Health check endpoints for the ingest API."""

import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class StatusResponse(BaseModel):
    status: str
    version: str


@router.get("/live")
async def liveness_check():
    """Liveness probe - always returns healthy if process is running."""
    return {"status": "alive", "version": "1.0.0"}


@router.get("/ready")
async def readiness_check(request: Request):
    """Readiness probe - only returns healthy when fully initialized."""
    try:
        initialization_status = getattr(request.app.state, "initialization_status", "unknown")

        if initialization_status == "ready":
            # Service is fully initialized
            queue = getattr(request.app.state, "queue", None)
            if queue:
                # Get queue status for observability
                queue_status = {
                    "queue_available": True,
                    "is_stopping": getattr(queue, "_is_stopping", False),
                }

                # Try to get queue size if method is available
                try:
                    queue_status["pending_jobs"] = await queue.size()
                except (AttributeError, Exception):
                    queue_status["pending_jobs"] = "unknown"
            else:
                queue_status = {"queue_available": False}

            return {
                "status": "ready",
                "version": "1.0.0",
                "initialization": {
                    "status": initialization_status,
                    "attempt": getattr(request.app.state, "initialization_attempt", 0),
                },
                "queue": queue_status,
            }
        else:
            # Service is not ready yet
            from fastapi import HTTPException

            raise HTTPException(
                status_code=503,
                detail={
                    "status": "not_ready",
                    "version": "1.0.0",
                    "initialization": {
                        "status": initialization_status,
                        "attempt": getattr(request.app.state, "initialization_attempt", 0),
                        "error": getattr(request.app.state, "initialization_error", None),
                    },
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in readiness check: {e}")
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503, detail={"status": "error", "version": "1.0.0", "error": str(e)}
        )
