"""The standalone checker must preserve private-file compatibility without leaks."""

from __future__ import annotations

import io
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError

import pytest

from scripts import verify_model_ids as checker

CANARY = "disposable-standalone-checker-credential"


@pytest.fixture
def stored(tmp_path, monkeypatch):
    data = tmp_path / "data"
    directory = data / "secrets" / "llm"
    directory.mkdir(parents=True)
    (directory / "custom_key").write_text(CANARY)
    monkeypatch.setenv("AIFACTORY_DATA_ROOT", str(data))
    return data


def test_checker_resolves_safe_private_reference_without_chmod(stored):
    path = stored / "secrets" / "llm" / "custom_key"
    mode = path.stat().st_mode
    assert checker._resolve_key({"api_key_file": "custom_key"}, "custom") == CANARY
    assert path.stat().st_mode == mode


@pytest.mark.parametrize("reference", ["../outside", "/etc/passwd", "a/b", ".", ".."])
def test_checker_rejects_unsafe_reference(stored, reference):
    with pytest.raises(ValueError):
        checker._resolve_key({"api_key_file": reference}, "custom")


def test_checker_refuses_symlink_outside_secret_directory(stored, tmp_path):
    outside = tmp_path / "outside"
    outside.write_text(CANARY)
    path = stored / "secrets" / "llm" / "custom_key"
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(OSError):
        checker._resolve_key({"api_key_file": "custom_key"}, "custom")


@contextmanager
def server(handler):
    instance = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    worker = threading.Thread(target=lambda: instance.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{instance.server_port}"
    finally:
        instance.shutdown()
        instance.server_close()
        worker.join(timeout=2)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_checker_transport_never_forwards_key_to_redirect_target(status):
    destination_requests = []
    source_requests = []

    class Destination(BaseHTTPRequestHandler):
        def do_GET(self):
            destination_requests.append(dict(self.headers))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *args):
            pass

    with server(Destination) as target:
        class Source(Destination):
            def do_GET(self):
                source_requests.append(self.headers.get("Authorization"))
                self.send_response(status)
                self.send_header("Location", target + "/stolen")
                self.end_headers()

        with server(Source) as origin:
            with pytest.raises(HTTPError):
                checker._get_json(origin + "/models", {"Authorization": "Bearer " + CANARY})
    assert source_requests == ["Bearer " + CANARY]
    assert destination_requests == []


def test_checker_uses_key_file_and_redacts_errors(stored, monkeypatch):
    def reject(req):
        assert req.headers["Authorization"] == "Bearer " + CANARY
        raise HTTPError(req.full_url, 401, "unauthorized", {}, io.BytesIO(json.dumps({
            "error": {"message": "credential rejected " + CANARY},
        }).encode()))

    monkeypatch.setattr(checker, "_open_no_redirect", reject)
    result = checker.probe_model({"api_key_file": "custom_key", "base_url": "https://provider.example/v1"}, "model")
    assert result[0] == "unverifiable"
    assert CANARY not in json.dumps(result)


def test_checker_requires_missing_key_file_instead_of_anonymous_probe(stored, monkeypatch):
    def forbidden(*args):
        pytest.fail("a provider requiring credentials was probed anonymously")

    monkeypatch.setattr(checker, "_open_no_redirect", forbidden)
    block = {"api_key_file": "missing_key", "base_url": "https://provider.example/v1"}
    assert checker.probe_model(block, "model")[0] == "unverifiable"
    assert checker.list_models("custom", block)[0] is None


def test_checker_bounds_provider_reply_size():
    with pytest.raises(ValueError):
        checker._read_bounded(io.BytesIO(b"x" * 2_097_153))
