import fnmatch
import json
import logging
from typing import Any

import asyncpg

logger = logging.getLogger(__name__)


class ExclusionRulesService:
    async def should_exclude(self, entity_id: str, entity_type: str, db_pool: asyncpg.Pool) -> bool:
        """Check if an artifact should be excluded based on rules.

        Args:
            entity_id: The entity ID to check (e.g., "org/repo/path/to/file.py")
            entity_type: The type of entity (e.g., "github_file")
            db_pool: Database connection pool

        Returns:
            True if the artifact should be excluded, False otherwise
        """
        query = """
            SELECT rule
            FROM exclusion_rules
            WHERE entity_type = $1
            AND is_active = true
        """

        try:
            async with db_pool.acquire() as conn:
                rules = await conn.fetch(query, entity_type)

            for row in rules:
                rule = row["rule"]
                # Parse JSON string if needed
                if isinstance(rule, str):
                    rule = json.loads(rule)
                if self._matches_rule(entity_id, entity_type, rule):
                    logger.debug(f"Entity {entity_id} matched exclusion rule: {rule}")
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking exclusion rules for {entity_id}: {e}")
            return False

    def _matches_rule(self, entity_id: str, entity_type: str, rule: dict[str, Any]) -> bool:
        """Check if an entity_id matches a specific rule.

        Args:
            entity_id: The entity ID to check
            entity_type: The type of entity
            rule: The rule definition (JSON object)

        Returns:
            True if the entity matches the rule, False otherwise
        """
        if entity_type == "github_file":
            return self._matches_github_file_rule(entity_id, rule)
        elif entity_type == "slack_channel":
            return self._matches_slack_channel_rule(entity_id, rule)
        elif entity_type == "linear_issue":
            return self._matches_linear_issue_rule(entity_id, rule)
        # Add more entity types as needed

        return False

    def _matches_github_file_rule(self, entity_id: str, rule: dict[str, Any]) -> bool:
        """Check if a GitHub file entity matches a rule.

        Entity ID format: org/repo/path/to/file.ext
        Rule format: {"repository": "repo-name", "file_path": "pattern/*"}
        """
        parts = entity_id.split("/", 2)
        if len(parts) < 3:
            logger.warning(f"Invalid GitHub file entity_id format: {entity_id}")
            return False

        org, repo, file_path = parts

        if "repository" in rule and rule["repository"] != repo:
            return False

        if "organization" in rule and rule["organization"] != org:
            return False

        if "file_path" in rule:
            pattern = rule["file_path"]
            if fnmatch.fnmatch(file_path, pattern):
                return True

        return False

    def _matches_slack_channel_rule(self, entity_id: str, rule: dict[str, Any]) -> bool:
        """Check if a Slack channel entity matches a rule.

        Entity ID format: channel_id_date (e.g., "C1234567890_2024-01-15")
        Rule format: {"channel_id": "C1234567890"} or {"channel_name": "general"}
        """
        channel_id = entity_id.split("_")[0] if "_" in entity_id else entity_id

        return "channel_id" in rule and rule["channel_id"] == channel_id

    def _matches_linear_issue_rule(self, entity_id: str, rule: dict[str, Any]) -> bool:
        """Check if a Linear issue entity matches a rule.

        Entity ID format: issue_uuid (e.g., "issue_11223344-5566-7788-9900-aabbccddeeff")
        Rule format: {"team": "Engineering"} or {"state": "cancelled"}

        Note: This would require additional context from the artifact metadata
        to properly match team or state.
        """
        if "issue_id_pattern" in rule:
            pattern = rule["issue_id_pattern"]
            if fnmatch.fnmatch(entity_id, pattern):
                return True

        return False

    async def get_active_rules(
        self, entity_type: str | None, db_pool: asyncpg.Pool
    ) -> list[dict[str, Any]]:
        """Get all active exclusion rules, optionally filtered by entity type.

        Args:
            entity_type: Optional entity type to filter by
            db_pool: Database connection pool

        Returns:
            List of exclusion rules
        """
        if entity_type:
            query = "SELECT * FROM exclusion_rules WHERE is_active = true AND entity_type = $1"
            params = [entity_type]
        else:
            query = "SELECT * FROM exclusion_rules WHERE is_active = true"
            params = []

        async with db_pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
