import logging

import asyncpg

from connectors.base import BaseTransformer
from connectors.base.document_source import DocumentSource
from connectors.jira.jira_artifacts import JiraIssueArtifact
from connectors.jira.jira_issue_document import (
    JiraIssueDocument,
)
from src.ingest.repositories import ArtifactRepository

logger = logging.getLogger(__name__)


class JiraTransformer(BaseTransformer[JiraIssueDocument]):
    def __init__(self):
        super().__init__(DocumentSource.JIRA)

    async def transform_artifacts(
        self, entity_ids: list[str], readonly_db_pool: asyncpg.Pool
    ) -> list[JiraIssueDocument]:
        repo = ArtifactRepository(readonly_db_pool)

        issue_artifacts = await repo.get_artifacts_by_entity_ids(JiraIssueArtifact, entity_ids)

        logger.info(
            f"Loaded {len(issue_artifacts)} Jira issue artifacts for {len(entity_ids)} entity IDs"
        )

        documents = []
        processed_count = 0
        skipped_count = 0
        error_count = 0

        for artifact in issue_artifacts:
            try:
                document = await self._create_document(artifact)

                if document:
                    documents.append(document)
                    processed_count += 1

                    if processed_count % 100 == 0:
                        logger.info(
                            f"Processed {processed_count}/{len(issue_artifacts)} Jira issues"
                        )
                else:
                    skipped_count += 1
                    logger.warning(f"Skipped artifact {artifact.entity_id} - no document created")

            except Exception as e:
                error_count += 1
                logger.error(f"Failed to transform artifact {artifact.id}: {e}")
                continue

        logger.info(
            f"Created {len(documents)} Jira documents from {len(issue_artifacts)} artifacts "
            f"(processed: {processed_count}, skipped: {skipped_count}, errors: {error_count})"
        )
        return documents

    def _extract_text_from_jira_doc(self, doc_body) -> str:
        if isinstance(doc_body, str):
            return doc_body

        if not isinstance(doc_body, dict):
            return ""

        if doc_body.get("type") == "doc" and "content" in doc_body:
            text_parts = []
            for content_item in doc_body.get("content", []):
                if content_item.get("type") == "paragraph" and "content" in content_item:
                    for text_item in content_item.get("content", []):
                        if text_item.get("type") == "text" and "text" in text_item:
                            text_parts.append(text_item["text"])
            return " ".join(text_parts)

        return ""

    async def _create_document(self, artifact: JiraIssueArtifact) -> JiraIssueDocument | None:
        try:
            metadata = artifact.metadata
            issue_id = metadata.issue_id

            activities = []
            participants: dict[str, str] = {}  # Track all unique participants

            if metadata.assignee_id and metadata.assignee:
                participants[metadata.assignee_id] = metadata.assignee
            if metadata.reporter_id and metadata.reporter:
                participants[metadata.reporter_id] = metadata.reporter

            for comment in artifact.content.comments:
                author = comment.get("author", {})
                author_id = author.get("accountId")
                author_name = author.get("displayName", "")

                if author_id and author_name:
                    participants[author_id] = author_name

                timestamp = comment.get("created", "")
                comment_body = self._extract_text_from_jira_doc(comment.get("body", ""))
                formatted_content = (
                    f"{timestamp} <@{author_id}|@{author_name}> commented: {comment_body}"
                )

                activities.append(
                    {
                        "activity_type": "comment",
                        "content": formatted_content,
                        "actor": author_name,
                        "actor_id": author_id,
                        "timestamp": timestamp,
                        "comment_id": comment.get("id"),
                    }
                )

            url = ""
            if metadata.site_domain and metadata.issue_key:
                # site_domain already includes .atlassian.net (e.g., "company.atlassian.net")
                url = f"https://{metadata.site_domain}/browse/{metadata.issue_key}"

            assignee_text = "Unassigned"
            if metadata.assignee_id and metadata.assignee:
                assignee_text = f"<@{metadata.assignee_id}|@{metadata.assignee}>"

            participant_mentions = []
            if participants:
                for user_id, user_name in participants.items():
                    participant_mentions.append(f"<@{user_id}|@{user_name}>")

            issue_created = artifact.content.issue_data.get("fields", {}).get("created")
            if issue_created:
                from dateutil.parser import parse

                try:
                    source_created_at = parse(issue_created)
                except Exception:
                    source_created_at = artifact.source_updated_at
            else:
                source_created_at = artifact.source_updated_at

            # Format participants as mention list for header display
            participant_mentions_text = ""
            if participants:
                mentions = [
                    f"<@{user_id}|@{user_name}>" for user_id, user_name in participants.items()
                ]
                participant_mentions_text = ", ".join(mentions)

            # Format labels
            labels_text = ", ".join(metadata.labels) if metadata.labels else ""

            # Format parent issue if available
            parent_issue_text = ""
            if metadata.parent_issue_key:
                # We only have the parent issue key, not the internal ID, so use the key for both
                parent_issue_text = f"<{metadata.parent_issue_key}|{metadata.parent_issue_key}>"

            document_data = {
                "issue_id": metadata.issue_key,  # "Issue ID" field (this is the key like "ECS-6")
                "issue_internal_id": metadata.issue_id,  # Internal numeric ID
                "issue_title": metadata.issue_title,
                "issue": f"<{metadata.issue_id}|{metadata.issue_title}>",  # "Issue" field
                "url": url,  # "URL" field
                "site_domain": metadata.site_domain,  # For URL construction in header
                "assignee": assignee_text,  # "Assignee" field
                "participants": participants,  # "Participants" field (object format for OpenSearch compatibility)
                "participants_text": participant_mentions_text,  # Formatted participants for header display
                "project": f"<{metadata.project_id}|{metadata.project_name}>",  # "Project" field
                "parent_issue": parent_issue_text,  # "Parent Issue" field
                "status": metadata.status,  # "Status" field
                "priority": metadata.priority,  # "Priority" field
                "labels": metadata.labels,  # Labels array
                "labels_text": labels_text,  # Formatted labels for header display
                "activities": activities,
                "source_created_at": source_created_at.isoformat(),
                "fields": artifact.content.issue_data.get("fields", {}),
            }

            document = JiraIssueDocument(
                id=f"jira_issue_{issue_id}",
                raw_data=document_data,
                source_updated_at=artifact.source_updated_at,
                permission_policy="tenant",
                permission_allowed_tokens=None,
            )

            return document

        except Exception as e:
            logger.error(f"Failed to create document for Jira issue {artifact.entity_id}: {e}")
            return None
