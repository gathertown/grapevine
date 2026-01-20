from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel


@dataclass
class DateWindow:
    start: datetime | None = None
    end: datetime | None = None

    def contains(self, dt: datetime) -> bool:
        if self.start and dt < self.start:
            return False

        return not (self.end and dt > self.end)

    def __str__(self) -> str:
        start_formatted = self.start.astimezone().isoformat() if self.start else "None"
        end_formatted = self.end.astimezone().isoformat() if self.end else "None"
        return f"DateWindow(start={start_formatted}, end={end_formatted})"


class ZendeskTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    refresh_token_expires_in: int
    expires_in: int | None = None


class ZendeskTokenPayload(BaseModel):
    """Persisted Zendesk Token info"""

    access_token: str
    refresh_token: str
    access_token_expires_at: datetime | None
    refresh_token_expires_at: datetime

    @classmethod
    def from_token_response(
        cls,
        token_response: ZendeskTokenResponse,
    ) -> "ZendeskTokenPayload":
        now = datetime.now(UTC)

        access_token_expires_at = None
        if token_response.expires_in:
            access_token_expires_at = now + timedelta(seconds=token_response.expires_in)

        refresh_token_expires_at = now + timedelta(seconds=token_response.refresh_token_expires_in)

        return ZendeskTokenPayload(
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            access_token_expires_at=access_token_expires_at,
            refresh_token_expires_at=refresh_token_expires_at,
        )


class ZendeskPageMetadata(BaseModel):
    # This can be missing in some responses
    after_cursor: str | None = None
    has_more: bool
