"""Utilities for upserting WorkOS users and memberships."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from src.utils.config import get_config_value
from src.utils.logging import get_logger

logger = get_logger(__name__)

WORKOS_BASE_URL = "https://api.workos.com/user_management"


@dataclass(slots=True)
class WorkOSUserUpsertResult:
    success: bool
    user_id: str | None = None
    email: str | None = None
    created: bool = False
    assigned: bool = False
    error: str | None = None


async def upsert_workos_user(
    *,
    email: str,
    organization_id: str,
    first_name: str | None = None,
    last_name: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> WorkOSUserUpsertResult:
    """Ensure a WorkOS user exists and is assigned to an organization.

    Args:
        email: User email address
        organization_id: WorkOS organization identifier
        first_name: Optional first name
        last_name: Optional last name
        client: Optional HTTP client (for testing)
    """

    api_key = get_config_value("WORKOS_API_KEY")
    if not api_key:
        return WorkOSUserUpsertResult(
            success=False,
            error="WORKOS_API_KEY not configured",
        )

    owned_client = False
    if client is None:
        client = httpx.AsyncClient(base_url=WORKOS_BASE_URL, timeout=10)
        owned_client = True

    def _base_headers() -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        }

    try:
        headers = _base_headers()

        # Step 1: lookup user by email
        response = await client.get("/users", headers=headers, params={"email": email, "limit": 1})
        if response.status_code != 200:
            logger.error(
                "WorkOS user lookup failed",
                status=response.status_code,
                body=response.text,
            )
            return WorkOSUserUpsertResult(
                success=False,
                error=f"WorkOS user lookup failed ({response.status_code})",
            )

        data = response.json()
        users = data.get("data", []) if isinstance(data, dict) else []
        user = users[0] if users else None
        created = False

        # Step 2: create if missing
        if not user:
            payload = {"email": email}
            if first_name:
                payload["first_name"] = first_name
            if last_name:
                payload["last_name"] = last_name
            response = await client.post("/users", headers=_base_headers(), json=payload)
            if response.status_code != 201:
                logger.error(
                    "WorkOS user creation failed",
                    status=response.status_code,
                    body=response.text,
                )
                return WorkOSUserUpsertResult(
                    success=False,
                    error=f"Failed to create WorkOS user ({response.status_code})",
                )
            user = response.json()
            created = True

        user_id = user.get("id") if isinstance(user, dict) else None
        if not user_id:
            return WorkOSUserUpsertResult(
                success=False,
                error="WorkOS user response missing id",
            )

        # Step 3: check membership
        response = await client.get(
            "/organization_memberships",
            headers=_base_headers(),
            params={"user_id": user_id, "organization_id": organization_id},
        )
        if response.status_code != 200:
            logger.error(
                "WorkOS membership lookup failed",
                status=response.status_code,
                body=response.text,
            )
            return WorkOSUserUpsertResult(
                success=False,
                error=f"WorkOS membership lookup failed ({response.status_code})",
            )

        memberships = response.json().get("data", [])
        assigned = any(
            m.get("user_id") == user_id
            and m.get("organization_id") == organization_id
            and m.get("status") == "active"
            for m in memberships
        )

        if not assigned:
            response = await client.post(
                "/organization_memberships",
                headers=_base_headers(),
                json={
                    "user_id": user_id,
                    "organization_id": organization_id,
                    "role_slug": "member",
                },
            )
            if response.status_code not in {200, 201}:
                logger.error(
                    "WorkOS membership creation failed",
                    status=response.status_code,
                    body=response.text,
                )
                return WorkOSUserUpsertResult(
                    success=False,
                    error=f"Failed to assign WorkOS user to organization ({response.status_code})",
                    created=created,
                )
            assigned = True

        return WorkOSUserUpsertResult(
            success=True,
            user_id=user_id,
            email=user.get("email") if isinstance(user, dict) else email,
            created=created,
            assigned=assigned,
        )
    except httpx.HTTPError as exc:
        logger.error("WorkOS user upsert HTTP error", error=str(exc))
        return WorkOSUserUpsertResult(success=False, error=str(exc))
    finally:
        if owned_client:
            await client.aclose()
