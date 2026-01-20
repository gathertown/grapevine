"""Tests for the webhook verifier registry and factory.

This module tests:
1. All source types have registered verifiers
2. The get_verifier factory correctly returns verifiers
3. Unknown source types return None
4. String and enum lookups both work
"""

import pytest

from src.ingest.gatekeeper.verifier_registry import (
    WebhookSourceType,
    get_all_source_types,
    get_verifier,
)


class TestWebhookSourceType:
    """Test the WebhookSourceType enum."""

    def test_all_expected_sources_exist(self):
        """Test that all expected source types are defined."""
        expected_sources = {
            "github",
            "slack",
            "linear",
            "notion",
            "google_email",
            "google_drive",
            "jira",
            "confluence",
            "gather",
            "trello",
            "gong",
            "hubspot",
            "attio",
        }
        actual_sources = {s.value for s in WebhookSourceType}
        assert actual_sources == expected_sources

    def test_source_type_is_string_enum(self):
        """Test that WebhookSourceType values are strings."""
        for source in WebhookSourceType:
            assert isinstance(source.value, str)
            assert source == source.value  # str enum comparison


class TestGetVerifier:
    """Test the get_verifier factory function."""

    @pytest.mark.parametrize("source_type", list(WebhookSourceType))
    def test_all_source_types_have_verifiers(self, source_type):
        """Test that every registered source type has a verifier."""
        verifier = get_verifier(source_type)
        assert verifier is not None
        # Verify it has the expected interface
        assert hasattr(verifier, "verify")
        assert callable(verifier.verify)

    @pytest.mark.parametrize(
        "source_string",
        ["github", "slack", "linear", "notion", "google_email", "hubspot"],
    )
    def test_string_lookup_works(self, source_string):
        """Test that verifiers can be looked up by string value."""
        verifier = get_verifier(source_string)
        assert verifier is not None

    def test_unknown_source_returns_none(self):
        """Test that unknown source types return None."""
        verifier = get_verifier("salesforce")
        assert verifier is None

        verifier = get_verifier("unknown_source")
        assert verifier is None

    def test_enum_and_string_return_same_verifier(self):
        """Test that enum and string lookups return the same verifier instance."""
        enum_verifier = get_verifier(WebhookSourceType.GITHUB)
        string_verifier = get_verifier("github")
        # Same instance (registry is cached)
        assert enum_verifier is string_verifier


class TestGetAllSourceTypes:
    """Test the get_all_source_types function."""

    def test_returns_all_source_types(self):
        """Test that get_all_source_types returns all enum values."""
        all_types = get_all_source_types()
        assert len(all_types) == len(WebhookSourceType)
        for source_type in WebhookSourceType:
            assert source_type in all_types


class TestVerifierProtocolCompliance:
    """Test that all verifiers comply with the WebhookVerifier protocol."""

    @pytest.mark.parametrize("source_type", list(WebhookSourceType))
    def test_verifier_has_verify_method(self, source_type):
        """Test that all verifiers have an async verify method with correct signature."""
        verifier = get_verifier(source_type)
        assert verifier is not None

        # Check the verify method exists and is callable
        assert hasattr(verifier, "verify")

        # Check it's a coroutine function (async)
        import inspect

        assert inspect.iscoroutinefunction(verifier.verify)
