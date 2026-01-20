from datetime import UTC, datetime, timedelta

from pydantic import BaseModel


class AsanaOauthTokenRes(BaseModel):
    access_token: str
    expires_in: int


class AsanaOauthTokenPayload(BaseModel):
    access_token: str
    refresh_token: str
    access_token_expires_at: datetime

    def refresh(self, token_response: AsanaOauthTokenRes) -> "AsanaOauthTokenPayload":
        """
        Return a new AsanaOauthTokenPayload with updated access token info.
        """
        now = datetime.now(UTC)
        access_token_expires_at = now + timedelta(seconds=token_response.expires_in)

        return AsanaOauthTokenPayload(
            access_token=token_response.access_token,
            refresh_token=self.refresh_token,
            access_token_expires_at=access_token_expires_at,
        )
