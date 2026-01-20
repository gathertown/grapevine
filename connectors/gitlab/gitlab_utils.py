"""Utility functions for GitLab data normalization."""

from typing import Any

from connectors.gitlab.gitlab_artifacts import (
    GitLabApproval,
    GitLabDiff,
    GitLabMergeRequestData,
    GitLabNote,
    GitLabPipeline,
    GitLabUser,
)


def normalize_user(user_data: dict[str, Any] | None) -> GitLabUser | None:
    """Normalize a GitLab user from API response."""
    if not user_data:
        return None

    return GitLabUser(
        id=user_data.get("id"),
        username=user_data.get("username", ""),
        name=user_data.get("name"),
        avatar_url=user_data.get("avatar_url"),
        web_url=user_data.get("web_url"),
    )


def normalize_pipeline(pipeline_data: dict[str, Any] | None) -> GitLabPipeline | None:
    """Normalize a GitLab pipeline from API response."""
    if not pipeline_data:
        return None

    return GitLabPipeline(
        id=pipeline_data.get("id", 0),
        status=pipeline_data.get("status", ""),
        ref=pipeline_data.get("ref"),
        sha=pipeline_data.get("sha"),
        web_url=pipeline_data.get("web_url"),
        created_at=pipeline_data.get("created_at"),
        updated_at=pipeline_data.get("updated_at"),
    )


def normalize_mr_data(mr_data: dict[str, Any]) -> GitLabMergeRequestData:
    """Normalize merge request data from GitLab API response."""
    # Determine if merged based on state or merged_at
    state = mr_data.get("state", "")
    merged = state == "merged" or mr_data.get("merged_at") is not None

    # Normalize assignees
    assignees_raw = mr_data.get("assignees") or []
    assignees = [normalize_user(a) for a in assignees_raw if a]
    assignees = [a for a in assignees if a is not None]

    # Normalize reviewers
    reviewers_raw = mr_data.get("reviewers") or []
    reviewers = [normalize_user(r) for r in reviewers_raw if r]
    reviewers = [r for r in reviewers if r is not None]

    return GitLabMergeRequestData(
        id=mr_data.get("id", 0),
        iid=mr_data.get("iid", 0),
        title=mr_data.get("title", ""),
        description=mr_data.get("description"),
        state=state,
        draft=mr_data.get("draft", False) or mr_data.get("work_in_progress", False),
        merged=merged,
        created_at=mr_data.get("created_at"),
        updated_at=mr_data.get("updated_at"),
        closed_at=mr_data.get("closed_at"),
        merged_at=mr_data.get("merged_at"),
        author=normalize_user(mr_data.get("author")),
        assignees=assignees,  # type: ignore[arg-type]
        reviewers=reviewers,  # type: ignore[arg-type]
        merged_by=normalize_user(mr_data.get("merged_by")),
        labels=mr_data.get("labels", []),
        changes_count=mr_data.get("changes_count"),
        user_notes_count=mr_data.get("user_notes_count"),
        web_url=mr_data.get("web_url"),
        source_branch=mr_data.get("source_branch"),
        target_branch=mr_data.get("target_branch"),
        source_project_id=mr_data.get("source_project_id"),
        target_project_id=mr_data.get("target_project_id"),
        merge_commit_sha=mr_data.get("merge_commit_sha"),
        squash_commit_sha=mr_data.get("squash_commit_sha"),
        sha=mr_data.get("sha"),
        head_pipeline=normalize_pipeline(mr_data.get("head_pipeline")),
    )


def normalize_notes(notes_raw: list[dict[str, Any]]) -> list[GitLabNote]:
    """Normalize notes/comments from GitLab API response."""
    notes = []
    for note_data in notes_raw:
        note = GitLabNote(
            id=note_data.get("id", 0),
            body=note_data.get("body", ""),
            author=normalize_user(note_data.get("author")),
            created_at=note_data.get("created_at"),
            updated_at=note_data.get("updated_at"),
            system=note_data.get("system", False),
            noteable_type=note_data.get("noteable_type"),
            resolvable=note_data.get("resolvable", False),
            resolved=note_data.get("resolved", False),
        )
        notes.append(note)
    return notes


def normalize_approvals(approvals_data: dict[str, Any]) -> list[GitLabApproval]:
    """Normalize approvals from GitLab API response."""
    approvals = []
    approved_by = approvals_data.get("approved_by", [])

    for approval_data in approved_by:
        user_data = approval_data.get("user")
        user = normalize_user(user_data)
        if user:
            approval = GitLabApproval(
                user=user,
                # GitLab doesn't provide per-approval timestamps in this endpoint
                approved_at=None,
            )
            approvals.append(approval)

    return approvals


def normalize_diffs(diffs_raw: list[dict[str, Any]]) -> list[GitLabDiff]:
    """Normalize diffs/file changes from GitLab API response."""
    diffs = []
    for diff_data in diffs_raw:
        diff = GitLabDiff(
            old_path=diff_data.get("old_path", ""),
            new_path=diff_data.get("new_path", ""),
            a_mode=diff_data.get("a_mode"),
            b_mode=diff_data.get("b_mode"),
            new_file=diff_data.get("new_file", False),
            renamed_file=diff_data.get("renamed_file", False),
            deleted_file=diff_data.get("deleted_file", False),
            diff=diff_data.get("diff"),
        )
        diffs.append(diff)
    return diffs
