"""The seeded demo login must survive the products' own email validation."""

import pytest

from core.demo_identity import (
    DEFAULT_DEMO_EMAIL,
    is_special_use_email,
    sandbox_demo_email,
    sane_demo_email,
)


@pytest.mark.parametrize(
    "email",
    [
        "sandbox.demo@aicom.local",
        "a@b.test",
        "a@b.invalid",
        "a@localhost",
        "a@x.onion",
    ],
)
def test_reserved_tlds_are_flagged(email):
    assert is_special_use_email(email) is True


@pytest.mark.parametrize("email", ["demo@example.com", "a@magic-ai-factory.com", "x@sub.co.uk"])
def test_ordinary_domains_pass_through(email):
    assert is_special_use_email(email) is False
    assert sane_demo_email(email) == email


def test_local_part_is_preserved_when_repairing():
    assert sane_demo_email("sandbox.demo@aicom.local") == "sandbox.demo@magic-ai-factory.com"
    assert sane_demo_email("ops.team@corp.test") == "ops.team@magic-ai-factory.com"


def test_blank_and_malformed_fall_back_to_default():
    assert sane_demo_email("") == DEFAULT_DEMO_EMAIL
    assert sane_demo_email(None) == DEFAULT_DEMO_EMAIL
    assert sane_demo_email("not-an-email") == DEFAULT_DEMO_EMAIL


def test_env_configured_reserved_address_is_repaired(monkeypatch):
    monkeypatch.setenv("AIFACTORY_SANDBOX_DEMO_EMAIL", "sandbox.demo@aicom.local")
    assert sandbox_demo_email() == "sandbox.demo@magic-ai-factory.com"


def test_repaired_address_passes_email_validator():
    """The whole point: pydantic EmailStr must accept what the factory seeds."""
    email_validator = pytest.importorskip("email_validator")
    with pytest.raises(email_validator.EmailNotValidError):
        email_validator.validate_email("sandbox.demo@aicom.local", check_deliverability=False)
    email_validator.validate_email(
        sane_demo_email("sandbox.demo@aicom.local"), check_deliverability=False
    )
