"""MCP server for corporate knowledge store access - Enhanced version with advanced search capabilities."""

# Initialize New Relic agent before any other imports
from pathlib import Path

import newrelic.agent

from src.utils.config import get_grapevine_environment

# Get the directory containing this file and environment
current_dir = Path(__file__).parent
config_path = current_dir / "newrelic.toml"
grapevine_env = get_grapevine_environment()
# Initialize New Relic with the MCP-specific TOML config and environment
newrelic.agent.initialize(str(config_path), environment=grapevine_env)

import argparse
import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.mcp.api.ask_endpoint import router as ask_router
from src.mcp.api.ask_streaming_endpoint import router as ask_streaming_router
from src.mcp.api.billing_endpoint import router as billing_router
from src.mcp.health import register_health_routes
from src.mcp.mcp_instance import get_mcp
from src.mcp.middleware import (
    MetricsMiddleware,
    NewRelicMiddleware,
    OrgContextMiddleware,
    PermissionsMiddleware,
)
from src.mcp.middleware.grapevine_logging import GrapevineLoggingMiddleware
from src.mcp.startup_checks import run_startup_checks_async
from src.mcp.tools import register_tools
from src.utils.config import get_frontend_url
from src.utils.logging import get_logger, get_uvicorn_log_config

# Get logger for this module
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app):
    """Initialize services on startup and handle graceful shutdown."""
    initialization_task = None

    # Initialize app state early so health checks work
    app.state.initialization_status = "starting"
    app.state.initialization_error = None
    app.state.initialization_attempt = 0

    async def initialize_services():
        """Continuously attempt to initialize services until successful."""

        while True:
            try:
                app.state.initialization_attempt += 1
                app.state.initialization_status = "waiting_for_config"

                logger.info(f"Initialization attempt #{app.state.initialization_attempt}")

                app.state.initialization_status = "initializing_services"

                logger.info("Registering MCP tools...")
                register_tools()

                logger.info("Running startup checks...")
                await run_startup_checks_async()

                app.state.initialization_status = "ready"
                app.state.initialization_error = None

                logger.info("✅ MCP server initialization complete")
                break  # Exit retry loop on success

            except Exception as e:
                # Record the error in New Relic for major startup failures
                newrelic.agent.record_exception()

                error_msg = str(e)
                logger.error(
                    f"❌ Initialization attempt #{app.state.initialization_attempt} failed: {error_msg}"
                )
                app.state.initialization_status = "failed"
                app.state.initialization_error = error_msg

                # Wait 1 second before trying again
                await asyncio.sleep(1)

    # Start initialization in background
    initialization_task = asyncio.create_task(initialize_services())

    yield

    # Graceful shutdown
    try:
        logger.info("🛑 Shutting down MCP server gracefully...")

        # Cancel initialization task if still running
        if initialization_task and not initialization_task.done():
            logger.info("⏱️  Stopping initialization task...")
            initialization_task.cancel()
            try:
                await initialization_task
            except asyncio.CancelledError:
                logger.info("✅ Initialization task cancelled successfully")
            except Exception as e:
                logger.warning(f"⚠️  Error during initialization task shutdown: {e}")

        logger.info("✅ Graceful shutdown complete")
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")


# Create MCP instance and get its HTTP app
mcp = get_mcp()
mcp_app = mcp.http_app(path="/")


# Create combined lifespan for FastAPI app
@asynccontextmanager
async def combined_lifespan(app: FastAPI):
    # Run our custom initialization lifespan
    async with lifespan(app):  # noqa: SIM117
        # Run MCP's lifespan
        # Note: Cannot combine these context managers as they need to be nested
        # for proper initialization order - our lifespan must complete setup
        # before MCP's lifespan starts
        async with mcp_app.lifespan(app):
            yield


# Add FastMCP-specific middleware to the MCP instance
# (These middleware only work with FastMCP, not FastAPI)
# Order matters:
# 1. OrgContextMiddleware sets up tenant context
# 2. PermissionsMiddleware generates principal permission tokens from user email
# 3. NewRelicMiddleware can use the org context for custom attributes
# 4. GrapevineLoggingMiddleware can extract it for logging and handle MCP message logging
# 5. MetricsMiddleware runs last for Prometheus metrics
mcp.add_middleware(OrgContextMiddleware())
mcp.add_middleware(PermissionsMiddleware())
mcp.add_middleware(NewRelicMiddleware())
# Only log payloads in local for debugging
include_payloads = get_grapevine_environment() == "local"
mcp.add_middleware(
    GrapevineLoggingMiddleware(include_payloads=include_payloads, max_payload_length=1000)
)
mcp.add_middleware(MetricsMiddleware())

# Create FastAPI app with combined lifespan
app = FastAPI(
    title="Enhanced MCP Knowledge Store Server",
    description="Corporate knowledge store with real-time search capabilities",
    version="1.0.0",
    lifespan=combined_lifespan,
)

# Add CORS middleware to allow frontend requests
allowed_origins = [get_frontend_url()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Gather auth middleware, excluding internal API endpoints that use JWT auth
# Register health check routes on FastAPI app
register_health_routes(app)

# Register REST API routes
app.include_router(ask_router, prefix="/v1")
app.include_router(ask_streaming_router, prefix="/v1")
app.include_router(billing_router, prefix="/v1")


# Mount the MCP app at root so well-known endpoints are directly exposed
app.mount("/", mcp_app)


def main():
    """Main function to start the MCP server."""
    parser = argparse.ArgumentParser(description="Enhanced MCP Knowledge Store Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument(
        "--host", type=str, default="0.0.0.0", help="Host to listen on (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload for development (default: False)"
    )
    args = parser.parse_args()

    logger = get_logger("mcp.server")
    logger.info(
        "Starting Enhanced MCP Knowledge Store server",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    logger.info(
        "Server endpoints available",
        health_endpoints=[
            "/health - Comprehensive health check",
            "/health/live - Liveness probe",
            "/health/ready - Readiness probe",
            "/metrics - Prometheus metrics",
        ],
        mcp_endpoints=[
            "/ - All MCP tool calls",
        ],
    )

    # Start the FastAPI server with custom logging configuration
    uvicorn.run(
        "src.mcp.server:app",
        host=args.host,
        port=args.port,
        log_level="info",
        reload=args.reload,
        log_config=get_uvicorn_log_config(),
        # give server 10min to shut down so long ask_agent and ask_agent_streaming calls have time to complete
        timeout_graceful_shutdown=600,
    )


if __name__ == "__main__":
    main()
