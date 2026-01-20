from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict

from langchain_text_splitters import RecursiveCharacterTextSplitter
from markdownify import markdownify as md

from connectors.base.base_chunk import BaseChunk
from connectors.base.base_document import BaseDocument
from connectors.base.document_source import DocumentSource
from connectors.zendesk.client.zendesk_help_center_models import ZendeskCategory, ZendeskSection
from connectors.zendesk.extractors.zendesk_artifacts import (
    ZendeskArticleArtifact,
    ZendeskCategoryArtifact,
    ZendeskCommentArtifact,
    ZendeskSectionArtifact,
    ZendeskUserArtifact,
)


class ZendeskArticleChunkMetadata(TypedDict):
    chunk_index: int
    total_chunks: int
    article_id: int


class ZendeskArticleChunkRawData(TypedDict):
    content: str
    chunk_index: int
    total_chunks: int
    article_id: int


class ZendeskArticleChunk(BaseChunk[ZendeskArticleChunkMetadata]):
    raw_data: ZendeskArticleChunkRawData

    def get_content(self) -> str:
        content = self.raw_data["content"]
        chunk_index = self.raw_data["chunk_index"]
        total_chunks = self.raw_data["total_chunks"]

        if total_chunks == 1:
            return content

        position_context = f"[Part {chunk_index + 1} of {total_chunks}]\n\n"
        return f"{position_context}{content}"

    def get_metadata(self) -> ZendeskArticleChunkMetadata:
        return ZendeskArticleChunkMetadata(
            article_id=self.raw_data["article_id"],
            chunk_index=self.raw_data["chunk_index"],
            total_chunks=self.raw_data["total_chunks"],
        )


class ZendeskArticleDocumentMetadata(TypedDict):
    article_id: int
    title: str
    label_names: list[str]
    author_id: int
    section_id: int | None
    section_name: str | None
    category_id: int | None
    category_name: str | None


@dataclass
class ZendeskArticleDocument(BaseDocument[ZendeskArticleChunk, ZendeskArticleDocumentMetadata]):
    article_artifact: ZendeskArticleArtifact
    section_artifact: ZendeskSectionArtifact | None
    category_artifact: ZendeskCategoryArtifact | None
    comment_artifacts: list[ZendeskCommentArtifact]
    user_artifacts: dict[int, ZendeskUserArtifact]

    def to_embedding_chunks(self) -> list[ZendeskArticleChunk]:
        full_content = self.get_content()

        if not full_content.strip():
            return []

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=6000,
            chunk_overlap=100,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        text_chunks = text_splitter.split_text(full_content)

        return [
            ZendeskArticleChunk(
                document=self,
                raw_data=ZendeskArticleChunkRawData(
                    content=chunk_text,
                    chunk_index=i,
                    total_chunks=len(text_chunks),
                    article_id=self.article_artifact.metadata.article_id,
                ),
            )
            for i, chunk_text in enumerate(text_chunks)
        ]

    def get_content(self) -> str:
        header_content = self._get_header_content()
        body_content = md(self.article_artifact.content.body, heading_style="ATX")
        comments_content = self._get_comments_content()

        return f"{header_content}\n\n{body_content}\n\n## Comments:\n{comments_content}"

    def _get_user_content(self, user: ZendeskUserArtifact | None) -> str:
        if not user:
            return ""

        name: str | None = None
        if user.content.name:
            name_likely_email = "@" in user.content.name
            name = user.content.name if name_likely_email else f"@{user.content.name}"

        email = user.content.email
        id = f"@{str(user.content.id)}"

        parts: list[str | None] = [name, email, id]
        defined_parts: list[str] = [part for part in parts if part]

        return f"<{'|'.join(defined_parts)}>"

    def _get_section_content(self, section: ZendeskSection | None) -> str:
        if not section:
            return ""
        parts: list[str] = [f"@{section.name}", section.html_url, f"@{section.id}"]
        return f"<{'|'.join(parts)}>"

    def _get_category_content(self, category: ZendeskCategory | None) -> str:
        if not category:
            return ""
        parts: list[str] = [f"@{category.name}", category.html_url, f"@{category.id}"]
        return f"<{'|'.join(parts)}>"

    def _get_header_content(self) -> str:
        article = self.article_artifact.content

        section = self.section_artifact.content if self.section_artifact else None
        category = self.category_artifact.content if self.category_artifact else None

        header_lines = [
            f"# {article.title}",
            f"- Category: {self._get_category_content(category)}",
            f"- Section: {self._get_section_content(section)}",
            f"- Author: {self._get_user_content(self.user_artifacts.get(article.author_id))}",
            f"- Labels: {', '.join(article.label_names)}",
            f"- Url: {article.html_url}",
            f"- Promoted: {article.promoted}",
            f"- Draft: {article.draft}",
            f"- Votes: +{self._get_upvotes(article.vote_count, article.vote_sum)} upvotes / -{self._get_downvotes(article.vote_count, article.vote_sum)} downvotes",
            f"- Created At: {article.created_at}",
            f"- Edited At: {article.edited_at}",
            f"- Updated At: {article.updated_at}",
        ]
        return "\n".join(header_lines)

    def _get_comments_content(self) -> str:
        # Most recent first
        sorted_comments = sorted(
            self.comment_artifacts, key=lambda ca: ca.content.created_at, reverse=True
        )

        comment_texts: list[str] = [
            "\n".join(
                [
                    f"- Author: {self._get_user_content(self.user_artifacts.get(ca.content.author_id))}",
                    f"- Timestamp: {ca.content.created_at}",
                    f"- Votes: +{self._get_upvotes(ca.content.vote_count, ca.content.vote_sum)} upvotes / -{self._get_downvotes(ca.content.vote_count, ca.content.vote_sum)} downvotes",
                    md(ca.content.body, heading_style="ATX"),
                ]
            )
            for ca in sorted_comments
        ]

        return "\n\n".join(comment_texts)

    def _get_upvotes(self, vote_count: int, vote_sum: int) -> int:
        return (vote_count + vote_sum) // 2

    def _get_downvotes(self, vote_count: int, vote_sum: int) -> int:
        return vote_count - self._get_upvotes(vote_count, vote_sum)

    def get_source_enum(self) -> DocumentSource:
        return DocumentSource.ZENDESK_ARTICLE

    def get_reference_id(self) -> str:
        return zendesk_article_reference_id(self.article_artifact.metadata.article_id)

    def get_metadata(self) -> ZendeskArticleDocumentMetadata:
        return ZendeskArticleDocumentMetadata(
            article_id=self.article_artifact.metadata.article_id,
            title=self.article_artifact.content.title,
            label_names=self.article_artifact.content.label_names,
            author_id=self.article_artifact.metadata.author_id,
            section_id=self.section_artifact.metadata.section_id if self.section_artifact else None,
            section_name=self.section_artifact.content.name if self.section_artifact else None,
            category_id=self.category_artifact.metadata.category_id
            if self.category_artifact
            else None,
            category_name=self.category_artifact.content.name if self.category_artifact else None,
        )

    def get_source_created_at(self) -> datetime:
        return datetime.fromisoformat(self.article_artifact.metadata.created_at)

    @classmethod
    def from_artifacts(
        cls,
        article_artifact: ZendeskArticleArtifact,
        comment_artifacts: list[ZendeskCommentArtifact],
        user_artifacts: dict[int, ZendeskUserArtifact],
        section_artifact: ZendeskSectionArtifact | None,
        category_artifact: ZendeskCategoryArtifact | None,
    ) -> "ZendeskArticleDocument":
        return ZendeskArticleDocument(
            id=zendesk_article_document_id(article_artifact.metadata.article_id),
            article_artifact=article_artifact,
            comment_artifacts=comment_artifacts,
            user_artifacts=user_artifacts,
            section_artifact=section_artifact,
            category_artifact=category_artifact,
            permission_policy="tenant",
            permission_allowed_tokens=None,
            source_updated_at=article_artifact.source_updated_at,
        )


def zendesk_article_reference_id(article_id: int) -> str:
    return f"r_zendesk_article_{article_id}"


def zendesk_article_document_id(article_id: int) -> str:
    return f"zendesk_article_{article_id}"
