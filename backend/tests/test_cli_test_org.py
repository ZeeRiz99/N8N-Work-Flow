"""Dev-only org helpers used by the UI audit: they never touch the demo organizations."""

import sys

import pytest

from app import cli
from app.core.config import get_settings


@pytest.mark.parametrize("slug", ["harbor-web", "portfolio-studio"])
def test_delete_org_refuses_the_demo_organizations(monkeypatch, slug):
    monkeypatch.setattr(get_settings(), "app_env", "development")
    monkeypatch.setattr(sys, "argv", ["cli", "delete-org", slug])
    assert cli.delete_org() == 1


def test_test_org_helpers_are_development_only(monkeypatch):
    monkeypatch.setattr(get_settings(), "app_env", "production")
    monkeypatch.setattr(sys, "argv", ["cli", "delete-org", "anything"])
    assert cli.delete_org() == 1
    monkeypatch.setattr(sys, "argv", ["cli", "create-test-org", "anything"])
    assert cli.create_test_org() == 1
