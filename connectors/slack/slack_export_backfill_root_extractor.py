import asyncio
import json
import math
import os
import secrets
import struct
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlparse
from uuid import UUID

import asyncpg
import boto3

from connectors.base import (
    BaseExtractor,
    TriggerIndexingCallback,
    get_slack_channel_entity_id,
    get_slack_team_entity_id,
    get_slack_user_entity_id,
)
from connectors.slack.slack_artifacts import (
    SlackChannelArtifact,
    SlackChannelContent,
    SlackChannelMetadata,
    SlackTeamArtifact,
    SlackTeamContent,
    SlackUserArtifact,
    SlackUserContent,
)
from connectors.slack.slack_models import (
    SlackChannelDayFile,
    SlackExportBackfillConfig,
    SlackExportBackfillRootConfig,
)
from src.clients.slack import SlackClient
from src.clients.sqs import SQSClient
from src.clients.ssm import SSMClient
from src.utils.file_encoding import read_json_file_safe
from src.utils.logging import LogContext, get_logger
from src.utils.tenant_config import increment_backfill_total_ingest_jobs

logger = get_logger(__name__)

# Number of channel-day files per child job
# For reference: on 8/26/25 we ran a huge slack export at around ~2k ingest jobs/min throughput
# on 15 pods with a batch size of 5.
# Using a bigger batch size generally better (can be much more efficient for indexing, too) as long as jobs don't
# get too long or risky.
CHILD_JOB_BATCH_SIZE = 25

# Number of artifacts to buffer before writing them to DB
ARTIFACT_BATCH_SIZE = 100


# Maximum concurrent SQS operations (e.g. sends) to prevent overwhelming the system
MAX_CONCURRENT_SQS_OPERATIONS = 100

# Maximum file size for individual files in ZIP (1GB)
MAX_FILE_SIZE = 1 * 1024 * 1024 * 1024  # 1GB


class SlackExportBackfillRootExtractor(BaseExtractor[SlackExportBackfillRootConfig]):
    source_name = "slack_export_backfill_root"

    def __init__(self, ssm_client: SSMClient, sqs_client: SQSClient):
        super().__init__()
        self.ssm_client = ssm_client
        self.sqs_client = sqs_client
        # Private fields to store public channels data read once from ZIP
        self._public_channel_name_to_id: dict[str, str] = {}
        self._public_channels_data: list[dict] = []
        # Private fields to store DM data read once from ZIP
        self._dm_id_to_participants: dict[str, list[str]] = {}
        self._dms_data: list[dict] = []
        # Semaphore to limit concurrent SQS operations
        self._sqs_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SQS_OPERATIONS)
        # Base directory for nested ZIP structure
        self._base_directory: str = ""

    def _is_safe_path(self, path: str, base_dir: Path) -> bool:
        """
        Validate that a path is safe and doesn't escape the base directory.

        Args:
            path: The path to validate (from ZIP entry)
            base_dir: The base directory that paths must stay within

        Returns:
            True if the path is safe, False otherwise
        """
        try:
            # Convert to Path and resolve (normalizes and makes absolute)
            full_path = (base_dir / path).resolve()
            base_resolved = base_dir.resolve()

            # Check if the resolved path is within the base directory
            if not full_path.is_relative_to(base_resolved):
                logger.error(f"Rejecting path that escapes base directory: {path} -> {full_path}")
                return False
        except (ValueError, RuntimeError) as e:
            logger.error(f"Path validation failed for {path}: {e}")
            return False

        return True

    def _check_zip_entry_looks_safe(self, zip_info: zipfile.ZipInfo, extract_dir: Path) -> bool:
        """
        Validate a ZIP entry before processing. Rejects unsafe paths, large files, and
        especially high compression ratios.

        Note: Symlink protection is handled by our extraction method - we read file content
        directly from the ZIP and write to controlled locations, never extracting symlinks as such.

        Args:
            zip_info: The ZIP entry info to validate
            extract_dir: The directory where extraction would occur

        Returns:
            True if the entry is safe to process, False otherwise
        """
        if zip_info.is_dir():
            return True  # Directories are generally safe

        # Validate the path
        if not self._is_safe_path(zip_info.filename, extract_dir):
            return False

        # Check file size to prevent resource exhaustion
        if zip_info.file_size > MAX_FILE_SIZE:
            logger.error(f"Rejecting file larger than {MAX_FILE_SIZE} bytes: {zip_info.filename}")
            return False

        # Check compression ratio for potential ZIP bombs
        if zip_info.compress_size > 0:
            compression_ratio = zip_info.file_size / zip_info.compress_size
            if compression_ratio > 100:  # Suspicious compression ratio
                logger.error(
                    f"Rejecting file with suspicious compression ratio {compression_ratio:.1f}: {zip_info.filename}"
                )
                return False

        return True

    async def process_job(
        self,
        job_id: str,
        config: SlackExportBackfillRootConfig,
        db_pool: asyncpg.Pool,
        trigger_indexing: TriggerIndexingCallback,
    ) -> None:
        # Generate a unique backfill ID for this root job
        backfill_id = secrets.token_hex(8)
        logger.info(
            f"Processing Slack export backfill root job {job_id} for tenant {config.tenant_id} with backfill_id {backfill_id}"
        )

        with LogContext(job_id=job_id), tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Download ZIP file to temp directory
            export_path = await self._download_file(config.uri, temp_path)

            # Detect base directory if ZIP has nested structure
            self._base_directory = await self._detect_base_directory(export_path)

            # Read channels.json and dms.json once and store in private fields
            # This must happen first so we know what channels/DMs are available
            await self._load_channels_data(export_path)
            await self._load_dms_data(export_path)

            # Process these in parallel since they're independent
            results = await asyncio.gather(
                self._process_channels_and_users_and_team(job_id, export_path, db_pool, config),
                self._analyze_channel_day_files(export_path),
                return_exceptions=True,
            )

            entities_result, channel_day_files_result = results

            if isinstance(entities_result, Exception):
                raise entities_result
            if isinstance(channel_day_files_result, Exception):
                raise channel_day_files_result

            # Type narrowing using cast - we know these aren't exceptions now
            channel_entity_ids, user_entity_ids, team_entity_ids = cast(
                tuple[list[str], list[str], list[str]], entities_result
            )
            channel_day_files = cast(list[SlackChannelDayFile], channel_day_files_result)

            logger.info(
                f"Root job {job_id} processed {len(channel_entity_ids)} channels (public channels + DMs), "
                f"{len(user_entity_ids)} users, {len(team_entity_ids)} teams, "
                f"found {len(channel_day_files)} channel-day and DM files with backfill_id {backfill_id}"
            )

            # Send child jobs for message processing
            if channel_day_files:
                # Calculate number of child job batches
                num_batches = math.ceil(len(channel_day_files) / CHILD_JOB_BATCH_SIZE)
                # Track total number of ingest jobs (child batches) for this backfill
                await increment_backfill_total_ingest_jobs(
                    backfill_id, config.tenant_id, num_batches
                )

                await self._send_child_jobs(config, channel_day_files, backfill_id)
                logger.info(
                    f"Sent child jobs for {len(channel_day_files)} channel-day and DM files"
                )

            logger.info(f"Successfully completed root job {job_id}")

    async def _download_file(self, uri: str, temp_dir: Path) -> Path:
        parsed_uri = urlparse(uri)

        if parsed_uri.scheme != "s3":
            raise ValueError(f"Only S3 URIs are supported, got: {uri}")

        bucket = parsed_uri.netloc
        key = parsed_uri.path.lstrip("/")
        filename = Path(parsed_uri.path).name or "slack_export.zip"
        download_path = temp_dir / filename

        logger.info(f"Downloading from S3: bucket={bucket}, key={key} to {download_path}")
        s3_client = boto3.client("s3")
        s3_client.download_file(bucket, key, str(download_path))

        logger.info(f"Downloaded file to {download_path}")
        return download_path

    def _should_skip_macos_metadata(self, path: str) -> bool:
        """
        Check if a file path is macOS metadata that should be ignored.

        Returns True for:
        - Paths starting with __MACOSX/
        - Files starting with ._ (AppleDouble format)
        """
        return (
            path.startswith("__MACOSX/")
            or "/__MACOSX/" in path
            or path.startswith("._")
            or "/._" in path
        )

    async def _detect_base_directory(self, export_path: Path) -> str:
        """
        Detect the base directory by finding channels.json in the ZIP.

        Slack exports always contain exactly one channels.json file at the root of the export.
        We find this file and use its parent directory as the base path.

        Returns the base directory path (with trailing slash) if files are nested,
        or empty string if channels.json is at root level.
        """
        with (
            zipfile.ZipFile(export_path, "r") as zip_ref,
            tempfile.TemporaryDirectory() as temp_dir,
        ):
            info_list = zip_ref.infolist()

            if not info_list:
                raise ValueError("ZIP file is empty")

            # temporary directory for validation (not used for actual extraction)
            temp_validation_dir = Path(temp_dir)

            # Find channels.json file - Slack exports always have exactly one
            channels_file_path = None
            channels_zip_info = None
            for info in info_list:
                # Skip macOS metadata
                if self._should_skip_macos_metadata(info.filename):
                    continue

                # First validate the entry is safe
                if not self._check_zip_entry_looks_safe(info, temp_validation_dir):
                    logger.error(f"Skipping unsafe ZIP entry: {info.filename}")
                    continue

                # Match exactly "channels.json" or "*/channels.json" but not "prefix_channels.json"
                if (
                    info.filename == "channels.json" or info.filename.endswith("/channels.json")
                ) and not info.is_dir():
                    # Additional validation: ensure the filename part is exactly "channels.json"
                    filename_only = os.path.basename(info.filename)
                    if filename_only == "channels.json":
                        channels_file_path = info.filename
                        channels_zip_info = info
                        logger.info(f"Found channels.json at: {channels_file_path}")
                        break

            if not channels_file_path or not channels_zip_info:
                # Log a couple filenames for debugging
                all_paths = [info.filename for info in info_list]
                logger.error(
                    "channels.json not found in Slack export ZIP",
                    file_count=len(all_paths),
                    sample_file_names=all_paths[:3],
                )
                raise ValueError("channels.json not found in Slack export ZIP file")

            # Validate the path is safe before processing
            if not self._is_safe_path(channels_file_path, temp_validation_dir):
                raise ValueError(f"Unsafe channels.json path detected: {channels_file_path}")

            # Extract base directory from channels.json path
            if "/" in channels_file_path:
                base_directory = channels_file_path.rsplit("/", 1)[0] + "/"

                # Additional validation of the base directory
                if not self._is_safe_path(base_directory, temp_validation_dir):
                    raise ValueError(f"Unsafe base directory detected: {base_directory}")

                logger.info(
                    f"Detected nested Slack export structure with base directory: '{base_directory}'"
                )
            else:
                base_directory = ""
                logger.info("Detected standard Slack export structure with files at root level")

            return base_directory

    async def _load_channels_data(self, export_path: Path) -> None:
        """Read channels.json once and store both full data and name->ID mapping in private fields."""
        self._public_channel_name_to_id = {}
        self._public_channels_data = []

        channels_path = f"{self._base_directory}channels.json"

        with (
            zipfile.ZipFile(export_path, "r") as zip_ref,
            zip_ref.open(channels_path) as channels_file,
        ):
            self._public_channels_data = json.loads(channels_file.read().decode("utf-8"))
            for channel in self._public_channels_data:
                channel_name = channel.get("name", "")
                self._public_channel_name_to_id[channel_name] = channel.get("id", "")
        logger.info(f"Found {len(self._public_channels_data)} public channels in {channels_path}")

    async def _load_dms_data(self, export_path: Path) -> None:
        """Read dms.json once and store both full data and id->participants mapping in private fields."""
        self._dm_id_to_participants = {}
        self._dms_data = []

        dms_path = f"{self._base_directory}dms.json"

        try:
            with (
                zipfile.ZipFile(export_path, "r") as zip_ref,
                zip_ref.open(dms_path) as dms_file,
            ):
                self._dms_data = json.loads(dms_file.read().decode("utf-8"))
                for dm in self._dms_data:
                    dm_id = dm.get("id", "")
                    members = dm.get("members", [])
                    if dm_id and members:
                        self._dm_id_to_participants[dm_id] = members
            logger.info(f"Found {len(self._dms_data)} DMs in {dms_path}")
        except KeyError:
            # dms.json might not exist in some exports (no DMs)
            logger.info(f"No {dms_path} found in export - no DMs to process")
        except Exception as e:
            logger.warning(f"Error reading {dms_path}: {e}")
            # Continue without DMs rather than failing the whole job

    async def _process_channels_and_users_and_team(
        self,
        job_id: str,
        export_path: Path,
        db_pool: asyncpg.Pool,
        config: SlackExportBackfillRootConfig,
    ) -> tuple[list[str], list[str], list[str]]:
        """Process channels, users, and team info from the ZIP file."""
        # Extract only the metadata files we need
        extract_dir = export_path.parent / "extracted_metadata"
        extract_dir.mkdir(exist_ok=True)

        users_file = None
        with zipfile.ZipFile(export_path, "r") as zip_ref:
            # Look for users.json (accounting for base directory)
            users_path = f"{self._base_directory}users.json"

            # First validate the path before any operations
            if not self._is_safe_path(users_path, extract_dir):
                raise ValueError(f"Unsafe users.json path detected: {users_path}")

            # Find the users.json entry
            users_info = None
            for info in zip_ref.infolist():
                if info.filename == users_path:
                    users_info = info
                    break

            if users_info:
                # Validate the ZIP entry before processing
                if not self._check_zip_entry_looks_safe(users_info, extract_dir):
                    raise ValueError(f"Unsafe users.json entry detected: {users_path}")

                # Safe extraction: read content and write to controlled location
                # SECURITY: We protect against symlink attacks by:
                # 1. Never using zipfile.extract() which would preserve symlinks
                # 2. Reading file content directly with zip_ref.open()
                # 3. Writing content to our controlled location with write_bytes()
                # This means symlinks in the ZIP are read as regular files, not followed
                safe_filename = "users.json"
                users_file = extract_dir / safe_filename

                # Read the file content from ZIP and write to safe location
                with zip_ref.open(users_info) as source:
                    content = source.read()
                    # Additional size check
                    if len(content) > MAX_FILE_SIZE:
                        raise ValueError("users.json exceeds maximum file size")
                    users_file.write_bytes(content)
                    logger.info(f"Safely extracted users.json to {users_file}")
            else:
                logger.error(f"{users_path} not found in ZIP")

        # Process in parallel
        tasks = []
        # Process channels using the data loaded in private fields
        tasks.append(self._process_channels_from_data(job_id, db_pool))
        # Process DMs using the data loaded in private fields
        tasks.append(self._process_dms_from_data(job_id, db_pool))

        if users_file and users_file.exists():
            tasks.append(self._process_users(job_id, users_file, db_pool))
            tasks.append(self._process_team(job_id, users_file, db_pool, config))
        else:
            raise ValueError("No users.json found in slack export")

        results = await asyncio.gather(*tasks)
        channel_entity_ids = results[0]
        dm_entity_ids = results[1]
        user_entity_ids = results[2] if len(results) > 2 else []
        team_entity_ids = results[3] if len(results) > 3 else []

        # Combine channel and DM entity IDs
        all_channel_entity_ids = channel_entity_ids + dm_entity_ids
        return all_channel_entity_ids, user_entity_ids, team_entity_ids

    async def _process_channels_from_data(self, job_id: str, db_pool: asyncpg.Pool) -> list[str]:
        """Process channels from the data already loaded in private fields."""
        entity_ids = []
        batch = []

        # Use the public channels data already loaded in _public_channels_data private field
        for channel in self._public_channels_data:
            entity_id = get_slack_channel_entity_id(channel_id=channel.get("id", ""))

            artifact = SlackChannelArtifact(
                entity_id=entity_id,
                ingest_job_id=UUID(job_id),
                content=SlackChannelContent(**channel),
                metadata=SlackChannelMetadata(),
                source_updated_at=datetime.fromtimestamp(channel.get("created", 0), tz=UTC)
                if channel.get("created")
                else datetime.now(tz=UTC),
            )

            batch.append(artifact)
            entity_ids.append(entity_id)

            if len(batch) >= ARTIFACT_BATCH_SIZE:
                await self.store_artifacts_batch(db_pool, batch)
                batch = []

        # Store remaining artifacts
        if batch:
            await self.store_artifacts_batch(db_pool, batch)

        logger.info(f"Processed {len(entity_ids)} public channel artifacts")
        return entity_ids

    async def _process_dms_from_data(self, job_id: str, db_pool: asyncpg.Pool) -> list[str]:
        """Process DMs from the data already loaded in private fields."""
        entity_ids = []
        batch = []

        # Use the DMs data already loaded in _dms_data private field
        for dm in self._dms_data:
            dm_id = dm.get("id", "")
            if not dm_id:
                continue

            # Create a channel-like structure for DMs
            dm_channel_data = {
                "id": dm_id,
                "name": dm_id,  # Use DM ID as name since DMs don't have names
                "created": dm.get("created", 0),
                "is_channel": False,
                "is_group": False,
                "is_im": True,  # This is a direct message
                "is_private": True,
                "members": dm.get("members", []),
                "purpose": {"value": "Direct message", "creator": "", "last_set": 0},
                "topic": {"value": "Direct message", "creator": "", "last_set": 0},
            }

            entity_id = get_slack_channel_entity_id(channel_id=dm_id)
            artifact = SlackChannelArtifact(
                entity_id=entity_id,
                ingest_job_id=UUID(job_id),
                content=SlackChannelContent(**dm_channel_data),
                metadata=SlackChannelMetadata(),
                source_updated_at=datetime.fromtimestamp(dm.get("created", 0), tz=UTC)
                if dm.get("created")
                else datetime.now(tz=UTC),
            )

            batch.append(artifact)
            entity_ids.append(entity_id)

            if len(batch) >= ARTIFACT_BATCH_SIZE:
                await self.store_artifacts_batch(db_pool, batch)
                batch = []

        # Store remaining artifacts
        if batch:
            await self.store_artifacts_batch(db_pool, batch)

        logger.info(f"Processed {len(entity_ids)} DM channel artifacts")
        return entity_ids

    def _read_local_file_header_lengths(
        self, zip_ref: zipfile.ZipFile, zip_info: zipfile.ZipInfo
    ) -> tuple[int, int]:
        """
        Read the actual filename and extra field lengths from the Local File Header.

        The Central Directory and Local File Header can have different extra field lengths,
        so we must read the Local File Header to get accurate byte positions.

        Returns:
            tuple[int, int]: (filename_length, extra_field_length) from Local File Header
        """
        # Seek to the Local File Header
        if zip_ref.fp is None:
            raise ValueError(f"ZIP file pointer is None for {zip_info.filename}")

        zip_ref.fp.seek(zip_info.header_offset)

        # Read the 30-byte Local File Header
        header_data = zip_ref.fp.read(30)
        if len(header_data) != 30:
            raise ValueError(f"Could not read Local File Header for {zip_info.filename}")

        # Parse the Local File Header structure
        # Format: signature(4) + version(2) + flags(2) + compression(2) +
        #         mod_time(2) + mod_date(2) + crc32(4) + compressed_size(4) +
        #         uncompressed_size(4) + filename_len(2) + extra_len(2)
        try:
            (
                signature,
                _version,
                _flags,
                _compression,
                _mod_time,
                _mod_date,
                _crc32,
                _compressed_size,
                _uncompressed_size,
                filename_len,
                extra_len,
            ) = struct.unpack("<LHHHHHLLLHH", header_data)

            # Verify this is a valid Local File Header
            if signature != 0x04034B50:
                raise ValueError(f"Invalid Local File Header signature: 0x{signature:08x}")

            return filename_len, extra_len

        except struct.error as e:
            raise ValueError(f"Could not parse Local File Header for {zip_info.filename}: {e}")

    async def _analyze_channel_day_files(self, export_path: Path) -> list[SlackChannelDayFile]:
        """Analyze ZIP file structure to get byte ranges for channel-day JSON files."""
        channel_day_files = []
        total_channel_day_files_found = 0
        private_channel_day_files_skipped = 0
        unsafe_files_skipped = 0

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            zipfile.ZipFile(export_path, "r") as zip_ref,
        ):
            # temporary directory for validation (not used for actual extraction)
            temp_validation_dir = Path(temp_dir)
            # Analyze channel-day files using the channel mapping from private field
            for zip_info in zip_ref.infolist():
                # Skip macOS metadata files
                if self._should_skip_macos_metadata(zip_info.filename):
                    continue

                # Validate the ZIP entry is safe
                if not self._check_zip_entry_looks_safe(zip_info, temp_validation_dir):
                    logger.error(
                        f"Skipping unsafe ZIP entry during channel analysis: {zip_info.filename}"
                    )
                    unsafe_files_skipped += 1
                    continue

                # Additional path validation
                if not self._is_safe_path(zip_info.filename, temp_validation_dir):
                    logger.error(f"Skipping file with unsafe path: {zip_info.filename}")
                    unsafe_files_skipped += 1
                    continue

                # Remove base directory prefix if present
                relative_path = zip_info.filename
                if self._base_directory and relative_path.startswith(self._base_directory):
                    relative_path = relative_path[len(self._base_directory) :]

                # Validate the relative path is also safe
                if not self._is_safe_path(relative_path, temp_validation_dir):
                    logger.error(f"Skipping file with unsafe relative path: {relative_path}")
                    unsafe_files_skipped += 1
                    continue

                # Look for channel-day files: <channel_name>/<date>.json
                if relative_path.count("/") == 1 and relative_path.endswith(".json"):
                    folder_name, filename = relative_path.split("/", 1)

                    # Skip metadata files
                    if filename in ["channels.json", "users.json", "dms.json"]:
                        continue

                    total_channel_day_files_found += 1

                    # Check if this is a DM folder (starts with 'D')
                    if folder_name.startswith("D"):
                        # This is a DM folder
                        if folder_name not in self._dm_id_to_participants:
                            private_channel_day_files_skipped += 1
                            continue

                        # Use the DM ID as both channel_name and channel_id for processing
                        channel_name = folder_name
                        channel_id = folder_name
                    else:
                        # This is a regular channel folder
                        # Skip private channels - only process public channels from channels.json
                        if folder_name not in self._public_channel_name_to_id:
                            private_channel_day_files_skipped += 1
                            continue

                        # Get channel ID from private field mapping, fallback to folder name if not found
                        channel_name = folder_name
                        channel_id = self._public_channel_name_to_id.get(folder_name, folder_name)

                    # Calculate actual start byte of file data within the ZIP
                    # ZIP files have a specific structure for each entry:
                    #
                    # 1. Central Directory Entry (what zip_info contains):
                    #    - Contains metadata about the file (name, size, compression, etc.)
                    #    - header_offset points to the Local File Header for this entry
                    #
                    # 2. Local File Header (30 bytes fixed structure)
                    #
                    # 3. Variable Length Fields:
                    #    - filename (variable length, specified in Local File Header)
                    #    - extra field (variable length, specified in Local File Header)
                    #
                    # 4. File Data:
                    #    - The actual compressed/uncompressed file content starts here
                    #
                    # IMPORTANT: We must read the Local File Header to get accurate lengths,
                    # because Central Directory and Local File Header can have different extra field lengths.
                    filename_len, extra_len = self._read_local_file_header_lengths(
                        zip_ref, zip_info
                    )

                    start_byte = (
                        zip_info.header_offset  # Points to start of Local File Header
                        + 30  # Skip the 30-byte fixed Local File Header structure
                        + filename_len  # Skip variable-length filename (from Local File Header)
                        + extra_len  # Skip variable-length extra field (from Local File Header)
                        # Now we're at the start of the actual file data
                    )

                    channel_day_files.append(
                        SlackChannelDayFile(
                            channel_name=channel_name,
                            channel_id=channel_id,
                            filename=filename,
                            start_byte=start_byte,
                            size=zip_info.compress_size,
                        )
                    )

        logger.info(
            f"Found {total_channel_day_files_found} total channel-day files, "
            f"skipped {private_channel_day_files_skipped} private channel-day files, "
            f"skipped {unsafe_files_skipped} unsafe files, "
            f"processing {len(channel_day_files)} public channel-day files"
        )
        return channel_day_files

    async def _send_child_jobs(
        self,
        config: SlackExportBackfillRootConfig,
        channel_day_files: list[SlackChannelDayFile],
        backfill_id: str,
    ) -> None:
        """Send child jobs to process channel-day files using byte ranges."""
        # Split channel_day_files into batches for child jobs
        # Each child job processes a small batch to avoid overwhelming the system

        total_channel_days = len(channel_day_files)
        logger.info(f"Preparing to send child jobs for {total_channel_days} channel-day files")

        # Create all child job tasks
        tasks = []
        for i in range(0, len(channel_day_files), CHILD_JOB_BATCH_SIZE):
            batch_files = channel_day_files[i : i + CHILD_JOB_BATCH_SIZE]
            batch_index = i // CHILD_JOB_BATCH_SIZE

            child_config = SlackExportBackfillConfig(
                tenant_id=config.tenant_id,
                uri=config.uri,  # Original S3 ZIP URI
                channel_day_files=batch_files,
                message_limit=config.message_limit,
                backfill_id=backfill_id,
                suppress_notification=config.suppress_notification,
            )

            # Create task to send this batch
            task = self._send_single_child_job(child_config, batch_index)
            tasks.append(task)

        # Send all child jobs in parallel
        logger.info(
            f"Sending {len(tasks)} child jobs to process {len(channel_day_files)} channel-day files..."
        )
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check for failures
        jobs_sent = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to send child job batch {i}: {result}")
                raise result
            jobs_sent += 1

        logger.info(
            f"Sent {jobs_sent} child jobs to process {len(channel_day_files)} channel-day files!"
        )

    async def _send_single_child_job(
        self,
        child_config: SlackExportBackfillConfig,
        batch_index: int,
    ) -> None:
        """Send a single child job message to SQS."""
        # Use semaphore to limit concurrent SQS operations
        async with self._sqs_semaphore:
            success = await self.sqs_client.send_backfill_ingest_message(
                backfill_config=child_config,
            )

            if not success:
                raise RuntimeError(f"Failed to send child job batch {batch_index} to SQS")

            log = logger.info if batch_index % 100 == 0 else logger.debug
            log(
                f"Sent child job batch {batch_index} with {len(child_config.channel_day_files)} "
                f"channel-days"
            )

    async def _process_users(
        self, job_id: str, users_file: Path, db_pool: asyncpg.Pool
    ) -> list[str]:
        """Process users and return entity IDs. `users_file` should be a valid path to a users.json file."""
        entity_ids = []
        batch = []

        users = read_json_file_safe(users_file, "users.json")

        for user in users:
            entity_id = get_slack_user_entity_id(user_id=user.get("id", ""))

            # Validate user data with Pydantic model
            artifact = SlackUserArtifact(
                entity_id=entity_id,
                ingest_job_id=UUID(job_id),
                content=SlackUserContent(**user),
                metadata={},
                # For now this is the only place we write to user artifacts so we can set source_updated_at to now()
                source_updated_at=datetime.now(tz=UTC),
            )

            batch.append(artifact)
            entity_ids.append(entity_id)

            if len(batch) >= ARTIFACT_BATCH_SIZE:
                await self.store_artifacts_batch(db_pool, batch)
                batch = []  # Clear batch to free memory

        # Store remaining artifacts
        if batch:
            await self.store_artifacts_batch(db_pool, batch)

        logger.info(f"Processed {len(entity_ids)} user artifacts")
        return entity_ids

    async def _process_team(
        self,
        job_id: str,
        users_file: Path,
        db_pool: asyncpg.Pool,
        config: SlackExportBackfillRootConfig,
    ) -> list[str]:
        """Process team and return entity IDs. `users_file` should be a valid path to a users.json file."""
        team_id = None
        if users_file.exists():
            users_data = read_json_file_safe(users_file, "users.json for team info")
            if users_data and len(users_data) > 0:
                team_id = users_data[0].get("team_id")
        else:
            raise ValueError("No users.json found in slack export - cannot fetch team info")

        if not team_id:
            raise ValueError("No team_id found in users.json - cannot fetch team info")

        logger.info(f"Found team ID: {team_id}, fetching team info from Slack API")
        team_entity_ids = await self._fetch_and_store_team_info(
            job_id, team_id, db_pool, config.tenant_id
        )

        if not team_entity_ids:
            raise RuntimeError(f"Failed to fetch team info for team {team_id}")

        return team_entity_ids

    async def _fetch_and_store_team_info(
        self, job_id: str, team_id: str, db_pool: asyncpg.Pool, tenant_id: str
    ) -> list[str]:
        token = await self.ssm_client.get_slack_token(tenant_id)
        if not token:
            raise ValueError(f"No Slack token configured for tenant {tenant_id}!")

        slack_client = SlackClient(token)
        team_info = slack_client.get_team_info()

        if not team_info:
            raise RuntimeError(f"Failed to fetch team info for team {team_id} from Slack API")

        # Validate team data with Pydantic model
        artifact = SlackTeamArtifact(
            entity_id=get_slack_team_entity_id(team_id=team_info.get("id", team_id)),
            ingest_job_id=UUID(job_id),
            content=SlackTeamContent(**team_info),
            metadata={},
            # For now this is the only place we write to team artifacts so we can set source_updated_at to now()
            source_updated_at=datetime.now(tz=UTC),
        )

        await self.store_artifact(db_pool, artifact)
        logger.info(
            f"Successfully fetched and stored team info for {team_info.get('name', team_id)}"
        )
        return [artifact.entity_id]
