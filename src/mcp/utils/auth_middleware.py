from dataclasses import dataclass
from typing import cast

from fastapi import Request, Response
from starlette.responses import JSONResponse

from src.mcp.utils.api_keys import verify_api_key
from src.mcp.utils.internal_jwt import verify_internal_jwt
from src.permissions.utils import make_email_permission_token
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AuthenticatedReqDetails:
    tenant_id: str
    permission_principal_token: str | None
    permission_audience: str | None


async def authenticate_request(
    request: Request,
) -> tuple[AuthenticatedReqDetails | None, Response | None]:
    """Authenticate a request using either API Key or JWT.

    Args:
        request: The FastAPI request object.

    Returns:
        A tuple containing:
        - result (AuthenticatedReqDetails | None): The authenticated request details if authentication is successful.
        - error_response (Response | None): A FastAPI response object if authentication fails.
    """
    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return (
            None,
            JSONResponse(
                {"error": "Authentication required. Please provide a valid API key or JWT."},
                status_code=401,
            ),
        )

    token = auth_header[7:]
    tenant_id: str | None = None
    permission_principal_token: str | None = None
    permission_audience: str | None = None

    # 1. Try validating as internal JWT first (more secure)
    claims = verify_internal_jwt(token)
    if claims:
        claimed_tenant_id = claims.get("tenant_id")
        if claimed_tenant_id:
            tenant_id = claimed_tenant_id
            email = cast(str | None, claims.get("email"))
            permission_principal_token = make_email_permission_token(email) if email else None
            permission_audience = cast(str | None, claims.get("permission_audience"))
        else:
            # Don't return error yet, try API key
            logger.error("Internal JWT missing tenant_id claim", claims=claims)

    # 2. If not a valid JWT, try API key
    if not tenant_id:
        try:
            tenant_id = await verify_api_key(token)
        except Exception as e:
            logger.error("API key verification failed", error=str(e))

    if not tenant_id:
        return (
            None,
            JSONResponse(
                {"error": "Invalid API key or JWT"},
                status_code=401,
            ),
        )

    return AuthenticatedReqDetails(
        tenant_id=tenant_id,
        permission_principal_token=permission_principal_token,
        permission_audience=permission_audience,
    ), None
