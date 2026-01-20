"""Transformer for Gong call artifacts into documents."""

import json
from typing import Any

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.doc_ids import get_gong_call_doc_id
from connectors.base.document_source import DocumentSource
from connectors.gong.gong_artifacts import (
    GongCallArtifact,
    GongCallTranscriptArtifact,
    GongCallUsersAccessArtifact,
    GongPermissionProfileArtifact,
    GongPermissionProfileUsersArtifact,
    GongUserArtifact,
)
from connectors.gong.gong_call_document import GongCallDocument
from src.ingest.repositories import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore
from src.utils.logging import get_logger
from src.utils.tenant_config import get_tenant_config_value

logger = get_logger(__name__)


async def get_selected_workspaces(tenant_id: str | None) -> str | list[str]:
    """Get selected workspace IDs from config, defaulting to 'all'.

    Args:
        tenant_id: Tenant ID to load config for

    Returns:
        "all", "none", or list of workspace IDs
    """
    if not tenant_id:
        # If no tenant_id provided, default to "all" for backward compatibility
        return "all"

    try:
        config_value = await get_tenant_config_value("GONG_SELECTED_WORKSPACE_IDS", tenant_id)

        logger.debug(
            "Retrieved GONG_SELECTED_WORKSPACE_IDS from config",
            tenant_id=tenant_id,
            config_value=config_value,
            config_value_type=type(config_value).__name__ if config_value is not None else "None",
        )

        if not config_value:
            # Not configured - default to "all" for backward compatibility
            logger.info(
                "No GONG_SELECTED_WORKSPACE_IDS configured, defaulting to 'all'",
                tenant_id=tenant_id,
            )
            return "all"

        if config_value == "all" or config_value == "none":
            logger.info(
                f"GONG_SELECTED_WORKSPACE_IDS is '{config_value}'",
                tenant_id=tenant_id,
                value=config_value,
            )
            return config_value

        # Try to parse as JSON array
        try:
            parsed = json.loads(config_value)
            if isinstance(parsed, list):
                logger.info(
                    "Parsed GONG_SELECTED_WORKSPACE_IDS as array",
                    tenant_id=tenant_id,
                    workspace_count=len(parsed),
                    workspaces=parsed,
                )
                return parsed
            else:
                logger.warning(
                    "GONG_SELECTED_WORKSPACE_IDS parsed but not a list, defaulting to 'all'",
                    tenant_id=tenant_id,
                    parsed_value=parsed,
                    parsed_type=type(parsed).__name__,
                )
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                "Failed to parse GONG_SELECTED_WORKSPACE_IDS, defaulting to 'all'",
                tenant_id=tenant_id,
                value=config_value,
                error=str(e),
            )

        return "all"
    except Exception as e:
        logger.error(
            "Error loading workspace selection config, defaulting to 'all'",
            tenant_id=tenant_id,
            error=str(e),
        )
        return "all"


class GongCallTransformer(BaseTransformer[GongCallDocument]):
    """Transform Gong call artifacts into documents."""

    def __init__(self) -> None:
        super().__init__(DocumentSource.GONG)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool, tenant_id: str | None = None
    ) -> list[GongCallDocument]:
        if not entity_ids:
            logger.warning("No entity_ids provided to GongCallTransformer")
            return []

        repo = ArtifactRepository(readonly_db_pool)

        # Store tenant_id for use in permission calculation
        self._tenant_id = tenant_id

        # Log workspace selection configuration
        selected_workspaces = await get_selected_workspaces(tenant_id)
        logger.info(
            "Gong workspace selection config for tenant",
            tenant_id=tenant_id,
            selected_workspaces=selected_workspaces,
            selected_workspaces_type=type(selected_workspaces).__name__,
            selected_workspaces_count=len(selected_workspaces)
            if isinstance(selected_workspaces, list)
            else None,
        )

        call_artifacts = await repo.get_artifacts_by_entity_ids(GongCallArtifact, entity_ids)
        logger.info(
            "Loaded %s Gong call artifacts for %s entity IDs",
            len(call_artifacts),
            len(entity_ids),
        )

        call_ids = [artifact.metadata.call_id for artifact in call_artifacts]

        transcript_ids = [f"gong_call_transcript_{call_id}" for call_id in call_ids]
        access_ids = [f"gong_call_users_access_{call_id}" for call_id in call_ids]

        transcript_artifacts = await repo.get_artifacts_by_entity_ids(
            GongCallTranscriptArtifact, transcript_ids, apply_exclusions=False
        )
        access_artifacts = await repo.get_artifacts_by_entity_ids(
            GongCallUsersAccessArtifact, access_ids, apply_exclusions=False
        )

        user_artifacts = await repo.get_artifacts(GongUserArtifact)

        # Fetch permission profile data for proper access evaluation
        profile_artifacts = await repo.get_artifacts(GongPermissionProfileArtifact)
        profile_user_artifacts = await repo.get_artifacts(GongPermissionProfileUsersArtifact)

        transcript_lookup = {
            artifact.content.call_id: artifact for artifact in transcript_artifacts
        }
        access_lookup = {artifact.content.call_id: artifact for artifact in access_artifacts}
        user_lookup = {artifact.content.id: artifact for artifact in user_artifacts}
        profile_lookup = {artifact.content.id: artifact for artifact in profile_artifacts}
        profile_user_lookup = {
            artifact.content.profile_id: artifact for artifact in profile_user_artifacts
        }

        logger.debug(f"Loaded {len(transcript_lookup)} transcript artifacts")
        logger.debug(f"Loaded {len(access_lookup)} access artifacts")
        logger.debug(f"Loaded {len(user_lookup)} user artifacts")
        logger.debug(f"Loaded {len(profile_lookup)} profile artifacts")
        logger.debug(f"Loaded {len(profile_user_lookup)} profile user artifacts")

        logger.debug(f"Loaded {profile_user_lookup} lookup object")

        documents: list[GongCallDocument] = []
        counter: ErrorCounter = {}
        skipped = 0

        for artifact in call_artifacts:
            with record_exception_and_ignore(
                logger,
                f"Failed to transform Gong call artifact {artifact.entity_id}",
                counter,
            ):
                transcript_artifact = transcript_lookup.get(artifact.metadata.call_id)
                access_artifact = access_lookup.get(artifact.metadata.call_id)

                document = await self._create_document(
                    artifact,
                    transcript_artifact,
                    access_artifact,
                    user_lookup,
                    profile_lookup,
                    profile_user_lookup,
                )
                if document:
                    documents.append(document)
                else:
                    skipped += 1

        logger.info(
            "Gong call transformation complete: successful=%s failed=%s skipped=%s produced=%s",
            counter.get("successful", 0),
            counter.get("failed", 0),
            skipped,
            len(documents),
        )
        return documents

    async def _is_workspace_selected(self, workspace_id: str | None) -> bool:
        """Check if a workspace is selected for tenant-level visibility.

        Args:
            workspace_id: Workspace ID to check

        Returns:
            True if workspace is selected for tenant-level visibility, False otherwise
        """
        if not workspace_id:
            # No workspace ID - default to not selected
            logger.debug("No workspace_id provided, defaulting to not selected")
            return False

        selected_workspaces = await get_selected_workspaces(self._tenant_id)

        if selected_workspaces == "all":
            # All workspaces selected
            logger.debug(
                f"Workspace {workspace_id} is selected (all workspaces selected)",
                workspace_id=workspace_id,
            )
            return True
        elif selected_workspaces == "none":
            # No workspaces selected
            logger.debug(
                f"Workspace {workspace_id} is not selected (no workspaces selected)",
                workspace_id=workspace_id,
            )
            return False
        elif isinstance(selected_workspaces, list):
            # Check if this workspace is in the selected list
            is_selected = workspace_id in selected_workspaces
            logger.debug(
                f"Workspace {workspace_id} selection check against list",
                workspace_id=workspace_id,
                selected_workspaces=selected_workspaces,
                is_selected=is_selected,
            )
            return is_selected
        else:
            # Unexpected value - default to not selected
            logger.warning(
                "Unexpected selected_workspaces value, defaulting to not selected",
                value=selected_workspaces,
                value_type=type(selected_workspaces).__name__,
                workspace_id=workspace_id,
            )
            return False

    async def _create_document(
        self,
        call_artifact: GongCallArtifact,
        transcript_artifact: GongCallTranscriptArtifact | None,
        access_artifact: GongCallUsersAccessArtifact | None,
        user_lookup: dict[str, GongUserArtifact],
        profile_lookup: dict[str, GongPermissionProfileArtifact],
        profile_user_lookup: dict[str, GongPermissionProfileUsersArtifact],
    ) -> GongCallDocument | None:
        call_id = call_artifact.metadata.call_id
        document_id = get_gong_call_doc_id(call_id)

        transcript_lines, transcript_chunks = self._build_transcript_chunks(
            call_artifact,
            transcript_artifact,
            user_lookup,
        )

        permissions = await self._build_permissions(
            call_artifact, access_artifact, user_lookup, profile_lookup, profile_user_lookup
        )

        raw_data: dict[str, Any] = {
            "call_id": call_artifact.metadata.call_id,
            "workspace_id": call_artifact.metadata.workspace_id,
            "title": call_artifact.content.meta_data.get("title"),
            "url": call_artifact.content.meta_data.get("url"),
            "meeting_url": call_artifact.content.meta_data.get("meetingUrl"),
            "calendar_event_id": call_artifact.content.meta_data.get("calendarEventId"),
            "is_private": call_artifact.metadata.is_private,
            "owner_user_id": call_artifact.metadata.owner_user_id,
            "owner_email": permissions.get("owner_email"),
            "library_folder_ids": call_artifact.metadata.library_folder_ids,
            "explicit_access_user_ids": call_artifact.metadata.explicit_access_user_ids,
            "explicit_access_emails": permissions.get("explicit_access_emails", []),
            "source_created_at": call_artifact.metadata.source_created_at,
            "source_updated_at": call_artifact.source_updated_at.isoformat(),
            "duration_ms": call_artifact.content.meta_data.get("duration"),
            "language": call_artifact.content.meta_data.get("language"),
            "media": call_artifact.content.meta_data.get("media"),
            "direction": call_artifact.content.meta_data.get("direction"),
            "system": call_artifact.content.meta_data.get("system"),
            "scope": call_artifact.content.meta_data.get("scope"),
            "participants": self._build_participants(call_artifact, user_lookup),
            "participant_emails_internal": permissions.get("participant_emails_internal", []),
            "participant_emails_external": permissions.get("participant_emails_external", []),
            "transcript_segment_count": len(transcript_artifact.content.transcript)
            if transcript_artifact
            else 0,
            "transcript_chunk_count": len(transcript_chunks),
            "transcript_lines": transcript_lines,
            "transcript_chunks": transcript_chunks,
        }

        document = GongCallDocument(
            id=document_id,
            raw_data=raw_data,
            source_updated_at=call_artifact.source_updated_at,
            permission_policy=permissions.get("permission_policy", "private"),
            permission_allowed_tokens=permissions.get("permission_allowed_tokens"),
        )

        return document

    async def _build_permissions(
        self,
        call_artifact: GongCallArtifact,
        access_artifact: GongCallUsersAccessArtifact | None,
        user_lookup: dict[str, GongUserArtifact],
        profile_lookup: dict[str, GongPermissionProfileArtifact],
        profile_user_lookup: dict[str, GongPermissionProfileUsersArtifact],
    ) -> dict[str, Any]:
        call_id = call_artifact.metadata.call_id
        logger.debug(f"Building permissions for Gong call {call_id}")

        owner_email = self._resolve_user_email(call_artifact.metadata.owner_user_id, user_lookup)

        internal_emails: set[str] = set()
        external_emails: set[str] = set()
        explicit_access_emails: list[str] = []

        # Build participant lists
        logger.debug(f"Processing {len(call_artifact.content.parties)} parties for call {call_id}")
        for party in call_artifact.content.parties:
            email = self._resolve_party_email(party, user_lookup)
            if email is None:
                logger.debug(f"Could not resolve email for party {party.get('id')}")
                continue
            affiliation = party.get("affiliation")
            email_lower = email.lower()
            if affiliation == "Internal":
                internal_emails.add(email_lower)
                logger.debug(f"Added internal participant: {email_lower}")
            elif affiliation == "External":
                external_emails.add(email_lower)
                logger.debug(f"Added external participant: {email_lower}")

        owner_lower: str | None = None
        if owner_email is not None:
            owner_lower = owner_email.lower()
            internal_emails.add(owner_lower)
            logger.debug(f"Added call owner: {owner_lower}")

        # Build explicit access list
        logger.debug(
            f"Processing {len(call_artifact.metadata.explicit_access_user_ids)} explicit access user IDs"
        )
        if call_artifact.metadata.explicit_access_user_ids:
            for user_id in call_artifact.metadata.explicit_access_user_ids:
                email_result = self._resolve_user_email(user_id, user_lookup)
                if email_result is None:
                    logger.debug(f"Could not resolve email for explicit access user {user_id}")
                    continue
                normalized_email = email_result.lower()
                explicit_access_emails.append(normalized_email)
                internal_emails.add(normalized_email)
                logger.debug(f"Added explicit access user: {normalized_email}")

        # Determine permission policy based on document specification:
        # - "tenant" only when call is in public library folder AND not private AND workspace is selected
        # - "private" otherwise
        library_folder_ids = call_artifact.metadata.library_folder_ids or []
        has_library_folder = bool(library_folder_ids)
        logger.debug(
            f"Call {call_id} library_folder_ids: {library_folder_ids} (has_library_folder: {has_library_folder})"
        )
        is_marked_private = bool(call_artifact.metadata.is_private)

        # Check if workspace is selected for tenant-level visibility
        call_workspace_id = call_artifact.metadata.workspace_id
        is_selected_workspace = await self._is_workspace_selected(call_workspace_id)

        permission_policy = (
            "tenant"
            if (has_library_folder and not is_marked_private and is_selected_workspace)
            else "private"
        )
        logger.info(
            f"Call {call_id} workspace selection check",
            call_id=call_id,
            workspace_id=call_workspace_id,
            is_selected_workspace=is_selected_workspace,
            has_library_folder=has_library_folder,
            is_marked_private=is_marked_private,
            permission_policy=permission_policy,
        )

        # For private calls, calculate allowed viewers by evaluating every workspace user
        # against their permission profile's permission level
        allowed_emails: set[str] = set()
        if permission_policy == "private":
            # Start with internal participants and explicit access (they always have access)
            allowed_emails.update(internal_emails)
            allowed_emails.update(explicit_access_emails)
            logger.debug(f"Initial allowed emails: {sorted(allowed_emails)}")

            # Evaluate users through workspace -> profiles -> users flow
            workspace_id = call_artifact.metadata.workspace_id
            if workspace_id:
                # Find all permission profile IDs for this workspace
                workspace_profile_ids = [
                    profile_id
                    for profile_id, profile in profile_lookup.items()
                    if profile.metadata.workspace_id == workspace_id
                ]
                logger.debug(
                    f"Found {len(workspace_profile_ids)} permission profiles for workspace {workspace_id}"
                )

                # Collect all users from these profiles
                workspace_users = []
                for profile_id in workspace_profile_ids:
                    if profile_id in profile_user_lookup:
                        profile_user_artifact = profile_user_lookup[profile_id]
                        logger.debug(
                            f"Profile {profile_id} has {len(profile_user_artifact.content.users)} users"
                        )
                        for profile_user in profile_user_artifact.content.users:
                            user_id_raw = profile_user.get("id")  # Changed from "userId" to "id"
                            if (
                                user_id_raw
                                and isinstance(user_id_raw, str)
                                and user_id_raw in user_lookup
                            ):
                                user_id = user_id_raw
                                workspace_users.append(user_lookup[user_id])
                                logger.debug(f"Added user {user_id} from profile {profile_id}")
                            else:
                                logger.debug(
                                    f"User {user_id_raw} not found in user_lookup or missing"
                                )

                logger.debug(
                    f"Evaluating permissions for {len(workspace_users)} users from workspace profiles in {workspace_id}"
                )

                # Build manager hierarchy for 'report-to-them' evaluation
                manager_hierarchy = self._build_manager_hierarchy(workspace_users)
                logger.debug(f"Built manager hierarchy with {len(manager_hierarchy)} managers")

                # Evaluate each user against their permission profile
                users_with_access = 0
                for user in workspace_users:
                    if self._can_user_access_call(
                        user,
                        call_artifact,
                        profile_lookup,
                        profile_user_lookup,
                        manager_hierarchy,
                        internal_emails,
                        user_lookup,
                    ):
                        user_email = self._resolve_user_email(user.content.id, user_lookup)
                        if user_email:
                            allowed_emails.add(user_email.lower())
                            users_with_access += 1

                logger.debug(
                    f"Permission evaluation complete: {users_with_access}/{len(workspace_users)} users granted access"
                )
                logger.debug(f"Final allowed emails: {sorted(allowed_emails)}")
            else:
                logger.warning(f"No workspace_id found for call {call_id}")

        # Convert to tokens for private policy
        allowed_tokens = None
        if permission_policy == "private":
            allowed_tokens = (
                [f"e:{email}" for email in sorted(allowed_emails)] if allowed_emails else None
            )
            logger.debug(
                f"Generated {len(allowed_tokens) if allowed_tokens else 0} permission tokens for call {call_id}"
            )
        else:
            logger.debug(f"Call {call_id} is public (tenant policy), no token restrictions")

        result = {
            "owner_email": owner_lower,
            "participant_emails_internal": sorted(internal_emails),
            "participant_emails_external": sorted(external_emails),
            "explicit_access_emails": sorted(set(explicit_access_emails)),
            "permission_policy": permission_policy,
            "permission_allowed_tokens": allowed_tokens,
        }
        logger.info(
            f"Permission building complete for call {call_id}: policy={permission_policy}, tokens={len(allowed_tokens) if allowed_tokens else 0}"
        )
        return result

    def _build_manager_hierarchy(self, users: list[GongUserArtifact]) -> dict[str, list[str]]:
        """Build a mapping of manager IDs to their direct reports."""
        hierarchy: dict[str, list[str]] = {}
        users_with_managers = 0

        for user in users:
            manager_id = user.content.manager_id
            if manager_id:
                if manager_id not in hierarchy:
                    hierarchy[manager_id] = []
                hierarchy[manager_id].append(user.content.id)
                users_with_managers += 1

        logger.debug(
            f"Built manager hierarchy: {len(hierarchy)} managers, {users_with_managers} users with managers"
        )
        return hierarchy

    def _can_user_access_call(
        self,
        user: GongUserArtifact,
        call_artifact: GongCallArtifact,
        profile_lookup: dict[str, GongPermissionProfileArtifact],
        profile_user_lookup: dict[str, GongPermissionProfileUsersArtifact],
        manager_hierarchy: dict[str, list[str]],
        internal_emails: set[str],
        user_lookup: dict[str, GongUserArtifact],
    ) -> bool:
        """Determine if a user can access a call based on their permission profile."""
        call_id = call_artifact.metadata.call_id
        user_id = user.content.id
        user_email = self._resolve_user_email(user_id, user_lookup)

        logger.debug(f"Evaluating access for user {user_id} ({user_email}) to call {call_id}")

        # Find the user's permission profile
        user_profile = self._get_user_permission_profile(user, profile_lookup, profile_user_lookup)

        if not user_profile:
            logger.debug(f"User {user_id} has no permission profile")
            return False

        # Get the callsAccess permission level from the profile
        # The profile content may have nested structure, so we need to extract it
        calls_access = self._get_calls_access_level(user_profile)
        if not calls_access:
            logger.debug(
                f"User {user_id} has no callsAccess configuration in profile {user_profile.content.id}"
            )
            return False

        permission_level = calls_access.get("permissionLevel", "none")
        logger.debug(f"User {user_id} has permission level: {permission_level}")

        # Evaluate based on permission level
        if permission_level == "all":
            # User can view every non-private call in the workspace
            result = not call_artifact.metadata.is_private
            logger.debug(
                f"User {user_id} 'all' permission check: {result} (call is private: {call_artifact.metadata.is_private})"
            )
            return result

        elif permission_level == "own":
            # User can view calls they participated in
            user_email = self._resolve_user_email(user.content.id, user_lookup)
            result = bool(user_email and user_email.lower() in internal_emails)
            logger.debug(
                f"User {user_id} 'own' permission check: {result} (user in participants: {user_email.lower() in internal_emails if user_email else False})"
            )
            return result

        elif permission_level == "managers-team":
            # User can view calls involving team members configured via teamLeadIds
            result = self._check_managers_team_access(
                user, call_artifact, calls_access, internal_emails, user_lookup
            )
            logger.debug(f"User {user_id} 'managers-team' permission check: {result}")
            return result

        elif permission_level == "report-to-them":
            # User can view calls involving the user or anyone in their report chain
            result = self._check_report_chain_access(
                user, call_artifact, manager_hierarchy, internal_emails, user_lookup
            )
            logger.debug(f"User {user_id} 'report-to-them' permission check: {result}")
            return result

        elif permission_level == "none":
            # User has no call access beyond explicit grants
            logger.debug(f"User {user_id} has 'none' permission level")
            return False

        logger.warning(f"User {user_id} has unknown permission level: {permission_level}")
        return False

    def _get_user_permission_profile(
        self,
        user: GongUserArtifact,
        profile_lookup: dict[str, GongPermissionProfileArtifact],
        profile_user_lookup: dict[str, GongPermissionProfileUsersArtifact],
    ) -> GongPermissionProfileArtifact | None:
        """Find the permission profile for a user."""
        user_id = user.content.id
        logger.debug(f"Looking for permission profile for user {user_id}")

        # Look through all profile user artifacts to find which profile this user belongs to
        for profile_id, profile_user_artifact in profile_user_lookup.items():
            logger.debug(
                f"Checking profile {profile_id} with {len(profile_user_artifact.content.users)} users"
            )
            for profile_user in profile_user_artifact.content.users:
                if profile_user.get("id") == user_id:  # Changed from "userId" to "id"
                    profile = profile_lookup.get(profile_id)
                    logger.debug(f"Found profile {profile_id} for user {user_id}")
                    return profile

        logger.debug(f"No permission profile found for user {user_id}")
        return None

    def _get_calls_access_level(
        self, profile: GongPermissionProfileArtifact
    ) -> dict[str, Any] | None:
        """Extract the callsAccess configuration from a permission profile."""
        profile_id = profile.content.id
        logger.debug(f"Extracting callsAccess from profile {profile_id}")

        # The profile content may have a nested structure with callsAccess
        # We need to look for it in the profile content
        profile_content = profile.content

        # Since the model uses extra="allow", callsAccess should be accessible as an attribute
        # or as a dict key if it's stored that way
        if hasattr(profile_content, "__dict__"):
            content_dict = profile_content.__dict__
            if "callsAccess" in content_dict:
                calls_access = content_dict["callsAccess"]
                logger.debug(
                    f"Found callsAccess in profile {profile_id} via __dict__: {calls_access}"
                )
                return calls_access

        # Try accessing as an attribute directly
        if hasattr(profile_content, "callsAccess"):
            calls_access = profile_content.callsAccess
            if calls_access:
                logger.debug(
                    f"Found callsAccess in profile {profile_id} via attribute: {calls_access}"
                )
                return calls_access

        # If it's a dict-like object, try accessing as key
        if hasattr(profile_content, "get") and callable(profile_content.get):
            calls_access = profile_content.get("callsAccess")
            if calls_access:
                logger.debug(f"Found callsAccess in profile {profile_id} via get(): {calls_access}")
                return calls_access

        logger.debug(f"No callsAccess found in profile {profile_id}")
        return None

    def _check_managers_team_access(
        self,
        user: GongUserArtifact,
        call_artifact: GongCallArtifact,
        calls_access: dict[str, Any],
        internal_emails: set[str],
        user_lookup: dict[str, GongUserArtifact],
    ) -> bool:
        """Check if user has access via managers-team permission level."""
        user_id = user.content.id
        call_id = call_artifact.metadata.call_id

        # Get teamLeadIds from the callsAccess configuration
        team_lead_ids = calls_access.get("teamLeadIds", [])
        logger.debug(f"User {user_id} managers-team check: teamLeadIds={team_lead_ids}")

        if not team_lead_ids:
            logger.debug(f"User {user_id} has no teamLeadIds configured")
            return False

        # Check if any participant in the call is in the user's team
        for party in call_artifact.content.parties:
            if party.get("affiliation") == "Internal":
                participant_user_id = party.get("userId")
                if participant_user_id in team_lead_ids:
                    participant_email = self._resolve_party_email(party, user_lookup)
                    logger.debug(
                        f"User {user_id} granted access via managers-team: participant {participant_user_id} ({participant_email}) is in teamLeadIds"
                    )
                    return True

        logger.debug(
            f"User {user_id} denied access via managers-team: no matching team members in call {call_id}"
        )
        return False

    def _check_report_chain_access(
        self,
        user: GongUserArtifact,
        call_artifact: GongCallArtifact,
        manager_hierarchy: dict[str, list[str]],
        internal_emails: set[str],
        user_lookup: dict[str, GongUserArtifact],
    ) -> bool:
        """Check if user has access via report-to-them permission level."""
        user_id = user.content.id
        call_id = call_artifact.metadata.call_id

        # Get all users in the report chain (user and their reports)
        report_chain = {user_id}
        self._get_reports_recursive(user_id, manager_hierarchy, report_chain)

        logger.debug(f"User {user_id} report chain: {report_chain}")

        # Check if any participant in the call is in the report chain
        for party in call_artifact.content.parties:
            if party.get("affiliation") == "Internal":
                participant_user_id = party.get("userId")
                if participant_user_id in report_chain:
                    participant_email = self._resolve_party_email(party, user_lookup)
                    logger.debug(
                        f"User {user_id} granted access via report-chain: participant {participant_user_id} ({participant_email}) is in report chain"
                    )
                    return True

        logger.debug(
            f"User {user_id} denied access via report-chain: no matching participants in call {call_id}"
        )
        return False

    def _get_reports_recursive(
        self, manager_id: str, hierarchy: dict[str, list[str]], reports: set[str]
    ) -> None:
        """Recursively get all direct and indirect reports of a manager."""
        if manager_id in hierarchy:
            direct_reports = hierarchy[manager_id]
            logger.debug(
                f"Manager {manager_id} has {len(direct_reports)} direct reports: {direct_reports}"
            )

            for report_id in direct_reports:
                if report_id not in reports:
                    reports.add(report_id)
                    logger.debug(f"Added report {report_id} to chain")
                    self._get_reports_recursive(report_id, hierarchy, reports)
        else:
            logger.debug(f"Manager {manager_id} has no direct reports in hierarchy")

    def _build_participants(
        self,
        call_artifact: GongCallArtifact,
        user_lookup: dict[str, GongUserArtifact],
    ) -> list[dict[str, Any]]:
        participants: list[dict[str, Any]] = []
        for party in call_artifact.content.parties:
            email = self._resolve_party_email(party, user_lookup)
            name = self._resolve_party_name(party, user_lookup)
            participants.append(
                {
                    "party_id": party.get("id"),
                    "user_id": party.get("userId"),
                    "name": name,
                    "email": email,
                    "speaker_id": party.get("speakerId"),
                    "affiliation": party.get("affiliation"),
                    "methods": party.get("methods", []),
                }
            )
        return participants

    def _build_transcript_chunks(
        self,
        call_artifact: GongCallArtifact,
        transcript_artifact: GongCallTranscriptArtifact | None,
        user_lookup: dict[str, GongUserArtifact],
        chunk_size: int = 1400,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        if not transcript_artifact or not transcript_artifact.content.transcript:
            return [], []

        call_id = call_artifact.metadata.call_id
        workspace_id = call_artifact.metadata.workspace_id
        parties = call_artifact.content.parties

        speaker_map = {party.get("speakerId"): party for party in parties if party.get("speakerId")}
        user_party_map = {party.get("userId"): party for party in parties if party.get("userId")}

        def describe_speaker(segment: dict[str, Any]) -> tuple[str, dict[str, Any]]:
            speaker_id = segment.get("speakerId")
            party = speaker_map.get(speaker_id) or user_party_map.get(speaker_id)

            label = "Unknown Speaker"
            speaker_meta: dict[str, Any] = {
                "speaker_id": speaker_id,
                "email": None,
                "name": None,
                "affiliation": None,
            }

            if party:
                speaker_meta["email"] = self._resolve_party_email(party, user_lookup)
                speaker_meta["name"] = self._resolve_party_name(party, user_lookup)
                speaker_meta["affiliation"] = party.get("affiliation")
                if speaker_meta["name"]:
                    label = speaker_meta["name"]
                elif speaker_meta["email"]:
                    label = speaker_meta["email"]
            elif speaker_id:
                email = self._resolve_user_email(speaker_id, user_lookup)
                if email:
                    label = email
                    speaker_meta["email"] = email

            return label, speaker_meta

        lines: list[str] = []
        chunks: list[dict[str, Any]] = []
        current_lines: list[str] = []
        current_segments: list[dict[str, Any]] = []
        current_speakers: dict[str | None, dict[str, Any]] = {}
        current_chars = 0

        def flush_chunk() -> None:
            nonlocal current_lines, current_segments, current_speakers, current_chars
            if not current_lines:
                return
            segment_indices = [
                seg.get("index") for seg in current_segments if seg.get("index") is not None
            ]
            chunks.append(
                {
                    "call_id": call_id,
                    "workspace_id": workspace_id,
                    "content": "\n".join(current_lines),
                    "segment_indices": segment_indices,
                    "start_ms": current_segments[0].get("start") if current_segments else None,
                    "end_ms": current_segments[-1].get("end") if current_segments else None,
                    "speakers": list(current_speakers.values()),
                }
            )
            current_lines = []
            current_segments = []
            current_speakers = {}
            current_chars = 0

        for segment in transcript_artifact.content.transcript:
            text = (segment.get("text") or "").strip()
            if not text:
                continue
            label, speaker_meta = describe_speaker(segment)
            line = f"[{self._format_ms(segment.get('start'))}] {label}: {text}"
            lines.append(line)
            current_lines.append(line)
            current_segments.append(segment)
            key = speaker_meta.get("speaker_id") or speaker_meta.get("email")
            if key not in current_speakers:
                current_speakers[key] = speaker_meta
            current_chars += len(line) + 1

            if current_chars >= chunk_size:
                flush_chunk()

        flush_chunk()

        return lines, chunks

    def _resolve_user_email(
        self, user_id: str | None, user_lookup: dict[str, GongUserArtifact]
    ) -> str | None:
        if not user_id:
            return None
        user_artifact = user_lookup.get(user_id)
        if not user_artifact:
            return None
        return (
            user_artifact.content.email_address or user_artifact.metadata.email or ""
        ).lower() or None

    def _resolve_party_email(
        self, party: dict[str, Any], user_lookup: dict[str, GongUserArtifact]
    ) -> str | None:
        email = party.get("emailAddress")
        if email:
            return email.lower()
        return self._resolve_user_email(party.get("userId"), user_lookup)

    def _resolve_party_name(
        self, party: dict[str, Any], user_lookup: dict[str, GongUserArtifact]
    ) -> str | None:
        name = party.get("name")
        if name:
            return name
        user_id = party.get("userId")
        if user_id and user_id in user_lookup:
            user = user_lookup[user_id]
            first = user.content.first_name or ""
            last = user.content.last_name or ""
            candidate = (first + " " + last).strip()
            if candidate:
                return candidate
        return None

    def _format_ms(self, milliseconds: int | float | None) -> str:
        if milliseconds is None:
            return "??:??"
        total_ms = max(0, int(milliseconds))
        seconds, ms = divmod(total_ms, 1000)
        minutes, seconds = divmod(seconds, 60)
        return f"{minutes:02d}:{seconds:02d}.{ms // 10:02d}"
