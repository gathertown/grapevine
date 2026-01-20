"""Health check endpoints and utilities for the MCP server."""

import asyncio
from datetime import datetime, timedelta
from typing import cast

from starlette.requests import Request
from starlette.responses import JSONResponse

from src.clients.openai import get_openai_client
from src.clients.redis import ping as redis_ping
from src.clients.supabase import get_control_db_connection
from src.mcp.middleware.metrics import get_metrics

# Cache for expensive health checks
_health_cache: dict[str, dict[str, object | None]] = {
    "openai": {"status": None, "expires_at": None},
    "redis": {"status": None, "expires_at": None},
}


async def check_postgres_health() -> tuple[bool, str]:
    """Check PostgreSQL connectivity using the control database."""
    try:
        conn = await get_control_db_connection()
        await conn.execute("SELECT 1")
        await conn.close()
        return True, "healthy"
    except Exception as e:
        return False, f"unhealthy: {str(e)}"


async def check_openai_health(use_cache: bool = True) -> tuple[bool, str]:
    """Check OpenAI API connectivity with caching."""
    now = datetime.now()

    # Check cache if enabled
    openai_cache = _health_cache["openai"]
    if (
        use_cache
        and openai_cache["expires_at"]
        and now < cast(datetime, openai_cache["expires_at"])
    ):
        cached_status = cast(tuple[bool, str], openai_cache["status"])
        return cached_status[0], f"{cached_status[1]} (cached)"

    try:
        # Light check - just verify we can create the client and have an API key
        client = get_openai_client()
        if not client._api_key:
            result = (False, "unhealthy: No API key configured")
        else:
            # Optionally make a lightweight API call (list models is relatively cheap)
            client.list_models()
            # For now, just check if client initializes properly
            result = (True, "healthy")

        # Cache the result for 5 minutes
        openai_cache["status"] = result
        openai_cache["expires_at"] = now + timedelta(minutes=5)

        return result
    except Exception as e:
        result = (False, f"unhealthy: {str(e)}")
        openai_cache["status"] = result
        openai_cache["expires_at"] = now + timedelta(minutes=1)  # Shorter cache for failures
        return result


async def check_redis_health(use_cache: bool = True) -> tuple[bool, str]:
    """Check Redis connectivity with caching."""
    now = datetime.now()

    # Check cache if enabled
    redis_cache = _health_cache["redis"]
    if use_cache and redis_cache["expires_at"] and now < cast(datetime, redis_cache["expires_at"]):
        cached_status = cast(tuple[bool, str], redis_cache["status"])
        return cached_status[0], f"{cached_status[1]} (cached)"

    try:
        # Use the Redis ping function from our client
        is_healthy = await redis_ping()
        result = (True, "healthy") if is_healthy else (False, "unhealthy: ping failed")

        # Cache the result for 5 minutes
        redis_cache["status"] = result
        redis_cache["expires_at"] = now + timedelta(minutes=5)

        return result
    except Exception as e:
        result = (False, f"unhealthy: {str(e)}")
        redis_cache["status"] = result
        redis_cache["expires_at"] = now + timedelta(minutes=1)  # Shorter cache for failures
        return result


def register_health_routes(app):
    """Register health check routes with the FastAPI app instance."""

    @app.get("/health")
    async def health_check(request: Request) -> JSONResponse:
        """Comprehensive health check endpoint for debugging and monitoring."""

        # Run all health checks in parallel
        results = await asyncio.gather(
            check_postgres_health(),
            check_openai_health(),
            check_redis_health(),
            return_exceptions=True,
        )

        checks: dict[str, str] = {}
        all_healthy = True

        service_names = ["postgres", "openai", "redis"]
        for i, result in enumerate(results):
            service = service_names[i]
            if isinstance(result, Exception):
                checks[service] = f"unhealthy: {str(result)}"
                all_healthy = False
            else:
                healthy, message = result  # type: ignore[misc]
                checks[service] = message
                if not healthy:
                    all_healthy = False

        return JSONResponse(
            {
                "status": "healthy" if all_healthy else "unhealthy",
                "service": "corporate-context-mcp",
                "timestamp": datetime.utcnow().isoformat(),
                "checks": checks,
            }
        )

    @app.get("/health/live")
    async def liveness_probe(request: Request) -> JSONResponse:
        """Liveness probe - always returns healthy if process is running.

        This should be lightweight and only check if the app itself is responsive.
        Does not check external dependencies or initialization status.
        """
        return JSONResponse(
            {
                "status": "alive",
                "service": "corporate-context-mcp",
                "timestamp": datetime.utcnow().isoformat(),
                "probe": "liveness",
            }
        )

    @app.get("/health/ready")
    async def readiness_probe(request: Request) -> JSONResponse:
        """Readiness probe - only returns healthy when fully initialized and services are available.

        Checks initialization status first, then critical dependencies if ready.
        """
        try:
            # Get initialization status from app state
            initialization_status = getattr(request.app.state, "initialization_status", "unknown")

            if initialization_status == "ready":
                # Service is fully initialized, check external dependencies
                results = await asyncio.gather(
                    check_postgres_health(),
                    check_openai_health(
                        use_cache=True
                    ),  # Use cache for readiness to avoid rate limits
                    return_exceptions=True,
                )

                all_healthy = True
                checks: dict[str, str] = {}

                # Map results to service names
                critical_services = [
                    ("postgres", results[0]),
                    ("openai", results[1]),
                ]

                for service_name, result in critical_services:
                    if isinstance(result, Exception):
                        checks[service_name] = f"unhealthy: {str(result)}"
                        all_healthy = False
                    else:
                        healthy, message = result  # type: ignore[misc]
                        checks[service_name] = message
                        if not healthy:
                            all_healthy = False

                response_data = {
                    "status": "ready" if all_healthy else "not_ready",
                    "service": "corporate-context-mcp",
                    "timestamp": datetime.utcnow().isoformat(),
                    "probe": "readiness",
                    "initialization": {
                        "status": initialization_status,
                        "attempt": getattr(request.app.state, "initialization_attempt", 0),
                    },
                    "checks": checks,
                }

                # Return 503 if services not healthy
                if not all_healthy:
                    response_data["error"] = "External services not ready"
                    return JSONResponse(response_data, status_code=503)

                return JSONResponse(response_data)
            else:
                # Service is not ready yet - return 503 with detailed status
                return JSONResponse(
                    {
                        "status": "not_ready",
                        "service": "corporate-context-mcp",
                        "timestamp": datetime.utcnow().isoformat(),
                        "probe": "readiness",
                        "initialization": {
                            "status": initialization_status,
                            "attempt": getattr(request.app.state, "initialization_attempt", 0),
                            "error": getattr(request.app.state, "initialization_error", None),
                        },
                        "error": "Service initialization not complete",
                    },
                    status_code=503,
                )

        except Exception as e:
            # Handle unexpected errors
            return JSONResponse(
                {
                    "status": "error",
                    "service": "corporate-context-mcp",
                    "timestamp": datetime.utcnow().isoformat(),
                    "probe": "readiness",
                    "error": str(e),
                },
                status_code=503,
            )

    @app.get("/metrics")
    async def metrics_endpoint(request: Request):
        """Prometheus metrics endpoint."""
        from starlette.responses import Response

        metrics_data = get_metrics()
        return Response(content=metrics_data, media_type="text/plain; version=0.0.4; charset=utf-8")
