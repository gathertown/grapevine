"""OpenAI client utility for embeddings and completions."""

import logging
import sys
from pathlib import Path

import tiktoken
from openai import AsyncOpenAI, OpenAI

project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from src.utils.config import get_config_value, get_openai_api_key, get_openai_base_url
from src.utils.rate_limiter import RateLimitedError, rate_limited

logger = logging.getLogger(__name__)

MAX_RETRIES = 4  # default max_retries is 2 for openai clients

# https://platform.openai.com/docs/api-reference/embeddings/create
# We include ~16% buffer in the token threshold below to account for discrepancies between
# tiktoken and the OpenAI API.
# See more: https://gather-town.slack.com/archives/C09DAE006QY/p1757812725575839?thread_ts=1757806731.402919&cid=C09DAE006QY
MAX_TOKENS_PER_BATCH = 250000  # true limit: 300k tokens
MAX_ITEMS_PER_BATCH = 2048
MAX_TOKENS_PER_TEXT = 7000  # true limit: 8192 tokens


class OpenAIClient:
    """A client for interacting with the OpenAI API."""

    def __init__(self):
        """Initialize the OpenAI client with both sync and async clients.

        Raises:
            ValueError: If no API key is found in config/env
        """
        api_key = get_openai_api_key()
        if not api_key:
            raise ValueError("OpenAI API key not provided. Set OPENAI_API_KEY environment variable")
        base_url = get_openai_base_url()

        self.sync_client = OpenAI(api_key=api_key, base_url=base_url, max_retries=MAX_RETRIES)
        self.async_client = AsyncOpenAI(api_key=api_key, base_url=base_url, max_retries=MAX_RETRIES)
        self._api_key = api_key

    def get_embedding_model(self) -> str:
        """Get the configured embedding model name.

        Returns:
            Model name for embeddings
        """
        return get_config_value("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")

    def list_models(self) -> list[str]:
        """List all available models."""
        return self.sync_client.models.list().data  # type: ignore  # TODO fix type error here, auto-suppressed on 8/5/25

    @rate_limited()
    async def create_embedding(self, text: str, model: str | None = None) -> list[float]:
        """Create an embedding for a single text.

        Args:
            text: Text to embed
            model: Model to use. If not provided, uses configured default.
        """
        if model is None:
            model = self.get_embedding_model()

        text, _ = self._process_text_for_embedding(text)

        try:
            response = await self.async_client.embeddings.create(input=text, model=model)
            return response.data[0].embedding
        except Exception as e:
            if "rate_limit_exceeded" in str(e):
                raise RateLimitedError(retry_after=60)
            raise

    def _process_text_for_embedding(self, text: str) -> tuple[str, int]:
        """Process and validate text for embedding - tokenize once and truncate if needed.

        Returns:
            Tuple of (processed_text, token_count)

        Raises:
            ValueError: If text is an empty string
        """
        if not text:
            raise ValueError("Cannot embed empty string")

        model = self.get_embedding_model()
        encoding = tiktoken.encoding_for_model(model)
        tokens = encoding.encode(text)

        if len(tokens) > MAX_TOKENS_PER_TEXT:
            logger.warning(
                f"Text exceeds token limit ({len(tokens)} tokens), truncating to {MAX_TOKENS_PER_TEXT} tokens"
            )
            tokens = tokens[:MAX_TOKENS_PER_TEXT]
            text = encoding.decode(tokens)
            return text, MAX_TOKENS_PER_TEXT

        return text, len(tokens)

    async def create_embeddings_batch(
        self, texts: list[str], model: str | None = None
    ) -> list[list[float]]:
        """Create embeddings for multiple texts, automatically batching to respect token and array limits.

        Args:
            texts: List of texts to embed
            model: Model to use. If not provided, uses configured default.

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # Validate and process all inputs upfront, get processed texts and token counts
        processed_texts = []
        token_counts = []
        for text in texts:
            processed_text, token_count = self._process_text_for_embedding(text)
            processed_texts.append(processed_text)
            token_counts.append(token_count)

        if model is None:
            model = self.get_embedding_model()

        total_estimated_tokens = sum(token_counts)
        if (
            total_estimated_tokens <= MAX_TOKENS_PER_BATCH
            and len(processed_texts) <= MAX_ITEMS_PER_BATCH
        ):
            return await self._create_embeddings_single_batch(processed_texts, model)

        logger.info(
            f"Large batch detected ({total_estimated_tokens} estimated tokens, {len(processed_texts)} items), splitting into smaller batches"
        )

        all_embeddings: list[list[float]] = []
        current_batch: list[str] = []
        current_batch_tokens = 0

        for text, text_tokens in zip(processed_texts, token_counts, strict=True):
            # Check if adding this text would exceed either limit
            if current_batch and (
                current_batch_tokens + text_tokens > MAX_TOKENS_PER_BATCH
                or len(current_batch) >= MAX_ITEMS_PER_BATCH
            ):
                logger.info(
                    f"Processing batch of {len(current_batch)} chunks ({current_batch_tokens} tokens)"
                )
                batch_embeddings = await self._create_embeddings_single_batch(current_batch, model)
                all_embeddings.extend(batch_embeddings)
                current_batch = [text]
                current_batch_tokens = text_tokens
            else:
                current_batch.append(text)
                current_batch_tokens += text_tokens

        if current_batch:
            logger.info(
                f"Processing final batch of {len(current_batch)} chunks ({current_batch_tokens} tokens)"
            )
            batch_embeddings = await self._create_embeddings_single_batch(current_batch, model)
            all_embeddings.extend(batch_embeddings)

        logger.info(f"Processed {len(processed_texts)} texts in multiple batches")
        return all_embeddings

    @rate_limited()
    async def _create_embeddings_single_batch(
        self, texts: list[str], model: str
    ) -> list[list[float]]:
        """
        Create embeddings for a single batch that fits within limits.
        `texts` should already be validated (`_process_text_for_embedding`)!
        """
        try:
            response = await self.async_client.embeddings.create(input=texts, model=model)
            return [item.embedding for item in response.data]
        except Exception as e:
            if "rate_limit_exceeded" in str(e):
                raise RateLimitedError(retry_after=60)
            raise


# Global client instance for the generate_embeddings function
_global_client: OpenAIClient | None = None


def get_openai_client() -> OpenAIClient:
    """Get or create the global OpenAI client instance."""
    global _global_client
    if _global_client is None:
        _global_client = OpenAIClient()
    return _global_client


def get_async_openai_client() -> AsyncOpenAI:
    return get_openai_client().async_client


# Legacy functions for backward compatibility
def get_embedding_model() -> str:
    """Get the configured embedding model name.

    Returns:
        Model name for embeddings
    """
    return get_config_value("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large")
