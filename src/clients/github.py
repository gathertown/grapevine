"""GitHub client utility for interacting with GitHub API."""

import sys
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import requests
from github import Github, GithubException
from github.Organization import Organization
from github.PaginatedList import PaginatedList
from github.PullRequest import PullRequest
from github.Repository import Repository
from pydantic import BaseModel, Field, ValidationError
from requests.structures import CaseInsensitiveDict

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.file_encoding import decode_file_content
from src.utils.filetype import is_plaintext_file
from src.utils.logging import get_logger
from src.utils.rate_limiter import RateLimitedError, rate_limited

if TYPE_CHECKING:
    from src.clients.github_app import GitHubAppClient

logger = get_logger(__name__)


# GraphQL API Response Types (Pydantic models for runtime validation)
# ruff: noqa: N815  # Allow camelCase field names to match GraphQL API
class GitHubGraphQLUser(BaseModel):
    """GitHub user from GraphQL API."""

    typename: str = Field(alias="__typename")  # "User" or "Bot" - always present per GraphQL spec
    login: str
    databaseId: int | None = None  # Nullable in GitHub's schema


class GitHubGraphQLPageInfo(BaseModel):
    """GraphQL pagination info."""

    hasNextPage: bool
    endCursor: str | None = None


class GitHubGraphQLComment(BaseModel):
    """Issue comment from GraphQL API."""

    databaseId: int
    body: str
    createdAt: str
    updatedAt: str
    url: str
    author: "GitHubGraphQLUser | None" = None


class GitHubGraphQLReviewComment(BaseModel):
    """Review comment (code comment) from GraphQL API."""

    databaseId: int
    body: str
    createdAt: str
    updatedAt: str
    url: str
    path: str
    line: int | None = None
    position: int | None = None
    diffHunk: str
    author: "GitHubGraphQLUser | None" = None


class GitHubGraphQLReviewCommentsConnection(BaseModel):
    """GraphQL connection for review comments."""

    nodes: list[GitHubGraphQLReviewComment | None]


class GitHubGraphQLReviewThread(BaseModel):
    """Review thread from GraphQL API."""

    comments: GitHubGraphQLReviewCommentsConnection


class GitHubGraphQLReview(BaseModel):
    """PR review from GraphQL API."""

    databaseId: int
    body: str | None = None
    state: str
    submittedAt: str | None = None
    url: str
    commit: dict[str, str] | None = None  # {"oid": "..."}
    author: "GitHubGraphQLUser | None" = None


class GitHubGraphQLCommentsConnection(BaseModel):
    """GraphQL connection for issue comments."""

    pageInfo: GitHubGraphQLPageInfo
    nodes: list[GitHubGraphQLComment | None]


class GitHubGraphQLReviewThreadsConnection(BaseModel):
    """GraphQL connection for review threads."""

    pageInfo: GitHubGraphQLPageInfo
    nodes: list[GitHubGraphQLReviewThread | None]


class GitHubGraphQLReviewsConnection(BaseModel):
    """GraphQL connection for reviews."""

    pageInfo: GitHubGraphQLPageInfo
    nodes: list[GitHubGraphQLReview | None]


class GitHubGraphQLAssignee(BaseModel):
    """Assignee from GraphQL API."""

    login: str
    databaseId: int


class GitHubGraphQLAssigneesConnection(BaseModel):
    """GraphQL connection for assignees."""

    nodes: list[GitHubGraphQLAssignee | None]


class GitHubGraphQLLabel(BaseModel):
    """Label from GraphQL API."""

    name: str


class GitHubGraphQLLabelsConnection(BaseModel):
    """GraphQL connection for labels."""

    nodes: list[GitHubGraphQLLabel | None]


class GitHubGraphQLRef(BaseModel):
    """Git ref from GraphQL API."""

    name: str
    target: dict[str, str]  # {"oid": "..."}


class GitHubGraphQLCommits(BaseModel):
    """Commits connection from GraphQL API."""

    totalCount: int


class GitHubGraphQLPullRequest(BaseModel):
    """Pull request from GraphQL API."""

    id: str
    number: int
    title: str
    body: str | None = None
    state: str  # OPEN, CLOSED, MERGED
    isDraft: bool
    merged: bool
    createdAt: str
    updatedAt: str
    closedAt: str | None = None
    mergedAt: str | None = None
    url: str
    commits: GitHubGraphQLCommits
    additions: int | None = None
    deletions: int | None = None
    changedFiles: int | None = None
    author: "GitHubGraphQLUser | None" = None
    assignees: GitHubGraphQLAssigneesConnection
    labels: GitHubGraphQLLabelsConnection
    headRef: GitHubGraphQLRef | None = None
    baseRef: GitHubGraphQLRef | None = None
    comments: GitHubGraphQLCommentsConnection
    reviewThreads: GitHubGraphQLReviewThreadsConnection
    reviews: GitHubGraphQLReviewsConnection


class GitHubGraphQLRepository(BaseModel):
    """Repository from GraphQL API."""

    pullRequest: GitHubGraphQLPullRequest | None = None


class GitHubGraphQLRateLimit(BaseModel):
    """Rate limit information from GraphQL API."""

    cost: int
    remaining: int


class GitHubGraphQLResponse(BaseModel):
    """Top-level GraphQL response."""

    model_config = {"populate_by_name": True}

    rateLimit: GitHubGraphQLRateLimit | None = None
    repository: GitHubGraphQLRepository | None = None


class GitHubClient:
    """A client for interacting with the GitHub API."""

    # Type annotations for instance variables
    _token: str
    _installation_id: int | None
    _app_client: "GitHubAppClient | None"
    client: Github
    per_page = 30

    def __init__(
        self,
        token: str | None = None,
        installation_id: int | None = None,
        app_client: "GitHubAppClient | None" = None,
        per_page: int | None = None,
    ):
        """Initialize the GitHub client.

        Args:
            token: GitHub personal access token (for PAT authentication).
            installation_id: GitHub App installation ID (for App authentication).
            app_client: GitHubAppClient instance (required for App authentication).
            per_page: how many items per page on all requests from this client, 0 < per_page <= 100; default 30

        Raises:
            ValueError: If neither token nor (installation_id + app_client) are provided
        """
        if installation_id is not None and app_client is not None:
            # GitHub App authentication
            logger.info(
                f"Initializing GitHub client with App authentication (installation {installation_id})"
            )
            # TODO AIVP-477 support caching/refreshing tokens
            self._token = app_client.get_installation_token(installation_id)
            self._installation_id = installation_id
            self._app_client = app_client
        elif token is not None:
            # PAT authentication
            logger.info("Initializing GitHub client with PAT authentication")
            self._token = token
            self._installation_id = None
            self._app_client = None
        else:
            raise ValueError("Either token or (installation_id + app_client) must be provided")

        if per_page is not None:
            if per_page <= 0 or per_page > 100:
                raise ValueError("per_page must be in range (0, 100]")
            self.per_page = per_page

        self.client = Github(self._token, per_page=self.per_page)

    def is_app_authenticated(self) -> bool:
        """Check if client is using GitHub App authentication (as opposed to PAT authentication)."""
        return self._installation_id is not None

    @rate_limited()
    def get_rate_limit(self) -> dict[str, Any]:
        """Get the current rate limit status.

        Returns:
            Dictionary containing rate limit information
        """
        try:
            rate_limit = self.client.get_rate_limit()
            return {
                "resources": {
                    "core": {
                        "limit": rate_limit.core.limit,  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                        "remaining": rate_limit.core.remaining,  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                        "reset": rate_limit.core.reset.timestamp(),  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                    },
                    "search": {
                        "limit": rate_limit.search.limit,  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                        "remaining": rate_limit.search.remaining,  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                        "reset": rate_limit.search.reset.timestamp(),  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                    },
                }
            }
        except GithubException as e:
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    def get_user_organizations(self) -> PaginatedList[Organization]:
        """Get all organizations that the authenticated user belongs to."""
        try:
            user = self.client.get_user()
            return user.get_orgs()
        except GithubException as e:
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    def get_organization_repos(self, org: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Get repositories for an organization.

        Args:
            org: Organization name
            limit: Maximum number of repositories to fetch (optional)

        Returns:
            List of repository dictionaries
        """
        logger = get_logger(__name__)

        try:
            github_org = self.client.get_organization(org)
            repos = []

            if limit:
                logger.info(
                    f"Starting to fetch up to {limit} repositories from {org} organization..."
                )
            else:
                logger.info(f"Starting to fetch repositories from {org} organization...")

            count = 0
            for repo in github_org.get_repos():
                count += 1
                repos.append(self._repo_to_dict(repo))

                # Log progress every 10 repositories
                if count % 10 == 0:
                    logger.info(f"Fetched {count} repositories so far...")

                # Stop if we've reached the limit
                if limit and count >= limit:
                    logger.info(f"Reached limit of {limit} repositories, stopping fetch")
                    break

            logger.info(f"Completed fetching {count} repositories from {org}")
            return repos
        except GithubException as e:
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    def get_installation_repositories(self) -> list[dict[str, Any]]:
        """Get all repositories accessible by a GitHub App installation.
        Only works with GitHub App authentication.

        Raises:
            ValueError: If not using GitHub App authentication
        """
        if not self.is_app_authenticated():
            raise ValueError("This method requires GitHub App authentication")

        try:
            # Use direct REST API since PyGithub doesn't have installation repositories endpoint
            url = "https://api.github.com/installation/repositories"
            headers = {
                "Authorization": f"token {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            repos = []
            page = 1
            per_page = 100

            while True:
                params = {"page": page, "per_page": per_page}
                response = requests.get(url, headers=headers, params=params)

                if response.status_code == 403 and "rate limit" in response.text.lower():
                    raise RateLimitedError(retry_after=60)
                elif response.status_code != 200:
                    response.raise_for_status()

                data = response.json()
                page_repos = data.get("repositories", [])

                if not page_repos:
                    break

                # Convert to our standard repository dictionary format
                for repo_data in page_repos:
                    repos.append(self._repo_to_dict_from_api(repo_data))

                # Check if there are more pages
                if len(page_repos) < per_page:
                    break

                page += 1

            logger.info(
                f"Found {len(repos)} repositories accessible by installation {self._installation_id}"
            )
            return repos

        except requests.RequestException as e:
            if (
                hasattr(e, "response")
                and e.response
                and e.response.status_code == 403
                and "rate limit" in str(e).lower()
            ):
                raise RateLimitedError(retry_after=60)
            logger.error(f"Error fetching installation repositories: {e}")
            raise
        except GithubException as e:
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    def get_individual_repo(self, repo_spec: str) -> dict[str, Any] | None:
        """Get a single repository by owner/repo format.

        Args:
            repo_spec: Repository in "owner/repo" format

        Returns:
            Repository dictionary or None if not found
        """
        try:
            repo = self.client.get_repo(repo_spec)
            return self._repo_to_dict(repo)
        except GithubException as e:
            if e.status == 404:
                return None
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    def get_individual_pull_request(self, repo_spec: str, pr_number: int) -> dict[str, Any] | None:
        """Get a single pull request by repository and PR number.

        Args:
            repo_spec: Repository in "owner/repo" format
            pr_number: Pull request number

        Returns:
            Pull request dictionary or None if not found
        """
        try:
            repo = self.client.get_repo(repo_spec)
            pr = repo.get_pull(pr_number)
            return self._pr_to_dict(pr)
        except GithubException as e:
            if e.status == 404:
                return None
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    def get_pulls(self, repo_full_name: str, state: str = "all") -> PaginatedList:
        """Get pull requests for a repository.

        Args:
            repo_full_name: Repository in "owner/repo" format
            state: PR state filter ('open', 'closed', 'all')

        Returns:
            Paginated list of pull requests
        """
        try:
            repo = self.client.get_repo(repo_full_name)
            return repo.get_pulls(state=state, sort="updated", direction="desc")
        except GithubException as e:
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    def get_pr_files(self, repo_full_name: str, pr_number: int) -> list[dict[str, Any]]:
        """Get list of files changed in a PR with their diffs.

        Args:
            repo_full_name: Repository in "owner/repo" format
            pr_number: Pull request number

        Returns:
            List of file change dictionaries containing:
            - filename: Path to the file
            - status: Change status (added, modified, removed, renamed)
            - additions: Number of lines added
            - deletions: Number of lines deleted
            - changes: Total number of changes
            - patch: Unified diff content (if available, limited to 3000 lines by GitHub)
            - previous_filename: Original filename for renamed files
        """
        try:
            repo = self.client.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)

            files = []
            for file in pr.get_files():
                file_dict = {
                    "filename": file.filename,
                    "status": file.status,
                    "additions": file.additions,
                    "deletions": file.deletions,
                    "changes": file.changes,
                    "patch": file.patch if hasattr(file, "patch") else None,
                    "previous_filename": file.previous_filename
                    if hasattr(file, "previous_filename")
                    else None,
                }
                files.append(file_dict)

            return files
        except GithubException as e:
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    def _fetch_page_with_retry(self, paginated_list: PaginatedList, page_num: int) -> list[Any]:
        """Fetch a single page from a paginated list with rate limit retry logic.

        Args:
            paginated_list: The paginated list to fetch from
            page_num: The page number to fetch

        Returns:
            List of items in the page

        Raises:
            RateLimitedError: When rate limited (will be retried by decorator)
            GithubException: For other GitHub API errors
        """
        try:
            return paginated_list.get_page(page_num)
        except GithubException as e:
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise

    def get_pulls_pages(
        self, repo_full_name: str, state: str = "all"
    ) -> Iterator[list[dict[str, Any]]]:
        """Get pull requests for a repository, yielding pages.

        Args:
            repo_full_name: Repository in "owner/repo" format
            state: PR state filter ('open', 'closed', 'all')

        Yields:
            Pages of pull request dictionaries

        Raises:
            RateLimitedError if rate limited by github (after sync retries)
            GitHubException for other API errors
        """
        repo = self.client.get_repo(repo_full_name)
        pulls = repo.get_pulls(state=state, sort="updated", direction="desc")

        # Process page by page
        page_num = 0
        while True:
            try:
                page = self._fetch_page_with_retry(pulls, page_num)
                if not page:
                    break

                # Convert each PR in the page to a dictionary
                pr_dicts = [self._pr_to_dict(pr) for pr in page]
                yield pr_dicts

                # If we got less than per_page items, we've reached the end
                if len(page) < self.per_page:
                    break

                page_num += 1
            except GithubException as e:
                # If we can't get the page, we've reached the end
                if e.status == 404:
                    break
                raise

    def get_repo_issue_comments_pages(
        self,
        repo_full_name: str,
        since: str | None = None,
        sort: str = "created",
        direction: str = "desc",
    ) -> Iterator[list[dict[str, Any]]]:
        """Get all issue comments for a repository, yielding pages.

        Args:
            repo_full_name: Repository in "owner/repo" format
            since: Only comments updated at or after this time (ISO 8601 format)
            sort: Either 'created' or 'updated'
            direction: Either 'asc' or 'desc'

        Yields:
            Pages of comment dictionaries

        Raises:
            RateLimitedError if rate limited by github (after sync retries)
            GitHubException for other API errors
        """
        repo = self.client.get_repo(repo_full_name)

        # Use repo.get_issues_comments() to get all issue comments for the repository
        if since and isinstance(since, str):
            # Convert string to datetime if needed
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            comments = repo.get_issues_comments(sort=sort, direction=direction, since=since_dt)
        else:
            comments = repo.get_issues_comments(sort=sort, direction=direction)

        # Process page by page
        page_num = 0
        while True:
            try:
                page = self._fetch_page_with_retry(comments, page_num)
                if not page:
                    break

                # Convert each comment in the page to a dictionary
                comment_dicts = []
                for comment in page:
                    comment_dict = self._comment_to_dict(comment)
                    # Extract issue number from the issue_url
                    if hasattr(comment, "issue_url") and comment.issue_url:
                        issue_num = comment.issue_url.split("/")[-1]
                        comment_dict["issue_number"] = int(issue_num)
                    comment_dicts.append(comment_dict)

                yield comment_dicts

                # If we got less than per_page items, we've reached the end
                if len(page) < self.per_page:
                    break

                page_num += 1
            except GithubException as e:
                # If we can't get the page, we've reached the end
                if e.status == 404:
                    break
                raise

    def get_repo_review_comments_pages(
        self,
        repo_full_name: str,
        since: str | None = None,
        sort: str = "created",
        direction: str = "desc",
    ) -> Iterator[list[dict[str, Any]]]:
        """Get all review comments for a repository, yielding pages.

        Args:
            repo_full_name: Repository in "owner/repo" format
            since: Only comments updated at or after this time (ISO 8601 format)
            sort: Either 'created' or 'updated'
            direction: Either 'asc' or 'desc'

        Yields:
            Pages of review comment dictionaries

        Raises:
            RateLimitedError if rate limited by github (after sync retries)
            GitHubException for other API errors
        """
        from datetime import datetime

        repo = self.client.get_repo(repo_full_name)

        # Use repo.get_pulls_comments() to get all review comments for the repository
        if since and isinstance(since, str):
            # Convert string to datetime if needed
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
            comments = repo.get_pulls_comments(sort=sort, direction=direction, since=since_dt)
        else:
            comments = repo.get_pulls_comments(sort=sort, direction=direction)

        # Process page by page
        page_num = 0
        while True:
            try:
                page = self._fetch_page_with_retry(comments, page_num)
                if not page:
                    break

                # Convert each comment in the page to a dictionary
                comment_dicts = []
                for comment in page:
                    comment_dict = self._review_comment_to_dict(comment)
                    # Extract PR number from the pull_request_url
                    if hasattr(comment, "pull_request_url") and comment.pull_request_url:
                        pr_num = comment.pull_request_url.split("/")[-1]
                        comment_dict["issue_number"] = int(
                            pr_num
                        )  # Use issue_number for consistency
                    comment_dicts.append(comment_dict)

                yield comment_dicts

                # If we got less than per_page items, we've reached the end
                if len(page) < self.per_page:
                    break

                page_num += 1
            except GithubException as e:
                # If we can't get the page, we've reached the end
                if e.status == 404:
                    break
                raise

    def iterate_paginated_list(self, paginated_list: PaginatedList) -> Iterator[dict[str, Any]]:
        """Helper to iterate through a paginated list and convert to dictionaries.

        Args:
            paginated_list: PyGithub PaginatedList object

        Yields:
            Dictionary representations of items
        """
        logger = get_logger(__name__)

        try:
            count = 0
            for item in paginated_list:
                count += 1
                if count % 10 == 0:
                    logger.info(f"Processed {count} items from paginated list")

                if hasattr(item, "pull_request") or hasattr(
                    item, "merged_at"
                ):  # It's an issue that's also a PR
                    yield self._pr_to_dict(item)
                else:
                    # Generic conversion
                    yield self._object_to_dict(item)
        except GithubException as e:
            logger.error(f"GitHub API error during pagination: {e}")
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise
        except Exception as e:
            logger.error(f"Unexpected error during pagination: {e}")
            raise

    @rate_limited()
    def get_pr_comments(
        self,
        repo_full_name: str,
        pr_number: int,
        direction: str = "desc",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all comments for a pull request.

        Args:
            repo_full_name: Repository in "owner/repo" format
            pr_number: Pull request number
            direction: Sort direction ('asc' or 'desc')
            limit: Maximum number of comments to return (None for all)

        Returns:
            List of comment dictionaries, sorted by created_at in the specified direction
        """
        try:
            repo = self.client.get_repo(repo_full_name)
            pr = repo.get_pull(pr_number)

            comments = []

            # Get issue comments
            for comment in pr.get_issue_comments():
                comment_dict = self._comment_to_dict(comment)
                comment_dict["comment_type"] = "issue"
                comments.append(comment_dict)

            # Get review comments (sorted by created descending from GitHub)
            for comment in pr.get_review_comments(sort="created", direction=direction):  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25
                comment_dict = self._review_comment_to_dict(comment)
                comment_dict["comment_type"] = "review"
                comments.append(comment_dict)

            # Get reviews - include all reviews (approvals, rejections, comments)
            for review in pr.get_reviews():
                review_dict = self._review_to_dict(review)
                review_dict["comment_type"] = "review"
                comments.append(review_dict)

            # Sort all comments by created_at, respecting the direction parameter
            comments.sort(key=lambda c: c.get("created_at") or "", reverse=(direction == "desc"))

            # Apply limit if specified
            if limit is not None:
                comments = comments[:limit]

            return comments
        except GithubException as e:
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise

    @rate_limited()
    def get_pull_request_with_comments_graphql(
        self, repo_spec: str, pr_number: int
    ) -> dict[str, Any] | None:
        """Get a single PR with all its comments and reviews via GraphQL.

        This is more efficient than REST API for PRs with many comments, as it fetches
        PR data + comments + reviews in a single request instead of multiple REST calls
        and full repository comment scans.

        Args:
            repo_spec: Repository in "owner/repo" format
            pr_number: Pull request number

        Returns:
            PR dictionary in same format as get_individual_pull_request() but with
            nested comments and reviews arrays, or None if PR not found
        """
        parts = repo_spec.split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid repo_spec format: {repo_spec}. Expected 'owner/repo'")

        owner, name = parts

        # GraphQL query to fetch PR with comments and reviews
        query = """
        query($owner: String!, $name: String!, $prNumber: Int!) {
          rateLimit {
            cost
            remaining
          }
          repository(owner: $owner, name: $name) {
            pullRequest(number: $prNumber) {
              id
              number
              title
              body
              state
              isDraft
              merged
              createdAt
              updatedAt
              closedAt
              mergedAt
              url
              commits { totalCount }
              additions
              deletions
              changedFiles
              author {
                __typename
                login
                ... on User { databaseId }
                ... on Bot { databaseId }
              }
              assignees(first: 20) {
                nodes {
                  login
                  databaseId
                }
              }
              labels(first: 50) {
                nodes {
                  name
                }
              }
              headRef {
                name
                target { oid }
              }
              baseRef {
                name
                target { oid }
              }
              comments(first: 100) {
                pageInfo { hasNextPage endCursor }
                nodes {
                  databaseId
                  body
                  createdAt
                  updatedAt
                  url
                  author {
                    __typename
                    login
                    ... on User { databaseId }
                    ... on Bot { databaseId }
                  }
                }
              }
              reviewThreads(first: 100) {
                pageInfo { hasNextPage endCursor }
                nodes {
                  comments(first: 50) {
                    nodes {
                      databaseId
                      body
                      createdAt
                      updatedAt
                      url
                      path
                      line
                      position
                      diffHunk
                      author {
                        __typename
                        login
                        ... on User { databaseId }
                        ... on Bot { databaseId }
                      }
                    }
                  }
                }
              }
              reviews(first: 100) {
                pageInfo { hasNextPage endCursor }
                nodes {
                  databaseId
                  body
                  state
                  submittedAt
                  url
                  commit { oid }
                  author {
                    __typename
                    login
                    ... on User { databaseId }
                    ... on Bot { databaseId }
                  }
                }
              }
            }
          }
        }
        """

        variables = {"owner": owner, "name": name, "prNumber": pr_number}

        try:
            data = self._execute_graphql(query, variables)

            # Validate the response with Pydantic for runtime type checking
            try:
                typed_data = GitHubGraphQLResponse.model_validate(data)
            except ValidationError as e:
                logger.error(
                    f"GitHub GraphQL response validation failed for {repo_spec}#{pr_number}: {e}"
                )
                raise

            # Check if PR exists
            if not typed_data.repository or not typed_data.repository.pullRequest:
                return None

            pr_data = typed_data.repository.pullRequest

            # Log GraphQL query cost from API response
            cost = typed_data.rateLimit.cost if typed_data.rateLimit else 0
            remaining = typed_data.rateLimit.remaining if typed_data.rateLimit else 0
            num_comments = len(pr_data.comments.nodes)
            num_review_threads = len(pr_data.reviewThreads.nodes)
            num_reviews = len(pr_data.reviews.nodes)
            logger.info(
                f"GraphQL PR fetch for {repo_spec}#{pr_number}: "
                f"cost={cost} points, remaining={remaining}, "
                f"fetched {num_comments} comments, {num_review_threads} review threads, {num_reviews} reviews"
            )

            # Transform GraphQL response to match REST API format
            # Note: We use PR number for the id field since that's what we actually use
            # for entity identification (the database ID from REST API is not used)
            result = {
                "id": pr_data.number,
                "number": pr_data.number,
                "title": pr_data.title,
                "body": pr_data.body,
                "state": pr_data.state.lower(),  # GraphQL returns OPEN/CLOSED/MERGED
                "draft": pr_data.isDraft,
                "merged": pr_data.merged,
                "created_at": pr_data.createdAt,
                "updated_at": pr_data.updatedAt,
                "closed_at": pr_data.closedAt,
                "merged_at": pr_data.mergedAt,
                "html_url": pr_data.url,
                "commits": pr_data.commits.totalCount,
                "additions": pr_data.additions,
                "deletions": pr_data.deletions,
                "changed_files": pr_data.changedFiles,
            }

            # Transform author
            if pr_data.author:
                result["user"] = {
                    "login": pr_data.author.login or "",
                    "id": pr_data.author.databaseId,
                    "type": pr_data.author.typename,
                }

            # Transform assignees
            result["assignees"] = [
                {"login": a.login, "id": a.databaseId}
                for a in pr_data.assignees.nodes
                if a is not None
            ]

            # Transform labels
            result["labels"] = [label.name for label in pr_data.labels.nodes if label is not None]

            # Transform head and base refs
            if pr_data.headRef:
                result["head"] = {
                    "ref": pr_data.headRef.name,
                    "sha": pr_data.headRef.target.get("oid", ""),
                }

            if pr_data.baseRef:
                result["base"] = {
                    "ref": pr_data.baseRef.name,
                    "sha": pr_data.baseRef.target.get("oid", ""),
                }

            # Transform comments (issue comments)
            comments = []
            for comment in pr_data.comments.nodes:
                if comment is None:
                    continue
                comments.append(
                    {
                        "id": comment.databaseId,
                        "body": comment.body,
                        "created_at": comment.createdAt,
                        "updated_at": comment.updatedAt,
                        "url": comment.url,
                        "user": {
                            "login": comment.author.login or "",
                            "id": comment.author.databaseId,
                            "type": comment.author.typename,
                        }
                        if comment.author
                        else None,
                        "comment_type": "issue",
                    }
                )

            # Transform review comments (code review comments in review threads)
            for thread in pr_data.reviewThreads.nodes:
                if thread is None:
                    continue
                for review_comment in thread.comments.nodes:
                    if review_comment is None:
                        continue
                    comments.append(
                        {
                            "id": review_comment.databaseId,
                            "body": review_comment.body,
                            "created_at": review_comment.createdAt,
                            "updated_at": review_comment.updatedAt,
                            "url": review_comment.url,
                            "path": review_comment.path,
                            "line": review_comment.line,
                            "position": review_comment.position,
                            "diff_hunk": review_comment.diffHunk,
                            "user": {
                                "login": review_comment.author.login or "",
                                "id": review_comment.author.databaseId,
                                "type": review_comment.author.typename,
                            }
                            if review_comment.author
                            else None,
                            "comment_type": "review",
                        }
                    )

            result["comments"] = comments

            # Transform reviews
            reviews = []
            for review in pr_data.reviews.nodes:
                if review is None:
                    continue
                reviews.append(
                    {
                        "id": review.databaseId,
                        "body": review.body,
                        "state": review.state,
                        "submitted_at": review.submittedAt,
                        "url": review.url,
                        "commit_id": review.commit.get("oid") if review.commit else None,
                        "user": {
                            "login": review.author.login or "",
                            "id": review.author.databaseId,
                            "type": review.author.typename,
                        }
                        if review.author
                        else None,
                    }
                )

            result["reviews"] = reviews

            # Log if pagination needed (for future enhancement)
            if pr_data.comments.pageInfo.hasNextPage:
                logger.warning(
                    f"PR #{pr_number} has more than 100 comments, pagination not implemented"
                )
            if pr_data.reviewThreads.pageInfo.hasNextPage:
                logger.warning(
                    f"PR #{pr_number} has more than 100 review threads, pagination not implemented"
                )
            if pr_data.reviews.pageInfo.hasNextPage:
                logger.warning(
                    f"PR #{pr_number} has more than 100 reviews, pagination not implemented"
                )

            return result

        except GithubException as e:
            if e.status == 404:
                return None
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise
        except Exception as e:
            logger.error(f"Failed to fetch PR #{pr_number} via GraphQL: {e}")
            raise

    @rate_limited()
    def get_file_content(
        self, repo_full_name: str, file_path: str, ref: str | None = None
    ) -> str | None:
        """Get file content from GitHub API with proper encoding handling.

        This method fetches file content from GitHub and attempts to decode it using
        the correct encoding. It tries multiple common encodings (UTF-8, Latin-1,
        Windows-1252, ISO-8859-1) and falls back to lossy UTF-8 decoding if needed.

        This ensures we can always retrieve and index file content, even when the
        encoding is non-standard or corrupted.

        Args:
            repo_full_name: Repository in "owner/repo" format
            file_path: Path to the file in the repository
            ref: Git reference (branch, tag, or commit SHA). Defaults to default branch.

        Returns:
            File content as string or None if not found/error
        """
        import base64

        logger = get_logger(__name__)

        try:
            # Use GitHub API to fetch file content
            url = f"https://api.github.com/repos/{repo_full_name}/contents/{file_path}"
            headers = {
                "Authorization": f"token {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            params = {}
            if ref:
                params["ref"] = ref

            response = requests.get(url, headers=headers, params=params)

            if response.status_code == 200:
                data = response.json()
                if data.get("type") == "file":
                    # Check if this is a plaintext file before attempting to decode
                    if not is_plaintext_file(file_path):
                        logger.debug(f"Skipping binary file: {file_path}")
                        return None

                    # Content is base64 encoded
                    binary_content = base64.b64decode(data["content"])
                    # Use the shared helper for encoding detection
                    return decode_file_content(
                        binary_content, file_path=f"{file_path} in {repo_full_name}"
                    )
                else:
                    logger.warning(f"File {file_path} is not a regular file")
                    return None
            elif response.status_code == 404:
                logger.warning(f"File {file_path} not found")
                return None
            elif response.status_code == 403 and "rate limit" in response.text.lower():
                raise RateLimitedError(retry_after=60)
            else:
                logger.error(f"Failed to fetch file {file_path}: {response.status_code}")
                return None

        except requests.RequestException as e:
            if (
                hasattr(e, "response")
                and e.response
                and e.response.status_code == 403
                and "rate limit" in str(e).lower()
            ):
                raise RateLimitedError(retry_after=60)
            logger.error(f"Error fetching file content for {file_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching file content for {file_path}: {e}")
            return None

    @rate_limited()
    def get_pr_timeline_events(
        self, repo_full_name: str, pr_number: int, since: str | None = None
    ) -> list[dict[str, Any]]:
        """Get timeline events for a pull request.

        Args:
            repo_full_name: Repository in "owner/repo" format
            pr_number: Pull request number
            since: ISO timestamp to fetch events after (for incremental updates)

        Returns:
            List of timeline event dictionaries
        """
        try:
            # Use direct REST API since PyGithub doesn't support timeline events yet
            url = f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/timeline"
            headers = {
                "Authorization": f"token {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            }

            params = {}
            if since:
                # Note: Timeline API doesn't support 'since' parameter directly,
                # but we can filter client-side for efficiency
                params["per_page"] = 100

            events = []
            page = 1

            while True:
                params["page"] = page
                response = requests.get(url, headers=headers, params=params)

                if response.status_code == 403:
                    # Check if it's a rate limit error
                    if "rate limit" in response.text.lower():
                        retry_after = int(response.headers.get("Retry-After", 60))
                        raise RateLimitedError(retry_after=retry_after)
                    else:
                        response.raise_for_status()
                elif response.status_code != 200:
                    response.raise_for_status()

                page_events = response.json()
                if not page_events:
                    break

                # Filter events by timestamp if 'since' is provided
                if since:
                    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
                    filtered_events = []

                    for event in page_events:
                        event_time_str = event.get("created_at")
                        if event_time_str:
                            try:
                                event_dt = datetime.fromisoformat(
                                    event_time_str.replace("Z", "+00:00")
                                )
                                if event_dt > since_dt:
                                    filtered_events.append(event)
                            except:
                                # Include event if we can't parse timestamp
                                filtered_events.append(event)
                        else:
                            filtered_events.append(event)

                    events.extend(filtered_events)

                    # If we found events older than 'since', we can stop pagination
                    if len(filtered_events) < len(page_events):
                        break
                else:
                    events.extend(page_events)

                # Check if there are more pages
                if len(page_events) < params.get("per_page", 30):
                    break

                page += 1

            return events

        except requests.RequestException as e:
            if (
                hasattr(e, "response")
                and e.response
                and hasattr(e.response, "status_code")
                and e.response.status_code == 403
                and "rate limit" in str(e).lower()
            ):
                raise RateLimitedError(retry_after=60)
            status_code = 500
            if hasattr(e, "response") and e.response and hasattr(e.response, "status_code"):
                status_code = e.response.status_code
            raise GithubException(status=status_code, data=str(e))

    # Helper methods for converting PyGithub objects to dictionaries

    def _repo_to_dict(self, repo: Repository) -> dict[str, Any]:
        """Convert a Repository object to a dictionary."""
        return {
            "id": repo.id,
            "name": repo.name,
            "full_name": repo.full_name,
            "owner": {"login": repo.owner.login, "id": repo.owner.id, "type": repo.owner.type},
            "private": repo.private,
            "description": repo.description,
            "fork": repo.fork,
            "created_at": repo.created_at.isoformat() if repo.created_at else None,
            "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
            "pushed_at": repo.pushed_at.isoformat() if repo.pushed_at else None,
            "homepage": repo.homepage,
            "size": repo.size,
            "stargazers_count": repo.stargazers_count,
            "watchers_count": repo.watchers_count,
            "language": repo.language,
            "forks_count": repo.forks_count,
            "archived": repo.archived,
            "disabled": getattr(repo, "disabled", False),
            "open_issues_count": repo.open_issues_count,
            "license": repo.license.key if repo.license else None,
            "topics": repo.get_topics(),
            "default_branch": repo.default_branch,
            "url": repo.html_url,
        }

    def _pr_to_dict(self, pr: PullRequest) -> dict[str, Any]:
        """Convert a PullRequest object to a dictionary."""
        return {
            "id": pr.id,
            "number": pr.number,
            "state": pr.state,
            "title": pr.title,
            "body": pr.body,
            "created_at": pr.created_at.isoformat() if pr.created_at else None,
            "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
            "closed_at": pr.closed_at.isoformat() if pr.closed_at else None,
            "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
            "user": {"login": pr.user.login, "id": pr.user.id, "type": pr.user.type}
            if pr.user
            else None,
            "assignee": {"login": pr.assignee.login, "id": pr.assignee.id} if pr.assignee else None,
            "assignees": [{"login": a.login, "id": a.id} for a in pr.assignees]
            if pr.assignees
            else [],
            "labels": [{"name": label.name, "color": label.color} for label in pr.labels],
            "milestone": {"title": pr.milestone.title, "number": pr.milestone.number}
            if pr.milestone
            else None,
            "draft": pr.draft,
            "head": {"ref": pr.head.ref, "sha": pr.head.sha} if pr.head else None,
            "base": {"ref": pr.base.ref, "sha": pr.base.sha} if pr.base else None,
            "url": pr.html_url,
            "commits": pr.commits,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "changed_files": pr.changed_files,
            "review_comments": pr.review_comments,
            "comments": pr.comments,
            "mergeable": pr.mergeable,
            "mergeable_state": pr.mergeable_state,
            "merged": pr.merged,
            "merged_by": {"login": pr.merged_by.login, "id": pr.merged_by.id}
            if pr.merged_by
            else None,
        }

    def _comment_to_dict(self, comment) -> dict[str, Any]:
        """Convert an IssueComment object to a dictionary."""
        return {
            "id": comment.id,
            "body": comment.body,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
            "updated_at": comment.updated_at.isoformat() if comment.updated_at else None,
            "user": {"login": comment.user.login, "id": comment.user.id} if comment.user else None,
            "url": comment.html_url,
        }

    def _review_comment_to_dict(self, comment) -> dict[str, Any]:
        """Convert a PullRequestReviewComment object to a dictionary."""
        return {
            "id": comment.id,
            "body": comment.body,
            "created_at": comment.created_at.isoformat() if comment.created_at else None,
            "updated_at": comment.updated_at.isoformat() if comment.updated_at else None,
            "user": {"login": comment.user.login, "id": comment.user.id} if comment.user else None,
            "path": comment.path,
            "position": comment.position,
            "line": comment.line,
            "url": comment.html_url,
            "diff_hunk": comment.diff_hunk,
        }

    def _review_to_dict(self, review) -> dict[str, Any]:
        """Convert a PullRequestReview object to a dictionary."""
        return {
            "id": review.id,
            "body": review.body,
            "state": review.state,
            "created_at": review.submitted_at.isoformat() if review.submitted_at else None,
            "user": {"login": review.user.login, "id": review.user.id} if review.user else None,
            "commit_id": review.commit_id,
            "url": review.html_url,
        }

    def _object_to_dict(self, obj) -> dict[str, Any]:
        """Generic conversion for PyGithub objects."""
        result = {}
        for attr in dir(obj):
            if not attr.startswith("_") and not callable(getattr(obj, attr)):
                try:
                    value = getattr(obj, attr)
                    # Convert datetime objects
                    if hasattr(value, "isoformat"):
                        result[attr] = value.isoformat()
                    # Skip complex objects
                    elif not isinstance(value, (str, int, float, bool, list, dict, type(None))):
                        continue
                    else:
                        result[attr] = value
                except:
                    continue
        return result

    def _execute_graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Execute a GraphQL query against GitHub's GraphQL API.

        Args:
            query: GraphQL query string
            variables: Variables for the query

        Returns:
            Response data from GraphQL API

        Raises:
            RateLimitedError: If rate limited
            Exception: If GraphQL returns errors
        """
        url = "https://api.github.com/graphql"
        headers = {
            "Authorization": f"bearer {self._token}",
            "Content-Type": "application/json",
        }

        response = requests.post(
            url, json={"query": query, "variables": variables}, headers=headers
        )

        # Check for rate limiting via HTTP status code
        if response.status_code == 403 and "rate limit" in response.text.lower():
            # Extract retry_after from x-ratelimit-reset header (epoch timestamp)
            retry_after = self._calculate_retry_after(response.headers)
            raise RateLimitedError(retry_after=retry_after)

        response.raise_for_status()
        data = response.json()

        # Handle GraphQL errors - check for rate limit errors in response body
        if "errors" in data:
            errors = data["errors"]
            # Check if any error is a rate limit error
            for error in errors:
                if isinstance(error, dict):
                    error_type = error.get("type", "").upper()
                    error_code = error.get("code", "").lower()
                    if error_type == "RATE_LIMIT" or "rate_limit" in error_code:
                        # Extract retry_after from headers
                        retry_after = self._calculate_retry_after(response.headers)
                        raise RateLimitedError(retry_after=retry_after)
            raise Exception(f"GraphQL errors: {data['errors']}")

        return data["data"]

    def _calculate_retry_after(self, headers: CaseInsensitiveDict) -> int:
        """Calculate retry_after seconds from GitHub rate limit headers.

        Args:
            headers: HTTP response headers from requests library

        Returns:
            Number of seconds to wait before retrying (minimum 1 second)
        """
        import time

        # GitHub provides x-ratelimit-reset as epoch timestamp
        # CaseInsensitiveDict handles case variations automatically
        reset_time = headers.get("x-ratelimit-reset")
        if reset_time:
            try:
                reset_epoch = int(reset_time)
                current_time = int(time.time())
                retry_after = max(1, reset_epoch - current_time)
                return retry_after
            except (ValueError, TypeError):
                pass

        # Default to 60 seconds if we can't parse the header
        return 60

    def get_all_pr_numbers_graphql(self, repo_spec: str) -> list[int]:
        """Get all PR numbers for a repository using GraphQL (efficient for backfills).

        This method uses GraphQL to fetch only PR numbers, which is much more efficient
        than fetching full PR objects via REST API. This is ideal for backfill operations
        where we just need to enumerate all PRs.

        Args:
            repo_spec: Repository in "owner/repo" format

        Returns:
            List of all PR numbers in the repository (sorted newest first)
        """
        parts = repo_spec.split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid repo_spec format: {repo_spec}. Expected 'owner/repo'")

        owner, name = parts

        # GraphQL query to fetch only PR numbers
        query = """
        query($owner: String!, $name: String!, $cursor: String) {
          rateLimit {
            cost
            remaining
          }
          repository(owner: $owner, name: $name) {
            pullRequests(first: 100, after: $cursor, orderBy: {field: UPDATED_AT, direction: DESC}) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                number
              }
            }
          }
        }
        """

        @rate_limited()
        def fetch_page(cursor: str | None) -> dict[str, Any]:
            """Fetch a single page of PR numbers with rate limiting."""
            variables = {"owner": owner, "name": name, "cursor": cursor}
            return self._execute_graphql(query, variables)

        pr_numbers = []
        cursor = None
        page_num = 0

        try:
            while True:
                page_num += 1
                data = fetch_page(cursor)

                # Check if repository exists
                if not data.get("repository"):
                    logger.warning(f"Repository not found: {repo_spec}")
                    break

                pr_connection = data["repository"]["pullRequests"]
                page_info = pr_connection["pageInfo"]
                nodes = pr_connection["nodes"]

                # Extract PR numbers from this page
                page_pr_numbers = [node["number"] for node in nodes if node is not None]
                pr_numbers.extend(page_pr_numbers)

                # Log progress
                cost = data.get("rateLimit", {}).get("cost", 0)
                remaining = data.get("rateLimit", {}).get("remaining", 0)
                logger.info(
                    f"GraphQL page {page_num} for {repo_spec}: "
                    f"fetched {len(page_pr_numbers)} PRs (total: {len(pr_numbers)}), "
                    f"cost={cost}, remaining={remaining}"
                )

                # Check if there are more pages
                if not page_info["hasNextPage"]:
                    break

                cursor = page_info["endCursor"]

            logger.info(f"Fetched {len(pr_numbers)} PR numbers for {repo_spec} using GraphQL")
            return pr_numbers

        except GithubException as e:
            if e.status == 403 and "rate limit" in str(e).lower():
                raise RateLimitedError(retry_after=60)
            raise
        except Exception as e:
            logger.error(f"Failed to fetch PR numbers for {repo_spec} via GraphQL: {e}")
            raise

    def _repo_to_dict_from_api(self, repo_data: dict[str, Any]) -> dict[str, Any]:
        """Convert repository data from GitHub API response to our standard format (matching `_repo_to_dict`).

        Args:
            repo_data: Repository data from GitHub API response
        """
        # Fields that can be copied directly from API response
        direct_fields = {
            "id",
            "name",
            "full_name",
            "owner",
            "private",
            "description",
            "fork",
            "created_at",
            "updated_at",
            "pushed_at",
            "homepage",
            "size",
            "stargazers_count",
            "watchers_count",
            "language",
            "forks_count",
            "archived",
            "open_issues_count",
            "default_branch",
            "topics",
        }

        # Copy direct fields
        result = {field: repo_data.get(field) for field in direct_fields}

        # Handle special cases that need transformation
        result.update(
            {
                "disabled": repo_data.get("disabled", False),  # Default to False
                "license": repo_data.get("license", {}).get("key")  # Extract key from nested object
                if repo_data.get("license")
                else None,
                "url": repo_data.get("html_url"),  # Rename html_url to url
            }
        )

        return result
