"""Token counting utilities for OpenAI models."""

from typing import Any

import tiktoken


def _get_encoding_for_model(model: str):
    """Get tiktoken encoding for model with safe fallbacks.

    Falls back to a generic encoding when the model is unknown (e.g., 'gpt-5').
    """
    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        # Prefer o200k_base if available, else cl100k_base
        try:
            return tiktoken.get_encoding("o200k_base")
        except Exception:
            return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str, model: str) -> int:
    encoding = _get_encoding_for_model(model)
    return len(encoding.encode(text or ""))


def count_messages_tokens(messages: list[dict[str, Any]], model: str) -> int:
    """Calculate total tokens in a conversation including message formatting overhead."""
    # Token counts for message formatting (based on OpenAI's guidelines)
    tokens_per_message = 3  # <|start|>role<|end|>
    tokens_per_name = 1

    total_tokens = 0

    for message in messages:
        total_tokens += tokens_per_message

        # Count tokens in each field
        if "role" in message:
            total_tokens += count_tokens(message["role"], model)

        if "content" in message:
            content = message["content"]
            if isinstance(content, str):
                # Simple string content
                total_tokens += count_tokens(content, model)
            elif isinstance(content, list):
                # Array content (with files/images)
                for item in content:
                    if isinstance(item, dict) and "text" in item:
                        total_tokens += count_tokens(item["text"], model)
                    # Note: We can't easily count tokens for images, so we skip them
            else:
                # Fallback: convert to string
                total_tokens += count_tokens(str(content), model)

        if "name" in message:
            total_tokens += tokens_per_name
            total_tokens += count_tokens(message["name"], model)

        # Handle function call outputs
        if "type" in message and message["type"] == "function_call_output":
            if "call_id" in message:
                total_tokens += count_tokens(message["call_id"], model)
            if "output" in message:
                total_tokens += count_tokens(message["output"], model)

    total_tokens += 3  # Every reply is primed with <|start|>assistant<|end|>

    return total_tokens
