from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Discriminator, Field, Tag


class FireFliesTooManyRequestsErrorMetadata(BaseModel):
    # received in epoch time in milliseconds
    retry_after: int = Field(alias="retryAfter")


class FirefliesTooManyRequestsErrorExtensions(BaseModel):
    code: Literal["too_many_requests"]
    status: Literal[429]
    metadata: FireFliesTooManyRequestsErrorMetadata


class FirefliesTooManyRequestsErrorRes(BaseModel):
    message: str
    code: Literal["too_many_requests"]
    extensions: FirefliesTooManyRequestsErrorExtensions


class FirefliesDefaultError(BaseModel):
    message: str
    code: str
    extensions: dict[str, Any] | None = None


handled_error_codes = {"too_many_requests"}
fallback_error_code = "default"


# Handle dicts and model instances
def fireflies_error_discriminator(
    v: Union[dict[str, Any], "FirefliesResError"],
) -> str:
    error_code = v.get("code") if isinstance(v, dict) else v.code

    if error_code in handled_error_codes:
        return error_code

    return fallback_error_code


FirefliesResError = Annotated[
    Annotated[FirefliesTooManyRequestsErrorRes, Tag("too_many_requests")]
    | Annotated[FirefliesDefaultError, Tag("default")],
    Discriminator(fireflies_error_discriminator),
]


class FirefliesGraphqlException(Exception):
    def __init__(self, errors: list[FirefliesResError]) -> None:
        self.errors = errors
        messages = [error.message for error in errors]
        super().__init__(f"Fireflies GraphQL errors: {messages}")


class FirefliesObjectNotFoundException(FirefliesGraphqlException):
    pass
