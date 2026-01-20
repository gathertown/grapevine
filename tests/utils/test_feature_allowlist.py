import pytest

from src.utils.feature_allowlist import (
    FeatureKeys,
    configure_in_memory_allowlist,
    get_tenant_features,
    is_feature_allowed_in_env,
    is_feature_enabled,
    list_all_features,
    reset_in_memory_allowlist,
)


def test_environment_defaults(monkeypatch):
    monkeypatch.setenv("GRAPEVINE_ENVIRONMENT", "local")

    assert is_feature_allowed_in_env(FeatureKeys.DUMMY_FEATURE)

    monkeypatch.setenv("GRAPEVINE_ENVIRONMENT", "production")

    assert not is_feature_allowed_in_env(FeatureKeys.DUMMY_FEATURE)


@pytest.mark.asyncio
async def test_is_feature_enabled_respects_allowlist(monkeypatch):
    tenant_id = "tenant-abc"
    monkeypatch.setenv("GRAPEVINE_ENVIRONMENT", "production")

    reset_in_memory_allowlist()
    assert not await is_feature_enabled(tenant_id, FeatureKeys.DUMMY_FEATURE)

    configure_in_memory_allowlist({tenant_id: [FeatureKeys.DUMMY_FEATURE]})

    assert await is_feature_enabled(tenant_id, FeatureKeys.DUMMY_FEATURE)


@pytest.mark.asyncio
async def test_get_tenant_features_returns_copy(monkeypatch):
    tenant_id = "tenant-xyz"
    monkeypatch.setenv("GRAPEVINE_ENVIRONMENT", "production")

    configure_in_memory_allowlist({tenant_id: [FeatureKeys.DUMMY_FEATURE]})
    features = await get_tenant_features(tenant_id)

    assert FeatureKeys.DUMMY_FEATURE in features


def test_list_all_features_contains_defined_keys():
    all_keys = list_all_features()

    assert FeatureKeys.DUMMY_FEATURE in all_keys
