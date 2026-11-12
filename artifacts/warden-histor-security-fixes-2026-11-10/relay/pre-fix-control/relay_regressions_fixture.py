"""Relay boundary regressions using urllib's real redirect logic and an in-memory transport."""
import importlib.util
import json
from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.request import BaseHandler
from urllib.response import addinfourl

import pytest

_spec = importlib.util.spec_from_file_location("warden_agentdojo_relay", Path(__file__).with_name("relay.py"))
relay = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(relay)

ENDPOINT = "https://api.fixture.invalid/chat/completions"
FIXTURE_KEY = "not-a-real-key-relay-fixture"


class MemoryTransport(BaseHandler):
    handler_order = 100  # Before the real HTTP(S) transports; no socket is opened.

    def __init__(self, statuses, target):
        self.statuses = list(statuses)
        self.target = target
        self.requests = []

    def open(self, request):
        self.requests.append(request)
        assert request.full_url == ENDPOINT, "request escaped the selected endpoint"
        assert self.statuses, "unexpected retry or redirect"
        code = self.statuses.pop(0)
        headers = Message()
        if 300 <= code < 400:
            headers["Location"] = self.target
        body = {"choices": [{"message": {"content": "fixture success"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3}} if code == 200 else {}
        response = addinfourl(BytesIO(json.dumps(body).encode()), headers, request.full_url, code)
        response.msg = "fixture response"
        return response

    https_open = open
    http_open = open


def run_relay(monkeypatch, tmp_path, statuses, target="https://other.fixture.invalid/capture"):
    req_dir, resp_dir = tmp_path / "req", tmp_path / "resp"
    req_dir.mkdir()
    resp_dir.mkdir()
    (req_dir / "one.json").write_text(json.dumps({"messages": [{"role": "user", "content": "fixture"}],
                                                "model": "untrusted-model", "max_tokens": 9000}))
    transport = MemoryTransport(statuses, target)
    original_build = relay.urllib.request.build_opener
    default_opener = original_build(transport)
    monkeypatch.setattr(relay.urllib.request, "build_opener", lambda *handlers: original_build(transport, *handlers))
    # Also intercept the old global-urlopen path so a redirect regression cannot open a real socket.
    monkeypatch.setattr(relay.urllib.request, "urlopen", default_opener.open)
    monkeypatch.setattr(relay, "read_key", lambda *args: FIXTURE_KEY)
    sleeps = []
    monkeypatch.setattr(relay.time, "sleep", sleeps.append)

    class ImmediateExecutor:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def submit(self, callback, work):
            callback(work)
            (tmp_path / "stop").touch()

    monkeypatch.setattr(relay, "ThreadPoolExecutor", ImmediateExecutor)
    monkeypatch.setattr("sys.argv", ["relay.py", str(tmp_path), "--env-file", "unused", "--env-name", "FIXTURE",
                                     "--url", ENDPOINT, "--model", "operator-model", "--budget-usd", "1"])
    relay.main()
    assert not list(req_dir.iterdir())
    return transport, json.loads((resp_dir / "one.json").read_text()), sleeps


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("target", ["https://other.fixture.invalid/capture", "http://other.fixture.invalid/capture",
                                  "https://api.fixture.invalid/other"])
def test_redirect_is_returned_as_error_without_followup(monkeypatch, tmp_path, status, target):
    transport, reply, sleeps = run_relay(monkeypatch, tmp_path, [status], target)
    assert len(transport.requests) == 1
    assert transport.requests[0].get_header("Authorization") == "Bearer " + FIXTURE_KEY
    assert reply["error"].startswith(f"http {status}:")
    assert FIXTURE_KEY not in json.dumps(reply)
    assert sleeps == [0.1]  # Redirect errors are not retried.


def test_https_success_keeps_selected_model_body_and_authorization(monkeypatch, tmp_path):
    transport, reply, sleeps = run_relay(monkeypatch, tmp_path, [200])
    assert len(transport.requests) == 1
    request = transport.requests[0]
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == "Bearer " + FIXTURE_KEY
    body = json.loads(request.data)
    assert body["model"] == "operator-model"
    assert body["max_tokens"] == 8192
    assert body["messages"] == [{"role": "user", "content": "fixture"}]
    assert reply["choices"][0]["message"]["content"] == "fixture success"
    assert sleeps == [0.1]


def test_existing_rate_limit_retry_still_succeeds(monkeypatch, tmp_path):
    transport, reply, sleeps = run_relay(monkeypatch, tmp_path, [429, 200])
    assert len(transport.requests) == 2
    assert all(request.get_header("Authorization") == "Bearer " + FIXTURE_KEY for request in transport.requests)
    assert reply["choices"][0]["message"]["content"] == "fixture success"
    assert sleeps == [2, 0.1]


@pytest.mark.parametrize("endpoint", ["http://api.fixture.invalid/chat/completions", "file:///tmp/fixture",
                                     "https://user:password@api.fixture.invalid/", "https://api.fixture.invalid/#fragment",
                                     "https://api.fixture.invalid/\n", "https://api.fixture.invalid:70000/", "https://"])
def test_invalid_endpoint_is_rejected_before_key_loading(monkeypatch, tmp_path, endpoint, capsys):
    def no_key(*args):
        raise AssertionError("invalid endpoint must be rejected before loading the key")

    monkeypatch.setattr(relay, "read_key", no_key)
    monkeypatch.setattr("sys.argv", ["relay.py", str(tmp_path), "--env-file", "unused", "--env-name", "FIXTURE",
                                     "--url", endpoint, "--model", "fixture", "--budget-usd", "1"])
    with pytest.raises(SystemExit) as error:
        relay.main()
    assert error.value.code == 2
    stderr = capsys.readouterr().err
    assert "HTTPS URL without credentials or a fragment" in stderr
    assert "user:password" not in stderr
