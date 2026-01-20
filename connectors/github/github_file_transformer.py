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
from connectors.base.doc_ids import get_github_file_doc_id
from connectors.base.document_source import DocumentSource
from connectors.github.github_file_artifacts import GitHubFileArtifact
from connectors.github.github_file_document import GitHubFileDocument
from src.ingest.repositories import ArtifactRepository
from src.utils.error_handling import ErrorCounter, record_exception_and_ignore

logger = logging.getLogger(__name__)


class GithubFileTransformer(BaseTransformer[GitHubFileDocument]):
    def __init__(self):
        super().__init__(DocumentSource.GITHUB_CODE)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[GitHubFileDocument]:
        logger.info(f"Starting transformation for {len(entity_ids)} entity IDs")

        # Query artifacts directly by entity_ids using the repository
        with newrelic.agent.FunctionTrace(name="GitHubFileTransformer/load_artifacts"):
            repo = ArtifactRepository(readonly_db_pool)
            file_artifacts = await repo.get_artifacts_by_entity_ids(GitHubFileArtifact, entity_ids)

        logger.info(
            f"Loaded {len(file_artifacts)} GitHub file artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        counter: ErrorCounter = {}
        skipped_count = 0

        with newrelic.agent.FunctionTrace(name="GitHubFileTransformer/create_documents"):
            for artifact in file_artifacts:
                with record_exception_and_ignore(
                    logger, f"Failed to transform artifact {artifact.id}", counter
                ):
                    document = await self._create_document(artifact)
                    if document:
                        documents.append(document)
                    else:
                        skipped_count += 1
                        logger.warning(
                            f"Skipped artifact {artifact.entity_id} - no document created"
                        )

        successful = counter.get("successful", 0)
        failed = counter.get("failed", 0)

        logger.info(
            f"GitHub file transformation complete: {successful} successful, {failed} failed, {skipped_count} skipped. "
            f"Created {len(documents)} documents from {len(file_artifacts)} artifacts"
        )
        return documents

    async def _create_document(self, artifact: GitHubFileArtifact) -> GitHubFileDocument | None:
        """Transform a single artifact into a GitHubFileDocument."""
        try:
            content = artifact.content
            metadata = artifact.metadata

            if not content:
                logger.warning(f"Artifact {artifact.id} has no content")
                return None

            file_path = content.path
            file_content = content.content

            if not file_path or not file_content:
                logger.warning(f"Missing required fields for artifact {artifact.id}")
                return None

            with newrelic.agent.FunctionTrace(name="GitHubFileTransformer/create_chunks"):
                chunks = self._create_chunks(file_content, file_path)

            document_data = {
                "file_path": file_path,
                "repository": content.repository or metadata.repository,
                "organization": content.organization,
                "source_created_at": content.source_created_at,
                "contributors": [contributor.model_dump() for contributor in content.contributors],
                "contributor_count": content.contributor_count,
                "source_branch": content.source_branch,
                "source_commit_sha": content.source_commit_sha,
                "chunks": chunks,
            }

            document_id = get_github_file_doc_id(artifact.entity_id)

            return GitHubFileDocument(
                id=document_id,
                raw_data=document_data,
                source_updated_at=artifact.source_updated_at,
                permission_policy="tenant",
                permission_allowed_tokens=None,
            )

        except Exception as e:
            logger.error(f"Error transforming artifact {artifact.entity_id}: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return None

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
            elif ext in {".go"}:
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.GO, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext in {".rs"}:
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.RUST, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext in {".html", ".htm"}:
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.HTML, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext in {".cs"}:
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.CSHARP, chunk_size=max_chunk_size, chunk_overlap=overlap
                )
            elif ext in {".php"}:
                splitter = RecursiveCharacterTextSplitter.from_language(
                    language=Language.PHP, chunk_size=max_chunk_size, chunk_overlap=overlap
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

            start = max(end - overlap, start + 1)

        return self._format_chunks(chunks, file_path)
