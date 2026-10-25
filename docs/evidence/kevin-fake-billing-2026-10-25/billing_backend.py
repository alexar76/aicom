#!/usr/bin/env python3
"""Independent, local-only fake billing ledger for Kevin Hall's controlled test.

The MCP fixture sends requests over AF_UNIX; only this backend appends the
authoritative ledger. It never contacts a payment provider and uses fictional
integer credits. Import ``start_backend`` or run ``--self-test`` on Linux.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import tempfile
import threading
from typing import Any, Iterator
import uuid


MAX_REQUEST_BYTES = 16 * 1024
MAX_SAFE_INTEGER = 2**53 - 1
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}\Z")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}\Z")
_REQUIRED = {"runId", "operationId", "method", "tool", "credits"}
_ALLOWED = _REQUIRED | {"idempotencyKey"}


class BillingRequestError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BillingRequestError("INVALID_REQUEST", "Duplicate JSON key")
        result[key] = value
    return result


def _invalid_constant(value: str) -> Any:
    raise BillingRequestError("INVALID_REQUEST", "Non-finite JSON number")


def _decode(line: bytes) -> dict[str, Any]:
    try:
        value = json.loads(line.decode("utf-8"), object_pairs_hook=_object,
                           parse_constant=_invalid_constant)
    except (UnicodeDecodeError, ValueError, RecursionError) as exc:
        raise BillingRequestError("INVALID_REQUEST", "Invalid JSON object") from exc
    if not isinstance(value, dict) or not _REQUIRED <= value.keys() or value.keys() - _ALLOWED:
        raise BillingRequestError("INVALID_REQUEST", "Unexpected or missing request fields")
    for field in ("runId", "operationId", "idempotencyKey"):
        if field not in value:
            continue
        if not isinstance(value[field], str) or not _ID.fullmatch(value[field]):
            raise BillingRequestError("INVALID_REQUEST", f"Invalid {field}")
    for field in ("method", "tool"):
        if not isinstance(value[field], str) or not _NAME.fullmatch(value[field]):
            raise BillingRequestError("INVALID_REQUEST", f"Invalid {field}")
    credits = value["credits"]
    if type(credits) is not int or not 1 <= credits <= MAX_SAFE_INTEGER:
        raise BillingRequestError("INVALID_REQUEST", "credits must be a positive safe integer")
    return value


def _dedup_key(request: dict[str, Any]) -> tuple[str, str, str, str, str]:
    if "idempotencyKey" in request:
        kind, identifier = "idempotencyKey", request["idempotencyKey"]
    else:
        kind, identifier = "operationId", request["operationId"]
    return request["runId"], request["method"], request["tool"], kind, identifier


class BillingBackend:
    """Single non-daemon socket worker, bounded clients, durable append-only ledger."""

    def __init__(self, socket_path: str | os.PathLike[str], ledger_path: str | os.PathLike[str]):
        self.socket_path = Path(socket_path)
        self.ledger_path = Path(ledger_path)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._index: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        self._socket: socket.socket | None = None
        self._active: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._fd: int | None = None
        self._failure: BaseException | None = None
        self._closed = False
        self._owns_socket = False

    def start(self) -> "BillingBackend":
        if self._closed or self._thread is not None:
            raise RuntimeError("Billing backend cannot be started twice")
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists() or self.socket_path.is_symlink():
            raise FileExistsError("Refusing to replace an existing billing socket")
        try:
            flags = os.O_RDWR | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            self._fd = os.open(self.ledger_path, flags, 0o600)
            self._restore_index()
            self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._socket.bind(str(self.socket_path))
            self._owns_socket = True
            os.chmod(self.socket_path, 0o600)
            self._socket.listen(32)
            self._socket.settimeout(0.2)
            self._thread = threading.Thread(target=self._serve, name="fake-billing-ledger", daemon=False)
            self._thread.start()
            return self
        except BaseException:
            self.close()
            raise

    def _restore_index(self) -> None:
        assert self._fd is not None
        os.lseek(self._fd, 0, os.SEEK_SET)
        with os.fdopen(os.dup(self._fd), "rb") as stream:
            while True:
                line = stream.readline(MAX_REQUEST_BYTES + 1)
                if not line:
                    break
                if len(line) > MAX_REQUEST_BYTES or not line.endswith(b"\n"):
                    raise ValueError("Existing billing ledger has an incomplete or oversized record")
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("Existing billing ledger record is not an object")
                request = {key: record[key] for key in _ALLOWED if key in record}
                _decode(json.dumps(request).encode("utf-8"))
                receipt = record.get("receiptId")
                if record.get("charged") is not True or not isinstance(receipt, str) or not _ID.fullmatch(receipt):
                    raise ValueError("Existing billing ledger has an invalid receipt")
                key = _dedup_key(request)
                if key in self._index:
                    raise ValueError("Existing billing ledger duplicates an idempotency key")
                self._index[key] = record

    def _charge(self, request: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._failure is not None:
                raise BillingRequestError("BACKEND_UNAVAILABLE", "Billing ledger is unavailable")
            key = _dedup_key(request)
            previous = self._index.get(key)
            if previous is not None:
                if previous["credits"] != request["credits"]:
                    raise BillingRequestError("IDEMPOTENCY_CONFLICT", "The prior request used different credits")
                return {"ok": True, "receiptId": previous["receiptId"], "charged": False,
                        "credits": 0}
            record = {"schema": "kevin.fake-billing-ledger/v1", **request,
                      "receiptId": str(uuid.uuid4()), "charged": True,
                      "recordedAt": datetime.now(timezone.utc).isoformat()}
            payload = (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            assert self._fd is not None
            try:
                pending = memoryview(payload)
                while pending:
                    written = os.write(self._fd, pending)
                    if written <= 0:
                        raise OSError("Billing ledger write made no progress")
                    pending = pending[written:]
                os.fsync(self._fd)
            except OSError as exc:
                # A partial/uncertain append must never be followed by a fresh charge.
                self._failure = exc
                raise BillingRequestError("BACKEND_UNAVAILABLE", "Billing ledger persistence failed") from exc
            self._index[key] = record
            return {"ok": True, "receiptId": record["receiptId"], "charged": True,
                    "credits": request["credits"]}

    def _handle(self, client: socket.socket) -> None:
        client.settimeout(2.0)
        data = bytearray()
        try:
            while b"\n" not in data:
                part = client.recv(MAX_REQUEST_BYTES + 1 - len(data))
                if not part:
                    raise BillingRequestError("INVALID_REQUEST", "Request must end with a newline")
                data.extend(part)
                if len(data) > MAX_REQUEST_BYTES:
                    raise BillingRequestError("REQUEST_TOO_LARGE", "Request exceeds 16 KiB")
            line, remainder = bytes(data).split(b"\n", 1)
            if remainder.strip():
                raise BillingRequestError("INVALID_REQUEST", "Only one request per connection is supported")
            response = self._charge(_decode(line))
        except BillingRequestError as exc:
            response = {"ok": False, "error": {"code": exc.code, "message": str(exc)}}
        except TimeoutError:
            response = {"ok": False, "error": {"code": "REQUEST_TIMEOUT", "message": "Request timed out"}}
        try:
            client.sendall((json.dumps(response, separators=(",", ":")) + "\n").encode("utf-8"))
        except OSError:
            # A disconnected client does not roll back an authoritative ledger entry.
            pass

    def _serve(self) -> None:
        assert self._socket is not None
        try:
            while not self._stop.is_set():
                try:
                    client, _ = self._socket.accept()
                except TimeoutError:
                    continue
                except OSError:
                    if self._stop.is_set():
                        break
                    raise
                self._active = client
                try:
                    with client:
                        self._handle(client)
                except OSError:
                    if not self._stop.is_set():
                        raise
                finally:
                    self._active = None
        except BaseException as exc:
            self._failure = exc
            self._stop.set()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stop.set()
        if self._active is not None:
            try:
                self._active.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if self._socket is not None:
            self._socket.close()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                raise RuntimeError("Billing backend did not stop")
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None
        if self._owns_socket:
            self.socket_path.unlink(missing_ok=True)
        if self._failure is not None:
            raise RuntimeError("Billing backend failed") from self._failure


@contextmanager
def start_backend(socket_path: str | os.PathLike[str], ledger_path: str | os.PathLike[str]) -> Iterator[BillingBackend]:
    backend = BillingBackend(socket_path, ledger_path)
    backend.start()
    try:
        yield backend
    finally:
        backend.close()


def self_test() -> dict[str, Any]:
    """Contract tests; intentionally invoked by the Linux runner, not at import."""
    checks = 0

    def check(value: bool) -> None:
        nonlocal checks
        if not value:
            raise AssertionError(f"Fake billing self-test failed at check {checks + 1}")
        checks += 1

    with tempfile.TemporaryDirectory(prefix="kevin-billing-selftest-") as temporary:
        root = Path(temporary)
        socket_path, ledger_path = root / "billing.sock", root / "ledger.jsonl"

        def send(request: dict[str, Any] | bytes) -> dict[str, Any]:
            payload = request if isinstance(request, bytes) else json.dumps(request).encode("utf-8")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(4.0)
                client.connect(str(socket_path))
                client.sendall(payload + b"\n")
                result = bytearray()
                while b"\n" not in result:
                    part = client.recv(16 * 1024)
                    if not part:
                        raise AssertionError("Billing backend closed without a response")
                    result.extend(part)
                return json.loads(result)

        request = {"runId": "self-test", "operationId": "call-1", "method": "tools/call",
                   "tool": "search", "credits": 7}
        with start_backend(socket_path, ledger_path):
            first = send(request)
            check(first["ok"] is True and first["charged"] is True and first["credits"] == 7)
            duplicate = send(request)
            check(duplicate["receiptId"] == first["receiptId"] and duplicate["charged"] is False
                  and duplicate["credits"] == 0)
            conflict = send({**request, "credits": 8})
            check(conflict["ok"] is False and conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT")
            keyed = send({**request, "operationId": "call-2", "idempotencyKey": "purchase-1"})
            retried = send({**request, "operationId": "call-3", "idempotencyKey": "purchase-1"})
            check(keyed["charged"] is True and retried["charged"] is False and retried["credits"] == 0)
            check(keyed["receiptId"] == retried["receiptId"])
            other_run = send({**request, "runId": "other-run"})
            check(other_run["charged"] is True and other_run["receiptId"] != first["receiptId"])
            for credits in (True, False, 0, -1, 1.5, "7", MAX_SAFE_INTEGER + 1):
                rejected = send({**request, "operationId": "invalid", "credits": credits})
                check(rejected["ok"] is False and rejected["error"]["code"] == "INVALID_REQUEST")
            for field, value in (("runId", ""), ("runId", "x" * 257), ("operationId", "\n"),
                                 ("method", "x" * 161), ("tool", ""), ("idempotencyKey", "")):
                rejected = send({**request, field: value})
                check(rejected["ok"] is False and rejected["error"]["code"] == "INVALID_REQUEST")
            check(send(b'{"runId":"one","runId":"two"}')["ok"] is False)
            check(send(b"{" + b" " * MAX_REQUEST_BYTES)["error"]["code"] == "REQUEST_TOO_LARGE")
            check(send({**request, "extra": "unaccepted"})["ok"] is False)
            responses: list[dict[str, Any]] = []
            failures: list[BaseException] = []

            def simultaneous() -> None:
                try:
                    responses.append(send({**request, "operationId": "parallel"}))
                except BaseException as exc:
                    failures.append(exc)

            threads = [threading.Thread(target=simultaneous) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5.0)
            check(not failures and all(not thread.is_alive() for thread in threads) and len(responses) == 8)
            check(sum(reply["charged"] is True for reply in responses) == 1)
            check(len({reply["receiptId"] for reply in responses}) == 1)
            entries = [json.loads(line) for line in ledger_path.read_text().splitlines()]
            check(len(entries) == 4 and sum(entry["credits"] for entry in entries) == 28)
        check(not socket_path.exists())
        # Restarting the backend must not permit the same operation to be charged again.
        with start_backend(socket_path, ledger_path):
            replay = send(request)
            check(replay["charged"] is False and replay["credits"] == 0
                  and replay["receiptId"] == first["receiptId"])
        check(len(ledger_path.read_text().splitlines()) == 4)
        check(not socket_path.exists())
    return {"status": "passed", "checks": checks, "transport": "AF_UNIX",
            "realPayments": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    options = parser.parse_args()
    if not options.self_test:
        parser.error("Use --self-test, or import start_backend from the Linux experiment runner")
    print(json.dumps(self_test(), sort_keys=True))


if __name__ == "__main__":
    main()
