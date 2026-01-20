"""Gatekeeper FastAPI service for multi-tenant webhook processing."""

import datetime
import os
from contextlib import asynccontextmanager
from pathlib import Path

import newrelic.agent

from src.utils.config import get_grapevine_environment

# Initialize New Relic with gatekeeper-specific TOML config and environment
config_path = Path(__file__).parent / "newrelic.toml"
grapevine_env = get_grapevine_environment()
# Initialize New Relic with the gatekeeper-specific TOML config and environment
newrelic.agent.initialize(str(config_path), environment=grapevine_env)

from fastapi import FastAPI, HTTPException, Request

from connectors.salesforce import SalesforceCDCManager
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.ingest.gatekeeper.routes import router as webhook_router
from src.ingest.gatekeeper.services.webhook_processor import WebhookProcessor
from src.utils.config import get_config_value
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Allow disabling webhook validation for development/testing
DANGEROUSLY_DISABLE_WEBHOOK_VALIDATION = os.getenv(
    "DANGEROUSLY_DISABLE_WEBHOOK_VALIDATION", ""
).lower() in ("true", "1", "yes")

if DANGEROUSLY_DISABLE_WEBHOOK_VALIDATION:
    logger.warning(
        "⚠️ DANGEROUSLY_DISABLE_WEBHOOK_VALIDATION is enabled. "
        "Webhook signatures will NOT be verified!"
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup and handle graceful shutdown."""
    logger.info("🚀 Starting Gatekeeper service...")

    # Initialize webhook processor and SQS client
    webhook_processor = WebhookProcessor()
    await webhook_processor.initialize()

    sqs_client = SQSClient()
    ssm_client = SSMClient()

    # Initialize Salesforce CDC manager
    cdc_manager = SalesforceCDCManager(ssm_client, sqs_client)
    await cdc_manager.start()

    app.state.webhook_processor = webhook_processor
    app.state.sqs_client = sqs_client
    app.state.ssm_client = ssm_client
    app.state.cdc_manager = cdc_manager
    app.state.dangerously_disable_webhook_validation = DANGEROUSLY_DISABLE_WEBHOOK_VALIDATION

    logger.info("✅ Gatekeeper service startup complete")

    yield

    logger.info("🛑 Shutting down Gatekeeper service...")

    # Cleanup resources in reverse order
    await cdc_manager.stop()
    await webhook_processor.cleanup()

    logger.info("✅ Gatekeeper service shutdown complete")


app = FastAPI(
    title="Corporate Context Gatekeeper",
    description="Multi-tenant webhook processing gateway with signature verification and SQS queuing",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check(request: Request):
    """Health check endpoint."""
    try:
        webhook_processor: WebhookProcessor = request.app.state.webhook_processor
        cdc_manager: SalesforceCDCManager = request.app.state.cdc_manager

        health_status = await webhook_processor.health_check()
        cdc_health = cdc_manager.health_check()

        # Combine health status
        health_status["components"]["salesforce_cdc"] = cdc_health

        # Overall status is healthy only if all components are healthy
        if health_status["status"] == "healthy" and cdc_health["status"] == "healthy":
            health_status["status"] = "healthy"
        else:
            health_status["status"] = "unhealthy"

        if health_status["status"] == "healthy":
            return health_status
        else:
            # Return 503 if any component is unhealthy
            raise HTTPException(status_code=503, detail=health_status)

    except Exception as e:
        # Record the error in New Relic
        newrelic.agent.record_exception()

        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail={"status": "unhealthy", "error": str(e)})


@app.get("/health/live")
async def liveness_check():
    """Liveness probe endpoint - checks if the application is alive."""
    # Simple check that the application is running
    # This should only fail if the process is completely broken
    return {"status": "alive", "timestamp": datetime.datetime.now().isoformat()}


@app.get("/health/ready")
async def readiness_check(request: Request):
    """Readiness probe endpoint - checks if the application is ready to serve traffic."""
    try:
        webhook_processor: WebhookProcessor = request.app.state.webhook_processor
        sqs_client: SQSClient = request.app.state.sqs_client

        health_status = await webhook_processor.health_check()

        # Also check SQS connectivity for queues
        try:
            ingest_queue = get_config_value(
                "INGEST_JOBS_QUEUE_ARN", "corporate-context-ingest-jobs-staging"
            )
            slackbot_queue = get_config_value(
                "SLACK_JOBS_QUEUE_ARN", "corporate-context-slackbot-staging"
            )

            # Test actual SQS connectivity by getting queue attributes
            ingest_attrs = await sqs_client.get_queue_attributes(ingest_queue)
            slackbot_attrs = await sqs_client.get_queue_attributes(slackbot_queue)

            if ingest_attrs is not None and slackbot_attrs is not None:
                health_status["components"]["sqs"] = "healthy"
            else:
                health_status["components"]["sqs"] = "unhealthy: failed to get queue attributes"
                health_status["status"] = "unhealthy"
        except Exception as e:
            health_status["components"]["sqs"] = f"unhealthy: {e}"
            health_status["status"] = "unhealthy"

        if health_status["status"] == "healthy":
            return {"status": "ready", "components": health_status}
        else:
            # Return 503 if any component is unhealthy
            raise HTTPException(
                status_code=503, detail={"status": "not_ready", "components": health_status}
            )

    except Exception as e:
        # Record the error in New Relic
        newrelic.agent.record_exception()

        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail={"status": "not_ready", "error": str(e)})


# Include webhook routes
app.include_router(webhook_router)


async def main():
    """Run the gatekeeper service."""
    import uvicorn

    port = get_config_value("GATEKEEPER_PORT", 8001)

    uvicorn.run("src.ingest.gatekeeper.main:app", host="0.0.0.0", port=port, reload=True)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
