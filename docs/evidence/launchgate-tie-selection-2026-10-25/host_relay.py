#!/usr/bin/env python3
"""Single-host, budgeted file relay; never put its key file in the runner/container.

Only the CLI reads a server-local key. No retry, redirect, proxy or fallback path
exists. A persisted reservation is never dispatched again after a restart, even
if its response was lost; that outcome is deliberately reported as unknown.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import uuid


ENDPOINT = "https://api.deepseek.com/chat/completions"
MAX_REQUEST_BYTES = 192_000
MAX_PROMPT_CHARS = 24_000
MAX_RESPONSE_BYTES = 1_048_576
MAX_CALLS = 620
ROLES = {"system", "user", "assistant", "tool"}
REQUEST_FIELDS = {"messages", "tools", "tool_choice", "response_format", "temperature", "max_tokens"}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class RelayError(Exception):
    def __init__(self, code, error_type="ValidationError"):
        self.code = code
        self.error_type = error_type
        super().__init__(code)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RelayError("duplicate_json_key")
        result[key] = value
    return result


def safe_json(data):
    try:
        return json.loads(data, object_pairs_hook=no_duplicate_keys,
                          parse_constant=lambda _: (_ for _ in ()).throw(RelayError("nonfinite_json")))
    except RelayError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise RelayError("invalid_json") from None


def read_regular(path, limit):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise RelayError("not_regular_file")
        data = source.read(limit + 1)
    if len(data) > limit:
        raise RelayError("file_too_large")
    return data


def validate_request(value, model):
    if not isinstance(value, dict) or set(value) - REQUEST_FIELDS:
        raise RelayError("request_fields")
    messages = value.get("messages")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 128:
        raise RelayError("messages_shape")
    for message in messages:
        if not isinstance(message, dict) or set(message) - {"role", "content", "tool_calls", "tool_call_id", "name"}:
            raise RelayError("message_fields")
        role = message.get("role")
        if not isinstance(role, str) or role not in ROLES:
            raise RelayError("message_role")
        content = message.get("content")
        if not isinstance(content, str) and not (role == "assistant" and content is None and message.get("tool_calls")):
            raise RelayError("message_content")
        if "name" in message and not isinstance(message["name"], str):
            raise RelayError("message_name")
        if role == "tool":
            if not isinstance(message.get("tool_call_id"), str) or not message["tool_call_id"]:
                raise RelayError("tool_call_id")
        elif "tool_call_id" in message:
            raise RelayError("tool_call_id_role")
        if "tool_calls" in message:
            calls = message["tool_calls"]
            if role != "assistant" or not isinstance(calls, list) or not 1 <= len(calls) <= 32:
                raise RelayError("tool_calls_shape")
            for call in calls:
                if not isinstance(call, dict) or set(call) != {"id", "type", "function"}:
                    raise RelayError("tool_call_fields")
                function = call.get("function")
                if (not isinstance(call["id"], str) or not call["id"] or call["type"] != "function"
                        or not isinstance(function, dict) or set(function) != {"name", "arguments"}
                        or not isinstance(function["name"], str) or not function["name"]
                        or not isinstance(function["arguments"], str)):
                    raise RelayError("tool_call_function")
    tools = value.get("tools", [])
    if not isinstance(tools, list) or len(tools) > 32:
        raise RelayError("tools_shape")
    for tool in tools:
        if not isinstance(tool, dict) or set(tool) != {"type", "function"} or tool["type"] != "function":
            raise RelayError("tool_definition")
        function = tool["function"]
        if (not isinstance(function, dict) or set(function) - {"name", "description", "parameters", "strict"}
                or not isinstance(function.get("name"), str) or not function["name"]
                or ("description" in function and not isinstance(function["description"], str))
                or ("parameters" in function and not isinstance(function["parameters"], dict))
                or ("strict" in function and not isinstance(function["strict"], bool))):
            raise RelayError("tool_definition_function")
    if value.get("tool_choice", "none") != "none":
        raise RelayError("tool_choice")
    if value.get("response_format", {"type": "json_object"}) != {"type": "json_object"}:
        raise RelayError("response_format")
    temperature = value.get("temperature", 0.3)
    if isinstance(temperature, bool) or not isinstance(temperature, (int, float)) or not math.isfinite(temperature) or temperature != 0.3:
        raise RelayError("temperature")
    maximum = value.get("max_tokens", 700)
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 700:
        raise RelayError("max_tokens")
    try:
        prompt = json.dumps({"messages": messages, "tools": tools}, ensure_ascii=False,
                            sort_keys=True, separators=(",", ":"), allow_nan=False)
        prompt.encode("utf-8")
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise RelayError("conversation_encoding") from None
    if len(prompt) > MAX_PROMPT_CHARS:
        raise RelayError("prompt_too_large")
    # Never forward model, URL, thinking, headers or other caller-controlled options.
    payload = {"model": model, "messages": messages, "tool_choice": "none",
               "response_format": {"type": "json_object"}, "temperature": 0.3,
               "max_tokens": maximum, "thinking": {"type": "disabled"}}
    if tools:
        payload["tools"] = tools
    return payload, len(prompt)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Relay:
    def __init__(self, root, key, model, *, max_calls=MAX_CALLS, workers=1, timeout=60, opener=None):
        if (isinstance(max_calls, bool) or not isinstance(max_calls, int) or not 1 <= max_calls <= MAX_CALLS
                or isinstance(workers, bool) or workers not in (1, 2) or not 0 < timeout <= 60):
            raise RelayError("relay_configuration")
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model):
            raise RelayError("model_configuration")
        if not isinstance(key, str) or not key or any(c.isspace() or ord(c) < 32 for c in key):
            raise RelayError("key_configuration")
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.req = self.root / "req"
        self.resp = self.root / "resp"
        for directory in (self.req, self.resp):
            if directory.is_symlink():
                raise RelayError("queue_directory_symlink")
            directory.mkdir(exist_ok=True)
        self.lock_handle = os.open(self.root / ".relay.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            fcntl.flock(self.lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self.lock_handle)
            raise RelayError("relay_already_running", "LockError") from None
        self.usage_path = self.root / "usage.jsonl"
        self.mutex = threading.Lock()
        self.seen = {}
        self.attempts = 0
        self.workers = workers
        self.max_calls = max_calls
        self.timeout = timeout
        self.model = model
        self.key = key
        self.opener = opener or build_opener(ProxyHandler({}), NoRedirect()).open
        try:
            if self.usage_path.exists():
                raw = read_regular(self.usage_path, 8_000_000)
                if raw and not raw.endswith(b"\n"):
                    raise RelayError("usage_ledger_incomplete", "LedgerError")
                for line in raw.splitlines():
                    event = safe_json(line)
                    if not isinstance(event, dict):
                        raise RelayError("usage_ledger_invalid", "LedgerError")
                    if event.get("event") == "reserved":
                        request_id = event.get("request_id")
                        number = event.get("attempt_number")
                        if (not isinstance(request_id, str) or not re.fullmatch(r"[0-9a-f]{32}", request_id)
                                or request_id in self.seen or number != self.attempts + 1):
                            raise RelayError("usage_ledger_invalid", "LedgerError")
                        self.seen[request_id] = event
                        self.attempts += 1
        except BaseException:
            self.close()
            raise

    def close(self):
        handle = getattr(self, "lock_handle", None)
        if handle is not None:
            fcntl.flock(handle, fcntl.LOCK_UN)
            os.close(handle)
            self.lock_handle = None

    def _append(self, event):
        # Caller holds mutex; fsync the reservation BEFORE dispatching a paid call.
        encoded = (json.dumps(event, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()
        fd = os.open(self.usage_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "ab") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())

    def _respond(self, filename, value):
        destination = self.resp / filename
        temporary = self.resp / ("." + filename + "." + uuid.uuid4().hex + ".tmp")
        data = (json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode()
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _reject(self, filename, metadata, code, error_type="ValidationError"):
        result = {"status": "error", "error": {"code": code, "type": error_type},
                  "metadata": {**metadata, "finished_at": utcnow()}}
        with self.mutex:
            self._append({"event": "rejected", "request_id": metadata["request_id"],
                          "requested_model": self.model, "at": utcnow(), "code": code, "type": error_type})
        self._respond(filename, result)
        return result

    def process(self, path):
        path = Path(path)
        if path.parent != self.req or path.suffix != ".json":
            raise RelayError("request_path")
        try:
            request_id = uuid.UUID(path.stem).hex
        except (ValueError, AttributeError):
            raise RelayError("request_filename") from None
        if not re.fullmatch(r"[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", path.stem):
            raise RelayError("request_filename")
        if (self.resp / path.name).exists():
            return None
        metadata = {"request_id": request_id, "requested_model": self.model, "started_at": utcnow()}
        try:
            raw = read_regular(path, MAX_REQUEST_BYTES)
            metadata["request_sha256"] = hashlib.sha256(raw).hexdigest()
            payload, prompt_chars = validate_request(safe_json(raw), self.model)
            metadata.update({"prompt_chars": prompt_chars, "max_tokens": payload["max_tokens"]})
        except RelayError as exc:
            return self._reject(path.name, metadata, exc.code, exc.error_type)
        except OSError:
            return self._reject(path.name, metadata, "request_file_error", "OSError")
        rejection = None
        with self.mutex:
            if request_id in self.seen:
                rejection = ("attempt_outcome_unknown", "PriorAttempt")
                metadata["attempt_number"] = self.seen[request_id]["attempt_number"]
            elif (self.root / "stop").exists():
                rejection = ("stopped", "StopRequested")
            elif self.attempts >= self.max_calls:
                rejection = ("budget_exhausted", "BudgetError")
            else:
                metadata["attempt_number"] = self.attempts + 1
                reservation = {"event": "reserved", **metadata}
                self._append(reservation)
                self.seen[request_id] = reservation
                self.attempts += 1
        if rejection:
            return self._reject(path.name, metadata, *rejection)
        try:
            if (self.root / "stop").exists():
                raise RelayError("stopped", "StopRequested")
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
            request = Request(ENDPOINT, data=encoded, headers={"Authorization": "Bearer " + self.key,
                                                           "Content-Type": "application/json"}, method="POST")
            with self.opener(request, timeout=self.timeout) as response:
                metadata["http_status"] = response.status
                body = response.read(MAX_RESPONSE_BYTES + 1)
            if not 200 <= metadata["http_status"] < 300:
                raise RelayError("provider_http_status", "HTTPStatusError")
            if len(body) > MAX_RESPONSE_BYTES:
                raise RelayError("provider_response_too_large", "ResponseError")
            provider = safe_json(body)
            if (not isinstance(provider, dict) or not isinstance(provider.get("model"), str)
                    or not isinstance(provider.get("id"), str) or not isinstance(provider.get("choices"), list)
                    or not provider["choices"] or not isinstance(provider.get("usage"), dict)):
                raise RelayError("provider_response_shape", "ResponseError")
            result = {"status": "ok", "provider_response": {key: provider[key] for key in ("id", "model", "choices", "usage")},
                      "metadata": metadata}
        except HTTPError as exc:
            metadata["http_status"] = exc.code
            exc.close()  # Never read or log an HTTP error response body.
            result = {"status": "error", "error": {"code": "provider_http_error", "type": "HTTPError", "http_status": exc.code}, "metadata": metadata}
        except (TimeoutError, socket.timeout):
            result = {"status": "error", "error": {"code": "network_timeout", "type": "TimeoutError"}, "metadata": metadata}
        except URLError:
            result = {"status": "error", "error": {"code": "network_error", "type": "URLError"}, "metadata": metadata}
        except RelayError as exc:
            result = {"status": "error", "error": {"code": exc.code, "type": exc.error_type}, "metadata": metadata}
        except Exception as exc:
            # Only the exception class is safe; str(exc) could contain headers/body.
            result = {"status": "error", "error": {"code": "transport_error", "type": type(exc).__name__}, "metadata": metadata}
        metadata["finished_at"] = utcnow()
        with self.mutex:
            event = {"event": "completed", **metadata, "status": result["status"]}
            if result["status"] == "ok":
                event["actual_model"] = result["provider_response"]["model"]
                event["usage"] = result["provider_response"]["usage"]
            else:
                event["error"] = result["error"]
            self._append(event)
        self._respond(path.name, result)
        return result

    def serve(self, *, poll_interval=0.1):
        active = {}
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            while not (self.root / "stop").exists():
                for future in list(active):
                    if future.done():
                        # File/ledger failure is fatal; never continue on uncertain accounting.
                        future.result()
                        active.pop(future)
                pending = set(active.values())
                for path in sorted(self.req.glob("*.json")):
                    if len(active) >= self.workers:
                        break
                    if path.name in pending or (self.resp / path.name).exists():
                        continue
                    active[pool.submit(self.process, path)] = path.name
                time.sleep(poll_interval)
            for future in active:
                future.result()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True)
    parser.add_argument("--key-file", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-calls", type=int, default=MAX_CALLS)
    parser.add_argument("--workers", type=int, choices=(1, 2), default=1)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    relay = None
    try:
        key = read_regular(Path(args.key_file), 8192).decode("utf-8").strip()
        relay = Relay(args.root, key, args.model, max_calls=args.max_calls, workers=args.workers, timeout=args.timeout)
        relay.serve()
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        # No traceback, local key path, request content, provider body or auth value.
        code = exc.code if isinstance(exc, RelayError) else "relay_failure"
        print(json.dumps({"status": "error", "error": {"code": code, "type": type(exc).__name__}}), flush=True)
        return 1
    finally:
        if relay is not None:
            relay.close()


if __name__ == "__main__":
    raise SystemExit(main())
