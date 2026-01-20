"""
Sync GitHub PR review comment reactions to database.

Queries GitHub GraphQL API for reactions on PR review comments and syncs
them to the pr_review_comment_reactions table in the tenant database.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from src.clients.ssm import SSMClient
from src.clients.tenant_db import tenant_db_manager
from src.cron import cron
from src.utils.logging import get_logger

logger = get_logger(__name__)

# MVP: Hard-coded tenant ID
TENANT_ID = "878f6fb522b441d1"

# Max number of PRs to batch per GraphQL query
MAX_PRS_PER_QUERY = 30

# Fragment for PR review comment reactions (reused for each PR)
PR_REACTIONS_FRAGMENT = """
reviews(last: 20) {
  nodes {
    id
    databaseId
    comments(last: 75) {
      nodes {
        databaseId
        reactions(last: 5) {
          nodes {
            content
            user { login }
            createdAt
          }
        }
      }
    }
  }
}
"""


def build_batch_graphql_query(pr_numbers: list[int]) -> str:
    """Build a GraphQL query that fetches multiple PRs using aliases.

    Args:
        pr_numbers: List of PR numbers to fetch (up to MAX_PRS_PER_QUERY)

    Returns:
        GraphQL query string with aliased PR fields
    """
    pr_fields = []
    for i, pr_number in enumerate(pr_numbers):
        pr_fields.append(f"""
    pr{i}: pullRequest(number: {pr_number}) {{
      number
      {PR_REACTIONS_FRAGMENT}
    }}""")

    query = f"""
query GetMultiplePRReactions($owner: String!, $repo: String!) {{
  repository(owner: $owner, name: $repo) {{
    {"".join(pr_fields)}
  }}
}}
"""
    return query


async def get_github_token_for_tenant(tenant_id: str) -> str | None:
    """Get GitHub app token for tenant"""
    ssm_client = SSMClient()

    return await ssm_client.get_github_app_token(tenant_id)


async def get_comments_needing_sync(tenant_id: str, days: int = 14) -> list[dict[str, Any]]:
    """Get PR review comments from last N days that need reaction syncing."""
    cutoff_date = datetime.now(UTC) - timedelta(days=days)

    async with tenant_db_manager.acquire_pool(tenant_id) as pool, pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                id,
                github_comment_id,
                github_review_id,
                github_pr_number,
                github_repo_owner,
                github_repo_name,
                last_synced_at
            FROM pr_review_comments
            WHERE created_at > $1
            ORDER BY github_pr_number, github_repo_owner, github_repo_name
            """,
            cutoff_date,
        )

        return [dict(row) for row in rows]


async def fetch_batch_pr_reactions(
    owner: str, repo: str, pr_numbers: list[int], github_token: str
) -> dict[int, dict[int, list[dict[str, Any]]]]:
    """Fetch reactions for all review comments in multiple PRs from GitHub GraphQL API.

    Args:
        owner: Repository owner
        repo: Repository name
        pr_numbers: List of PR numbers to fetch (up to MAX_PRS_PER_QUERY)
        github_token: GitHub API token

    Returns:
        Nested dict mapping pr_number -> github_comment_id -> list of reactions
        Each reaction has format: {user: str, reaction_type: str, created_at: str}

    Raises:
        Exception: If there's an error fetching reactions from GitHub API
    """
    if not pr_numbers:
        return {}

    if len(pr_numbers) > MAX_PRS_PER_QUERY:
        raise ValueError(
            f"Cannot fetch more than {MAX_PRS_PER_QUERY} PRs per query, got {len(pr_numbers)}"
        )

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Content-Type": "application/json",
    }

    # Build dynamic query for multiple PRs
    query = build_batch_graphql_query(pr_numbers)

    payload = {
        "query": query,
        "variables": {"owner": owner, "repo": repo},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.github.com/graphql", json=payload, headers=headers
        )
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            error_msg = f"GitHub GraphQL errors for {owner}/{repo}: {data['errors']}"
            logger.error(error_msg)
            raise Exception(error_msg)

        # Parse the response and build reaction map
        reactions_by_pr: dict[int, dict[int, list[dict[str, Any]]]] = {}

        repo_data = data.get("data", {}).get("repository")
        if not repo_data:
            raise Exception(f"No repository data returned for {owner}/{repo}")

        # Map GitHub GraphQL reaction content values to database format
        reaction_content_mapping = {
            "THUMBS_UP": "thumbs_up",
            "THUMBS_DOWN": "thumbs_down",
            "LAUGH": "laugh",
            "HOORAY": "hooray",
            "CONFUSED": "confused",
            "HEART": "heart",
            "ROCKET": "rocket",
            "EYES": "eyes",
        }

        # Process each aliased PR response (pr0, pr1, pr2, etc.)
        for i in range(len(pr_numbers)):
            pr_alias = f"pr{i}"
            pr_data = repo_data.get(pr_alias)

            if not pr_data:
                logger.warning(f"No pull request data returned for {owner}/{repo}#{pr_numbers[i]}")
                continue

            pr_number = pr_data.get("number")
            if not pr_number:
                logger.warning(f"PR at alias {pr_alias} missing number field")
                continue

            reactions_by_comment: dict[int, list[dict[str, Any]]] = defaultdict(list)
            reviews = pr_data.get("reviews", {}).get("nodes", [])

            for review in reviews:
                if not review:
                    continue

                comments = review.get("comments", {}).get("nodes", [])
                for comment in comments:
                    if not comment:
                        continue

                    comment_id = comment.get("databaseId")
                    if not comment_id:
                        continue

                    # Process all reactions for this comment
                    reactions = comment.get("reactions", {}).get("nodes", [])
                    for reaction in reactions:
                        content = reaction.get("content")
                        user = (reaction.get("user") or {}).get("login")
                        created_at = reaction.get("createdAt")

                        # Map reaction content to database format
                        reaction_type = reaction_content_mapping.get(content)
                        if user and reaction_type:
                            reactions_by_comment[comment_id].append(
                                {
                                    "user": user,
                                    "reaction_type": reaction_type,
                                    "created_at": created_at or datetime.now(UTC).isoformat(),
                                }
                            )

            reactions_by_pr[pr_number] = dict(reactions_by_comment)

        return reactions_by_pr


async def sync_reactions_for_comment(
    tenant_id: str,
    comment_id: str,
    github_comment_id: int,
    reactions: list[dict[str, Any]],
) -> None:
    """Sync reactions for a single comment to the database."""
    async with tenant_db_manager.acquire_pool(tenant_id) as pool, pool.acquire() as conn:  # noqa: SIM117
        # Start transaction
        async with conn.transaction():
            # Delete existing reactions for this comment
            await conn.execute(
                "DELETE FROM pr_review_comment_reactions WHERE comment_id = $1", comment_id
            )

            # Insert new reactions
            for reaction in reactions:
                await conn.execute(
                    """
                    INSERT INTO pr_review_comment_reactions
                        (comment_id, github_username, reaction_type, synced_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (comment_id, github_username, reaction_type) DO UPDATE
                    SET synced_at = NOW()
                    """,
                    comment_id,
                    reaction["user"],
                    reaction["reaction_type"],
                )

            # Update last_synced_at on the comment
            await conn.execute(
                "UPDATE pr_review_comments SET last_synced_at = NOW() WHERE id = $1",
                comment_id,
            )


# Run every hour
# https://crontab.guru/#0_*_*_*_*
@cron(id="sync_github_pr_reactions", crontab="0 * * * *", tags=["github", "pr-review"])
async def sync_github_pr_reactions() -> None:
    """Sync GitHub PR review comment reactions for tenant."""
    logger.info(f"Starting GitHub PR reactions sync for tenant {TENANT_ID}")

    # Get GitHub app token for tenant
    github_token = await get_github_token_for_tenant(TENANT_ID)
    if not github_token:
        logger.warning(f"No GitHub app token found for tenant {TENANT_ID}")
        return

    # Get comments from last 2 weeks
    comments = await get_comments_needing_sync(TENANT_ID, days=14)
    if not comments:
        logger.info("No comments found needing sync")
        return

    logger.info(f"Found {len(comments)} comments to sync")

    # Group comments by PR (owner/repo/pr_number)
    prs_to_sync: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for comment in comments:
        pr_key = (
            comment["github_repo_owner"],
            comment["github_repo_name"],
            comment["github_pr_number"],
        )
        prs_to_sync[pr_key].append(comment)

    logger.info(f"Syncing reactions for {len(prs_to_sync)} PRs")

    # Group PRs by repository for batching
    repos_to_sync: dict[tuple[str, str], list[tuple[int, list[dict[str, Any]]]]] = defaultdict(list)
    for (owner, repo, pr_number), pr_comments in prs_to_sync.items():
        repos_to_sync[(owner, repo)].append((pr_number, pr_comments))

    # Sync reactions for each repository
    total_synced = 0
    total_errors = 0

    for (owner, repo), pr_list in repos_to_sync.items():
        # Sort PRs by number for consistent batching
        pr_list.sort(key=lambda x: x[0])

        # Process PRs in batches of MAX_PRS_PER_QUERY
        for batch_start in range(0, len(pr_list), MAX_PRS_PER_QUERY):
            batch = pr_list[batch_start : batch_start + MAX_PRS_PER_QUERY]
            pr_numbers = [pr_number for pr_number, _ in batch]

            try:
                # Fetch reactions for all PRs in this batch
                # This will raise an exception on any error to prevent data loss
                reactions_by_pr = await fetch_batch_pr_reactions(
                    owner, repo, pr_numbers, github_token
                )

                # Sync reactions for each comment in each PR
                for pr_number, pr_comments in batch:
                    reactions_by_comment = reactions_by_pr.get(pr_number, {})

                    for comment in pr_comments:
                        comment_id = comment["id"]
                        github_comment_id = comment["github_comment_id"]
                        reactions = reactions_by_comment.get(github_comment_id, [])

                        await sync_reactions_for_comment(
                            TENANT_ID, comment_id, github_comment_id, reactions
                        )
                        total_synced += 1

                logger.info(
                    f"Synced reactions for {owner}/{repo} batch: PRs {pr_numbers} "
                    f"({sum(len(comments) for _, comments in batch)} comments)"
                )

                # Rate limiting: small delay between batches
                await asyncio.sleep(0.5)

            except Exception as e:
                # Skip this batch entirely on error to avoid deleting existing reactions
                total_errors += len(batch)
                logger.error(f"Error syncing reactions for {owner}/{repo} PRs {pr_numbers}: {e}")

    logger.info(
        f"GitHub PR reactions sync complete: {total_synced} comments synced, {total_errors} PRs with errors"
    )
