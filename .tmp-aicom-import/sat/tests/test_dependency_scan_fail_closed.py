"""An unavailable or truncated vulnerability database must not greenlight a build."""
import io
import json
import urllib.error

import pytest

from scripts import dependency_scan as scan


@pytest.fixture
def one_package(monkeypatch):
    key = ("PyPI", "synthetic-package", "1.0")
    monkeypatch.setattr(scan, "collect", lambda *a, **kw: ({key}, {key: {"."}}))
    monkeypatch.setattr("sys.argv", ["dependency_scan.py"])


def test_unavailable_database_fails_gate(one_package, monkeypatch, capsys):
    def offline(*a, **kw):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(scan.urllib.request, "urlopen", offline)
    assert scan.main() == 2
    assert "OK:" not in capsys.readouterr().out


@pytest.mark.parametrize("response", [{"results": []}, {"results": [None]},
    {"results": [{"next_page_token": "more"}]}])
def test_partial_database_response_fails_gate(one_package, monkeypatch, response):
    monkeypatch.setattr(scan.urllib.request, "urlopen",
                        lambda *a, **kw: io.BytesIO(json.dumps(response).encode()))
    assert scan.main() == 2


def test_complete_clean_response_passes(one_package, monkeypatch):
    monkeypatch.setattr(scan.urllib.request, "urlopen",
                        lambda *a, **kw: io.BytesIO(b'{"results":[{}]}'))
    assert scan.main() == 0


def test_missing_advisory_details_fail_gate(one_package, monkeypatch):
    monkeypatch.setattr(scan, "osv_batch", lambda packages: {packages[0]: ["GHSA-test"]})
    monkeypatch.setattr(scan.urllib.request, "urlopen", lambda *a, **kw: io.BytesIO(b'{}'))
    assert scan.main() == 2
