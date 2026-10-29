"""Offline relay contract tests. All transport is fake; never reads a real key.

Intended for the networkless Linux test container, not a Mac runtime experiment.
"""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError, URLError
import uuid


spec = importlib.util.spec_from_file_location("launchgate_host_relay", Path(__file__).with_name("host_relay.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

FAKE_KEY = "synthetic-relay-test-key"
MODEL = "deepseek-flash"


class FakeResponse:
    status = 200

    def __init__(self, payload=None):
        self.payload = payload or {"id": "test-response", "model": MODEL,
                                   "choices": [{"finish_reason": "stop", "message": {
                                       "role": "assistant", "content": '{"selected_hotel_id":"H-A","reason":"fixture"}'}}],
                                   "usage": {"prompt_tokens": 20, "completion_tokens": 10},
                                   "debug_not_forwarded": "not part of the relay envelope"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return json.dumps(self.payload).encode()[:limit]


class FakeTransport:
    def __init__(self, error=None, payload=None):
        self.error = error
        self.payload = payload
        self.requests = []
        self.mutex = threading.Lock()

    def __call__(self, request, timeout):
        with self.mutex:
            self.requests.append((request, timeout))
        if self.error:
            raise self.error
        return FakeResponse(self.payload)


def valid_request():
    return {"messages": [{"role": "user", "content": "Choose from these synthetic records; return JSON."}],
            "tools": [{"type": "function", "function": {"name": "hotels", "parameters": {"type": "object"}}}],
            "tool_choice": "none", "response_format": {"type": "json_object"},
            "temperature": 0.3, "max_tokens": 700}


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "relay"
        self.transport = FakeTransport()
        self.relay = module.Relay(self.root, FAKE_KEY, MODEL, opener=self.transport)

    def tearDown(self):
        self.relay.close()
        self.temporary.cleanup()

    def request_file(self, payload=None):
        path = self.root / "req" / (str(uuid.uuid4()) + ".json")
        path.write_text(json.dumps(valid_request() if payload is None else payload))
        return path

    def events(self):
        path = self.root / "usage.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_fixed_endpoint_options_full_answer_whitelist_and_no_key_in_evidence(self):
        path = self.request_file()
        result = self.relay.process(path)
        self.assertEqual(result["status"], "ok")
        request, timeout = self.transport.requests[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, module.ENDPOINT)
        self.assertEqual(timeout, 60)
        self.assertEqual(payload["model"], MODEL)
        self.assertEqual(payload["temperature"], 0.3)
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["tool_choice"], "none")
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(payload["max_tokens"], 700)
        self.assertEqual(set(result["provider_response"]), {"id", "model", "choices", "usage"})
        self.assertEqual(result["metadata"]["attempt_number"], 1)
        self.assertEqual([e["event"] for e in self.events()], ["reserved", "completed"])
        for artifact in [self.root / "resp" / path.name, self.root / "usage.jsonl"]:
            self.assertNotIn(FAKE_KEY, artifact.read_text())
        self.assertFalse(list((self.root / "resp").glob("*.tmp")))

    def test_assistant_tool_history_is_forwarded_as_conversation(self):
        payload = valid_request()
        payload["messages"] = [
            {"role": "user", "content": "Choose one hotel and explain using JSON."},
            {"role": "assistant", "content": None, "tool_calls": [{"id": "call-1", "type": "function",
                "function": {"name": "hotels", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "call-1", "content": '{"hotels": [], "note": "fixture"}'},
        ]
        self.assertEqual(self.relay.process(self.request_file(payload))["status"], "ok")
        self.assertEqual(json.loads(self.transport.requests[0][0].data)["messages"], payload["messages"])

    def test_invalid_requests_never_reserve_or_dispatch(self):
        changes = [
            {"model": "another-model"}, {"url": "https://invalid.example"},
            {"thinking": {"type": "enabled"}}, {"max_tokens": 701}, {"max_tokens": True},
            {"temperature": 1.0}, {"tool_choice": "auto"}, {"response_format": {"type": "text"}},
            {"messages": [{"role": "developer", "content": "invalid role"}]},
            {"messages": [{"role": [], "content": "invalid role type"}]},
            {"messages": [{"role": "user", "content": "x" * 24_001}]},
            {"messages": [{"role": "tool", "content": "missing call id"}]},
            {"messages": [{"role": "user", "content": "bad surrogate \ud800"}]},
        ]
        for change in changes:
            with self.subTest(fields=list(change)):
                payload = valid_request()
                payload.update(change)
                result = self.relay.process(self.request_file(payload))
                self.assertEqual(result["status"], "error")
        self.assertEqual(self.transport.requests, [])
        self.assertEqual(self.relay.attempts, 0)
        self.assertFalse(any(e["event"] == "reserved" for e in self.events()))

    def test_tool_schema_counts_toward_prompt_size(self):
        payload = valid_request()
        payload["tools"][0]["function"]["description"] = "x" * 24_000
        result = self.relay.process(self.request_file(payload))
        self.assertEqual(result["error"]["code"], "prompt_too_large")
        self.assertEqual(self.transport.requests, [])

    def test_duplicate_json_keys_rejected_before_dispatch(self):
        path = self.request_file()
        path.write_text('{"messages":[],"messages":[]}')
        result = self.relay.process(path)
        self.assertEqual(result["error"]["code"], "duplicate_json_key")
        self.assertEqual(self.transport.requests, [])

    def test_http_error_body_is_never_read_logged_or_retried(self):
        class ErrorBody(io.BytesIO):
            reads = 0
            def read(self, *args):
                self.reads += 1
                return super().read(*args)
        body = ErrorBody(("private body " + FAKE_KEY).encode())
        self.transport.error = HTTPError(module.ENDPOINT, 429, "private message " + FAKE_KEY, {}, body)
        path = self.request_file()
        result = self.relay.process(path)
        self.assertEqual(result["error"], {"code": "provider_http_error", "type": "HTTPError", "http_status": 429})
        self.assertEqual(body.reads, 0)
        self.assertEqual(len(self.transport.requests), 1)
        self.assertIsNone(self.relay.process(path))
        self.assertEqual(len(self.transport.requests), 1)
        self.assertNotIn(FAKE_KEY, json.dumps(result) + json.dumps(self.events()))
        self.assertEqual(self.relay.attempts, 1)

    def test_network_error_has_no_raw_reason_and_consumes_one_attempt(self):
        self.transport.error = URLError("private network reason " + FAKE_KEY)
        result = self.relay.process(self.request_file())
        self.assertEqual(result["error"], {"code": "network_error", "type": "URLError"})
        self.assertNotIn(FAKE_KEY, json.dumps(result) + json.dumps(self.events()))
        self.assertEqual(self.relay.attempts, 1)

    def test_timeout_has_no_retry(self):
        self.transport.error = TimeoutError("private timeout " + FAKE_KEY)
        result = self.relay.process(self.request_file())
        self.assertEqual(result["error"]["code"], "network_timeout")
        self.assertEqual(len(self.transport.requests), 1)

    def test_concurrent_dispatch_cannot_exceed_hard_budget(self):
        self.relay.max_calls = 3
        paths = [self.request_file() for _ in range(12)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(self.relay.process, paths))
        self.assertEqual(len(self.transport.requests), 3)
        self.assertEqual(sum(r["status"] == "ok" for r in results), 3)
        self.assertEqual(sum(r.get("error", {}).get("code") == "budget_exhausted" for r in results), 9)
        self.assertEqual([e["attempt_number"] for e in self.events() if e["event"] == "reserved"], [1, 2, 3])

    def test_restart_preserves_budget_and_never_rebills_missing_response(self):
        self.relay.max_calls = 1
        path = self.request_file()
        self.assertEqual(self.relay.process(path)["status"], "ok")
        (self.root / "resp" / path.name).unlink()
        self.relay.close()
        self.relay = module.Relay(self.root, FAKE_KEY, MODEL, max_calls=1, opener=self.transport)
        result = self.relay.process(path)
        self.assertEqual(result["error"]["code"], "attempt_outcome_unknown")
        self.assertEqual(self.relay.process(self.request_file())["error"]["code"], "budget_exhausted")
        self.assertEqual(len(self.transport.requests), 1)

    def test_crash_reservation_without_completion_is_not_dispatched(self):
        path = self.request_file()
        with self.relay.mutex:
            self.relay._append({"event": "reserved", "request_id": uuid.UUID(path.stem).hex,
                                "attempt_number": 1, "requested_model": MODEL})
        self.relay.close()
        self.relay = module.Relay(self.root, FAKE_KEY, MODEL, opener=self.transport)
        result = self.relay.process(path)
        self.assertEqual(result["error"]["code"], "attempt_outcome_unknown")
        self.assertEqual(self.transport.requests, [])

    def test_stop_prevents_dispatch(self):
        (self.root / "stop").touch()
        result = self.relay.process(self.request_file())
        self.assertEqual(result["error"]["code"], "stopped")
        self.assertEqual(self.transport.requests, [])
        self.assertEqual(self.relay.attempts, 0)

    def test_incomplete_persistent_ledger_fails_closed(self):
        self.relay.close()
        (self.root / "usage.jsonl").write_text('{"event":"reserved"')
        with self.assertRaises(module.RelayError) as caught:
            module.Relay(self.root, FAKE_KEY, MODEL, opener=self.transport)
        self.assertEqual(caught.exception.code, "usage_ledger_incomplete")
        self.assertEqual(self.transport.requests, [])

    def test_only_one_relay_can_own_a_queue(self):
        with self.assertRaises(module.RelayError) as caught:
            module.Relay(self.root, FAKE_KEY, MODEL, opener=self.transport)
        self.assertEqual(caught.exception.code, "relay_already_running")

    def test_request_symlink_is_not_followed(self):
        target = Path(self.temporary.name) / "outside.json"
        target.write_text(json.dumps(valid_request()))
        path = self.root / "req" / (str(uuid.uuid4()) + ".json")
        path.symlink_to(target)
        result = self.relay.process(path)
        self.assertEqual(result["error"]["code"], "request_file_error")
        self.assertEqual(self.transport.requests, [])

    def test_redirect_handler_never_builds_a_redirect_request(self):
        handler = module.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "redirect", {}, "https://invalid.example"))

    def test_out_of_plan_configuration_is_rejected(self):
        for index, overrides in enumerate([{"max_calls": module.MAX_CALLS + 1}, {"workers": 3}, {"timeout": 61}]):
            with self.subTest(overrides=overrides), self.assertRaises(module.RelayError) as caught:
                module.Relay(self.root.parent / ("invalid-config-" + str(index)), FAKE_KEY, MODEL, opener=self.transport, **overrides)
            self.assertEqual(caught.exception.code, "relay_configuration")


if __name__ == "__main__":
    unittest.main()
