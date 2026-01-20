"""GitHub citation resolvers."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.github.github_file_document import GitHubFileDocumentMetadata
from connectors.github.github_pull_request_document import GitHubPRDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class GitHubPRCitationResolver(BaseCitationResolver[GitHubPRDocumentMetadata]):
    """Resolver for GitHub Pull Request citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[GitHubPRDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        logger.info(f"GitHub PR resolver: doc_id={document.id}")

        # Use existing pr_url if available
        pr_url = document.metadata["pr_url"]
        if pr_url:
            return pr_url

        # Fallback to constructing URL from metadata
        org = document.metadata["organization"]
        repo = document.metadata["repository"]
        pr_number = document.metadata["pr_number"]

        if org and repo and pr_number:
            return f"https://github.com/{org}/{repo}/pull/{pr_number}"

        return ""


class GitHubFileCitationResolver(BaseCitationResolver[GitHubFileDocumentMetadata]):
    """Resolver for GitHub file/code citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[GitHubFileDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        try:
            doc_contents = await resolver._get_document_contents(document.id)
            lines = doc_contents.split("\n")
            excerpt_lines = excerpt.split("\n")
            logger.info(
                f"GitHub file resolver: doc_id={document.id} - {len(excerpt_lines)} line excerpt in a {len(lines)} lines doc"
            )

            # Use fuzzy matching to find the best matching line(s)
            best_match_line = None
            best_ratio = 0.0
            similarity_threshold = 0.05

            # Try exact match first for efficiency
            try:
                start_line = lines.index(excerpt_lines[0]) + 1
                if len(excerpt_lines) > 1:
                    end_line = start_line + len(excerpt_lines) - 1
                    logger.debug(
                        f"Found exact match for multi-line excerpt at lines {start_line}-{end_line}"
                    )
                    line_ref = f"L{start_line}-L{end_line}"
                else:
                    logger.debug(f"Found exact match for excerpt at line {start_line}")
                    line_ref = f"L{start_line}"
            except ValueError:
                # Use fuzzy matching to find the best line
                for i, line in enumerate(lines):
                    ratio = SequenceMatcher(None, excerpt_lines[0].strip(), line.strip()).ratio()
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_match_line = i + 1

                logger.debug(f"Best fuzzy match ratio: {best_ratio} at line {best_match_line}")

                if best_ratio >= similarity_threshold and best_match_line is not None:
                    start_line = best_match_line

                    # For multi-line excerpts, verify subsequent lines also match reasonably
                    if len(excerpt_lines) > 1:
                        end_line = start_line + len(excerpt_lines) - 1
                        # Check if we have enough lines in the document
                        if end_line <= len(lines):
                            # Verify that subsequent lines also match reasonably well
                            subsequent_match_good = True
                            for j in range(1, len(excerpt_lines)):
                                if start_line + j - 1 < len(lines):
                                    subsequent_ratio = SequenceMatcher(
                                        None,
                                        excerpt_lines[j].strip(),
                                        lines[start_line + j - 1].strip(),
                                    ).ratio()
                                    if (
                                        subsequent_ratio < 0.4
                                    ):  # Lower threshold for subsequent lines
                                        subsequent_match_good = False
                                        break

                            if subsequent_match_good:
                                line_ref = f"L{start_line}-L{end_line}"
                                logger.debug(f"Found fuzzy multi-line match at {line_ref}")
                            else:
                                # Fall back to single line if multi-line doesn't match well
                                line_ref = f"L{start_line}"
                                logger.warning(
                                    f"Multi-line match failed, using single line {line_ref}"
                                )
                        else:
                            line_ref = f"L{start_line}"
                            logger.warning(
                                f"Not enough lines for multi-line match, using single line {line_ref}"
                            )
                    else:
                        line_ref = f"L{start_line}"
                        logger.debug(f"Found fuzzy single-line match at {line_ref}")
                else:
                    # Try quoted excerpt fallback
                    if excerpt.startswith('"') and excerpt.endswith('"'):
                        logger.info(
                            f"Fuzzy match failed, trying without quotes for document {document.id}"
                        )
                        stripped_excerpt = excerpt[1:-1]
                        url = await self.resolve_citation(document, stripped_excerpt, resolver)
                        if url:
                            return url

                    logger.warning(
                        f"Could not find good fuzzy match (best ratio: {best_ratio:.3f}) for excerpt '{excerpt[:50]}...' in document {document.id}, skipping line numbers"
                    )
                    # Return base GitHub file URL without line number
                    return f"https://github.com/{document.metadata['organization']}/{document.metadata['repository']}/blob/main/{document.metadata['file_path']}"

            # Use commit SHA, branch, or fallback to main for deeplinks
            organization = document.metadata["organization"]
            repository = document.metadata["repository"]
            file_path = document.metadata["file_path"]

            # Prefer commit SHA for stable links, fallback to branch, then main
            commit_sha = document.metadata.get("source_commit_sha")
            branch = document.metadata.get("source_branch")

            # Construct the URL with preferred branch/ref
            if commit_sha:
                logger.debug(f"Using commit SHA for {document.id}: {commit_sha}")
                return f"https://github.com/{organization}/{repository}/blob/{commit_sha}/{file_path}#{line_ref}"
            elif branch:
                logger.debug(f"Using branch for {document.id}: {branch}")
                return f"https://github.com/{organization}/{repository}/blob/{branch}/{file_path}#{line_ref}"
            else:
                # Fallback to main branch (existing behavior)
                logger.debug(f"No commit SHA or branch found for {document.id}, using main branch")
                return f"https://github.com/{organization}/{repository}/blob/main/{file_path}#{line_ref}"

        except Exception as e:
            logger.error(f"Error resolving GitHub file citation for {document.id}: {e}")
            # Return base URL as fallback
            organization = document.metadata["organization"]
            repository = document.metadata["repository"]
            file_path = document.metadata["file_path"]
            return f"https://github.com/{organization}/{repository}/blob/main/{file_path}"
