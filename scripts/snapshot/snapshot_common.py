#!/usr/bin/env python

import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from rich.console import Console
from rich.table import Table
from tqdm import tqdm

from src.utils.config import get_opensearch_url


class SnapshotStructure:
    METADATA_DIR = "metadata"
    OPENSEARCH_DIR = "opensearch"
    POSTGRESQL_DIR = "postgresql"
    OPENSEARCH_DATA_DIR = "data"
    POSTGRESQL_DATA_DIR = "data"

    METADATA_FILE = "metadata.json"
    OPENSEARCH_MAPPINGS_FILE = "mappings.json"
    OPENSEARCH_SETTINGS_FILE = "settings.json"
    OPENSEARCH_EXPORT_SUMMARY_FILE = "export_summary.json"
    POSTGRESQL_SCHEMA_FILE = "schema.sql"
    POSTGRESQL_SUMMARY_FILE = "postgres_summary.json"

    @staticmethod
    def get_metadata_dir(base_dir: Path) -> Path:
        return base_dir / SnapshotStructure.METADATA_DIR

    @staticmethod
    def get_metadata_file(base_dir: Path) -> Path:
        return SnapshotStructure.get_metadata_dir(base_dir) / SnapshotStructure.METADATA_FILE

    @staticmethod
    def get_opensearch_dir(base_dir: Path) -> Path:
        return base_dir / SnapshotStructure.OPENSEARCH_DIR

    @staticmethod
    def get_opensearch_data_dir(base_dir: Path) -> Path:
        return (
            SnapshotStructure.get_opensearch_dir(base_dir) / SnapshotStructure.OPENSEARCH_DATA_DIR
        )

    @staticmethod
    def get_opensearch_mappings_file(base_dir: Path) -> Path:
        return (
            SnapshotStructure.get_opensearch_dir(base_dir)
            / SnapshotStructure.OPENSEARCH_MAPPINGS_FILE
        )

    @staticmethod
    def get_opensearch_settings_file(base_dir: Path) -> Path:
        return (
            SnapshotStructure.get_opensearch_dir(base_dir)
            / SnapshotStructure.OPENSEARCH_SETTINGS_FILE
        )

    @staticmethod
    def get_opensearch_export_summary_file(base_dir: Path) -> Path:
        return (
            SnapshotStructure.get_opensearch_dir(base_dir)
            / SnapshotStructure.OPENSEARCH_EXPORT_SUMMARY_FILE
        )

    @staticmethod
    def get_opensearch_index_data_file(base_dir: Path, index_name: str) -> Path:
        return SnapshotStructure.get_opensearch_data_dir(base_dir) / f"{index_name}.jsonl"

    @staticmethod
    def get_postgresql_dir(base_dir: Path) -> Path:
        return base_dir / SnapshotStructure.POSTGRESQL_DIR

    @staticmethod
    def get_postgresql_data_dir(base_dir: Path) -> Path:
        return (
            SnapshotStructure.get_postgresql_dir(base_dir) / SnapshotStructure.POSTGRESQL_DATA_DIR
        )

    @staticmethod
    def get_postgresql_schema_file(base_dir: Path) -> Path:
        return (
            SnapshotStructure.get_postgresql_dir(base_dir)
            / SnapshotStructure.POSTGRESQL_SCHEMA_FILE
        )

    @staticmethod
    def get_postgresql_summary_file(base_dir: Path) -> Path:
        return (
            SnapshotStructure.get_postgresql_dir(base_dir)
            / SnapshotStructure.POSTGRESQL_SUMMARY_FILE
        )

    @staticmethod
    def get_postgresql_table_data_file(base_dir: Path, table_name: str) -> Path:
        return SnapshotStructure.get_postgresql_data_dir(base_dir) / f"{table_name}.bin"


@dataclass
class OperationResult:
    success: bool
    item_count: int
    file_size_mb: float
    duration_seconds: float
    error: str | None = None
    details: dict[str, Any] | None = None


class ProgressMonitor:
    def __init__(self, file_path: Path, total_items: int, avg_item_size: int = 2000):
        self.file_path = file_path
        self.total_items = total_items
        self.avg_item_size = avg_item_size
        self.last_size = 0
        self.items_processed = 0
        self.stop_monitoring = False
        self.monitor_thread = None

    def start(self, progress_bar: tqdm):
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop, args=(progress_bar,), daemon=True
        )
        self.monitor_thread.start()

    def stop(self):
        self.stop_monitoring = True
        if self.monitor_thread:
            self.monitor_thread.join(timeout=0.5)

    def _monitor_loop(self, progress_bar: tqdm):
        while not self.stop_monitoring:
            try:
                if self.file_path.exists():
                    current_size = self.file_path.stat().st_size
                    if current_size > self.last_size:
                        size_diff = current_size - self.last_size
                        estimated_new_items = int(size_diff / self.avg_item_size)
                        if (
                            estimated_new_items > 0
                            and self.items_processed + estimated_new_items <= self.total_items
                        ):
                            progress_bar.update(estimated_new_items)
                            self.items_processed += estimated_new_items
                        self.last_size = current_size
            except:
                pass
            time.sleep(0.5)

    def get_remaining_items(self) -> int:
        return max(0, self.total_items - self.items_processed)


class ProgressFileWrapper:
    def __init__(self, file_obj, progress_bar: tqdm, total_size: int, expected_items: int):
        self.file = file_obj
        self.progress_bar = progress_bar
        self.total_size = total_size
        self.expected_items = expected_items
        self.bytes_read = 0
        self.last_progress = 0

    def read(self, size=-1):
        data = self.file.read(size)
        if data:
            self.bytes_read += len(data)
            if self.total_size > 0 and self.expected_items > 0:
                progress_pct = self.bytes_read / self.total_size
                progress_pct = min(progress_pct, 0.95)
                current_progress = int(progress_pct * self.expected_items)
                if current_progress > self.last_progress:
                    self.progress_bar.update(current_progress - self.last_progress)
                    self.last_progress = current_progress
        return data

    def __getattr__(self, name):
        return getattr(self.file, name)


class DatabaseHealthChecker:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.console = Console()

    async def check_all(self) -> list[str]:
        issues = []

        issues.extend(await self._check_opensearch())

        issues.extend(self._check_postgresql())

        return issues

    async def _check_opensearch(self) -> list[str]:
        try:
            from src.clients.opensearch import OpenSearchClient

            client = OpenSearchClient(get_opensearch_url())
            health = await client.client.cluster.health()
            if health["status"] == "red":
                return ["OpenSearch cluster status is RED"]
        except Exception as e:
            return [f"OpenSearch connection failed: {str(e)}"]
        return []

    def _check_postgresql(self) -> list[str]:
        try:
            import psycopg2

            from src.utils.config import get_database_url

            conn = psycopg2.connect(get_database_url())
            conn.close()
        except Exception as e:
            return [f"PostgreSQL connection failed: {str(e)}"]
        return []

    def display_issues(self, issues: list[str]):
        if issues:
            self.console.print("\n[yellow]Warning: Health check issues detected:[/yellow]")
            for issue in issues:
                self.console.print(f"  - {issue}")


class HostInfoExtractor:
    @staticmethod
    def get_opensearch_host(url: str | None = None) -> str:
        if not url:
            url = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")

        parsed = urlparse(url)
        if parsed.hostname:
            port = parsed.port or (443 if parsed.scheme == "https" else 9200)
            return f"{parsed.hostname}:{port}"
        return "localhost:9200"

    @staticmethod
    def get_postgresql_host(db_url: str) -> str:
        parsed = urlparse(db_url)
        return f"{parsed.hostname}:{parsed.port or 5432}"


class TableFormatter:
    def __init__(self, console: Console):
        self.console = console

    def create_plan_table(self) -> Table:
        table = Table()
        table.add_column("Database", style="cyan", no_wrap=True)
        table.add_column("Data", style="magenta")
        table.add_column("Host", style="green")
        table.add_column("Item Count", justify="right", style="yellow")
        table.add_column("Size", justify="right", style="blue")
        return table

    def create_results_table(self) -> Table:
        table = Table()
        table.add_column("Database", style="cyan", no_wrap=True)
        table.add_column("Component", style="magenta")
        table.add_column("Item Count", justify="right", style="green")
        table.add_column("File Size", justify="right", style="yellow")
        return table

    def create_status_table(self) -> Table:
        table = Table()
        table.add_column("Database", style="cyan", no_wrap=True)
        table.add_column("Component", style="magenta")
        table.add_column("Status", justify="center", style="green")
        return table

    def format_size(self, size_mb: float) -> str:
        if size_mb >= 1024:
            return f"{size_mb / 1024:.1f} GB"
        elif size_mb >= 1:
            return f"{size_mb:.1f} MB"
        else:
            return f"{size_mb * 1024:.1f} KB"

    def format_count_with_limit(self, count: int, total: int, has_limit: bool) -> str:
        count_str = f"{count:,}"
        if has_limit and total > count:
            count_str += f" (of {total:,})"
        return count_str

    def add_total_row(
        self,
        table: Table,
        total_items: int,
        total_size_mb: float,
        full_total: int | None = None,
    ):
        total_display = f"[bold]{total_items:,}[/bold]"
        if full_total and full_total > total_items:
            total_display = f"[bold]{total_items:,} (of {full_total:,})[/bold]"

        size_display = f"[bold]{self.format_size(total_size_mb)}[/bold]"
        table.add_row("", "", "", total_display, size_display)


def format_duration(seconds: float) -> str:
    if seconds >= 60:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        return f"{seconds:.1f}s"


def parse_size_string(size_str: str) -> float:
    size_str = size_str.lower().strip()

    if size_str.endswith("gb"):
        return float(size_str[:-2]) * 1024
    elif size_str.endswith("mb"):
        return float(size_str[:-2])
    elif size_str.endswith("kb"):
        return float(size_str[:-2]) / 1024
    elif size_str.endswith("b"):
        return float(size_str[:-1]) / (1024 * 1024)
    else:
        try:
            return float(size_str) / (1024 * 1024)
        except ValueError:
            return 0


def get_file_size_mb(file_path: Path) -> float:
    if file_path.exists():
        return file_path.stat().st_size / (1024 * 1024)
    return 0


def estimate_row_size(table_name: str) -> int:
    if table_name == "chunks":
        return 7300
    elif table_name == "documents":
        return 2000
    else:
        return 1000


class DataOperator(ABC):
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.console = Console()

    @abstractmethod
    def execute(self) -> OperationResult:
        pass

    def log(self, message: str, level: str = "info"):
        if self.verbose:
            if level == "error":
                self.console.print(f"[red]{message}[/red]")
            elif level == "warning":
                self.console.print(f"[yellow]{message}[/yellow]")
            else:
                self.console.print(message)
