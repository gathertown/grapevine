"""GitLab file transformer - transforms artifacts into documents for indexing."""

import logging
from pathlib import Path
from typing import Any

import asyncpg
import newrelic.agent
from langchain_text_splitters import (
    Language,
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from connectors.base import BaseTransformer
from connectors.base.doc_ids import get_gitlab_file_doc_id
from connectors.base.document_source import DocumentSource
from connectors.gitlab.gitlab_file_artifacts import GitLabFileArtifact
from connectors.gitlab.gitlab_file_document import GitLabFileDocument
from src.ingest.repositories import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class GitLabFileTransformer(BaseTransformer[GitLabFileDocument]):
    """Transforms GitLab file artifacts into documents."""

    def __init__(self) -> None:
        super().__init__(DocumentSource.GITLAB_CODE)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[GitLabFileDocument]:
        logger.info(f"Starting transformation for {len(entity_ids)} entity IDs")

        with newrelic.agent.FunctionTrace(name="GitLabFileTransformer/load_artifacts"):
            repo = ArtifactRepository(readonly_db_pool)
            file_artifacts = await repo.get_artifacts_by_entity_ids(GitLabFileArtifact, entity_ids)

        logger.info(
            f"Loaded {len(file_artifacts)} GitLab file artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}
        skipped_count = 0

        with newrelic.agent.FunctionTrace(name="GitLabFileTransformer/create_documents"):
            for artifact in file_artifacts:
                with record_exception_and_ignore(
                    logger, f"Failed to transform artifact {artifact.id}", counter
                ):
                    document = self._create_document(artifact)
                    if document:
                        documents.append(document)
                    else:
                        skipped_count += 1
                        logger.warning(
                            f"Skipped artifact {artifact.entity_id} - no document created"
                        )

        failed = counter.get("failed", 0)

        logger.info(
            f"GitLab file transformation complete: {len(documents)} successful, {failed} failed, "
            f"{skipped_count} skipped from {len(file_artifacts)} artifacts"
        )
        return documents

    def _create_document(self, artifact: GitLabFileArtifact) -> GitLabFileDocument | None:
        """Transform a single artifact into a GitLabFileDocument."""
        content = artifact.content

        if not content:
            logger.warning(f"Artifact {artifact.id} has no content")
            return None

        file_path = content.path
        file_content = content.content

        if not file_path or not file_content:
            logger.warning(f"Missing required fields for artifact {artifact.id}")
            return None

        with newrelic.agent.FunctionTrace(name="GitLabFileTransformer/create_chunks"):
            chunks = self._create_chunks(file_content, file_path)

        document_data = {
            "file_path": file_path,
            "project_id": content.project_id,
            "project_path": content.project_path,
            "source_created_at": content.source_created_at,
            "contributors": [contributor.model_dump() for contributor in content.contributors],
            "contributor_count": content.contributor_count,
            "source_branch": content.source_branch,
            "source_commit_sha": content.source_commit_sha,
            "chunks": chunks,
        }

        document_id = get_gitlab_file_doc_id(artifact.entity_id)

        return GitLabFileDocument(
            id=document_id,
            raw_data=document_data,
            source_updated_at=artifact.source_updated_at,
            permission_policy="tenant",
            permission_allowed_tokens=None,
        )

    def _create_chunks(
        self, content: str, file_path: str, max_chunk_size: int = 2000, overlap: int = 200
    ) -> list[dict[str, Any]]:
        """Create chunks from file content using appropriate splitters."""
        if not content or len(content) <= max_chunk_size:
            return (
                [
                    {
                        "content": content,
                        "chunk_index": 0,
                        "total_chunks": 1,
                        "file_path": file_path,
                        "file_extension": Path(file_path).suffix.lower(),
                        "chunk_size": len(content),
                        "is_first_chunk": True,
                        "is_last_chunk": True,
                    }
                ]
                if content
                else []
            )

        ext = Path(file_path).suffix.lower()

        try:
            if ext == ".py":
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.PYTHON, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext in {".js", ".jsx", ".mjs", ".cjs"}:
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.JS, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext in {".ts", ".tsx"}:
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.TS, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext in {".md", ".mdx"}:
                header_splitter = MarkdownHeaderTextSplitter(
                    headers_to_split_on=[
                        ("#", "Header 1"),
                        ("##", "Header 2"),
                        ("###", "Header 3"),
                    ]
                )
                md_chunks = header_splitter.split_text(content)

                final_chunks = []
                for chunk in md_chunks:
                    chunk_text = (
                        chunk.page_content if hasattr(chunk, "page_content") else str(chunk)
                    )
                    if len(chunk_text) <= max_chunk_size:
                        final_chunks.append(chunk_text)
                    else:
                        text_splitter = RecursiveCharacterTextSplitter.from_language(
                            language=Language.MARKDOWN,
                            chunk_size=max_chunk_size,
                            chunk_overlap=overlap,
                        )
                        sub_chunks = text_splitter.split_text(chunk_text)
                        final_chunks.extend(sub_chunks)

                return self._format_chunks(final_chunks, file_path)

            elif ext in {".cpp", ".cc", ".cxx", ".c", ".h", ".hpp"}:
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.CPP, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext == ".go":
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.GO, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext == ".rs":
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.RUST, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext in {".html", ".htm"}:
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.HTML, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext == ".java":
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.JAVA, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext == ".rb":
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.RUBY, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext == ".php":
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.PHP, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext == ".scala":
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.SCALA, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext in {".kt", ".kts"}:
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.KOTLIN, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext == ".swift":
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.SWIFT, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            else:
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=max_chunk_size,
                    chunk_overlap=overlap,
                    separators=["\n\n", "\n", ". ", " ", ""],
                )

            chunks = splitter.split_text(content)
            return self._format_chunks([chunk for chunk in chunks if chunk.strip()], file_path)

        except Exception as e:
            logger.warning(
                f"LangChain splitting failed for {file_path}: {e}, using simple splitting"
            )
            return self._simple_split(content, file_path, max_chunk_size, overlap)

    def _format_chunks(self, chunks: list[str], file_path: str) -> list[dict[str, Any]]:
        """Format chunks into the expected structure."""
        formatted_chunks = []
        total_chunks = len(chunks)

        for i, chunk_content in enumerate(chunks):
            formatted_chunks.append(
                {
                    "content": chunk_content,
                    "chunk_index": i,
                    "total_chunks": total_chunks,
                    "file_path": file_path,
                    "file_extension": Path(file_path).suffix.lower(),
                    "chunk_size": len(chunk_content),
                    "is_first_chunk": i == 0,
                    "is_last_chunk": i == total_chunks - 1,
                }
            )

        return formatted_chunks

    def _simple_split(
        self, content: str, file_path: str, max_chunk_size: int, overlap: int
    ) -> list[dict[str, Any]]:
        """Simple fallback splitting method."""
        chunks = []
        start = 0

        while start < len(content):
            end = min(start + max_chunk_size, len(content))

            if end < len(content):
                for i in range(end, max(start + max_chunk_size // 2, end - 200), -1):
                    if content[i] == "\n":
                        end = i + 1
                        break
                else:
                    for i in range(end, max(start + max_chunk_size // 2, end - 100), -1):
                        if content[i].isspace():
                            end = i
                            break

            chunk = content[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # If we've reached the end, stop to avoid redundant overlapping chunks
            if end >= len(content):
                break

            start = max(end - overlap, start + 1)

        return self._format_chunks(chunks, file_path)
