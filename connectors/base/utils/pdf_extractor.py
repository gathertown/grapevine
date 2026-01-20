import io
import logging

from markitdown import MarkItDown

logger = logging.getLogger(__name__)

# Suppress pdfminer warnings
logging.getLogger("pdfminer").setLevel(logging.ERROR)


def extract_pdf_text(pdf_bytes: bytes, source_identifier: str) -> str:
    """Extract text content from a PDF.

    Args:
        pdf_bytes: Raw PDF file bytes
        source_identifier: Identifier for logging (e.g., file ID or name)

    Returns:
        Extracted text content, or empty string if extraction fails
    """
    try:
        md = MarkItDown()
        pdf_stream = io.BytesIO(pdf_bytes)
        result = md.convert(pdf_stream)

        extracted_text = result.text_content.strip()

        if extracted_text:
            logger.debug(f"Extracted {len(extracted_text)} characters from {source_identifier}")
            return extracted_text
        else:
            logger.warning(f"No text content extracted from {source_identifier}")
            return ""

    except Exception as e:
        logger.error(f"Failed to extract text from {source_identifier}: {e}")
        return ""
