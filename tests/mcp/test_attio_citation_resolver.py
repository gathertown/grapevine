"""Tests for Attio citation resolvers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from connectors.attio.attio_citation_resolver import (
    AttioCompanyCitationResolver,
    AttioDealCitationResolver,
    AttioPersonCitationResolver,
)
from connectors.attio.attio_company_document import AttioCompanyDocumentMetadata
from connectors.attio.attio_deal_document import AttioDealDocumentMetadata
from connectors.attio.attio_person_document import AttioPersonDocumentMetadata
from connectors.base.document_source import DocumentSource, DocumentWithSourceAndMetadata


@pytest.fixture
def mock_workspace_slug():
    """Fixture to mock get_config_value_with_pool for workspace slug."""

    def _mock(workspace_slug: str | None):
        return patch(
            "connectors.attio.attio_citation_resolver.get_config_value_with_pool",
            new_callable=AsyncMock,
            return_value=workspace_slug,
        )

    return _mock


def create_mock_citation_resolver() -> MagicMock:
    """Create a mock CitationResolver."""
    mock_resolver = MagicMock()
    mock_resolver.tenant_id = "test-tenant"
    mock_resolver.db_pool = MagicMock()
    return mock_resolver


class TestAttioCompanyCitationResolver:
    """Test suite for AttioCompanyCitationResolver."""

    @pytest.mark.asyncio
    async def test_resolve_citation_success(self, mock_workspace_slug):
        """Test that company citation resolver generates correct URL."""
        resolver = AttioCompanyCitationResolver()

        document = DocumentWithSourceAndMetadata(
            id="attio_company_rec_abc123",
            source=DocumentSource.ATTIO_COMPANY,
            metadata=AttioCompanyDocumentMetadata(
                company_id="rec_abc123",
                company_name="Acme Corporation",
                source="attio_company",
                type="attio_company",
            ),
        )

        mock_citation_resolver = create_mock_citation_resolver()

        with mock_workspace_slug("grapevineai"):
            url = await resolver.resolve_citation(
                document, excerpt="some excerpt", resolver=mock_citation_resolver
            )

        assert url == "https://app.attio.com/grapevineai/company/rec_abc123/overview"

    @pytest.mark.asyncio
    async def test_resolve_citation_missing_company_id(self, mock_workspace_slug):
        """Test that empty string is returned when company_id is empty."""
        resolver = AttioCompanyCitationResolver()

        document = DocumentWithSourceAndMetadata(
            id="attio_company_unknown",
            source=DocumentSource.ATTIO_COMPANY,
            metadata=AttioCompanyDocumentMetadata(
                company_id="",
                company_name="Unknown Company",
                source="attio_company",
                type="attio_company",
            ),
        )

        mock_citation_resolver = create_mock_citation_resolver()

        with mock_workspace_slug("grapevineai"):
            url = await resolver.resolve_citation(
                document, excerpt="some excerpt", resolver=mock_citation_resolver
            )

        assert url == ""

    @pytest.mark.asyncio
    async def test_resolve_citation_missing_workspace_slug(self, mock_workspace_slug):
        """Test that empty string is returned when workspace_slug is not configured."""
        resolver = AttioCompanyCitationResolver()

        document = DocumentWithSourceAndMetadata(
            id="attio_company_rec_abc123",
            source=DocumentSource.ATTIO_COMPANY,
            metadata=AttioCompanyDocumentMetadata(
                company_id="rec_abc123",
                company_name="Acme Corporation",
                source="attio_company",
                type="attio_company",
            ),
        )

        mock_citation_resolver = create_mock_citation_resolver()

        with mock_workspace_slug(None):
            url = await resolver.resolve_citation(
                document, excerpt="some excerpt", resolver=mock_citation_resolver
            )

        assert url == ""


class TestAttioPersonCitationResolver:
    """Test suite for AttioPersonCitationResolver."""

    @pytest.mark.asyncio
    async def test_resolve_citation_success(self, mock_workspace_slug):
        """Test that person citation resolver generates correct URL."""
        resolver = AttioPersonCitationResolver()

        document = DocumentWithSourceAndMetadata(
            id="attio_person_rec_person456",
            source=DocumentSource.ATTIO_PERSON,
            metadata=AttioPersonDocumentMetadata(
                person_id="rec_person456",
                person_name="John Doe",
                source="attio_person",
                type="attio_person",
            ),
        )

        mock_citation_resolver = create_mock_citation_resolver()

        with mock_workspace_slug("grapevineai"):
            url = await resolver.resolve_citation(
                document, excerpt="some excerpt", resolver=mock_citation_resolver
            )

        assert url == "https://app.attio.com/grapevineai/person/rec_person456/overview"

    @pytest.mark.asyncio
    async def test_resolve_citation_missing_person_id(self, mock_workspace_slug):
        """Test that empty string is returned when person_id is empty."""
        resolver = AttioPersonCitationResolver()

        document = DocumentWithSourceAndMetadata(
            id="attio_person_unknown",
            source=DocumentSource.ATTIO_PERSON,
            metadata=AttioPersonDocumentMetadata(
                person_id="",
                person_name="Unknown Person",
                source="attio_person",
                type="attio_person",
            ),
        )

        mock_citation_resolver = create_mock_citation_resolver()

        with mock_workspace_slug("grapevineai"):
            url = await resolver.resolve_citation(
                document, excerpt="some excerpt", resolver=mock_citation_resolver
            )

        assert url == ""

    @pytest.mark.asyncio
    async def test_resolve_citation_missing_workspace_slug(self, mock_workspace_slug):
        """Test that empty string is returned when workspace_slug is not configured."""
        resolver = AttioPersonCitationResolver()

        document = DocumentWithSourceAndMetadata(
            id="attio_person_rec_person456",
            source=DocumentSource.ATTIO_PERSON,
            metadata=AttioPersonDocumentMetadata(
                person_id="rec_person456",
                person_name="John Doe",
                source="attio_person",
                type="attio_person",
            ),
        )

        mock_citation_resolver = create_mock_citation_resolver()

        with mock_workspace_slug(None):
            url = await resolver.resolve_citation(
                document, excerpt="some excerpt", resolver=mock_citation_resolver
            )

        assert url == ""


class TestAttioDealCitationResolver:
    """Test suite for AttioDealCitationResolver."""

    @pytest.mark.asyncio
    async def test_resolve_citation_success(self, mock_workspace_slug):
        """Test that deal citation resolver generates correct URL."""
        resolver = AttioDealCitationResolver()

        document = DocumentWithSourceAndMetadata(
            id="attio_deal_rec_deal789",
            source=DocumentSource.ATTIO_DEAL,
            metadata=AttioDealDocumentMetadata(
                deal_id="rec_deal789",
                deal_name="Enterprise Deal",
                source="attio_deal",
                type="attio_deal",
            ),
        )

        mock_citation_resolver = create_mock_citation_resolver()

        with mock_workspace_slug("grapevineai"):
            url = await resolver.resolve_citation(
                document, excerpt="some excerpt", resolver=mock_citation_resolver
            )

        assert url == "https://app.attio.com/grapevineai/deal/rec_deal789/overview"

    @pytest.mark.asyncio
    async def test_resolve_citation_missing_deal_id(self, mock_workspace_slug):
        """Test that empty string is returned when deal_id is missing."""
        resolver = AttioDealCitationResolver()

        document = DocumentWithSourceAndMetadata(
            id="attio_deal_unknown",
            source=DocumentSource.ATTIO_DEAL,
            metadata=AttioDealDocumentMetadata(
                deal_id=None,
                deal_name="Unknown Deal",
                source="attio_deal",
                type="attio_deal",
            ),
        )

        mock_citation_resolver = create_mock_citation_resolver()

        with mock_workspace_slug("grapevineai"):
            url = await resolver.resolve_citation(
                document, excerpt="some excerpt", resolver=mock_citation_resolver
            )

        assert url == ""

    @pytest.mark.asyncio
    async def test_resolve_citation_with_uuid_format(self, mock_workspace_slug):
        """Test that deal citation resolver handles UUID-format record IDs."""
        resolver = AttioDealCitationResolver()

        document = DocumentWithSourceAndMetadata(
            id="attio_deal_853cfb93-63e7-4eed-82e4-50e4fa054e59",
            source=DocumentSource.ATTIO_DEAL,
            metadata=AttioDealDocumentMetadata(
                deal_id="853cfb93-63e7-4eed-82e4-50e4fa054e59",
                deal_name="Lead 123",
                source="attio_deal",
                type="attio_deal",
            ),
        )

        mock_citation_resolver = create_mock_citation_resolver()

        with mock_workspace_slug("grapevineai"):
            url = await resolver.resolve_citation(
                document, excerpt="some excerpt", resolver=mock_citation_resolver
            )

        assert (
            url
            == "https://app.attio.com/grapevineai/deal/853cfb93-63e7-4eed-82e4-50e4fa054e59/overview"
        )

    @pytest.mark.asyncio
    async def test_resolve_citation_missing_workspace_slug(self, mock_workspace_slug):
        """Test that empty string is returned when workspace_slug is not configured."""
        resolver = AttioDealCitationResolver()

        document = DocumentWithSourceAndMetadata(
            id="attio_deal_rec_deal789",
            source=DocumentSource.ATTIO_DEAL,
            metadata=AttioDealDocumentMetadata(
                deal_id="rec_deal789",
                deal_name="Enterprise Deal",
                source="attio_deal",
                type="attio_deal",
            ),
        )

        mock_citation_resolver = create_mock_citation_resolver()

        with mock_workspace_slug(None):
            url = await resolver.resolve_citation(
                document, excerpt="some excerpt", resolver=mock_citation_resolver
            )

        assert url == ""
