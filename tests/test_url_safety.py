"""URL safety validators (git remote SSRF guards)."""

from __future__ import annotations

import pytest

from web.backend.services.url_safety import validate_git_remote_url


def test_validate_git_remote_accepts_github_https():
    assert validate_git_remote_url("https://github.com/org/repo.git") == (
        "https://github.com/org/repo.git"
    )


def test_validate_git_remote_rejects_private_ip():
    with pytest.raises(ValueError, match="private"):
        validate_git_remote_url("https://192.168.1.1/repo.git")


def test_validate_git_remote_rejects_localhost():
    with pytest.raises(ValueError, match="not allowed"):
        validate_git_remote_url("https://localhost/repo.git")


def test_validate_git_remote_rejects_http():
    with pytest.raises(ValueError, match="https"):
        validate_git_remote_url("http://github.com/org/repo.git")


def test_validate_git_remote_rejects_unknown_host():
    with pytest.raises(ValueError, match="github"):
        validate_git_remote_url("https://evil.example.com/repo.git")
