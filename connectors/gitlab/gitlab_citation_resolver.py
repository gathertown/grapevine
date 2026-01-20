"""GitLab citation resolvers."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from connectors.base import BaseCitationResolver
from connectors.base.document_source import DocumentWithSourceAndMetadata
from connectors.gitlab.gitlab_file_document import GitLabFileDocumentMetadata
from connectors.gitlab.gitlab_merge_request_document import GitLabMRDocumentMetadata
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.mcp.api.citation_resolver import CitationResolver

logger = get_logger(__name__)


class GitLabMRCitationResolver(BaseCitationResolver[GitLabMRDocumentMetadata]):
    """Resolver for GitLab Merge Request citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[GitLabMRDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        logger.info(f"GitLab MR resolver: doc_id={document.id}")

        # Use existing mr_url if available
        mr_url = document.metadata.get("mr_url")
        if mr_url:
            return mr_url

        # Fallback to constructing URL from metadata
        project_path = document.metadata.get("project_path")
        mr_iid = document.metadata.get("mr_iid")

        if project_path and mr_iid:
            return f"https://gitlab.com/{project_path}/-/merge_requests/{mr_iid}"

        return ""


class GitLabFileCitationResolver(BaseCitationResolver[GitLabFileDocumentMetadata]):
    """Resolver for GitLab file/code citations."""

    async def resolve_citation(
        self,
        document: DocumentWithSourceAndMetadata[GitLabFileDocumentMetadata],
        excerpt: str,
        resolver: CitationResolver,
    ) -> str:
        try:
            doc_contents = await resolver._get_document_contents(document.id)
            lines = doc_contents.split("\n")
            excerpt_lines = excerpt.split("\n")
            logger.info(
                f"GitLab file resolver: doc_id={document.id} - {len(excerpt_lines)} line excerpt "
                f"in a {len(lines)} lines doc"
            )

            project_path = document.metadata.get("project_path", "")
            file_path = document.metadata.get("file_path", "")
            commit_sha = document.metadata.get("source_commit_sha")
            branch = document.metadata.get("source_branch")

            # Determine the ref to use (commit SHA preferred, then branch, then default branch)
            ref = commit_sha or branch or "main"

            # Base URL without line numbers
            base_url = f"https://gitlab.com/{project_path}/-/blob/{ref}/{file_path}"

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
                    line_ref = f"L{start_line}-{end_line}"
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
                                    if subsequent_ratio < 0.4:
                                        subsequent_match_good = False
                                        break

                            if subsequent_match_good:
                                line_ref = f"L{start_line}-{end_line}"
                                logger.debug(f"Found fuzzy multi-line match at {line_ref}")
                            else:
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
                        f"Could not find good fuzzy match (best ratio: {best_ratio:.3f}) "
                        f"for excerpt '{excerpt[:50]}...' in document {document.id}, "
                        f"skipping line numbers"
                    )
                    return base_url

            return f"{base_url}#{line_ref}"

        except Exception as e:
            logger.error(f"Error resolving GitLab file citation for {document.id}: {e}")
            # Return base URL as fallback
            project_path = document.metadata.get("project_path", "")
            file_path = document.metadata.get("file_path", "")
            return f"https://gitlab.com/{project_path}/-/blob/main/{file_path}"
