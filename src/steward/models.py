import secrets
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TenantRow:
    id: str
    state: str
    error_message: str | None
    provisioned_at: datetime | None
    created_at: datetime
    updated_at: datetime
    workos_org_id: str
    deleted_at: datetime | None
    trial_start_at: datetime | None
    source: str | None


@dataclass
class TenantCredentials:
    """Tenant credentials and resource identifiers.

    PostgreSQL credentials (db_name, db_rw_user, db_rw_pass) are stored in SSM.
    """

    tenant_id: str
    db_name: str = field(default="")
    db_rw_user: str = field(default="")
    db_rw_pass: str = field(default_factory=lambda: secrets.token_urlsafe(32))  # noqa: S303

    def __post_init__(self):
        if not self.db_name:
            self.db_name = f"db_{self.tenant_id}"
        if not self.db_rw_user:
            self.db_rw_user = f"{self.tenant_id}_app_rw"
