"""
Custom exceptions for job processing.
"""


class ExtendVisibilityException(Exception):
    """
    Exception to signal that an SQS message's visibility timeout should be extended.

    This allows delayed processing of messages without requeuing them.
    """

    def __init__(
        self, visibility_timeout_seconds: int, message: str = "Message processing delayed"
    ):
        """
        Initialize the exception.

        Args:
            visibility_timeout_seconds: Number of seconds to extend visibility timeout
            message: Optional error message
        """
        self.visibility_timeout_seconds = visibility_timeout_seconds
        super().__init__(message)
