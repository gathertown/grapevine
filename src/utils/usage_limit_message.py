"""
Usage Limit Message Generation

Provides functionality to generate standardized usage limit messages
when tenants exceed their usage limits.
"""

from src.utils.logging import get_logger
from src.utils.tenant_config import get_tenant_company_name
from src.utils.usage_tracker import UsageCheckResult

logger = get_logger(__name__)


async def generate_usage_limit_message(tenant_id: str, usage_result: UsageCheckResult) -> str:
    """
    Generate a standardized usage limit exceeded message for a tenant.

    Args:
        tenant_id: Tenant identifier
        usage_result: UsageCheckResult containing trial status and limit details

    Returns:
        Formatted usage limit message string for subscription, trial quota exhaustion, or trial expiration
    """
    try:
        company_name = await get_tenant_company_name(tenant_id)

        # Generate the appropriate message based on trial status and limit type
        if usage_result.tier == "expired_trial":
            message = (
                f"{company_name}'s 30-day trial of Grapevine has expired. "
                f"Please ask your admin about signing up for a plan."
            )
        elif usage_result.is_trial and usage_result.quota_exceeded and usage_result.tier == "trial":
            # Only show trial quota message for actual trial tier (no subscription)
            message = (
                f"{company_name} has used all available requests in this month's trial of Grapevine. "
                f"Please ask your admin about signing up for a plan to continue using Grapevine."
            )
        elif usage_result.quota_exceeded:
            # Standard subscription quota exceeded case
            message = (
                f"{company_name} has reached this month's request limit for Grapevine. "
                f"Please ask your admin about increasing your plan limits."
            )
        else:
            # Fallback case (shouldn't normally reach here)
            logger.warning(
                f"Unexpected usage check state for tenant {tenant_id}: tier={usage_result.tier}, is_trial={usage_result.is_trial}, quota_exceeded={usage_result.quota_exceeded}"
            )
            message = (
                f"{company_name} has reached the usage limit for Grapevine. "
                f"Please ask your admin about your plan."
            )

        logger.info(
            f"Generated usage limit message for tenant {tenant_id} (tier: {usage_result.tier}, is_trial: {usage_result.is_trial}, quota_exceeded: {usage_result.quota_exceeded})"
        )
        return message

    except Exception as e:
        logger.error(
            f"Failed to generate usage limit message for tenant {tenant_id}: {e}", exc_info=True
        )

        # Return a generic fallback message if anything fails
        if usage_result.tier == "expired_trial":
            return (
                "Your 30-day trial of Grapevine has expired. "
                "Please ask your admin about signing up for a plan."
            )
        elif usage_result.is_trial and usage_result.quota_exceeded and usage_result.tier == "trial":
            # Only show trial quota message for actual trial tier (no subscription)
            return (
                "You have used all available requests in this month's trial of Grapevine. "
                "Please ask your admin about signing up for a plan to continue using Grapevine."
            )
        elif usage_result.quota_exceeded:
            return (
                "You have reached this month's request limit for Grapevine. "
                "Please ask your admin about increasing your plan limits."
            )
        else:
            logger.warning(
                f"Unexpected usage check state in fallback for tenant {tenant_id}: tier={usage_result.tier}, is_trial={usage_result.is_trial}, quota_exceeded={usage_result.quota_exceeded}"
            )
            return (
                "You have reached the usage limit for Grapevine. "
                "Please ask your admin about your plan."
            )
