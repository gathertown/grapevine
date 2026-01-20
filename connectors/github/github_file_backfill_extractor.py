import asyncio
import math
import os
import shutil
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import asyncpg
import newrelic.agent

from connectors.base import BaseExtractor, TriggerIndexingCallback, get_github_file_entity_id
from connectors.base.document_source import DocumentSource
from connectors.github.github_file_artifacts import (
    GitHubFileArtifact,
    GitHubFileContent,
    GitHubFileContributor,
    GitHubFileMetadata,
)
from connectors.github.github_file_utils import generate_binary_file_metadata_content
from connectors.github.github_models import GitHubFileBackfillConfig, GitHubFileBatch
from connectors.github.github_repo_utils import CloneResult, clone_repository
from src.clients.github import GitHubClient
from src.clients.github_factory import get_github_client_for_tenant
from src.clients.ssm import SSMClient
from src.ingest.utils import DEFAULT_INDEX_BATCH_SIZE
from src.utils.file_encoding import decode_file_content
from src.utils.filetype import is_plaintext_file
from src.utils.logging import get_logger
from src.utils.tenant_config import (
    increment_backfill_attempted_ingest_jobs,
    increment_backfill_done_ingest_jobs,
    increment_backfill_total_index_jobs,
)

logger = get_logger(__name__)


class GitHubFileBackfillExtractor(BaseExtractor[GitHubFileBackfillConfig]):
    """
    Extracts GitHub files from specific batches of file paths.
    This is a child job of GitHubFileBackfillRootExtractor.
    """

    source_name = "github_file_backfill"

    def __init__(self, ssm_client: SSMClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.temp_dir: str | None = None

    async def process_job(
        self,
        job_id: str,
        config: GitHubFileBackfillConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        logger.info(f"Processing {len(config.file_batches)} file batches for job {job_id}")

        try:
            # Get GitHub client for this tenant
            github_client = await get_github_client_for_tenant(config.tenant_id, self.ssm_client)

            # Create temporary directory for cloning
            temp_dir = tempfile.mkdtemp(prefix="github_file_batch_")
            self.temp_dir = temp_dir
            logger.info(f"Created temporary directory: {self.temp_dir}")

            # Process all file batches
            all_file_entity_ids: list[str] = []

            for batch_idx, file_batch in enumerate(config.file_batches):
                logger.info(
                    f"Processing batch {batch_idx + 1}/{len(config.file_batches)}: "
                    f"{len(file_batch.file_paths)} files from {file_batch.org_or_owner}/{file_batch.repo_name}"
                )

                batch_entity_ids = await self._process_file_batch(
                    job_id, github_client, file_batch, db_pool
                )
                all_file_entity_ids.extend(batch_entity_ids)

            logger.info(
                f"Successfully processed {len(all_file_entity_ids)} file artifacts for job {job_id}"
            )

            # Calculate total number of index batches and track them upfront
            total_index_batches = math.ceil(len(all_file_entity_ids) / DEFAULT_INDEX_BATCH_SIZE)
            if config.backfill_id and total_index_batches > 0:
                await increment_backfill_total_index_jobs(
                    config.backfill_id, config.tenant_id, total_index_batches
                )

            # Trigger indexing in batches
            for i in range(0, len(all_file_entity_ids), DEFAULT_INDEX_BATCH_SIZE):
                batched_entity_ids = all_file_entity_ids[i : i + DEFAULT_INDEX_BATCH_SIZE]
                await trigger_indexing(
                    batched_entity_ids,
                    DocumentSource.GITHUB_CODE,
                    config.tenant_id,
                    config.backfill_id,
                    config.suppress_notification,
                )

            logger.info(
                f"Successfully triggered index job for {len(all_file_entity_ids)} files from job {job_id}"
            )

            # Track completion if backfill_id exists
            if config.backfill_id:
                await increment_backfill_done_ingest_jobs(config.backfill_id, config.tenant_id, 1)

        finally:
            # Always track that we attempted this job, regardless of success/failure
            if config.backfill_id:
                await increment_backfill_attempted_ingest_jobs(
                    config.backfill_id, config.tenant_id, 1
                )

            # Clean up temporary directory
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                    logger.info(f"Cleaned up temporary directory: {self.temp_dir}")
                except Exception as e:
                    logger.error(f"Error cleaning up temporary directory: {e}")

    async def _process_file_batch(
        self,
        job_id: str,
        github_client: GitHubClient,
        file_batch: GitHubFileBatch,
        db_pool: asyncpg.Pool,
    ) -> list[str]:
        """Process a specific batch of files from a repository."""
        try:
            repo_spec = f"{file_batch.org_or_owner}/{file_batch.repo_name}"
            repo_url = f"https://github.com/{repo_spec}"

            # Clone the repository
            if self.temp_dir is None:
                raise ValueError("Temporary directory not initialized")

            with newrelic.agent.FunctionTrace(name="GitHubFileBackfill/clone_repository"):
                clone_result: CloneResult = await clone_repository(
                    repo_url, github_client, self.temp_dir
                )

            repo_path = clone_result.repo_path
            logger.info(
                f"Cloned repository to: {repo_path} (SHA: {clone_result.commit_sha}, branch: {clone_result.branch or 'unknown'})"
            )

            # Validate we got a commit SHA (empty repos have no commits)
            if not clone_result.commit_sha:
                logger.warning(
                    f"Repository {repo_spec} has no commits (empty repository). "
                    f"Skipping batch with {len(file_batch.file_paths)} files."
                )
                # Return empty list - no files can be processed from empty repo
                return []

            # Configure sparse checkout for only the files we need
            with newrelic.agent.FunctionTrace(name="GitHubFileBackfill/checkout_files"):
                sparse_success = await self._configure_sparse_checkout(
                    repo_path, file_batch.file_paths
                )

                if not sparse_success:
                    # Fallback: try full checkout for smaller repos
                    logger.warning(
                        f"Sparse checkout failed, attempting full checkout for {repo_spec}"
                    )
                    full_checkout_cmd = [
                        "git",
                        "-C",
                        str(repo_path),
                        "checkout",
                    ]

                    process = await asyncio.create_subprocess_exec(
                        *full_checkout_cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await process.communicate()

                    if process.returncode != 0:
                        error_msg = stderr.decode() if stderr else "Unknown error"
                        raise RuntimeError(f"Both sparse and full checkout failed: {error_msg}")

                    logger.info("Full checkout completed as fallback")

            entity_ids = []
            artifacts = []

            # Track aggregate stats for contributor extraction across all files
            contributor_stats: dict[str, int | float | str] = {
                "total_duration": 0.0,
                "total_commits": 0,
                "total_contributors": 0,
                "files_processed": 0,
                "slow_files_5s": 0,
                "slow_files_10s": 0,
                "slow_files_30s": 0,
                "max_duration": 0.0,
                "max_duration_file": "",
            }

            # Track aggregate file size metrics
            file_size_stats: dict[str, int | float | str] = {
                "total_bytes": 0,
                "total_files": 0,
                "max_file_size": 0,
                "max_file_size_path": "",
                "large_files_1mb": 0,
                "large_files_10mb": 0,
                "large_files_100mb": 0,
            }

            # Process each file in the batch
            with newrelic.agent.FunctionTrace(name="GitHubFileBackfill/process_files"):
                for relative_path in file_batch.file_paths:
                    file_path = repo_path / relative_path

                    if not file_path.exists():
                        logger.warning(f"File not found: {relative_path} in {repo_spec}")
                        continue

                    try:
                        # Get file contributors first (needed for both plaintext and binary files)
                        with newrelic.agent.FunctionTrace(
                            name="GitHubFileBackfill/get_file_contributors"
                        ):
                            contributors, file_stats = await self._get_file_contributors(
                                repo_path, Path(relative_path), use_follow=False
                            )

                        # Accumulate stats
                        duration = float(file_stats["git_log_duration"])
                        contributor_stats["total_duration"] = (
                            float(contributor_stats["total_duration"]) + duration
                        )
                        contributor_stats["total_commits"] = int(
                            contributor_stats["total_commits"]
                        ) + int(file_stats["commits_found"])
                        contributor_stats["total_contributors"] = int(
                            contributor_stats["total_contributors"]
                        ) + int(file_stats["contributors_found"])
                        contributor_stats["files_processed"] = (
                            int(contributor_stats["files_processed"]) + 1
                        )

                        if duration > 30:
                            contributor_stats["slow_files_30s"] = (
                                int(contributor_stats["slow_files_30s"]) + 1
                            )
                        elif duration > 10:
                            contributor_stats["slow_files_10s"] = (
                                int(contributor_stats["slow_files_10s"]) + 1
                            )
                        elif duration > 5:
                            contributor_stats["slow_files_5s"] = (
                                int(contributor_stats["slow_files_5s"]) + 1
                            )

                        if duration > float(contributor_stats["max_duration"]):
                            contributor_stats["max_duration"] = duration
                            contributor_stats["max_duration_file"] = relative_path

                        # Check if file is plaintext and read content accordingly
                        with newrelic.agent.FunctionTrace(
                            name="GitHubFileBackfill/read_file_content"
                        ):
                            # Get file size for tracking
                            file_size = file_path.stat().st_size

                            # check if the file seems like plaintext. Might change after reading file contents.
                            is_plaintext = is_plaintext_file(str(file_path))
                            if is_plaintext:
                                # Read file content with proper encoding detection
                                with open(file_path, "rb") as f:
                                    binary_content = f.read()
                                content = decode_file_content(
                                    binary_content, file_path=f"{relative_path} in {repo_spec}"
                                )

                                # Check for null bytes, which are a sign that the file is actually binary even though
                                # we thought it was text
                                if "\0" in content:
                                    logger.info(
                                        f"File {relative_path} in {repo_spec} contains null bytes, treating as binary"
                                    )
                                    # we'll reprocess this as a binary file, replacing content with metadata
                                    is_plaintext = False

                            if not is_plaintext:
                                # Generate metadata content for binary files
                                last_modified = datetime.fromtimestamp(
                                    file_path.stat().st_mtime
                                ).isoformat()
                                content = generate_binary_file_metadata_content(
                                    file_path=relative_path,
                                    organization=file_batch.org_or_owner,
                                    repository=file_batch.repo_name,
                                    file_size_bytes=file_size,
                                    contributors=contributors,
                                    last_modified=last_modified,
                                )

                        # Track file size metrics
                        file_size_stats["total_bytes"] = (
                            int(file_size_stats["total_bytes"]) + file_size
                        )
                        file_size_stats["total_files"] = int(file_size_stats["total_files"]) + 1

                        if file_size > int(file_size_stats["max_file_size"]):
                            file_size_stats["max_file_size"] = file_size
                            file_size_stats["max_file_size_path"] = relative_path

                        if file_size >= 100_000_000:  # 100 MB
                            file_size_stats["large_files_100mb"] = (
                                int(file_size_stats["large_files_100mb"]) + 1
                            )
                        elif file_size >= 10_000_000:  # 10 MB
                            file_size_stats["large_files_10mb"] = (
                                int(file_size_stats["large_files_10mb"]) + 1
                            )
                        elif file_size >= 1_000_000:  # 1 MB
                            file_size_stats["large_files_1mb"] = (
                                int(file_size_stats["large_files_1mb"]) + 1
                            )

                        entity_id = get_github_file_entity_id(
                            organization=file_batch.org_or_owner,
                            repository=file_batch.repo_name,
                            file_path=relative_path,
                        )

                        artifact = GitHubFileArtifact(
                            entity_id=entity_id,
                            ingest_job_id=UUID(job_id),
                            content=GitHubFileContent(
                                path=relative_path,
                                content=content,
                                source_created_at=datetime.fromtimestamp(
                                    file_path.stat().st_mtime
                                ).isoformat(),
                                contributors=contributors,
                                contributor_count=len(contributors),
                                organization=file_batch.org_or_owner,
                                repository=file_batch.repo_name,
                                source_branch=file_batch.branch,
                                source_commit_sha=file_batch.commit_sha,
                            ),
                            metadata=GitHubFileMetadata(
                                repository=file_batch.repo_name,
                                organization=file_batch.org_or_owner,
                                file_extension=file_path.suffix.lower(),
                                source_branch=file_batch.branch,
                                source_commit_sha=file_batch.commit_sha,
                            ),
                            # We just pulled this file's data fresh, so we can set source_updated_at to now()
                            source_updated_at=datetime.now(tz=UTC),
                        )

                        artifacts.append(artifact)
                        entity_ids.append(entity_id)

                    except Exception as e:
                        logger.error(f"Error processing file {relative_path}: {e}")
                        continue

            # Store all artifacts in a single batch operation
            if artifacts:
                with newrelic.agent.FunctionTrace(name="GitHubFileBackfill/store_artifacts_batch"):
                    await self.store_artifacts_batch(db_pool, artifacts)

            # Log aggregate contributor extraction stats
            if int(contributor_stats["files_processed"]) > 0:
                avg_duration = float(contributor_stats["total_duration"]) / int(
                    contributor_stats["files_processed"]
                )
                logger.info(
                    "Contributor extraction stats",
                    repo=repo_spec,
                    total_time_seconds=float(contributor_stats["total_duration"]),
                    files_processed=int(contributor_stats["files_processed"]),
                    avg_time_seconds=avg_duration,
                    max_time_seconds=float(contributor_stats["max_duration"]),
                    max_duration_file=contributor_stats["max_duration_file"],
                    slow_files_5s=int(contributor_stats["slow_files_5s"]),
                    slow_files_10s=int(contributor_stats["slow_files_10s"]),
                    slow_files_30s=int(contributor_stats["slow_files_30s"]),
                    total_commits=int(contributor_stats["total_commits"]),
                    total_contributors=int(contributor_stats["total_contributors"]),
                )

            # Log file size statistics
            if int(file_size_stats["total_files"]) > 0:
                total_bytes = int(file_size_stats["total_bytes"])
                total_files = int(file_size_stats["total_files"])
                avg_file_size = total_bytes / total_files
                total_mb = total_bytes / (1024 * 1024)

                logger.info(
                    "File size statistics",
                    repo=repo_spec,
                    total_files=total_files,
                    total_bytes=total_bytes,
                    total_mb=f"{total_mb:.2f}",
                    avg_file_size_bytes=int(avg_file_size),
                    avg_file_size_kb=f"{avg_file_size / 1024:.2f}",
                    max_file_size_bytes=int(file_size_stats["max_file_size"]),
                    max_file_size_mb=f"{int(file_size_stats['max_file_size']) / (1024 * 1024):.2f}",
                    max_file_size_path=file_size_stats["max_file_size_path"],
                    large_files_1mb=int(file_size_stats["large_files_1mb"]),
                    large_files_10mb=int(file_size_stats["large_files_10mb"]),
                    large_files_100mb=int(file_size_stats["large_files_100mb"]),
                )

            logger.info(f"Processed and stored {len(entity_ids)} files from batch in {repo_spec}")

            # Clean up this repository's clone
            if repo_path and repo_path.exists():
                try:
                    shutil.rmtree(repo_path)
                except Exception as e:
                    logger.error(f"Error cleaning up repo {repo_path}: {e}")

            return entity_ids

        except Exception as e:
            logger.error(
                f"Failed to process file batch from {file_batch.org_or_owner}/{file_batch.repo_name}: {e}"
            )
            raise

    async def _get_file_contributors(
        self, repo_path: Path, file_path: Path, use_follow: bool = True
    ) -> tuple[list[GitHubFileContributor], dict[str, int | float]]:
        """Get contributor information for a specific file using git log.

        Args:
            repo_path: Path to the git repository
            file_path: Relative path to the file within the repository
            use_follow: If True, use --follow to track renames (slower for large repos)

        Returns:
            Tuple of (contributors list, stats dict with timing/count info)
        """
        stats: dict[str, int | float] = {
            "git_log_duration": 0.0,
            "commits_found": 0,
            "contributors_found": 0,
        }

        try:
            cmd = [
                "git",
                "-C",
                str(repo_path),
                "log",
                "--format=%aN|%aE|%aI",
            ]

            # Only add --follow for smaller repos to avoid performance issues
            if use_follow:
                cmd.append("--follow")

            cmd.extend(["--", str(file_path)])

            # Track git subprocess execution time
            git_log_start = time.perf_counter()
            with newrelic.agent.FunctionTrace(name="GitHubFileBackfill/git_log_subprocess"):
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, _ = await process.communicate()

            stats["git_log_duration"] = time.perf_counter() - git_log_start

            if process.returncode != 0:
                return [], stats

            # Track contributor parsing time
            with newrelic.agent.FunctionTrace(name="GitHubFileBackfill/parse_git_log_output"):
                output_lines = stdout.decode().strip().split("\n")
                stats["commits_found"] = len([line for line in output_lines if line])

                contributors_map = {}
                for line in output_lines:
                    if not line:
                        continue

                    parts = line.split("|")
                    if len(parts) == 3:
                        name, email, timestamp = parts
                        if email not in contributors_map:
                            contributors_map[email] = GitHubFileContributor(
                                name=name,
                                email=email,
                                commit_count=0,
                                last_contribution_at=timestamp,
                            )
                        contributors_map[email].commit_count += 1

                contributors = list(contributors_map.values())
                stats["contributors_found"] = len(contributors)

            # Log if this file took unusually long
            if stats["git_log_duration"] > 5.0:
                logger.info(
                    "Slow contributor extraction",
                    file_path=str(file_path),
                    duration_seconds=float(stats["git_log_duration"]),
                    commits_found=int(stats["commits_found"]),
                    contributors_found=int(stats["contributors_found"]),
                )

            return contributors, stats

        except Exception as e:
            logger.error(f"Error getting contributors for {file_path}: {e}")
            return [], stats

    async def _get_repo_commit_count(self, repo_path: Path) -> int:
        """Get total commit count for the repository to determine if --follow should be used."""
        try:
            cmd = [
                "git",
                "-C",
                str(repo_path),
                "rev-list",
                "--count",
                "--all",  # Count all commits in the repository
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await process.communicate()

            if process.returncode == 0:
                return int(stdout.decode().strip())
            else:
                # If we can't get count, default to 0 (will use --follow)
                return 0

        except Exception as e:
            logger.error(f"Error getting commit count for {repo_path}: {e}")
            return 0

    async def _configure_sparse_checkout(self, repo_path: Path, file_paths: list[str]) -> bool:
        """
        Configure sparse checkout to only download specific files.
        Returns True if successful, False if fallback is needed.
        """
        try:
            # Step 1: Initialize sparse checkout with cone mode for better performance
            #
            # PERFORMANCE TRADE-OFF: Cone mode uses --cone for O(1) performance but
            # downloads ALL files in parent directories. This can download 10x-100x
            # more files than strictly needed.
            #
            # Example: To get "src/utils/helper.py", cone mode downloads:
            #   - ALL files in top-level directory
            #   - ALL files in src/
            #   - ALL files in src/utils/
            #
            # When this is problematic:
            #   - Large parent directories (src/ with 1000+ files)
            #   - Shallow file paths (most files in top 2 levels)
            #   - Sparse file selection (3 files from 1000-file directory)
            #
            # Alternative: Use --no-cone (non-cone mode)
            #   Pros: Downloads ONLY the exact files specified
            #   Cons: O(N*M) performance, deprecated by git
            #   Change: Replace "--cone" with "--no-cone" and remove parent dir logic
            #
            # Future improvement: Add adaptive mode that chooses cone/non-cone based
            # on file distribution analysis (avg depth, files per directory, etc.)
            #
            init_cmd = [
                "git",
                "-C",
                str(repo_path),
                "sparse-checkout",
                "init",
                "--cone",  # TODO: Consider making this configurable or adaptive
            ]

            logger.info(f"Initializing sparse checkout for {len(file_paths)} files")
            process = await asyncio.create_subprocess_exec(
                *init_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.warning(f"Failed to initialize sparse checkout: {error_msg}")
                return False

            # Step 2: Set the paths we want to check out
            # For cone mode, we need to handle both files and directories
            # NOTE: Adding parent dirs means cone mode will download ALL files
            # in those directories, not just our target files. See comment above
            # about performance trade-offs.
            paths_to_set = set()
            for file_path in file_paths:
                # Add the file path
                paths_to_set.add(file_path)
                # Also add parent directories for cone mode compatibility
                parts = file_path.split("/")
                for i in range(1, len(parts)):
                    parent = "/".join(parts[:i])
                    if parent:
                        paths_to_set.add(parent)

            set_cmd = ["git", "-C", str(repo_path), "sparse-checkout", "set"] + list(paths_to_set)

            process = await asyncio.create_subprocess_exec(
                *set_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.warning(f"Failed to set sparse checkout paths: {error_msg}")
                # Try to disable sparse checkout before returning
                await self._disable_sparse_checkout(repo_path)
                return False

            # Step 3: Perform the checkout
            checkout_cmd = [
                "git",
                "-C",
                str(repo_path),
                "checkout",
            ]

            logger.info("Performing sparse checkout...")
            process = await asyncio.create_subprocess_exec(
                *checkout_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.warning(f"Checkout failed during sparse checkout: {error_msg}")
                # Try to disable sparse checkout
                await self._disable_sparse_checkout(repo_path)
                return False

            # Step 4: Verify that all files were found
            files_found = 0
            for file_path in file_paths:
                full_path = repo_path / file_path
                if full_path.exists():
                    files_found += 1

            if files_found < len(file_paths):
                logger.warning(
                    "Didn't find all file paths in sparse checkout, falling back to full checkout"
                )
                await self._disable_sparse_checkout(repo_path)
                return False

            # Calculate overhead ratio to help identify when cone mode is inefficient
            overhead_ratio = len(paths_to_set) / len(file_paths) if file_paths else 1
            logger.info(
                f"Sparse checkout successful: {files_found}/{len(file_paths)} files present. "
                f"Cone mode checked out {len(paths_to_set)} paths (includes parent dirs, ratio: {overhead_ratio:.1f}x). "
                f"If ratio >10x, consider non-cone mode for bandwidth savings."
            )
            return True

        except Exception as e:
            logger.error(f"Unexpected error during sparse checkout: {e}")
            # Try to disable sparse checkout
            await self._disable_sparse_checkout(repo_path)
            return False

    async def _disable_sparse_checkout(self, repo_path: Path) -> None:
        """Disable sparse checkout to allow fallback to full checkout."""
        try:
            disable_cmd = [
                "git",
                "-C",
                str(repo_path),
                "sparse-checkout",
                "disable",
            ]

            process = await asyncio.create_subprocess_exec(
                *disable_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            logger.info("Disabled sparse checkout")
        except Exception as e:
            logger.error(f"Failed to disable sparse checkout: {e}")
