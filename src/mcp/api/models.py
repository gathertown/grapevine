"""API models for the agent endpoints."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class FileAttachment(BaseModel):
    name: str
    mimetype: str
    content: str  # Base64 encoded content


class AskRequest(BaseModel):
    query: str
    previous_response_id: str | None = None
    files: list[FileAttachment] = []


class AgentDecision(BaseModel):
    """Pydantic model for agent decision responses with structured outputs."""

    decision: Literal["continue", "finish"]
    confidence: Literal["high", "medium", "low"]
    final_answer: str | None = Field(None, description="The final answer when decision is 'finish'")

    @model_validator(mode="before")
    @classmethod
    def validate_final_answer(cls, values):
        """Custom validation to ensure final_answer is only set when decision is 'finish'."""
        if isinstance(values, dict):
            if values.get("decision") == "finish" and "final_answer" not in values:
                raise ValueError("final_answer is required when decision is 'finish'")
            elif values.get("decision") == "continue" and "final_answer" in values:
                # Remove final_answer if decision is continue
                values = {k: v for k, v in values.items() if k != "final_answer"}
        return values
