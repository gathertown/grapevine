"""API key verification service."""

import hmac

from src.clients.ssm import SSMClient
from src.clients.tenant_db import _tenant_db_manager
from src.utils.logging import get_logger

logger = get_logger(__name__)

# Tenant IDs whose API key usage should NOT count towards billing -- This is only for Exponent API usage
# To add a tenant to the whitelist, add their tenant ID to this set
API_KEY_NON_BILLABLE_TENANT_IDS: set[str] = {
    "395c9f9106fd408a",  # BuildPass
    "878f6fb522b441d1",  # Gather Staging
    "b015587adf3247bc",  # Pangram
}


async def verify_api_key(api_key: str | None) -> str | None:
    """Verify an API key and return the associated tenant ID.

    Args:
        api_key: The plain API key to verify (format: gv_{tenant_id}_{random})

    Returns:
        The tenant ID if valid, None otherwise
    """
    if not api_key or not api_key.startswith("gv_"):
        logger.debug("Invalid API key format")
        return None

    try:
        parts = api_key.split("_")
        if len(parts) < 3:
            logger.debug("Invalid API key format - missing components")
            return None

        tenant_id = parts[1]  # Full tenant ID
        ssm_key_id = parts[2][:8]  # First 8 chars of random portion
        stored_prefix = f"gv_{tenant_id}_{ssm_key_id}"

        async with (
            _tenant_db_manager.acquire_pool(tenant_id) as pool,
            pool.acquire() as conn,
        ):
            key_record = await conn.fetchrow(
                "SELECT id FROM api_keys WHERE prefix = $1",
                stored_prefix,
            )

            if not key_record:
                logger.debug("API key not found in database", tenant_id=tenant_id)
                return None

            db_id = str(key_record["id"])
            ssm_client = SSMClient()
            stored_key = await ssm_client.get_api_key(tenant_id, f"gv_api_{db_id}")

            if not stored_key or not hmac.compare_digest(stored_key, api_key):
                logger.debug("API key mismatch in SSM", tenant_id=tenant_id)
                return None

            await conn.execute(
                "UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE prefix = $1",
                stored_prefix,
            )

        logger.info(
            "API key verified successfully",
            tenant_id=tenant_id,
            ssm_key_id=ssm_key_id,
        )
        return tenant_id

    except Exception as e:
        logger.error("Failed to verify API key", error=str(e))
        return None
