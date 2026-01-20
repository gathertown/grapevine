from datetime import datetime

from pydantic import AliasChoices, BaseModel, Field

from connectors.fireflies.client.fireflies_errors import FirefliesResError


class GetFirefliesTranscriptsReq(BaseModel):
    # date filering is inclusive and down to the ms precision
    from_date: datetime | None
    to_date: datetime | None
    page_size: int = 50


class GetFirefliesTranscriptsVariables(BaseModel):
    # date filering is inclusive and down to the ms precision
    from_date: str | None
    to_date: str | None
    limit: int = 50
    skip: int = 0

    @classmethod
    def from_req(cls, req: GetFirefliesTranscriptsReq) -> "GetFirefliesTranscriptsVariables":
        return GetFirefliesTranscriptsVariables(
            from_date=req.from_date.isoformat() if req.from_date else None,
            to_date=req.to_date.isoformat() if req.to_date else None,
            limit=req.page_size,
        )


class FirefliesSpeaker(BaseModel):
    id: int
    name: str | None


class FirefliesSummary(BaseModel):
    notes: str | None


class FirefliesSentence(BaseModel):
    text: str
    speaker_id: int | None


class FirefliesMeetingInfo(BaseModel):
    summary_status: str | None  # processing | processed | failed | skipped


class FirefliesTranscript(BaseModel):
    id: str
    # Comes from the api as dateString, everywhere else as date_string
    date_string: str = Field(validation_alias=AliasChoices("dateString", "date_string"))
    transcript_url: str

    title: str | None
    organizer_email: str | None
    # list of email addresses invited to the meeting (includes non-fireflies users)
    participants: list[str]

    # duration in minutes
    duration: float | None

    meeting_info: FirefliesMeetingInfo
    speakers: list[FirefliesSpeaker] | None
    summary: FirefliesSummary | None
    sentences: list[FirefliesSentence] | None


class FirefliesTranscriptsResData(BaseModel):
    transcripts: list[FirefliesTranscript]


class FirefliesGraphqlRes[T](BaseModel):
    data: T | None = None
    errors: list[FirefliesResError] | None = None


class FirefliesTranscriptsRes(BaseModel):
    data: FirefliesTranscriptsResData


class FirefliesTranscriptResData(BaseModel):
    transcript: FirefliesTranscript


class FirefliesTranscriptRes(BaseModel):
    data: FirefliesTranscriptResData
