"""
Utilities for consistent job completion logging and metrics reporting.
"""

from typing import TYPE_CHECKING, Any

import newrelic.agent

from src.utils.error_handling import LoggerType

if TYPE_CHECKING:
    from src.jobs.sqs_job_processor import SQSMessageMetadata


def record_job_completion(
    logger: LoggerType,
    job_type: str,
    job_status: str,
    base_fields: dict[str, Any],
    error_message: str | None = None,
    rate_limit_reason: str | None = None,
    sqs_metadata: "SQSMessageMetadata | None" = None,
    duration_seconds: float | None = None,
) -> None:
    """
    Record job completion with consistent logging and New Relic metrics.

    Args:
        logger: Logger instance to use
        job_type: Type of job ("Ingest", "Index", etc.)
        job_status: Status of the job ("success", "failed", "rate_limited")
        base_fields: Base fields to include in both logs and metrics (tenant_id, source, etc.)
        error_message: Error message for failed jobs
        rate_limit_reason: Rate limit reason for rate_limited jobs
        sqs_metadata: Optional SQS message metadata for deduplication tracking
        duration_seconds: Optional duration in seconds for processing the job
    """
    # Derive event name from job type
    event_name = f"{job_type}JobComplete"

    # Determine log level and message based on status
    if job_status == "success":
        log_level = "info"
        message = f"{job_type} job completed successfully"
    elif job_status == "rate_limited":
        log_level = "info"
        message = f"{job_type} job rate limited or delayed: {rate_limit_reason}"
    elif job_status == "failed":
        log_level = "error"
        message = f"{job_type} job failed: {error_message}"
    else:
        raise ValueError(f"Unknown job_status: {job_status}")

    # Create log fields
    log_fields = {**base_fields, "job_status": job_status}

    # Add SQS metadata to log fields if available
    if sqs_metadata:
        if sqs_metadata["message_id"]:
            log_fields["sqs_message_id"] = sqs_metadata["message_id"]
        if sqs_metadata["approximate_receive_count"]:
            log_fields["sqs_receive_count"] = sqs_metadata["approximate_receive_count"]

    # Add duration to log fields if available
    if duration_seconds is not None:
        log_fields["duration_seconds"] = round(duration_seconds, 3)

    # Log the completion
    if log_level == "info":
        logger.info(message, **log_fields)
    else:
        logger.error(message, **log_fields)

    # Create New Relic event fields
    event_fields = {**base_fields, "job_status": job_status}

    # Add SQS metadata to event fields if available
    if sqs_metadata:
        if sqs_metadata["message_id"]:
            event_fields["sqs_message_id"] = sqs_metadata["message_id"]
        if sqs_metadata["approximate_receive_count"]:
            event_fields["sqs_receive_count"] = sqs_metadata["approximate_receive_count"]

    # Add duration to event fields if available
    if duration_seconds is not None:
        event_fields["duration_seconds"] = round(duration_seconds, 3)

    # Add status-specific fields
    if error_message:
        event_fields["error_message"] = error_message
    if rate_limit_reason:
        event_fields["rate_limit_reason"] = rate_limit_reason

    # Record New Relic custom event
    newrelic.agent.record_custom_event(event_name, event_fields)
