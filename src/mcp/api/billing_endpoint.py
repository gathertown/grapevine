"""REST API endpoint for billing usage via internal JWT authentication."""

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from src.mcp.utils.internal_jwt import verify_internal_jwt
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


@router.get("/billing/usage")
async def billing_usage_endpoint(request: Request) -> JSONResponse:
    """REST API endpoint for billing usage information.

    Requires internal JWT authentication via Authorization: Bearer header.
    Returns tenant_id, usage limits, and current usage for the billing period.
    """
    try:
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                {"error": "Authentication required. Please provide a valid JWT token."},
                status_code=401,
            )

        token = auth_header[7:]  # Remove "Bearer " prefix

        claims = verify_internal_jwt(token)
        if not claims:
            return JSONResponse(
                {"error": "Invalid or expired JWT token"},
                status_code=401,
            )

        # Extract tenant_id from claims
        tenant_id = claims.get("tenant_id")
        if not tenant_id:
            logger.error("JWT missing tenant_id claim", claims=claims)
            return JSONResponse(
                {"error": "Invalid JWT: missing tenant_id"},
                status_code=401,
            )

        # Get usage tracker and billing limits
        from src.utils.usage_tracker import get_usage_tracker

        usage_tracker = get_usage_tracker()

        # Get tenant billing limits
        limits = await usage_tracker.get_tenant_limits(tenant_id)

        # Get current usage for requests metric
        requests_used = await usage_tracker.get_monthly_usage(tenant_id, "requests")

        # Build response with camelCase keys for TypeScript consumers
        response_data = {
            "tenantId": tenant_id,
            "requestsUsed": requests_used,
            "requestsAvailable": limits.monthly_requests,
            "tier": limits.tier,
            "isTrial": limits.is_trial,
            "isGatherManaged": limits.is_gather_managed,
        }

        # Include billing period info if available
        if limits.billing_cycle_anchor:
            response_data["billingCycleAnchor"] = limits.billing_cycle_anchor.isoformat()
        if limits.trial_start_at:
            response_data["trialStartAt"] = limits.trial_start_at.isoformat()

        return JSONResponse(response_data)

    except Exception as e:
        logger.error("Error in /billing/usage endpoint", error=str(e))
        return JSONResponse({"error": "Internal server error"}, status_code=500)
