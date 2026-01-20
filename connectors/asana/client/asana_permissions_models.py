from typing import Annotated, Literal

from pydantic import Discriminator, Tag

from connectors.asana.client.asana_api_models import (
    AsanaIdentifiedResource,
    AsanaListRes,
    AsanaTeam,
    AsanaUser,
    get_prefixed_opt_fields,
)

AsanaProjectMember = Annotated[
    Annotated[AsanaUser, Tag("user")] | Annotated[AsanaTeam, Tag("team")],
    Discriminator("resource_type"),
]


class AsanaProjectMembership(AsanaIdentifiedResource, frozen=True):
    @classmethod
    def get_opt_fields(cls) -> list[str]:
        distinct_fields = {
            *get_prefixed_opt_fields(AsanaUser, "member"),
            *get_prefixed_opt_fields(AsanaTeam, "member"),
        }

        return super().get_opt_fields() + list(distinct_fields)

    resource_type: Literal["membership"]
    member: AsanaProjectMember


class AsanaTeamMembership(AsanaIdentifiedResource, frozen=True):
    @classmethod
    def get_opt_fields(cls) -> list[str]:
        return super().get_opt_fields() + get_prefixed_opt_fields(AsanaUser, "user")

    resource_type: Literal["team_membership"]
    user: AsanaUser


class AsanaProjectMembershipListRes(AsanaListRes[AsanaProjectMembership]):
    pass


class AsanaTeamMembershipListRes(AsanaListRes[AsanaTeamMembership]):
    pass
