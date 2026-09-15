"""A deploy that exits 0 is not published if nobody outside the account can open it."""

import urllib.error
import urllib.request

import pytest

from web.backend.services.auto_publish import verify_published_url


class _Resp:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _patch_opener(monkeypatch, behaviour):
    class _Opener:
        def open(self, req, timeout=None):
            return behaviour(req)

    monkeypatch.setattr(urllib.request, "build_opener", lambda *a, **k: _Opener())


def test_a_serving_deployment_is_reachable(monkeypatch):
    _patch_opener(monkeypatch, lambda req: _Resp(200))
    out = verify_published_url("https://x.vercel.app")
    assert out["reachable"] is True
    assert out["status"] == 200


def test_vercel_sso_redirect_is_not_published(monkeypatch):
    """The real finding: every product on the account 302s to sso-api."""

    def behaviour(req):
        raise urllib.error.HTTPError(
            req.full_url, 302, "Found",
            {"location": "https://vercel.com/sso-api?url=https%3A%2F%2Fx.vercel.app"}, None,
        )

    _patch_opener(monkeypatch, behaviour)
    out = verify_published_url("https://x.vercel.app")
    assert out["reachable"] is False
    assert out["reason"] == "deployment_protection"
    assert "Deployment Protection" in out["detail"]


def test_an_ordinary_in_app_redirect_is_fine(monkeypatch):
    def behaviour(req):
        raise urllib.error.HTTPError(
            req.full_url, 302, "Found", {"location": "https://x.vercel.app/login"}, None
        )

    _patch_opener(monkeypatch, behaviour)
    out = verify_published_url("https://x.vercel.app")
    assert out["reachable"] is True


def test_unreachable_host_is_reported(monkeypatch):
    def behaviour(req):
        raise urllib.error.URLError("name or service not known")

    _patch_opener(monkeypatch, behaviour)
    out = verify_published_url("https://nope.vercel.app")
    assert out["reachable"] is False
    assert out["reason"].startswith("unreachable:")


def test_no_url_is_not_reachable():
    assert verify_published_url("")["reason"] == "no_url"
