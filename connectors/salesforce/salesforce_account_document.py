"""
Salesforce Account document and chunk classes.
"""

from dataclasses import dataclass

from connectors.salesforce.salesforce_artifacts import SUPPORTED_SALESFORCE_OBJECTS
from connectors.salesforce.salesforce_base_document import (
    BaseSalesforceChunk,
    BaseSalesforceDocument,
    BaseSalesforceDocumentMetadata,
)
from src.utils.type_conversion import safe_float, safe_int


class SalesforceAccountDocumentMetadata(BaseSalesforceDocumentMetadata):
    """Metadata for Salesforce Account documents."""

    account_type: str | None
    industry: str | None
    annual_revenue: float | None
    number_of_employees: int | None
    website: str | None
    account_number: str | None
    site: str | None
    ticker_symbol: str | None
    ownership: str | None
    rating: str | None
    sic_desc: str | None
    fax: str | None
    year_started: str | None


@dataclass
class SalesforceAccountChunk(BaseSalesforceChunk):
    """Represents a single Salesforce Account chunk."""


@dataclass
class SalesforceAccountDocument(BaseSalesforceDocument):
    """Represents a Salesforce Account as a document."""

    def get_content(self) -> str:
        """Get the formatted Account record content."""
        record_data = self.raw_data.get("record_data", {})
        if not record_data:
            return "Account: [No data available]"

        lines = []

        # Header
        name = record_data.get("Name", "Unknown Account")
        lines.append(f"Account: {name}")
        lines.append("")

        # Key fields
        if record_data.get("AccountNumber"):
            lines.append(f"Account Number: {record_data['AccountNumber']}")
        if record_data.get("Type"):
            lines.append(f"Type: {record_data['Type']}")
        if record_data.get("Industry"):
            lines.append(f"Industry: {record_data['Industry']}")
        if record_data.get("Website"):
            lines.append(f"Website: {record_data['Website']}")
        if record_data.get("Phone"):
            lines.append(f"Phone: {record_data['Phone']}")
        if record_data.get("Fax"):
            lines.append(f"Fax: {record_data['Fax']}")
        if record_data.get("NumberOfEmployees"):
            lines.append(f"Employees: {record_data['NumberOfEmployees']}")
        if record_data.get("Site"):
            lines.append(f"Site: {record_data['Site']}")
        if record_data.get("TickerSymbol"):
            lines.append(f"Ticker Symbol: {record_data['TickerSymbol']}")
        if record_data.get("Ownership"):
            lines.append(f"Ownership: {record_data['Ownership']}")
        if record_data.get("Rating"):
            lines.append(f"Rating: {record_data['Rating']}")
        if record_data.get("SicDesc"):
            lines.append(f"Industry Classification: {record_data['SicDesc']}")
        if record_data.get("YearStarted"):
            lines.append(f"Year Started: {record_data['YearStarted']}")

        # Annual Revenue
        if record_data.get("AnnualRevenue"):
            revenue_str = self._format_currency(record_data["AnnualRevenue"])
            if revenue_str:
                lines.append(f"Annual Revenue: {revenue_str}")

        # Billing Address
        billing_address = self._format_address(
            "BillingStreet",
            "BillingCity",
            "BillingState",
            "BillingPostalCode",
            "BillingCountry",
            record_data,
        )
        if billing_address:
            lines.append(f"Billing Address: {billing_address}")

        # Shipping Address
        shipping_address = self._format_address(
            "ShippingStreet",
            "ShippingCity",
            "ShippingState",
            "ShippingPostalCode",
            "ShippingCountry",
            record_data,
        )
        if shipping_address:
            lines.append(f"Shipping Address: {shipping_address}")

        # Parent Account
        if record_data.get("Parent", {}).get("Name"):
            lines.append(f"Parent Account: {record_data['Parent']['Name']}")

        # Description
        if record_data.get("Description"):
            lines.extend(["", "Description:", record_data["Description"]])

        # Custom fields
        lines.extend(self._format_custom_fields(record_data))

        return "\n".join(lines)

    def _create_chunk(self) -> SalesforceAccountChunk:
        """Create an Account-specific chunk."""
        return SalesforceAccountChunk(
            document=self,
            raw_data=self.raw_data,
        )

    def get_object_type(self) -> SUPPORTED_SALESFORCE_OBJECTS:
        return "Account"

    def get_metadata(self) -> SalesforceAccountDocumentMetadata:
        """Get Account-specific document metadata."""
        base_metadata = super().get_metadata()
        record_data = self.raw_data.get("record_data", {})

        # Convert to Account-specific metadata
        account_metadata: SalesforceAccountDocumentMetadata = {
            **base_metadata,
            "account_type": record_data.get("Type"),
            "industry": record_data.get("Industry"),
            "annual_revenue": safe_float(record_data.get("AnnualRevenue")),
            "number_of_employees": safe_int(record_data.get("NumberOfEmployees")),
            "website": record_data.get("Website"),
            "account_number": record_data.get("AccountNumber"),
            "site": record_data.get("Site"),
            "ticker_symbol": record_data.get("TickerSymbol"),
            "ownership": record_data.get("Ownership"),
            "rating": record_data.get("Rating"),
            "sic_desc": record_data.get("SicDesc"),
            "fax": record_data.get("Fax"),
            "year_started": record_data.get("YearStarted"),
        }
        return account_metadata
