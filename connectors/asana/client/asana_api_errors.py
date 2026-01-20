from connectors.asana.client.asana_api_models import AsanaEventListErrorRes


class AsanaApiServiceAccountOnlyError(Exception):
    """
    Exception raised when the Asana API returns an error indicating that only
    service accounts can access the requested resource.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)


class AsanaApiInvalidSyncTokenError(Exception):
    """
    Exception raised when the Asana API returns an invalid sync token error.
    Happens on the first sync or if the sync token is expired.
    """

    def __init__(self, res: AsanaEventListErrorRes) -> None:
        super().__init__()
        self.response = res


class AsanaApiPaymentRequiredError(Exception):
    """
    Exception raised when the Asana API returns a 402 Payment Required error.
    Happens when the tenant is on a free plan and tries to access premium features (aka search).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
