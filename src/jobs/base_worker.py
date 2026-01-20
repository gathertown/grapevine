import asyncio
import contextlib
import threading
from abc import ABC, abstractmethod

import uvicorn
from fastapi import FastAPI

from src.clients.ssm import SSMClient
from src.clients.tenant_db import tenant_db_manager
from src.utils.logging import get_logger

logger = get_logger(__name__)


class BaseJobWorker(ABC):
    """Base class for job workers with shared database and HTTP server functionality."""

    def __init__(self, http_port: int | None = None):
        self.ssm_client = SSMClient()
        self.tenant_db_manager = tenant_db_manager
        self.http_port = http_port or self._get_default_http_port()
        self._app = self._create_app()

    @abstractmethod
    def _get_default_http_port(self) -> int:
        """Get the default HTTP server port for this worker type."""
        pass

    async def cleanup(self) -> None:
        """Clean up resources."""
        await self.tenant_db_manager.cleanup()

    def _create_app(self) -> FastAPI:
        app = FastAPI(
            title=f"{self.__class__.__name__} HTTP Server",
            docs_url=None,
            redoc_url=None,
        )

        self._register_health_routes(app)

        self._register_custom_routes(app)

        return app

    def _register_health_routes(self, app: FastAPI) -> None:
        @app.get("/health/live")
        async def liveness():
            """Liveness check - returns 200 if server is running."""
            return {"status": "healthy", "service": self.__class__.__name__}

        @app.get("/health/ready")
        async def readiness():
            """Readiness check - returns 200 if worker is running."""
            return {"status": "ready", "service": self.__class__.__name__}

    def _register_custom_routes(self, app: FastAPI) -> None:  # noqa: B027
        pass

    async def start_http_server(self) -> None:
        """Start the HTTP server."""
        config = uvicorn.Config(
            self._app,
            host="0.0.0.0",
            port=self.http_port,
            log_level="warning",
        )
        server = uvicorn.Server(config)

        logger.info(f"Starting HTTP server on port {self.http_port}")
        await server.serve()

    def run_http_server_thread(self) -> None:
        asyncio.set_event_loop(asyncio.new_event_loop())
        loop = asyncio.get_event_loop()

        loop.run_until_complete(self.start_http_server())

    async def run_with_dedicated_http_thread(self, main_task_coro) -> None:
        http_thread = threading.Thread(
            target=self.run_http_server_thread,
            daemon=True,
            name="http-server",
        )
        http_thread.start()
        logger.info(f"Started HTTP server in dedicated thread on port {self.http_port}")

        try:
            await main_task_coro
        finally:
            logger.info("Main processing completed")

    async def run_with_http_server(self, main_task_coro) -> None:
        main_task = asyncio.create_task(main_task_coro)
        http_task = asyncio.create_task(self.start_http_server())

        try:
            done, pending = await asyncio.wait(
                [main_task, http_task], return_when=asyncio.FIRST_COMPLETED
            )

            if main_task in done:
                http_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await http_task
                await main_task

            if http_task in done:
                main_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await main_task
                await http_task

        except Exception:
            for task in pending:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            raise
