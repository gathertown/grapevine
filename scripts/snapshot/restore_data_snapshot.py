#!/usr/bin/env python
"""
Data Snapshot Restoration Tool

Restores unified data snapshots created by create_data_snapshot.py
Supports OpenSearch and PostgreSQL restoration.
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

import asyncpg
from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from tqdm import tqdm

project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))

from snapshot_common import (
    DataOperator,
    HostInfoExtractor,
    OperationResult,
    ProgressFileWrapper,
    SnapshotStructure,
    TableFormatter,
    format_duration,
    get_file_size_mb,
)

from src.clients.opensearch import OpenSearchClient
from src.utils.config import (
    get_restore_target_database_url,
    get_restore_target_opensearch_url,
)


class RestoreTargetOpenSearchClient(OpenSearchClient):
    """OpenSearch client specifically for restore operations."""

    def __init__(self):
        restore_url = get_restore_target_opensearch_url()
        # URL already includes credentials if needed
        super().__init__(url=restore_url)


class OpenSearchRestorer(DataOperator):
    def __init__(
        self,
        snapshot_dir: Path,
        target_prefix: str = "",
        overwrite: bool = False,
        verbose: bool = False,
    ):
        super().__init__(verbose)
        self.snapshot_dir = snapshot_dir
        self.target_prefix = target_prefix
        self.overwrite = overwrite
        self.client = RestoreTargetOpenSearchClient()

    def execute(self) -> OperationResult:
        """Restore OpenSearch data"""
        start_time = time.time()

        try:
            mappings, settings = self._load_mappings_and_settings()

            summary = self._load_export_summary()
            if not summary:
                raise Exception("No OpenSearch export summary found in snapshot")

            exported_indices = summary.get("exported_indices", [])

            restored_stats = {
                "indices_created": 0,
                "indices_skipped": 0,
                "total_documents": 0,
                "indices": {},
            }

            for index_name in exported_indices:
                created = self._create_index_if_needed(index_name, mappings, settings)

                if created:
                    restored_stats["indices_created"] += 1

                    doc_count = self._restore_index_data(index_name)
                    restored_stats["total_documents"] += doc_count
                    restored_stats["indices"][index_name] = {
                        "documents": doc_count,
                        "status": "restored",
                    }
                else:
                    restored_stats["indices_skipped"] += 1
                    restored_stats["indices"][index_name] = {
                        "documents": 0,
                        "status": "skipped",
                    }

            if restored_stats["total_documents"] > 0:
                print(f"✓ Restored {restored_stats['total_documents']:,} OpenSearch documents")

            duration = time.time() - start_time
            return OperationResult(
                success=True,
                item_count=restored_stats["total_documents"],
                file_size_mb=0,
                duration_seconds=duration,
                details=restored_stats,
            )

        except Exception as e:
            duration = time.time() - start_time
            return OperationResult(
                success=False,
                item_count=0,
                file_size_mb=0,
                duration_seconds=duration,
                error=str(e),
            )

    def _load_mappings_and_settings(self) -> tuple[dict, dict]:
        mappings_file = SnapshotStructure.get_opensearch_mappings_file(self.snapshot_dir)
        with open(mappings_file) as f:
            mappings = json.load(f)

        settings_file = SnapshotStructure.get_opensearch_settings_file(self.snapshot_dir)
        with open(settings_file) as f:
            settings = json.load(f)

        return mappings, settings

    def _load_export_summary(self) -> dict | None:
        summary_file = SnapshotStructure.get_opensearch_export_summary_file(self.snapshot_dir)
        if not summary_file.exists():
            return None

        with open(summary_file) as f:
            return json.load(f)

    def _create_index_if_needed(self, index_name: str, mappings: dict, settings: dict) -> bool:
        target_index = f"{self.target_prefix}{index_name}" if self.target_prefix else index_name

        try:
            exists = await self.client.client.indices.exists(index=target_index)

            if exists and not self.overwrite:
                self.log(f"Index {target_index} exists, skipping (use --overwrite to replace)")
                return False

            if exists and self.overwrite:
                await self.client.client.indices.delete(index=target_index)

            index_settings = settings.get(index_name, {}).get("settings", {})
            clean_settings = {}

            if "index" in index_settings:
                index_config = index_settings["index"].copy()
                for key in ["uuid", "creation_date", "provided_name", "version"]:
                    index_config.pop(key, None)
                index_config.pop("blocks", None)
                clean_settings["index"] = index_config

            index_mappings = mappings.get(index_name, {}).get("mappings", {})

            body = {}
            if clean_settings:
                body["settings"] = clean_settings
            if index_mappings:
                body["mappings"] = index_mappings

            if body:
                await self.client.client.indices.create(index=target_index, body=body)
            else:
                await self.client.client.indices.create(index=target_index)

            return True

        except Exception as e:
            self.log(f"Failed to create index {target_index}: {e}", "error")
            return False

    def _restore_index_data(self, index_name: str) -> int:
        target_index = f"{self.target_prefix}{index_name}" if self.target_prefix else index_name
        data_file = SnapshotStructure.get_opensearch_index_data_file(self.snapshot_dir, index_name)

        if not data_file.exists():
            self.log(f"No data file found for {index_name}")
            return 0

        try:
            total_lines = 0
            with open(data_file) as f:
                for line in f:
                    if line.strip():
                        total_lines += 1

            documents = []
            docs_processed = 0

            progress_bar = tqdm(
                total=total_lines,
                desc="Restoring OpenSearch data",
                unit="docs",
                dynamic_ncols=True,
            )

            with open(data_file) as f:
                for line in f:
                    if line.strip():
                        doc = json.loads(line)
                        documents.append(doc)
                        docs_processed += 1
                        progress_bar.update(1)

                        if len(documents) >= 1000:
                            self._bulk_index_documents(target_index, documents)
                            documents = []

            if documents:
                self._bulk_index_documents(target_index, documents)

            progress_bar.close()

            await self.client.client.indices.refresh(index=target_index)
            count_response = await self.client.client.count(index=target_index)
            doc_count = count_response["count"]

            return doc_count

        except Exception as e:
            self.log(f"Failed to restore data to {target_index}: {e}", "error")
            return 0

    def _bulk_index_documents(self, index_name: str, documents: list[dict]):
        body = []

        for doc in documents:
            action = {"index": {"_index": index_name, "_id": doc["_id"]}}

            if "_routing" in doc:
                action["index"]["_routing"] = doc["_routing"]

            body.append(action)
            body.append(doc["_source"])

        response = await self.client.client.bulk(body=body)

        if response.get("errors"):
            error_count = sum(1 for item in response["items"] if "error" in item.get("index", {}))
            if error_count > 0:
                self.log(
                    f"{error_count} documents had errors during bulk indexing",
                    "warning",
                )


class PostgreSQLRestorer(DataOperator):
    """Handles PostgreSQL data restoration"""

    def __init__(
        self,
        snapshot_dir: Path,
        overwrite: bool = False,
        skip_schema: bool = False,
        verbose: bool = False,
    ):
        super().__init__(verbose)
        self.snapshot_dir = snapshot_dir
        self.overwrite = overwrite
        self.skip_schema = skip_schema

    def execute(self) -> OperationResult:
        """Restore PostgreSQL data"""
        start_time = time.time()

        postgres_dir = SnapshotStructure.get_postgresql_dir(self.snapshot_dir)
        if not postgres_dir.exists():
            return OperationResult(
                success=False,
                item_count=0,
                file_size_mb=0,
                duration_seconds=0,
                error="No PostgreSQL data found in snapshot",
            )

        data_dir = SnapshotStructure.get_postgresql_data_dir(self.snapshot_dir)
        if not data_dir.exists() or not any(data_dir.glob("*.bin")):
            return OperationResult(
                success=False,
                item_count=0,
                file_size_mb=0,
                duration_seconds=0,
                error="Invalid PostgreSQL snapshot format",
            )

        try:
            total_rows, tables_restored = asyncio.run(self._restore_async(postgres_dir))

            if tables_restored:
                print(f"✓ Restored {total_rows:,} PostgreSQL rows")

            duration = time.time() - start_time
            return OperationResult(
                success=True,
                item_count=total_rows,
                file_size_mb=0,
                duration_seconds=duration,
                details={"tables_restored": tables_restored, "total_rows": total_rows},
            )

        except Exception as e:
            duration = time.time() - start_time
            return OperationResult(
                success=False,
                item_count=0,
                file_size_mb=0,
                duration_seconds=duration,
                error=str(e),
            )

    async def _restore_async(self, postgres_dir: Path) -> tuple[int, list[str]]:
        db_url = get_restore_target_database_url()
        conn = await asyncpg.connect(db_url)

        try:
            await conn.execute("SET search_path TO public")

            if not self.skip_schema:
                await self._restore_schema(conn)

            SnapshotStructure.get_postgresql_data_dir(self.snapshot_dir)
            summary = self._load_postgres_summary()

            total_rows = 0
            tables_restored = []

            for table_name in ["documents", "chunks"]:
                binary_file = SnapshotStructure.get_postgresql_table_data_file(
                    self.snapshot_dir, table_name
                )

                if not binary_file.exists():
                    self.log(f"No binary file found for {table_name}")
                    continue

                expected_rows = 0
                if summary and "export_results" in summary:
                    table_info = summary["export_results"].get(table_name, {})
                    expected_rows = table_info.get("rows", 0)

                if self.overwrite:
                    try:
                        await conn.execute(f"TRUNCATE TABLE public.{table_name} CASCADE")
                    except Exception as e:
                        self.log(f"Could not truncate {table_name}: {e}", "warning")

                rows_imported = await self._restore_table(
                    conn, table_name, binary_file, expected_rows
                )
                total_rows += rows_imported
                tables_restored.append(table_name)

            return total_rows, tables_restored

        finally:
            await conn.close()

    async def _restore_schema(self, conn):
        """Restore PostgreSQL schema using pg_restore"""
        schema_dump_file = SnapshotStructure.get_postgresql_schema_file(
            self.snapshot_dir
        ).with_suffix(".dump")

        if not schema_dump_file.exists():
            return

        print("Restoring PostgreSQL schema...", end="", flush=True)

        try:
            if self.overwrite:
                await conn.execute("DROP TABLE IF EXISTS chunks CASCADE")
                await conn.execute("DROP TABLE IF EXISTS documents CASCADE")
                await conn.execute("DROP TABLE IF EXISTS messages CASCADE")
                await conn.execute("DROP TABLE IF EXISTS schema_migrations CASCADE")

            db_url = get_restore_target_database_url()

            pg_restore_cmd = [
                "pg_restore",
                "--dbname",
                db_url,
                "--schema=public",
                "--no-owner",
                "--no-privileges",
                "--no-comments",
                "--if-exists",
                "--clean" if self.overwrite else "--no-clean",
                str(schema_dump_file),
            ]

            result = subprocess.run(pg_restore_cmd, capture_output=True, text=True)

            # Check if restore was successful despite SET command errors
            if result.returncode != 0:
                # Check if it's just SET command errors
                if "transaction_timeout" in result.stderr or "SET" in result.stderr:
                    # Verify that tables were actually created
                    tables_exist = await conn.fetchval(
                        "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename IN ('documents', 'chunks'))"
                    )
                    if tables_exist:
                        print(" ✓ (with warnings)")
                        if self.verbose:
                            self.console.print(
                                "\n[yellow]Warning: Some SET commands failed due to PostgreSQL version mismatch, but schema was restored successfully[/yellow]"
                            )
                    else:
                        raise subprocess.CalledProcessError(
                            result.returncode, pg_restore_cmd, result.stdout, result.stderr
                        )
                else:
                    raise subprocess.CalledProcessError(
                        result.returncode, pg_restore_cmd, result.stdout, result.stderr
                    )
            else:
                print(" ✓")

        except subprocess.CalledProcessError as e:
            print(" ✗")
            self.console.print(f"\n[red]Error: {e.stderr.strip()}[/red]")
            raise Exception(f"Schema restoration failed: {e.stderr}")
        except Exception as e:
            print(" ✗")
            self.console.print(f"\n[red]Error: {str(e)}[/red]")
            raise Exception(f"Schema restoration error: {str(e)}")

    async def _restore_table(
        self, conn, table_name: str, binary_file: Path, expected_rows: int
    ) -> int:
        table_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tablename = $1)",
            table_name,
        )

        if not table_exists:
            raise Exception(f"Table public.{table_name} does not exist in database")

        file_size = binary_file.stat().st_size

        progress_bar = tqdm(
            total=expected_rows if expected_rows > 0 else None,
            desc=f"Restoring PostgreSQL {table_name}",
            unit="rows",
            dynamic_ncols=True,
        )

        with open(binary_file, "rb") as f:
            wrapped_file = ProgressFileWrapper(f, progress_bar, file_size, expected_rows)
            result = await conn.copy_to_table(table_name, source=wrapped_file, format="binary")

        if isinstance(result, str) and "COPY" in result:
            parts = result.split()
            if len(parts) >= 2 and parts[1].isdigit():
                imported_rows = int(parts[1])
            else:
                imported_rows = expected_rows
        else:
            imported_rows = expected_rows

        if expected_rows > 0:
            progress_bar.n = expected_rows
            progress_bar.refresh()

        progress_bar.close()

        return imported_rows

    def _load_postgres_summary(self) -> dict | None:
        summary_file = SnapshotStructure.get_postgresql_summary_file(self.snapshot_dir)
        if not summary_file.exists():
            return None

        with open(summary_file) as f:
            return json.load(f)


class RestorationPlanner:
    def __init__(
        self,
        snapshot_dir: Path,
        target_prefix: str = "",
        restore_opensearch: bool = True,
        restore_postgres: bool = True,
        verbose: bool = False,
    ):
        self.snapshot_dir = snapshot_dir
        self.target_prefix = target_prefix
        self.restore_opensearch = restore_opensearch
        self.restore_postgres = restore_postgres
        self.verbose = verbose
        self.console = Console()
        self.formatter = TableFormatter(self.console)

    def create_plan(self) -> dict[str, Any]:
        plan = {
            "opensearch": self._plan_opensearch_restoration(),
            "postgresql": self._plan_postgresql_restoration(),
            "metadata": self._load_metadata(),
        }

        return plan

    def display_plan(self, plan: dict[str, Any], snapshot_name: str):
        table = self.formatter.create_plan_table()

        total_items = 0
        total_size_mb = 0

        if self.restore_opensearch and plan["opensearch"]["status"] == "ready":
            for index_info in plan["opensearch"]["indices"]:
                table.add_row(
                    "OpenSearch",
                    f"Index: {index_info['target_name']}",
                    plan["opensearch"]["host"],
                    f"{index_info['doc_count']:,}",
                    self.formatter.format_size(index_info["size_mb"]),
                )
                total_items += index_info["doc_count"]
                total_size_mb += index_info["size_mb"]
        elif not self.restore_opensearch:
            table.add_row("OpenSearch", "Skipped", "—", "—", "—")
        else:
            table.add_row("OpenSearch", "No data", "—", "0", "0 MB")

        if self.restore_postgres and plan["postgresql"]["status"] == "ready":
            for table_info in plan["postgresql"]["tables"]:
                table.add_row(
                    "PostgreSQL",
                    f"Table: {table_info['name']}",
                    plan["postgresql"]["host"],
                    f"{table_info['row_count']:,}",
                    self.formatter.format_size(table_info["size_mb"]),
                )
                total_items += table_info["row_count"]
                total_size_mb += table_info["size_mb"]
        elif not self.restore_postgres:
            table.add_row("PostgreSQL", "Skipped", "—", "—", "—")
        else:
            table.add_row("PostgreSQL", "No data", "—", "0", "0 MB")

        self.formatter.add_total_row(table, total_items, total_size_mb)

        self.console.print()
        self.console.print(table)

    def _plan_opensearch_restoration(self) -> dict[str, Any]:
        """Plan OpenSearch restoration"""
        if not self.restore_opensearch:
            return {"status": "skipped"}

        try:
            restore_url = get_restore_target_opensearch_url()
            host = HostInfoExtractor.get_opensearch_host(restore_url)

            summary_file = SnapshotStructure.get_opensearch_export_summary_file(self.snapshot_dir)
            if not summary_file.exists():
                return {"status": "no_data"}

            with open(summary_file) as f:
                summary = json.load(f)

            indices_info = []
            for index_name in summary.get("exported_indices", []):
                target_name = (
                    f"{self.target_prefix}{index_name}" if self.target_prefix else index_name
                )
                result = summary.get("export_results", {}).get(index_name, {})
                doc_count = result.get("total_documents", 0)

                data_file = SnapshotStructure.get_opensearch_index_data_file(
                    self.snapshot_dir, index_name
                )
                size_mb = get_file_size_mb(data_file)

                indices_info.append(
                    {
                        "name": index_name,
                        "target_name": target_name,
                        "doc_count": doc_count,
                        "size_mb": size_mb,
                    }
                )

            return {"status": "ready", "host": host, "indices": indices_info}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _plan_postgresql_restoration(self) -> dict[str, Any]:
        """Plan PostgreSQL restoration"""
        if not self.restore_postgres:
            return {"status": "skipped"}

        try:
            db_url = get_restore_target_database_url()
            host = HostInfoExtractor.get_postgresql_host(db_url)

            summary_file = SnapshotStructure.get_postgresql_summary_file(self.snapshot_dir)
            if not summary_file.exists():
                return {"status": "no_data"}

            with open(summary_file) as f:
                summary = json.load(f)

            tables_info = []
            for table_name in ["documents", "chunks"]:
                table_data = summary.get("export_results", {}).get(table_name, {})
                if table_data.get("status") == "success":
                    tables_info.append(
                        {
                            "name": table_name,
                            "row_count": table_data.get("rows", 0),
                            "size_mb": table_data.get("size_mb", 0),
                        }
                    )

            return {"status": "ready", "host": host, "tables": tables_info}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _load_metadata(self) -> dict | None:
        metadata_file = SnapshotStructure.get_metadata_file(self.snapshot_dir)
        if not metadata_file.exists():
            return None

        with open(metadata_file) as f:
            return json.load(f)


class DataSnapshotRestorer:
    def __init__(
        self,
        snapshot_file: str,
        target_prefix: str = "",
        overwrite: bool = True,
        skip_confirmation: bool = False,
        restore_opensearch: bool = True,
        restore_postgres: bool = True,
        verbose: bool = False,
        skip_schema: bool = False,
    ):
        self.snapshot_file = Path(snapshot_file)
        self.target_prefix = target_prefix
        self.overwrite = overwrite
        self.skip_confirmation = skip_confirmation
        self.restore_opensearch = restore_opensearch
        self.restore_postgres = restore_postgres
        self.skip_schema = skip_schema
        self.verbose = verbose
        self.temp_dir = Path(tempfile.mkdtemp(prefix="restore_"))

        self.console = Console()
        self.formatter = TableFormatter(self.console)

        if not self.snapshot_file.exists():
            raise FileNotFoundError(f"Snapshot file not found: {snapshot_file}")

        self.snapshot_dir = None
        self.restore_plan = None
        self.restoration_results = {}

    async def restore_snapshot(self):
        start_time = time.time()

        try:
            if not self._step1_extract_and_plan():
                self._cleanup()
                sys.exit(1)

            if not self._step2_confirm_restoration():
                self._cleanup()
                sys.exit(1)

            if not self._step3_execute_restoration():
                self._cleanup()
                sys.exit(1)

            await self._step4_show_results()

            total_time = time.time() - start_time
            self.console.print(f"\nTotal time: {format_duration(total_time)}")

            self._cleanup()

        except Exception as e:
            self.console.print(f"\n[red]Error restoring snapshot: {e}[/red]")
            self._cleanup()
            sys.exit(1)

    def _step1_extract_and_plan(self) -> bool:
        self.console.print()

        self._check_environment_variables()

        with Live(
            Spinner(
                "dots",
                text=f"Extracting and analyzing snapshot: {self.snapshot_file.name}",
                style="magenta",
            ),
            console=self.console,
            refresh_per_second=4,
        ) as live:
            with tarfile.open(self.snapshot_file, "r:gz") as tar:
                tar.extractall(self.temp_dir)

            extracted_dirs = [d for d in Path(self.temp_dir).iterdir() if d.is_dir()]
            if not extracted_dirs:
                raise Exception("No directories found in snapshot archive")

            self.snapshot_dir = extracted_dirs[0]

            planner = RestorationPlanner(
                self.snapshot_dir,
                self.target_prefix,
                self.restore_opensearch,
                self.restore_postgres,
                self.verbose,
            )
            self.restore_plan = planner.create_plan()

            live.update(Text(f"✓ Analyzed snapshot: {self.snapshot_file.name}", style="green"))
            live.stop()

        planner.display_plan(self.restore_plan, self.snapshot_file.name)

        return True

    def _step2_confirm_restoration(self) -> bool:
        if self.skip_confirmation:
            self.console.print("\n[yellow]Skipping confirmation (--yes flag provided)[/yellow]")
            return True

        self.console.print("\n[red]CONFIRMATION REQUIRED[/red]")
        self.console.print("[red]============================[/red]")

        if self.overwrite:
            self.console.print("\n[red]WARNING: Overwrite mode is enabled![/red]")
            self.console.print(
                "[red]   Existing indices and tables will be DELETED and recreated.[/red]"
            )

        if not self.target_prefix:
            self.console.print(
                "\n[yellow]No prefix specified - indices will be restored with original names[/yellow]"
            )
        else:
            self.console.print(
                f"\n[blue]Prefix: '{self.target_prefix}' will be added to all index names[/blue]"
            )

        self.console.print(
            "\n[yellow]Do you want to proceed with this restoration? (y/N):[/yellow] ",
            end="",
        )

        try:
            confirmation = input().strip().lower()
        except EOFError:
            self.console.print("y")
            confirmation = "y"

        if confirmation not in ["y", "yes"]:
            self.console.print("\n[red]Restoration cancelled by user[/red]")
            return False

        return True

    def _step3_execute_restoration(self) -> bool:
        """Step 3: Execute the restoration process."""
        all_success = True

        try:
            if self.restore_opensearch:
                restorer = OpenSearchRestorer(
                    self.snapshot_dir, self.target_prefix, self.overwrite, self.verbose
                )
                result = restorer.execute()
                self.restoration_results["opensearch"] = result
                if not result.success:
                    all_success = False
            else:
                self.console.print(
                    "\n[yellow]Skipping OpenSearch restoration (--no-opensearch flag)[/yellow]"
                )

            if self.restore_postgres:
                restorer = PostgreSQLRestorer(
                    self.snapshot_dir, self.overwrite, self.skip_schema, self.verbose
                )
                result = restorer.execute()
                self.restoration_results["postgresql"] = result
                if not result.success:
                    all_success = False
            else:
                self.console.print(
                    "\n[yellow]Skipping PostgreSQL restoration (--no-postgres flag)[/yellow]"
                )

            return all_success

        except Exception as e:
            self.console.print(f"\n[red]Error during restoration: {e}[/red]")
            return False

    async def _step4_show_results(self):
        await self._show_final_results_table()

    async def _show_final_results_table(self):
        table = self.formatter.create_status_table()

        if "opensearch" in self.restoration_results:
            result = self.restoration_results["opensearch"]
            if result.success and result.details:
                actual_counts = await self._get_actual_opensearch_counts(result.details)

                for index_name, index_info in result.details.get("indices", {}).items():
                    if index_info["status"] == "restored":
                        expected = index_info["documents"]
                        actual = actual_counts.get(index_name, None)
                        status_str = self._format_status(expected, actual)
                        table.add_row("OpenSearch", f"Index: {index_name}", status_str)
                    elif index_info["status"] == "skipped":
                        table.add_row("OpenSearch", f"Index: {index_name}", "Skipped (exists)")

        if "postgresql" in self.restoration_results:
            result = self.restoration_results["postgresql"]
            if result.success and result.details:
                actual_counts = self._get_actual_postgresql_counts(result.details)

                for table_name in result.details.get("tables_restored", []):
                    expected = self._get_expected_postgresql_count(table_name)
                    actual = actual_counts.get(table_name, None)
                    status_str = self._format_status(expected, actual)
                    table.add_row("PostgreSQL", f"Table: public.{table_name}", status_str)

        self.console.print()
        self.console.print(table)

        # Check if all restorations were successful
        all_success = True
        if (
            "opensearch" in self.restoration_results
            and not self.restoration_results["opensearch"].success
        ):
            all_success = False
        if (
            "postgresql" in self.restoration_results
            and not self.restoration_results["postgresql"].success
        ):
            all_success = False

        if all_success:
            self.console.print("\n[green]✓ Snapshot restored successfully![/green]")
        else:
            self.console.print("\n[red]✗ Snapshot restoration failed![/red]")
            if (
                "postgresql" in self.restoration_results
                and not self.restoration_results["postgresql"].success
            ):
                error = self.restoration_results["postgresql"].error
                if error:
                    self.console.print(f"\n[red]PostgreSQL Error: {error}[/red]")

        self.console.print(f"\nRestored from: {self.snapshot_file.name}")

    def _format_status(self, expected: int, actual: int | None) -> str:
        if actual is None or expected == 0:
            return "N/A"
        elif actual == expected:
            return "100% Restored"
        else:
            percentage = (actual / expected * 100) if expected > 0 else 0
            return f"[red]{percentage:.0f}% Restored[/red]"

    async def _get_actual_opensearch_counts(self, details: dict) -> dict[str, int]:
        counts = {}
        try:
            client = RestoreTargetOpenSearchClient()
            for index_name, index_info in details.get("indices", {}).items():
                if index_info["status"] == "restored":
                    try:
                        count_response = await client.client.count(index=index_name)
                        counts[index_name] = count_response["count"]
                    except:
                        pass
        except:
            pass
        return counts

    def _get_actual_postgresql_counts(self, details: dict) -> dict[str, int]:
        counts = {}
        try:
            db_url = get_restore_target_database_url()

            async def get_counts():
                conn = await asyncpg.connect(db_url)
                try:
                    results = {}
                    for table in details.get("tables_restored", []):
                        try:
                            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
                            results[table] = count
                        except:
                            pass
                    return results
                finally:
                    await conn.close()

            counts = asyncio.run(get_counts())
        except:
            pass
        return counts

    def _get_expected_postgresql_count(self, table_name: str) -> int:
        if self.restore_plan and "postgresql" in self.restore_plan:
            for table_info in self.restore_plan["postgresql"].get("tables", []):
                if table_info["name"] == table_name:
                    return table_info["row_count"]
        return 0

    def _check_environment_variables(self):
        has_db_target = bool(os.environ.get("RESTORE_TARGET_DATABASE_URL"))
        has_os_target = bool(
            os.environ.get("RESTORE_TARGET_OPENSEARCH_URL")
            or os.environ.get("RESTORE_TARGET_OPENSEARCH_HOST")
        )

        # Check which targets are needed based on what we're restoring
        needs_db = self.restore_postgres
        needs_os = self.restore_opensearch

        if needs_db or needs_os:
            missing_targets = []
            if needs_db and not has_db_target:
                missing_targets.append("RESTORE_TARGET_DATABASE_URL")
            if needs_os and not has_os_target:
                missing_targets.append(
                    "RESTORE_TARGET_OPENSEARCH_URL (or RESTORE_TARGET_OPENSEARCH_HOST)"
                )

            if missing_targets:
                self.console.print(
                    "[red]Missing required RESTORE_TARGET_* environment variables:[/red]"
                )
                for target in missing_targets:
                    self.console.print(f"[red]   - {target}[/red]")
                self.console.print(
                    "[red]   Required for safety to prevent accidental production restores[/red]"
                )

    def _cleanup(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(
        description="Restore OpenSearch and PostgreSQL data snapshot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("snapshot_file", help="Path to the snapshot file (.tar.gz)")
    parser.add_argument("--prefix", help="Prefix to add to restored index names", default="")
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Don't overwrite existing indices and tables",
    )
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--no-opensearch", action="store_true", help="Skip OpenSearch restoration")
    parser.add_argument("--no-postgres", action="store_true", help="Skip PostgreSQL restoration")
    parser.add_argument(
        "--opensearch-only",
        action="store_true",
        help="Only restore OpenSearch data, skip PostgreSQL",
    )
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Skip PostgreSQL schema restoration (use existing schema)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args()

    # Handle opensearch-only flag
    if args.opensearch_only:
        restore_opensearch = True
        restore_postgres = False
    else:
        restore_opensearch = not args.no_opensearch
        restore_postgres = not args.no_postgres

    try:
        restorer = DataSnapshotRestorer(
            snapshot_file=args.snapshot_file,
            target_prefix=args.prefix,
            overwrite=not args.no_overwrite,
            skip_confirmation=args.yes,
            restore_opensearch=restore_opensearch,
            restore_postgres=restore_postgres,
            verbose=args.verbose,
            skip_schema=args.skip_schema,
        )
        asyncio.run(restorer.restore_snapshot())
    except KeyboardInterrupt:
        print("\n\nRestore interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
