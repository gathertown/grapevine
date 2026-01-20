"""Usage tracking of OpenAI API responses, for reporting and billing"""

from src.utils.logging import get_logger

logger = get_logger(__name__)


def report_usage_data(response):
    """Extract token usage and metadata from OpenAI API response, and report."""

    # No usage data tagged on the request. This should never happen _now_,
    # but if we change models or APIs, we'll need to adjust this
    if not (hasattr(response, "usage") and response.usage):
        logger.warning("No usage data found in response")
        return

    # Extract token usage information
    try:
        # GPT-5 uses input_tokens/output_tokens instead of prompt_tokens/completion_tokens
        usage_data = {
            "prompt_tokens": response.usage.input_tokens,  # Map to standard Langfuse field
            "completion_tokens": response.usage.output_tokens,  # Map to standard Langfuse field
            "total_tokens": response.usage.total_tokens,
        }

        # Include additional GPT-5 specific details if available
        # Add optional details if available
        if hasattr(response.usage, "input_tokens_details") and response.usage.input_tokens_details:
            cached_tokens = getattr(response.usage.input_tokens_details, "cached_tokens", None)
            if cached_tokens is not None:
                usage_data["cached_tokens"] = cached_tokens

        if (
            hasattr(response.usage, "output_tokens_details")
            and response.usage.output_tokens_details
        ):
            reasoning_tokens = getattr(
                response.usage.output_tokens_details, "reasoning_tokens", None
            )
            if reasoning_tokens is not None:
                usage_data["reasoning_tokens"] = reasoning_tokens

        # Extract response metadata
        model = getattr(response, "model", "unknown")
        response_id = getattr(response, "id", "unknown")

        # TODO: Actually reported the metered billing somewhere real - likely NR + Stripe metering
        # Will also require plumbing in the tenant and user making the request

        logger.info(
            f"Usage data reported for model {model}, response ID {response_id}: {usage_data}"
        )

    except Exception as usage_error:
        logger.warning(f"Error extracting usage data: {usage_error}")
