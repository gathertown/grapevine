"""Unit tests for the GongCallTransformer."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.gong import (
    GongCallArtifact,
    GongCallContent,
    GongCallDocument,
    GongCallMetadata,
    GongCallTranscriptArtifact,
    GongCallTranscriptContent,
    GongCallTransformer,
    GongCallUsersAccessArtifact,
    GongCallUsersAccessContent,
    GongPermissionProfileArtifact,
    GongPermissionProfileContent,
    GongPermissionProfileMetadata,
    GongPermissionProfileUsersArtifact,
    GongPermissionProfileUsersContent,
    GongPermissionProfileUsersMetadata,
    GongUserArtifact,
    GongUserContent,
    GongUserMetadata,
)


@pytest.fixture()
async def transformer() -> GongCallTransformer:
    return GongCallTransformer()


@pytest.fixture()
def user_lookup() -> dict[str, GongUserArtifact]:
    return {
        "user-1": GongUserArtifact(
            content=GongUserContent(id="user-1", emailAddress="owner@example.com"),
            metadata=GongUserMetadata(email="owner@example.com"),
            source_updated_at=datetime(2024, 1, 2, tzinfo=UTC),
        ),
        "user-2": GongUserArtifact(
            content=GongUserContent(id="user-2", emailAddress="participant@example.com"),
            metadata=GongUserMetadata(email="participant@example.com"),
            source_updated_at=datetime(2024, 1, 2, tzinfo=UTC),
        ),
    }


@pytest.fixture()
def call_artifact() -> GongCallArtifact:
    return GongCallArtifact(
        content=GongCallContent(
            meta_data={
                "title": "Weekly Sync",
                "url": "https://app.gong.com/calls/weekly-sync",
                "meetingUrl": "https://zoom.us/j/123456",
                "duration": 900000,
                "direction": "outbound",
                "language": "en",
                "media": "zoom",
                "system": "zoom",
                "scope": "company",
            },
            parties=[
                {
                    "id": "party-1",
                    "userId": "user-1",
                    "emailAddress": "owner@example.com",
                    "affiliation": "Internal",
                    "speakerId": "speaker-1",
                },
                {
                    "id": "party-2",
                    "userId": "user-2",
                    "affiliation": "External",
                    "speakerId": "speaker-2",
                },
            ],
        ),
        metadata=GongCallMetadata(
            call_id="call-1",
            workspace_id="ws-1",
            owner_user_id="user-1",
            is_private=True,
            explicit_access_user_ids=["user-2"],
            library_folder_ids=["folder-1"],
        ),
        source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


@pytest.fixture()
def transcript_artifact() -> GongCallTranscriptArtifact:
    return GongCallTranscriptArtifact(
        content=GongCallTranscriptContent(
            call_id="call-1",
            transcript=[
                {
                    "index": 0,
                    "speakerId": "speaker-1",
                    "start": 0,
                    "end": 5000,
                    "text": "Hello team",
                },
                {
                    "index": 1,
                    "speakerId": "speaker-2",
                    "start": 5000,
                    "end": 10000,
                    "text": "Thanks for joining",
                },
            ],
        ),
        source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


@pytest.fixture()
def access_artifact() -> GongCallUsersAccessArtifact:
    return GongCallUsersAccessArtifact(
        content=GongCallUsersAccessContent(
            call_id="call-1",
            users=[{"id": "user-2"}],
        ),
        source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
    )


class TestGongCallTransformer:
    @pytest.mark.asyncio
    async def test_create_document_builds_expected_data(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        transcript_artifact: GongCallTranscriptArtifact,
        access_artifact: GongCallUsersAccessArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        # Set tenant_id required for workspace selection check
        transformer._tenant_id = "test-tenant"
        document = await transformer._create_document(
            call_artifact,
            transcript_artifact,
            access_artifact,
            user_lookup,
            profile_lookup={},
            profile_user_lookup={},
        )

        assert isinstance(document, GongCallDocument)
        assert document.raw_data["call_id"] == "call-1"
        assert document.permission_policy == "private"
        assert set(document.permission_allowed_tokens or []) == {
            "e:owner@example.com",
            "e:participant@example.com",
        }
        assert document.raw_data["transcript_segment_count"] == 2
        assert document.raw_data["transcript_chunk_count"] == 1

    def test_build_transcript_chunks_handles_missing_transcript(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        lines, chunks = transformer._build_transcript_chunks(
            call_artifact,
            transcript_artifact=None,
            user_lookup=user_lookup,
        )

        assert lines == []
        assert chunks == []

    def test_build_transcript_chunks_respects_chunk_size(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        long_transcript = GongCallTranscriptArtifact(
            content=GongCallTranscriptContent(
                call_id="call-1",
                transcript=[
                    {
                        "index": idx,
                        "speakerId": "speaker-1",
                        "start": idx * 1000,
                        "end": (idx + 1) * 1000,
                        "text": f"Segment {idx}",
                    }
                    for idx in range(5)
                ],
            ),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        lines, chunks = transformer._build_transcript_chunks(
            call_artifact,
            transcript_artifact=long_transcript,
            user_lookup=user_lookup,
            chunk_size=40,
        )

        assert len(lines) == 5
        # chunk_size small to force grouping
        assert len(chunks) > 1
        assert all(chunk["call_id"] == "call-1" for chunk in chunks)

    @pytest.mark.asyncio
    async def test_build_permissions_splits_internal_external(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        access_artifact: GongCallUsersAccessArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        # Set tenant_id required for workspace selection check
        transformer._tenant_id = "test-tenant"
        permissions = await transformer._build_permissions(
            call_artifact,
            access_artifact,
            user_lookup,
            profile_lookup={},
            profile_user_lookup={},
        )

        assert permissions["owner_email"] == "owner@example.com"
        assert permissions["participant_emails_internal"] == [
            "owner@example.com",
            "participant@example.com",
        ]
        assert permissions["participant_emails_external"] == ["participant@example.com"]
        assert permissions["explicit_access_emails"] == ["participant@example.com"]
        assert permissions["permission_policy"] == "private"

    @pytest.mark.asyncio
    async def test_build_permissions_handles_public_call(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        call_artifact.metadata.is_private = False
        # Set tenant_id required for workspace selection check
        transformer._tenant_id = "test-tenant"

        permissions = await transformer._build_permissions(
            call_artifact,
            access_artifact=None,
            user_lookup=user_lookup,
            profile_lookup={},
            profile_user_lookup={},
        )

        assert permissions["permission_policy"] == "tenant"
        assert permissions["permission_allowed_tokens"] is None

    def test_build_manager_hierarchy(self, transformer: GongCallTransformer) -> None:
        """Test manager hierarchy building functionality."""
        users = [
            GongUserArtifact(
                content=GongUserContent(
                    id="user-1",
                    emailAddress="user1@example.com",
                    managerId="manager-1",
                ),
                metadata=GongUserMetadata(),
                source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            GongUserArtifact(
                content=GongUserContent(
                    id="user-2",
                    emailAddress="user2@example.com",
                    managerId="manager-1",
                ),
                metadata=GongUserMetadata(),
                source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
            ),
            GongUserArtifact(
                content=GongUserContent(
                    id="manager-1",
                    emailAddress="manager@example.com",
                    managerId=None,
                ),
                metadata=GongUserMetadata(),
                source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]

        hierarchy = transformer._build_manager_hierarchy(users)

        assert "manager-1" in hierarchy
        assert set(hierarchy["manager-1"]) == {"user-1", "user-2"}
        assert len(hierarchy) == 1  # Only one manager

    def test_build_manager_hierarchy_no_managers(self, transformer: GongCallTransformer) -> None:
        """Test manager hierarchy building with no managers."""
        users = [
            GongUserArtifact(
                content=GongUserContent(
                    id="user-1",
                    emailAddress="user1@example.com",
                    managerId=None,
                ),
                metadata=GongUserMetadata(),
                source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
            ),
        ]

        hierarchy = transformer._build_manager_hierarchy(users)

        assert len(hierarchy) == 0

    def test_can_user_access_call_all_permission(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        """Test 'all' permission level allows access to all non-private calls."""
        # Create a profile with 'all' permission
        profile_artifact = GongPermissionProfileArtifact(
            content=GongPermissionProfileContent(
                id="profile-1",
                name="All Access Profile",
                callsAccess={"permissionLevel": "all"},  # type: ignore[call-arg] # TODO: remove allow="extra" and model this properly
            ),
            metadata=GongPermissionProfileMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_user_artifact = GongPermissionProfileUsersArtifact(
            content=GongPermissionProfileUsersContent(
                profile_id="profile-1",
                users=[{"id": "user-1"}],
            ),
            metadata=GongPermissionProfileUsersMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_lookup = {"profile-1": profile_artifact}
        profile_user_lookup = {"profile-1": profile_user_artifact}

        # Test with non-private call
        call_artifact.metadata.is_private = False
        user = user_lookup["user-1"]

        can_access = transformer._can_user_access_call(
            user, call_artifact, profile_lookup, profile_user_lookup, {}, set(), user_lookup
        )

        assert can_access is True

    def test_can_user_access_call_own_permission(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        """Test 'own' permission level allows access to calls user participated in."""
        # Create a profile with 'own' permission
        profile_artifact = GongPermissionProfileArtifact(
            content=GongPermissionProfileContent(
                id="profile-1",
                name="Own Access Profile",
                callsAccess={"permissionLevel": "own"},  # type: ignore[call-arg] # TODO: remove allow="extra" and model this properly
            ),
            metadata=GongPermissionProfileMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_user_artifact = GongPermissionProfileUsersArtifact(
            content=GongPermissionProfileUsersContent(
                profile_id="profile-1",
                users=[{"id": "user-1"}],
            ),
            metadata=GongPermissionProfileUsersMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_lookup = {"profile-1": profile_artifact}
        profile_user_lookup = {"profile-1": profile_user_artifact}

        user = user_lookup["user-1"]

        can_access = transformer._can_user_access_call(
            user,
            call_artifact,
            profile_lookup,
            profile_user_lookup,
            {},
            {"owner@example.com", "participant@example.com"},
            user_lookup,
        )

        assert can_access is True  # user-1 is the owner

    def test_can_user_access_call_managers_team_permission(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        """Test 'managers-team' permission level with teamLeadIds."""
        # Create a profile with 'managers-team' permission
        profile_artifact = GongPermissionProfileArtifact(
            content=GongPermissionProfileContent(
                id="profile-1",
                name="Managers Team Profile",
                callsAccess={"permissionLevel": "managers-team", "teamLeadIds": ["user-2"]},  # type: ignore[call-arg] # TODO: remove allow="extra" and model this properly
            ),
            metadata=GongPermissionProfileMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_user_artifact = GongPermissionProfileUsersArtifact(
            content=GongPermissionProfileUsersContent(
                profile_id="profile-1",
                users=[{"id": "user-1"}],
            ),
            metadata=GongPermissionProfileUsersMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_lookup = {"profile-1": profile_artifact}
        profile_user_lookup = {"profile-1": profile_user_artifact}

        # Add user-2 to user lookup for this test
        user2_artifact = GongUserArtifact(
            content=GongUserContent(
                id="user-2",
                emailAddress="user2@example.com",
            ),
            metadata=GongUserMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
        extended_user_lookup = {**user_lookup, "user-2": user2_artifact}

        user = extended_user_lookup["user-1"]

        # Add user-2 as an internal participant for this test
        call_artifact.content.parties[1]["affiliation"] = "Internal"
        call_artifact.content.parties[1]["emailAddress"] = "user2@example.com"

        # Test with call that has user-2 as participant
        can_access = transformer._can_user_access_call(
            user,
            call_artifact,
            profile_lookup,
            profile_user_lookup,
            {},
            {"user2@example.com"},
            extended_user_lookup,
        )

        assert can_access is True  # user-2 is in teamLeadIds

    def test_can_user_access_call_report_chain_permission(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        """Test 'report-to-them' permission level with manager hierarchy."""
        # Create users with manager hierarchy
        manager_user = GongUserArtifact(
            content=GongUserContent(
                id="manager-1",
                emailAddress="manager@example.com",
                managerId=None,
            ),
            metadata=GongUserMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        report_user = GongUserArtifact(
            content=GongUserContent(
                id="report-1",
                emailAddress="report@example.com",
                managerId="manager-1",
            ),
            metadata=GongUserMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        extended_user_lookup = {
            "manager-1": manager_user,
            "report-1": report_user,
            **user_lookup,
        }

        # Create a profile with 'report-to-them' permission
        profile_artifact = GongPermissionProfileArtifact(
            content=GongPermissionProfileContent(
                id="profile-1",
                name="Report Chain Profile",
                callsAccess={"permissionLevel": "report-to-them"},  # type: ignore[call-arg] # TODO: remove allow="extra" and model this properly
            ),
            metadata=GongPermissionProfileMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_user_artifact = GongPermissionProfileUsersArtifact(
            content=GongPermissionProfileUsersContent(
                profile_id="profile-1",
                users=[{"id": "manager-1"}],
            ),
            metadata=GongPermissionProfileUsersMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_lookup = {"profile-1": profile_artifact}
        profile_user_lookup = {"profile-1": profile_user_artifact}

        manager = extended_user_lookup["manager-1"]
        hierarchy = {"manager-1": ["report-1"]}

        # Add report-1 as an internal participant for this test
        call_artifact.content.parties.append(
            {
                "id": "party-3",
                "userId": "report-1",
                "emailAddress": "report@example.com",
                "affiliation": "Internal",
                "speakerId": "speaker-3",
            }
        )

        # Test with call that has report-1 as participant
        can_access = transformer._can_user_access_call(
            manager,
            call_artifact,
            profile_lookup,
            profile_user_lookup,
            hierarchy,
            {"report@example.com"},
            extended_user_lookup,
        )

        assert can_access is True  # manager can see calls with their reports

    def test_can_user_access_call_none_permission(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        """Test 'none' permission level denies access."""
        # Create a profile with 'none' permission
        profile_artifact = GongPermissionProfileArtifact(
            content=GongPermissionProfileContent(
                id="profile-1",
                name="No Access Profile",
                callsAccess={"permissionLevel": "none"},  # type: ignore[call-arg] # TODO: remove allow="extra" and model this properly
            ),
            metadata=GongPermissionProfileMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_user_artifact = GongPermissionProfileUsersArtifact(
            content=GongPermissionProfileUsersContent(
                profile_id="profile-1",
                users=[{"id": "user-1"}],
            ),
            metadata=GongPermissionProfileUsersMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_lookup = {"profile-1": profile_artifact}
        profile_user_lookup = {"profile-1": profile_user_artifact}

        user = user_lookup["user-1"]

        can_access = transformer._can_user_access_call(
            user, call_artifact, profile_lookup, profile_user_lookup, {}, set(), user_lookup
        )

        assert can_access is False  # 'none' permission denies access

    def test_can_user_access_call_no_profile(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        """Test user with no permission profile cannot access calls."""
        user = user_lookup["user-1"]

        can_access = transformer._can_user_access_call(
            user, call_artifact, {}, {}, {}, set(), user_lookup
        )

        assert can_access is False  # No profile means no access

    def test_can_user_access_call_private_call_all_permission(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        """Test 'all' permission level denies access to private calls."""
        # Create a profile with 'all' permission
        profile_artifact = GongPermissionProfileArtifact(
            content=GongPermissionProfileContent(
                id="profile-1",
                name="All Access Profile",
                callsAccess={"permissionLevel": "all"},  # type: ignore[call-arg] # TODO: remove allow="extra" and model this properly
            ),
            metadata=GongPermissionProfileMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_user_artifact = GongPermissionProfileUsersArtifact(
            content=GongPermissionProfileUsersContent(
                profile_id="profile-1",
                users=[{"id": "user-1"}],
            ),
            metadata=GongPermissionProfileUsersMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_lookup = {"profile-1": profile_artifact}
        profile_user_lookup = {"profile-1": profile_user_artifact}

        # Test with private call
        call_artifact.metadata.is_private = True
        user = user_lookup["user-1"]

        can_access = transformer._can_user_access_call(
            user, call_artifact, profile_lookup, profile_user_lookup, {}, set(), user_lookup
        )

        assert can_access is False  # 'all' permission doesn't include private calls

    @pytest.mark.asyncio
    async def test_build_permissions_with_real_profile_data(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        """Test permission building with realistic profile data."""
        # Create realistic permission profiles
        all_profile = GongPermissionProfileArtifact(
            content=GongPermissionProfileContent(
                id="profile-all",
                name="All Access",
                callsAccess={"permissionLevel": "all"},  # type: ignore[call-arg] # TODO: remove allow="extra" and model this properly
            ),
            metadata=GongPermissionProfileMetadata(workspace_id="ws-1"),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        own_profile = GongPermissionProfileArtifact(
            content=GongPermissionProfileContent(
                id="profile-own",
                name="Own Access",
                callsAccess={"permissionLevel": "own"},  # type: ignore[call-arg] # TODO: remove allow="extra" and model this properly
            ),
            metadata=GongPermissionProfileMetadata(workspace_id="ws-1"),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        managers_team_profile = GongPermissionProfileArtifact(
            content=GongPermissionProfileContent(
                id="profile-managers-team",
                name="Managers Team",
                callsAccess={"permissionLevel": "managers-team", "teamLeadIds": ["user-2"]},  # type: ignore[call-arg] # TODO: remove allow="extra" and model this properly
            ),
            metadata=GongPermissionProfileMetadata(workspace_id="ws-1"),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        none_profile = GongPermissionProfileArtifact(
            content=GongPermissionProfileContent(
                id="profile-none",
                name="No Access",
                callsAccess={"permissionLevel": "none"},  # type: ignore[call-arg] # TODO: remove allow="extra" and model this properly
            ),
            metadata=GongPermissionProfileMetadata(workspace_id="ws-1"),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        # Create profile user mappings
        profile_user_artifact_all = GongPermissionProfileUsersArtifact(
            content=GongPermissionProfileUsersContent(
                profile_id="profile-all",
                users=[{"id": "user-1"}],
            ),
            metadata=GongPermissionProfileUsersMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_user_artifact_own = GongPermissionProfileUsersArtifact(
            content=GongPermissionProfileUsersContent(
                profile_id="profile-own",
                users=[{"id": "user-2"}],
            ),
            metadata=GongPermissionProfileUsersMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_user_artifact_managers = GongPermissionProfileUsersArtifact(
            content=GongPermissionProfileUsersContent(
                profile_id="profile-managers-team",
                users=[{"id": "user-3"}],
            ),
            metadata=GongPermissionProfileUsersMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_user_artifact_none = GongPermissionProfileUsersArtifact(
            content=GongPermissionProfileUsersContent(
                profile_id="profile-none",
                users=[{"id": "user-4"}],
            ),
            metadata=GongPermissionProfileUsersMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        profile_lookup = {
            "profile-all": all_profile,
            "profile-own": own_profile,
            "profile-managers-team": managers_team_profile,
            "profile-none": none_profile,
        }

        profile_user_lookup = {
            "profile-all": profile_user_artifact_all,
            "profile-own": profile_user_artifact_own,
            "profile-managers-team": profile_user_artifact_managers,
            "profile-none": profile_user_artifact_none,
        }

        # Create access artifact with users who should have access
        access_artifact = GongCallUsersAccessArtifact(
            content=GongCallUsersAccessContent(
                call_id="call-1",
                users=[
                    {"id": "user-1"},  # Has 'all' permission
                    {"id": "user-2"},  # Has 'own' permission and is participant
                    {"id": "user-3"},  # Has 'managers-team' permission
                ],
            ),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        # Add user-2 and user-3 to user lookup for this test
        user2_artifact = GongUserArtifact(
            content=GongUserContent(
                id="user-2",
                emailAddress="user2@example.com",
            ),
            metadata=GongUserMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        user3_artifact = GongUserArtifact(
            content=GongUserContent(
                id="user-3",
                emailAddress="user3@example.com",
            ),
            metadata=GongUserMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        user4_artifact = GongUserArtifact(
            content=GongUserContent(
                id="user-4",
                emailAddress="user4@example.com",
            ),
            metadata=GongUserMetadata(),
            source_updated_at=datetime(2024, 1, 1, tzinfo=UTC),
        )

        extended_user_lookup = {
            **user_lookup,
            "user-2": user2_artifact,
            "user-3": user3_artifact,
            "user-4": user4_artifact,
        }

        # Add user-2 as internal participant
        call_artifact.content.parties[1]["affiliation"] = "Internal"
        call_artifact.content.parties[1]["emailAddress"] = "user2@example.com"

        # Set tenant_id required for workspace selection check
        transformer._tenant_id = "test-tenant"

        permissions = await transformer._build_permissions(
            call_artifact,
            access_artifact,
            extended_user_lookup,
            profile_lookup,
            profile_user_lookup,
        )

        # Should include users with access through profiles + participants + explicit access
        # Based on the logging, we can see:
        # - owner@example.com and user2@example.com are participants (always included)
        # - user-3 has managers-team permission and user-2 is in teamLeadIds, so they get access
        # - user-1 has 'all' permission but call is private, so no access
        # - user-4 has 'none' permission, so no access
        expected_emails = {
            "owner@example.com",  # Internal participant (owner)
            "user2@example.com",  # Internal participant
            "user3@example.com",  # Has managers-team permission with user-2 in teamLeadIds
        }

        assert permissions["permission_policy"] == "private"
        assert set(permissions["permission_allowed_tokens"]) == {
            f"e:{email}" for email in sorted(expected_emails)
        }

    @pytest.mark.asyncio
    async def test_transform_artifacts_fetches_and_creates_documents(
        self,
        transformer: GongCallTransformer,
        call_artifact: GongCallArtifact,
        transcript_artifact: GongCallTranscriptArtifact,
        access_artifact: GongCallUsersAccessArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> None:
        repo_mock = AsyncMock()
        repo_mock.get_artifacts_by_entity_ids.side_effect = [
            [call_artifact],
            [transcript_artifact],
            [access_artifact],
        ]
        repo_mock.get_artifacts.side_effect = [
            list(user_lookup.values()),  # For GongUserArtifact
            [],  # For GongPermissionProfileArtifact (empty for test)
            [],  # For GongPermissionProfileUsersArtifact (empty for test)
        ]

        with patch(
            "connectors.gong.gong_call_transformer.ArtifactRepository",
            return_value=repo_mock,
        ):
            documents = await transformer.transform_artifacts(
                ["gong_call_call-1"],
                MagicMock(),
            )

        assert len(documents) == 1
        assert documents[0].raw_data["call_id"] == "call-1"
