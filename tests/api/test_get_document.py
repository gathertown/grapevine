"""Integration tests for get_document function with document ID fixing."""

import pytest

import src.mcp.tools.get_document as get_document_module
from src.clients.supabase import get_global_db_connection

# Extract the actual function from the MCP decorated object
get_document = get_document_module.get_document.fn


@pytest.mark.skip(reason="Needs local test environment - integration test requires database")
class TestGetDocumentSlashFix:
    """Integration tests for get_document with GITHUB_CODE document ID slash fixing."""

    async def _check_document_exists(self, doc_id: str) -> None:
        """Check if document exists in database, skip test if not found."""
        conn = await get_global_db_connection()
        try:
            row = await conn.fetchrow("SELECT id FROM documents WHERE id = $1", doc_id)
            if not row:
                pytest.skip(f"Test document {doc_id} not found in database")
        finally:
            await conn.close()

    def _assert_valid_get_document_result(self, result: dict, expected_doc_id: str) -> None:
        """Assert that get_document result has valid structure and content."""
        assert "document_id" in result
        assert "content" in result
        assert result["document_id"] == expected_doc_id
        assert isinstance(result["content"], str)
        assert len(result["content"]) > 0  # Should have actual content

    @pytest.mark.asyncio
    async def test_get_document_with_underscore_format(self):
        """Test that document lookup works with proper underscore format."""
        doc_id = "github_file_gather-town-v2_modules_gather-game-logic_src_framework_serialization_ExtensionCodec.ts"

        await self._check_document_exists(doc_id)
        result = await get_document(doc_id)
        self._assert_valid_get_document_result(result, doc_id)

    @pytest.mark.asyncio
    async def test_get_document_with_slash_format_gets_fixed(self):
        """Test that document lookup works when slash format is provided and gets fixed."""
        slash_doc_id = "github_file_gather-town-v2_modules_gather-game-logic_src_framework/serialization/ExtensionCodec.ts"
        fixed_doc_id = "github_file_gather-town-v2_modules_gather-game-logic_src_framework_serialization_ExtensionCodec.ts"

        await self._check_document_exists(fixed_doc_id)
        result = await get_document(slash_doc_id)
        self._assert_valid_get_document_result(result, fixed_doc_id)
