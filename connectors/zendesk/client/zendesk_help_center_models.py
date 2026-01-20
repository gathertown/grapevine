from pydantic import BaseModel

from connectors.zendesk.client.zendesk_models import ZendeskPageMetadata


class ZendeskArticle(BaseModel):
    id: int

    title: str
    body: str
    draft: bool
    comments_disabled: bool
    promoted: bool
    label_names: list[str]
    html_url: str
    vote_count: int
    vote_sum: int

    author_id: int
    content_tag_ids: list[int]
    section_id: int

    created_at: str
    updated_at: str
    edited_at: str


class ZendeskSection(BaseModel):
    id: int

    name: str
    description: str | None
    html_url: str

    created_at: str
    updated_at: str

    category_id: int
    parent_section_id: int | None


class ZendeskCategory(BaseModel):
    id: int

    name: str
    description: str | None
    html_url: str

    created_at: str
    updated_at: str


class ZendeskComment(BaseModel):
    id: int

    body: str
    html_url: str
    vote_count: int
    vote_sum: int

    created_at: str
    updated_at: str

    author_id: int
    source_id: int  # will be an article id
    source_type: str  # Article


class ZendeskIncrementalArticlesRes(BaseModel):
    next_page: str | None
    end_time: int
    articles: list[ZendeskArticle]

    # These are missing if no articles
    sections: list[ZendeskSection] = []
    categories: list[ZendeskCategory] = []


class ZendeskCommentRes(BaseModel):
    meta: ZendeskPageMetadata
    comments: list[ZendeskComment]
