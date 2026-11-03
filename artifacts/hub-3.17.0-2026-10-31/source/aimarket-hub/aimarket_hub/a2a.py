"""A2A 1.0 facade for the marketplace: discovery, and paid execution as Tasks.

The Hub is not a conversational model and must not pretend to be one. Its A2A skills are
the two things it can actually deliver:

* ``marketplace-search`` — search the live, policy-filtered market catalogue and return
  structured offers. Answered with a direct ``Message``; nothing is stored.
* ``marketplace-invoke`` — buy and run one capability. Answered with a ``Task``
  (``a2a_tasks.py``), because a paid call is something the client may have to come back
  to: to pay for it, to supply credentials, or to read it again after a timeout.

The invoke skill is a bridge, not a second payment path. It POSTs the exact invoke bytes to
``/ai-market/v2/invoke`` through the ASGI app itself (see ``InvokeBridge.invoke``), so the
mandate/allowance admission, the credits holds, the seller-direct x402 verification, the
invoice nonces the x402 middleware mints on every 402, the sandbox trial and the metrics
are the ones every other buyer goes through. Calling the handler as a Python function
would skip the middleware — no invoice would be minted and, with nonce binding on by
default, every x402 payment would then be refused as an unknown nonce.

Payment rides the request the way each rail already does (docs/a2a.md):

* credits — ``X-API-Key`` as an HTTP header on ``POST /a2a``;
* mandates — ``X-AIMarket-Mandate`` and ``X-AIMarket-Mandate-Proof`` as HTTP headers, with
  the invoke in ONE raw ``application/json`` part holding the exact bytes the proof signs
  (for ``POST /ai-market/v2/invoke``). Re-serializing a data part would change the bytes
  and fail every mandated call as ``mandate_proof_invalid``;
* x402 — the a2a-x402 v0.2 standalone flow: the task answers ``TASK_STATE_INPUT_REQUIRED``
  with the hub's own terms, and the client replies on that task with
  ``x402.payment.payload``. One profile deviation: the payload must carry the settle
  ``txHash``, because this hub verifies the chain and never settles (it holds no key and no
  gas — settle.py). A signature alone is not a payment here;
* nothing — a caller with no payment is presented to the hub's free trial under the same
  per-caller identity the MCP gateway uses (``mcp_gateway.visitor_for``), so one caller has
  one allowance whichever protocol it speaks.

SendMessage blocks until the task is finished or waiting for the client, unless the client
sends ``returnImmediately``: then the task is answered WORKING at once and runs on. Either way a
client may register push notification webhooks (``a2a_push.py``) and hear about every change
without polling — including the ones no request of its own causes: an owner answering an
approval (mandates.md §5.6), a task that runs on after the answer, the sweep expiring a task.
Streaming stays off.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import logging
import math
import secrets
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, Response

from aimarket_hub import a2a_push
from aimarket_hub import a2a_tasks as tasks_mod
from aimarket_hub.a2a_tasks import (
    AUTH_REQUIRED, CANCELED, COMPLETED, FAILED, INPUT_REQUIRED, INTERRUPTED, REJECTED, TERMINAL,
    WORKING, A2ATaskStore,
)

logger = logging.getLogger(__name__)

A2A_PROTOCOL_VERSION = "1.0"
MAX_A2A_BODY_BYTES = 128 * 1024
MAX_A2A_PARTS = 16
MAX_A2A_PART_BYTES = 64 * 1024
MAX_A2A_QUERY_CHARS = 2_000
MAX_A2A_RESULTS = 20
MAX_LIST_PAGE = 100
#: Tasks running after their answer (returnImmediately) at once. Past it the next one runs
#: before answering, as if the client had not asked: a burst cannot pile up unbounded work.
MAX_BACKGROUND_INVOKES = 32
#: The bridge's own invoke carries its task and this process's secret, so the invoke route
#: can journal the task's charges (a2a_tasks.ChargeJournal) and no outside caller can.
TASK_HEADER = "X-AIMarket-A2A-Task"
INTERNAL_HEADER = "X-AIMarket-Internal"
INTERNAL_SECRET = secrets.token_hex(24)
#: The x402 payment payload is forwarded as a header; the MCP gateway caps it the same way.
MAX_PAYMENT_CHARS = 8192

X402_EXTENSION_URI = "https://github.com/google-agentic-commerce/a2a-x402/blob/main/spec/v0.2"
INVOKE_PATH = "/ai-market/v2/invoke"
MANDATE_HEADER = "X-AIMarket-Mandate"
PROOF_HEADER = "X-AIMarket-Mandate-Proof"
A2A_PROOF_HEADER = "X-AIMarket-A2A-Proof"
SANDBOX_HEADER = "X-AIMarket-Sandbox-Visitor"
# Provider-side subcontracting headers. A provider buying inside a job does so at the
# invoke endpoint, where the job tree is joined; here they are refused rather than dropped,
# because a dropped job header silently turns an allowance-funded purchase into a stranger's.
_JOB_HEADERS = ("X-AIMarket-Job", "X-AIMarket-Job-Grant")
# The only request headers that ever reach the invoke. Nothing else the A2A client sent is
# forwarded — in particular not a sandbox visitor id of its own choosing.
_FORWARDED = ("X-API-Key", MANDATE_HEADER, PROOF_HEADER, "X-AIMarket-Affiliate")
_INVOKE_FIELDS = ("product_id", "capability_id", "source_hub", "input", "max_price_usd", "verify", "subcontract")

SearchCallable = Callable[..., Awaitable[dict[str, Any]]]
#: (exact invoke bytes, headers to send, caller address) -> (status, response headers, JSON body)
InvokeCallable = Callable[[bytes, dict[str, str], str], Awaitable[tuple[int, Mapping[str, str], Any]]]


@dataclass
class InvokeBridge:
    """What ``marketplace-invoke`` needs from the app, injected (``api`` imports this module).

    ``invoke`` must run the request through the ASGI app, middleware included — see the
    module docstring for what breaks otherwise. ``client_address`` is the hub's proxy-aware
    caller address; ``resolve_account`` maps an X-API-Key to its credit account ("" when
    unknown or credits are off); ``verify_mandate(digest, proof, method, path, body)`` checks
    a mandate request proof and consumes its nonce; ``is_priced`` says whether a capability
    costs anything (unknown counts as priced).
    """

    invoke: InvokeCallable
    tasks: A2ATaskStore
    client_address: Callable[[Any], str]
    resolve_account: Callable[[str], str]
    verify_mandate: Callable[[str, str, str, str, bytes], bool]
    is_priced: Callable[[str, str, str], bool]
    allow_request: Callable[[str], bool] = lambda caller: True
    #: The payment secret of one of this hub's own invoices (settle.InvoiceStore.secret_for).
    #: A paying follow-up is redeemed for the task that was quoted: the bridge presents the
    #: secret of THAT task's invoice, so the client never handles it and a task that was not
    #: quoted an invoice cannot redeem one.
    payment_secret: Callable[[str], str] = lambda nonce: ""
    #: Push notifications (a2a_push.py). None: the card says pushNotifications false and the
    #: push methods answer PushNotificationNotSupported.
    push: a2a_push.PushDispatcher | None = None
    #: What an abandoned task's call cost, read from the ledger (agents.py): {"outcome":
    #: "none" | "released" | "charged" | "unknown", "receipts": [...]}. None: every abandoned
    #: task is failed as "may have been charged", as before leases.
    recover: Callable[[dict[str, Any]], dict[str, Any]] | None = None
    #: An owner-approval request as THIS hub stored it (mandates.approval_public), or None.
    #: A 402 that says "approval_required" is believed only when it names one of these — for
    #: this mandate and these exact bytes — never on the word of a peer that answered it.
    approval_lookup: Callable[[str], dict[str, Any] | None] | None = None


def _signed_path(request: Request) -> str:
    """The path a mandate proof over POST /a2a signs: relative to the hub's base URL
    (mandates.md §5.1), so a hub mounted under a prefix (root_path) checks what the
    client signed — "/a2a", not "/hub/a2a"."""
    path = request.url.path
    root = str(request.scope.get("root_path") or "")
    if root and path.startswith(root):
        path = path[len(root):] or "/"
    return path


def build_agent_card(*, hub_name: str, hub_url: str, hub_version: str,
                     invoke: bool = False, push: bool = False) -> dict[str, Any]:
    """Return an A2A 1.0 AgentCard containing only implemented capabilities."""
    base = hub_url.rstrip("/")
    skills: list[dict[str, Any]] = [
        {
            "id": "marketplace-search",
            "name": "Search the AI capability market",
            "description": (
                "Find executable offers by natural-language intent and optional budget, "
                "latency, trust, hub and category filters."
            ),
            "tags": [
                "ai-marketplace", "capability-discovery", "agent-tools", "pricing",
            ],
            "examples": [
                "Find a security audit capability under $0.10",
                "Найди проверяемый сервис памяти для AI-агента",
            ],
            "inputModes": ["text/plain", "application/json"],
            "outputModes": ["text/plain", "application/json"],
        }
    ]
    card: dict[str, Any] = {
        "name": hub_name.strip() or "Independent AI Hub",
        "description": (
            "Search a live federated market of executable AI capabilities. Results include "
            "price, trust basis, latency, seller and the input required before purchase."
        ),
        "supportedInterfaces": [
            {
                "url": f"{base}/a2a",
                "protocolBinding": "JSONRPC",
                "protocolVersion": A2A_PROTOCOL_VERSION,
            }
        ],
        "provider": {"organization": hub_name.strip() or "Independent AI", "url": base},
        "version": hub_version,
        "documentationUrl": f"{base}/developers",
        "capabilities": {
            "streaming": False,
            "pushNotifications": bool(push and invoke),
            "extendedAgentCard": False,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": skills,
    }
    if not invoke:
        return card
    card["description"] += (
        " Buy and run an offer in the same conversation; every result carries a signed receipt."
    )
    skills.append({
        "id": "marketplace-invoke",
        "name": "Buy and run a market capability",
        "description": (
            "Run one offer found by marketplace-search and return its result with a signed "
            "receipt, as a Task. Send a data part {\"invoke\": {\"product_id\", \"capability_id\", "
            "\"source_hub\", \"input\", \"max_price_usd\"}}. Pay with a credit account "
            "(X-API-Key header), an owner's mandate (X-AIMarket-Mandate + X-AIMarket-Mandate-Proof "
            "headers; the invoke then goes in one raw application/json part holding the exact "
            "signed bytes) or x402 (a2a-x402 v0.2; the payload must include the settle txHash). "
            "The first few priced calls per caller are a free trial. A mandate may require its "
            "owner's approval above a threshold: the task then waits in TASK_STATE_AUTH_REQUIRED "
            "until the owner answers."
        ),
        "tags": ["ai-marketplace", "paid-invoke", "x402", "receipts", "agent-mandates"],
        "examples": [
            '{"invoke": {"product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1", '
            '"source_hub": "local", "input": {"device_id": "om-wx-01"}, "max_price_usd": 0.01}}',
        ],
        "inputModes": ["application/json"],
        "outputModes": ["application/json", "text/plain"],
    })
    card["capabilities"]["extensions"] = [{
        "uri": X402_EXTENSION_URI,
        "description": (
            "x402 payments on marketplace-invoke (standalone flow). Profile deviation: this hub "
            "verifies the transfer on chain and never settles, so x402.payment.payload must "
            "carry the settle txHash of a USDC transfer to the payTo it quoted."
        ),
        "required": False,
    }]
    card["securitySchemes"] = {
        "aimarketApiKey": {"apiKeySecurityScheme": {
            "location": "header",
            "name": "X-API-Key",
            "description": "A credit account on this hub. Optional: the free trial and x402 need none.",
        }},
        "aimarketMandate": {"apiKeySecurityScheme": {
            "location": "header",
            "name": MANDATE_HEADER,
            "description": (
                "An owner's signed mandate (aimarket-protocol/mandates.md), with "
                f"{PROOF_HEADER} signed over POST {INVOKE_PATH} and the exact invoke bytes."
            ),
        }},
    }
    return card


def invoke_enabled() -> bool:
    """AIMARKET_A2A_INVOKE=0 keeps /a2a discovery-only (the card then says so too)."""
    import os

    return os.getenv("AIMARKET_A2A_INVOKE", "1").strip().lower() not in ("0", "false", "no", "off")


def _rpc_error(
    request_id: str | int | None,
    code: int,
    message: str,
    *,
    reason: str,
) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
            "data": [
                {
                    "@type": "type.googleapis.com/google.rpc.ErrorInfo",
                    "reason": reason,
                    "domain": "a2a-protocol.org",
                }
            ],
        },
    }


def _json_error(
    request_id: str | int | None,
    code: int,
    message: str,
    *,
    reason: str,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        _rpc_error(request_id, code, message, reason=reason),
        status_code=status_code,
        media_type="application/json",
        headers={"A2A-Version": A2A_PROTOCOL_VERSION},
    )


def _number(
    value: Any,
    name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a JSON number")
    out = float(value)
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    if minimum is not None and out < minimum:
        raise ValueError(f"{name} must be >= {minimum:g}")
    if maximum is not None and out > maximum:
        raise ValueError(f"{name} must be <= {maximum:g}")
    return out


def _search_args(params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    message = params.get("message")
    if not isinstance(message, dict):
        raise ValueError("message is required")
    if message.get("role") != "ROLE_USER":
        raise ValueError("message.role must be ROLE_USER")
    message_id = message.get("messageId")
    if not isinstance(message_id, str) or not message_id.strip() or len(message_id) > 200:
        raise ValueError("message.messageId must be a non-empty string up to 200 characters")
    if message.get("taskId") is not None:
        raise LookupError("task not found")

    parts = message.get("parts")
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_A2A_PARTS:
        raise ValueError(f"message.parts must contain 1..{MAX_A2A_PARTS} parts")

    texts: list[str] = []
    options: dict[str, Any] | None = None
    content_fields = {"text", "raw", "url", "data"}
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ValueError(f"message.parts[{index}] must be an object")
        if len(json.dumps(part, ensure_ascii=False).encode()) > MAX_A2A_PART_BYTES:
            raise ValueError(f"message.parts[{index}] exceeds {MAX_A2A_PART_BYTES} bytes")
        present = [name for name in content_fields if name in part]
        if len(present) != 1:
            raise ValueError(
                f"message.parts[{index}] must contain exactly one of text, raw, url, data"
            )
        kind = present[0]
        if kind == "text":
            if not isinstance(part["text"], str):
                raise ValueError(f"message.parts[{index}].text must be a string")
            texts.append(part["text"])
        elif kind == "data":
            if options is not None or not isinstance(part["data"], dict):
                raise ValueError("exactly one structured data part is supported")
            options = part["data"]
        else:
            raise TypeError("only text and structured JSON inputs are supported")

    options = options or {}
    allowed = {"intent", "limit", "budget", "maxLatencyMs", "minTrust", "hub", "category"}
    unknown = sorted(set(options) - allowed)
    if unknown:
        raise ValueError(f"unsupported search option: {unknown[0]}")
    intent_value = options.get("intent", "\n".join(texts).strip())
    if not isinstance(intent_value, str):
        raise ValueError("intent must be a string")
    intent = intent_value.strip()
    if len(intent) > MAX_A2A_QUERY_CHARS:
        raise ValueError(f"intent exceeds {MAX_A2A_QUERY_CHARS} characters")

    limit_value = options.get("limit", 10)
    if isinstance(limit_value, bool) or not isinstance(limit_value, int):
        raise ValueError("limit must be an integer")
    if not 1 <= limit_value <= MAX_A2A_RESULTS:
        raise ValueError(f"limit must be between 1 and {MAX_A2A_RESULTS}")

    budget = _number(options.get("budget"), "budget", minimum=0)
    max_latency_value = options.get("maxLatencyMs")
    if max_latency_value is not None and (
        isinstance(max_latency_value, bool) or not isinstance(max_latency_value, int)
    ):
        raise ValueError("maxLatencyMs must be an integer")
    max_latency = _number(max_latency_value, "maxLatencyMs", minimum=1)
    min_trust = _number(options.get("minTrust"), "minTrust", minimum=0, maximum=1)

    hub = options.get("hub", "any")
    category = options.get("category")
    if not isinstance(hub, str) or not hub.strip() or len(hub) > 300:
        raise ValueError("hub must be a non-empty string up to 300 characters")
    if category is not None and (
        not isinstance(category, str) or not category.strip() or len(category) > 80
    ):
        raise ValueError("category must be a non-empty string up to 80 characters")

    search_args = {
        "intent": intent,
        "budget": budget,
        "max_latency_ms": int(max_latency) if max_latency is not None else None,
        "min_trust": min_trust,
        "hub": hub.strip(),
        "category": category.strip() if isinstance(category, str) else None,
        "include_demo": False,
        "include_stale": False,
        "limit": limit_value,
    }
    return intent, search_args


# ── marketplace-invoke: parsing ──────────────────────────────────────────────


@dataclass
class _Incoming:
    """A validated SendMessage ``message``, before any skill interprets it."""

    message_id: str
    context_id: str | None
    task_id: str | None
    texts: list[str] = field(default_factory=list)
    data: list[Any] = field(default_factory=list)
    raws: list[tuple[bytes, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Invoke:
    raw: bytes
    product_id: str
    capability_id: str
    source_hub: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()

    @property
    def b64(self) -> str:
        return base64.b64encode(self.raw).decode("ascii")


@dataclass
class _Payment:
    header: str
    tx_hash: str
    nonce: str
    network: str
    payer: str


class _PaymentWithoutSettlement(ValueError):
    """An x402 payload with no transaction in it: well-formed, but not a payment here."""


def _asks_for_invoke(message: Any) -> bool:
    if not isinstance(message, dict):
        return False
    if message.get("taskId") is not None:
        return True
    for part in message.get("parts") or []:
        if not isinstance(part, dict):
            continue
        if "raw" in part:
            return True
        if isinstance(part.get("data"), dict) and "invoke" in part["data"]:
            return True
    return False


def _b64decode(text: Any, name: str) -> bytes:
    """ProtoJSON ``bytes``: standard or URL-safe base64, padding optional."""
    if not isinstance(text, str):
        raise ValueError(f"{name} must be a base64 string")
    cleaned = text.strip()
    padded = cleaned + "=" * (-len(cleaned) % 4)
    try:
        if "-" in cleaned or "_" in cleaned:
            return base64.urlsafe_b64decode(padded)
        return base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"{name} is not valid base64") from exc


def _parse_message(params: dict[str, Any]) -> _Incoming:
    message = params.get("message")
    if not isinstance(message, dict):
        raise ValueError("message is required")
    if message.get("role") != "ROLE_USER":
        raise ValueError("message.role must be ROLE_USER")
    message_id = message.get("messageId")
    if not isinstance(message_id, str) or not message_id.strip() or len(message_id) > 200:
        raise ValueError("message.messageId must be a non-empty string up to 200 characters")
    task_id = message.get("taskId")
    if task_id is not None and (not isinstance(task_id, str) or not task_id or len(task_id) > 200):
        raise ValueError("message.taskId must be a non-empty string")
    context_id = message.get("contextId")
    if context_id is not None and (
        not isinstance(context_id, str) or not context_id.strip() or len(context_id) > 200
    ):
        raise ValueError("message.contextId must be a non-empty string up to 200 characters")
    metadata = message.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValueError("message.metadata must be an object")

    parts = message.get("parts")
    if not isinstance(parts, list) or not 1 <= len(parts) <= MAX_A2A_PARTS:
        raise ValueError(f"message.parts must contain 1..{MAX_A2A_PARTS} parts")
    incoming = _Incoming(message_id=message_id, context_id=context_id, task_id=task_id,
                         metadata=dict(metadata or {}))
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            raise ValueError(f"message.parts[{index}] must be an object")
        if len(json.dumps(part, ensure_ascii=False).encode()) > MAX_A2A_PART_BYTES:
            raise ValueError(f"message.parts[{index}] exceeds {MAX_A2A_PART_BYTES} bytes")
        present = [name for name in ("text", "raw", "url", "data") if name in part]
        if len(present) != 1:
            raise ValueError(f"message.parts[{index}] must contain exactly one of text, raw, url, data")
        kind = present[0]
        if kind == "text":
            if not isinstance(part["text"], str):
                raise ValueError(f"message.parts[{index}].text must be a string")
            incoming.texts.append(part["text"])
        elif kind == "data":
            if incoming.data:
                raise ValueError("exactly one structured data part is supported")
            incoming.data.append(part["data"])
        elif kind == "raw":
            media = str(part.get("mediaType") or "").split(";", 1)[0].strip().lower()
            incoming.raws.append((_b64decode(part["raw"], f"message.parts[{index}].raw"), media))
        else:
            raise TypeError("url parts are not supported; send the invoke as data or raw JSON")
    return incoming


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not valid JSON")


def _validate_invoke(obj: Any) -> dict[str, Any]:
    """The invoke body's fields, checked against the hub's own InvokeRequest bounds.

    Checked here so a malformed request is an INVALID_PARAMS answer rather than a task that
    fails with a 422, and so nothing unexpected (a channel's payment_authorization, a field
    from a future protocol) is carried into a paid call by accident.
    """
    if not isinstance(obj, dict):
        raise ValueError("the invoke must be a JSON object")
    unknown = sorted(set(obj) - set(_INVOKE_FIELDS))
    if unknown:
        raise ValueError(f"unsupported invoke field: {unknown[0]}")
    out: dict[str, Any] = {}
    for name in ("product_id", "capability_id"):
        value = obj.get(name)
        if not isinstance(value, str) or not 2 <= len(value.strip()) <= 80:
            raise ValueError(f"invoke.{name} must be a string of 2-80 characters")
        out[name] = value.strip()
    source_hub = obj.get("source_hub", "local")
    if not isinstance(source_hub, str) or not source_hub.strip() or len(source_hub) > 256:
        raise ValueError("invoke.source_hub must be 'local' or the hub URL search returned")
    out["source_hub"] = source_hub.strip()
    payload = obj.get("input", {})
    if not isinstance(payload, dict):
        raise ValueError("invoke.input must be an object")
    out["input"] = payload
    if obj.get("max_price_usd") is not None:
        out["max_price_usd"] = _number(obj["max_price_usd"], "invoke.max_price_usd", minimum=0, maximum=1_000_000)
    for name in ("verify", "subcontract"):
        if obj.get(name) is not None:
            if not isinstance(obj[name], dict):
                raise ValueError(f"invoke.{name} must be an object")
            out[name] = obj[name]
    from pydantic import ValidationError

    from aimarket_hub.api_models import InvokeRequest

    try:
        InvokeRequest.model_validate(out)
    except ValidationError as exc:
        # ValidationError.__str__ includes input_value: never echo the buyer's input.
        raise ValueError("invoke does not satisfy the request schema") from exc
    return out


def _invoke_from(incoming: _Incoming, *, mandated: bool, required: bool) -> _Invoke | None:
    invokes = [d for d in incoming.data if isinstance(d, dict) and "invoke" in d]
    if incoming.data and not invokes:
        raise ValueError('the data part of an invoke message must be {"invoke": {...}}')
    if len(incoming.raws) > 1:
        raise ValueError("send the invoke as exactly one raw part")
    if incoming.raws and invokes:
        raise ValueError("send the invoke as a raw part or as a data part, not both")
    if incoming.raws:
        raw, media = incoming.raws[0]
        if media != "application/json":
            raise ValueError("a raw part must be the invoke JSON with mediaType application/json")
        try:
            obj = json.loads(raw, parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("the raw part is not a JSON invoke body") from exc
        fields = _validate_invoke(obj)
        # The bytes go on EXACTLY as received: a mandate proof signs them.
        return _Invoke(raw=raw, product_id=fields["product_id"], capability_id=fields["capability_id"],
                       source_hub=fields["source_hub"])
    if invokes:
        if mandated:
            raise ValueError(
                f"a mandated invoke must be one raw application/json part holding the exact bytes "
                f"{PROOF_HEADER} signs (POST {INVOKE_PATH}); a data part would be re-serialized"
            )
        block = invokes[0]
        if set(block) != {"invoke"}:
            raise ValueError('the data part of an invoke message must be exactly {"invoke": {...}}')
        fields = _validate_invoke(block["invoke"])
        raw = json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return _Invoke(raw=raw, product_id=fields["product_id"], capability_id=fields["capability_id"],
                       source_hub=fields["source_hub"])
    if required:
        raise ValueError('no invoke in the message: send a data part {"invoke": {...}} or a raw invoke')
    return None


def _payment_from(metadata: dict[str, Any], *, required_terms: dict[str, Any] | None) -> _Payment | None:
    """The a2a-x402 ``payment-submitted`` payload of a follow-up, as the header the hub reads."""
    status = metadata.get("x402.payment.status")
    payload = metadata.get("x402.payment.payload")
    if status is None and payload is None:
        return None
    if status != "payment-submitted" or payload is None:
        raise ValueError(
            "x402.payment.status must be payment-submitted with x402.payment.payload "
            "(or payment-rejected to cancel)"
        )
    from aimarket_hub import settle

    decoded: dict[str, Any] | None = None
    if isinstance(payload, str) and settle.is_tx_hash(payload):
        header = payload.strip()
    elif isinstance(payload, dict):
        decoded = payload
        header = base64.b64encode(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).decode("ascii")
    else:
        raise ValueError("x402.payment.payload must be a PaymentPayload object or a transaction hash")
    if len(header) > MAX_PAYMENT_CHARS:
        raise ValueError(f"x402.payment.payload exceeds {MAX_PAYMENT_CHARS} characters")
    ref = settle.extract_payment_ref(header, decoded)
    network = ""
    payer = ""
    if decoded is not None:
        accepted = decoded.get("accepted") if isinstance(decoded.get("accepted"), dict) else {}
        network = str(decoded.get("network") or accepted.get("network") or "")
        inner = decoded.get("payload") if isinstance(decoded.get("payload"), dict) else {}
        auth = inner.get("authorization") if isinstance(inner.get("authorization"), dict) else {}
        payer = str(auth.get("from") or decoded.get("payer") or "")
    if not network and required_terms:
        accepts = required_terms.get("accepts") or [{}]
        network = str((accepts[0] if isinstance(accepts, list) and accepts else {}).get("network") or "")
    if not ref["tx_hash"]:
        raise _PaymentWithoutSettlement(
            "this hub verifies a transfer on chain and never settles one: send the USDC transfer "
            "to the quoted payTo yourself, then put its txHash in x402.payment.payload"
        )
    return _Payment(header=header, tx_hash=ref["tx_hash"], nonce=ref["nonce"], network=network, payer=payer)


# ── marketplace-invoke: answers → task states ───────────────────────────────


@dataclass
class _Outcome:
    state: str
    message: dict[str, Any]
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    nonce: str | None = None
    #: The owner approval the task now waits on (mandates.md §5.6), and until when.
    awaiting: str = ""
    waits_until: float | None = None


def _expiry(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _agent_message(task_id: str, context_id: str, text: str, *, data: Any = None,
                   metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    parts: list[dict[str, Any]] = [{"text": text, "mediaType": "text/plain"}]
    if data is not None:
        parts.append({"data": data, "mediaType": "application/json"})
    message: dict[str, Any] = {
        "messageId": f"a2am_{secrets.token_hex(8)}",
        "contextId": context_id,
        "taskId": task_id,
        "role": "ROLE_AGENT",
        "parts": parts,
    }
    if metadata:
        message["metadata"] = metadata
    return message


def _decode_terms(header: str | None) -> dict[str, Any] | None:
    """The V2 PaymentRequired from a PAYMENT-REQUIRED header — whoever minted it.

    A federated 402 passes the PEER's terms through unchanged (x402_passthrough), so this
    never assumes the hub wrote them; the payTo is then that peer's seller.
    """
    if not header:
        return None
    try:
        decoded = json.loads(base64.b64decode(header.strip() + "=" * (-len(header.strip()) % 4)))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    return decoded if isinstance(decoded, dict) and decoded.get("accepts") else None


def _payable(terms: dict[str, Any] | None) -> bool:
    """Terms a payer can act on: at least one offer for a positive amount."""
    for offer in (terms or {}).get("accepts") or []:
        try:
            if isinstance(offer, dict) and int(str(offer.get("amount") or "0")) > 0:
                return True
        except ValueError:
            continue
    return False


def _usd(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return 0.0
    return float(value)


def _x402_error(detail: str) -> str:
    """The a2a-x402 error code for a hub ``payment_invalid`` detail."""
    text = (detail or "").lower()
    if "already been spent" in text or "already been used" in text or "already spent" in text:
        return "DUPLICATE_NONCE"
    if "expired" in text:
        return "EXPIRED_PAYMENT"
    if "signature" in text or "authorization" in text:
        return "INVALID_SIGNATURE"
    if "atomic units" in text or "the call costs" in text:
        return "INVALID_AMOUNT"
    if "network" in text:
        return "NETWORK_MISMATCH"
    if "insufficient" in text or "balance" in text:
        return "INSUFFICIENT_FUNDS"
    return "SETTLEMENT_FAILED"


def _detail_text(body: dict[str, Any]) -> str:
    detail = body.get("detail")
    if isinstance(detail, str):
        return detail[:500]
    if detail is None:
        return ""
    if isinstance(detail, list):
        # FastAPI's validation shape repeats the offending value under `input` (and `ctx`):
        # the buyer's own input, which a task must not keep.
        detail = [{k: v for k, v in d.items() if k not in ("input", "ctx")} if isinstance(d, dict) else d
                  for d in detail]
    return json.dumps(detail, ensure_ascii=False)[:500]


_AUTH_HINT = (
    f"Send X-API-Key (a credit account on this hub) or {MANDATE_HEADER} with {PROOF_HEADER} as "
    "HTTP headers on a follow-up message to this task."
)


def _outcome(*, status_code: int, headers: Mapping[str, str], body: Any, task_id: str, context_id: str,
             invoke: _Invoke, hub_url: str, payment: _Payment | None, trial_exhausted: bool,
             mandated: bool = False, approval: dict[str, Any] | None = None) -> _Outcome:
    """Map one invoke answer onto the task state A2A clients act on (docs/a2a.md, state table)."""
    if not isinstance(body, dict):
        body = {"success": False, "error": "invalid_response", "detail": str(body)[:500]}
    error = str(body.get("error") or "")
    detail = _detail_text(body)
    cap = invoke.capability_id
    # The bill of materials is on the root's answer whether the root delivered or not
    # (mandates.md §6.4): a root that failed after its subcontractors delivered still paid for
    # them, and the bill is what explains the charge. Where a completed task keeps it, too.
    bill = body.get("subcontracting")
    task_meta = {"aimarket": {"subcontracting": bill}} if isinstance(bill, dict) else {}

    def say(state: str, text: str, *, data: Any = None, metadata: dict[str, Any] | None = None,
            nonce: str | None = None) -> _Outcome:
        return _Outcome(state=state, message=_agent_message(task_id, context_id, text, data=data, metadata=metadata),
                        metadata=task_meta, nonce=nonce)

    if 200 <= status_code < 300:
        if body.get("success") is False:
            return say(FAILED, f"{cap} did not complete: {error or detail or 'the provider failed'}", data=body)
        return _completed(body, task_id=task_id, context_id=context_id, invoke=invoke, hub_url=hub_url,
                          payment=payment)

    terms = _decode_terms(headers.get("payment-required"))
    nonce = str(headers.get("x-payment-nonce") or body.get("nonce") or "")
    aimarket: dict[str, Any] = {"error": error or f"http_{status_code}"}
    if detail:
        aimarket["detail"] = detail
    for key in ("needed", "balance", "limit", "mandate", "payment_ways", "missing", "accepts", "sandbox"):
        if key in body and not (key == "accepts" and status_code == 402):
            aimarket[key] = body[key]
    if trial_exhausted:
        aimarket["trial_exhausted"] = True
    # The hub's refusal, minus the V1 x402 twin of terms that are already in
    # x402.payment.required in V2 form.
    # Never persist FastAPI's validation input echo (or arbitrary provider error bodies).
    refusal = {"success": False, "error": error or f"http_{status_code}", "detail": detail}

    if (status_code == 402 and error == "payment_invalid") or error == "payment_malformed":
        meta: dict[str, Any] = {
            "x402.payment.status": "payment-failed",
            "x402.payment.error": _x402_error(detail),
            "aimarket": aimarket,
        }
        if terms:
            meta["x402.payment.required"] = terms
        return say(INPUT_REQUIRED,
                   f"The payment was not accepted: {detail or error}. Pay again per "
                   "x402.payment.required (a fresh nonce), or reply with x402.payment.status "
                   "payment-rejected to cancel.", data=refusal, metadata=meta, nonce=nonce or None)

    if status_code == 402 and error == "approval_required" and approval is not None:
        # mandates.md §5.6: nothing is wrong with the call; it waits for the person whose money
        # it spends. The task waits as long as the request does, and moves on its own when the
        # owner answers (approval_listener), telling the client's webhooks. ``approval`` is
        # this hub's own record, checked by the caller — never the answer's word for it.
        aimarket["approval"] = approval
        outcome = say(AUTH_REQUIRED,
                      f"{cap} costs ${_usd(approval.get('amount_usd')):g}, over what the mandate may spend "
                      f"without its owner. Waiting for an owner of the funding account to approve request "
                      f"{approval.get('approval_id')} (up to ${_usd(approval.get('max_usd')):g}). Once approved, "
                      "send a follow-up on this task with a fresh mandate proof over the same invoke bytes.",
                      data=refusal, metadata={"aimarket": aimarket})
        outcome.awaiting = str(approval.get("approval_id") or "")
        outcome.waits_until = _expiry(approval.get("expires_at"))
        return outcome

    if error == "approval_queue_full":
        # Not a retry-later: only the owner answering waiting requests makes room.
        return say(REJECTED, f"{error}: {detail}", data=refusal, metadata={"aimarket": aimarket})

    if status_code == 402:
        if error in ("mandate_limit", "mandate_unfunded", "allowance_exhausted", "listing_not_sellable",
                     "approval_denied"):
            return say(REJECTED, f"{error}: {detail}".strip(": "), data=refusal, metadata={"aimarket": aimarket})
        if mandated:
            # A mandate spends the owner's credits and cannot be combined with an x402 payment
            # (mandate_rail_unsupported), so on-chain terms would be an offer the agent can never
            # take. What is missing is the owner's money; once topped up, a follow-up with a
            # fresh proof runs the same task.
            return say(AUTH_REQUIRED,
                       f"The mandate's funding account cannot pay for {cap}: {detail or error}. The owner "
                       "must top it up; then send a follow-up with a fresh mandate proof.",
                       data=refusal, metadata={"aimarket": aimarket})
        # Asked by code BEFORE looking for terms: the x402 middleware puts an offer on every
        # 402, including a mandate refusal that has nothing to do with a price.
        if error in ("mandate_required", "payment_authorization_required") or not _payable(terms):
            # No way to pay on chain (a credits-only hub, a listing with no payee): only
            # credentials can move this call forward.
            return say(AUTH_REQUIRED, f"{detail or error or 'payment required'}. {_AUTH_HINT}", data=refusal,
                       metadata={"aimarket": aimarket})
        needed = _usd(body.get("needed"))
        text = (
            f"Payment required: {f'${needed:g}' if needed else 'a price'} for {cap}. Pay per "
            "x402.payment.required and reply on this task with x402.payment.payload — it must include "
            "the settle txHash (this hub verifies the transfer on chain and never settles one). "
            + _AUTH_HINT.replace("Send", "Or send", 1)
        )
        if trial_exhausted:
            text = "The free trial for this caller is used up. " + text
        meta = {"x402.payment.status": "payment-required", "x402.payment.required": terms, "aimarket": aimarket}
        return say(INPUT_REQUIRED, text, data=refusal, metadata=meta, nonce=nonce or None)

    if status_code == 401 or error in ("mandate_malformed", "mandate_required"):
        return say(AUTH_REQUIRED, f"{error or 'unauthorized'}: {detail}. {_AUTH_HINT}", data=refusal,
                   metadata={"aimarket": aimarket})

    if status_code == 400 and error == "incomplete_input":
        return say(INPUT_REQUIRED,
                   f"{detail} Reply on this task with the complete invoke (same capability). Any "
                   "payment already made is not consumed.", data=refusal, metadata={"aimarket": aimarket})

    if payment is not None and status_code != 402:
        from aimarket_hub.settle import invoice_ttl_s

        # The nonce stays bound to this task, but the invoice it belongs to expires
        # invoice_ttl_s() after the quote: past that, the same payload is refused as expired
        # although the transfer is on chain. Say so, rather than promising an open retry.
        return say(INPUT_REQUIRED,
                   "The paid call did not complete. Correct the request or retry on this task "
                   "with the same payment payload before its invoice expires "
                   f"({invoice_ttl_s()} s after the quote); the invoice nonce stays bound to this task.",
                   data=refusal, metadata={"aimarket": aimarket, "x402.payment.status": "payment-retry",
                                           "x402.invoice_ttl_s": invoice_ttl_s()})

    if status_code in (400, 403, 404, 409, 413, 422):
        return say(REJECTED, f"{error or 'refused'}: {detail}".strip(": "), data=refusal,
                   metadata={"aimarket": aimarket})

    # 429 (rate limit, or a trial the hub would not turn into a price), 5xx, anything else.
    return say(FAILED, f"{error or f'http {status_code}'}: {detail}".strip(": "), data=refusal,
               metadata={"aimarket": aimarket})


def _completed(body: dict[str, Any], *, task_id: str, context_id: str, invoke: _Invoke, hub_url: str,
               payment: _Payment | None) -> _Outcome:
    base = hub_url.rstrip("/")
    local = invoke.source_hub in ("", "local")
    # Oracle-core providers (including GAIA) return `output`; local capabilities
    # return `result`. Preserve an explicitly null `result`, just as the provider
    # response verifier does, rather than dropping a federated oracle's delivery.
    result = body.get("result", body.get("output"))
    result_part = (
        {"text": result, "mediaType": "text/plain"} if isinstance(result, str)
        else {"data": result, "mediaType": "application/json"}
    )
    artifacts: list[dict[str, Any]] = [{
        "artifactId": "result",
        "name": "result",
        "description": f"What {invoke.capability_id} returned",
        "parts": [result_part],
    }]
    receipt = body.get("receipt")
    if isinstance(receipt, dict):
        receipt_meta: dict[str, Any] = {"sourceHub": invoke.source_hub}
        if local:
            receipt_meta["verifyEndpoint"] = f"{base}/ai-market/v2/receipts/verify"
        else:
            # A federated receipt is signed by the provider, not by this hub: check it against
            # the key its origin publishes, not against this hub's verifier.
            receipt_meta["signerWellKnown"] = f"{invoke.source_hub.rstrip('/')}/.well-known/ai-market.json"
        artifacts.append({
            "artifactId": "aimarket-receipt",
            "name": "aimarket-receipt",
            "description": "The signed gateway receipt for this call",
            "parts": [{"data": receipt, "mediaType": "application/json"}],
            "metadata": receipt_meta,
        })
    provenance = body.get("provenance_receipt")
    if isinstance(provenance, dict):
        artifacts.append({
            "artifactId": "provenance",
            "name": "provenance",
            "description": "The AWR/2 work receipt for this call",
            "parts": [{"data": provenance, "mediaType": "application/json"}],
            "metadata": {k: provenance[k] for k in ("digest_sri", "receipt_url", "verify_url") if provenance.get(k)},
        })
    aimarket: dict[str, Any] = {"capability": {
        "product_id": invoke.product_id, "capability_id": invoke.capability_id, "source_hub": invoke.source_hub,
    }}
    for key in ("price_usd", "list_price_usd", "latency_ms", "remaining_balance", "mandate", "subcontracting",
                "job", "verification", "routed_via"):
        if key in body:
            aimarket[key] = body[key]
    # A local trial reports itself as top-level keys, a federated one as an object: one shape here.
    if isinstance(body.get("sandbox"), dict):
        aimarket["sandbox"] = body["sandbox"]
    elif body.get("sandbox"):
        aimarket["sandbox"] = {"sandbox": True, **{k: body[k] for k in ("remaining", "used", "max_trials") if k in body}}
    price = _usd(body.get("price_usd"))
    priced = price > 0
    status_meta: dict[str, Any] = {}
    # Receipts only for a payment the hub actually took: a payload sent for a call that turned
    # out to cost nothing was never checked, and calling it settled would be a lie.
    if payment is not None and (priced or _usd(body.get("list_price_usd")) > 0):
        # Rebuilt from what the client forwarded and the hub accepted — the invoke answer does
        # not echo the settlement. `payer` only when the payload named one (a bare txHash
        # payload does not, and a guessed payer would be worse than none).
        receipt_entry: dict[str, Any] = {"success": True, "transaction": payment.tx_hash, "network": payment.network}
        if payment.payer:
            receipt_entry["payer"] = payment.payer
        status_meta["x402.payment.status"] = "payment-completed"
        status_meta["x402.payment.receipts"] = [receipt_entry]
    text = f"{invoke.capability_id} completed" + (f" (${price:g})" if priced else "")
    message = _agent_message(task_id, context_id, text, metadata=status_meta or None)
    return _Outcome(state=COMPLETED, message=message, artifacts=artifacts, metadata={"aimarket": aimarket})


# ── principals ──────────────────────────────────────────────────────────────


def _principal(kind: str, value: str) -> str:
    digest = hashlib.sha256(f"aimarket-a2a-principal/1\n{kind}\n{value}".encode("utf-8")).hexdigest()[:40]
    return f"{kind}:{digest}"


def _is_sri(value: str) -> bool:
    return value.startswith("sha256-") and 20 <= len(value) <= 100


def _history_user(incoming: _Incoming, invoke: _Invoke | None, *, task_id: str, context_id: str) -> dict[str, Any]:
    """The user's message as history keeps it: what was asked for, never the input itself
    (it is purged with the invoke body) and never a payment payload."""
    if invoke is not None:
        parts: list[dict[str, Any]] = [{
            "data": {"invoke": {"product_id": invoke.product_id, "capability_id": invoke.capability_id,
                                "source_hub": invoke.source_hub}},
            "mediaType": "application/json",
            "metadata": {"aimarket.redacted": "input and payment are not stored"},
        }]
    else:
        parts = [{"text": "(follow-up)", "mediaType": "text/plain",
                  "metadata": {"aimarket.redacted": "content and payment are not stored"}}]
    message: dict[str, Any] = {"messageId": incoming.message_id, "contextId": context_id, "taskId": task_id,
                               "role": "ROLE_USER", "parts": parts}
    status = incoming.metadata.get("x402.payment.status")
    if isinstance(status, str):
        message["metadata"] = {"x402.payment.status": status[:40]}
    return message


def _parse_timestamp(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    if not isinstance(value, str):
        raise ValueError("statusTimestampAfter must be an RFC 3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("statusTimestampAfter must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _optional_int(value: Any, name: str, *, low: int, high: int | None = None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < low or (high is not None and value > high):
        raise ValueError(f"{name} must be between {low} and {high}" if high is not None else f"{name} must be >= {low}")
    return value


def _count(method: str, result: str) -> None:
    try:
        from aimarket_hub.metrics import record_a2a_request

        record_a2a_request(method, result)
    except Exception:  # noqa: BLE001 - metrics are optional (prometheus_client may be absent)
        pass


def attach_a2a_routes(
    router: APIRouter,
    *,
    hub_name: str,
    hub_url: str,
    hub_version: str,
    search: SearchCallable,
    bridge: InvokeBridge | None = None,
) -> Callable[[], None]:
    """Attach the public Agent Card and bounded A2A JSON-RPC endpoint.

    Without a ``bridge`` the endpoint is discovery-only: no skill creates a Task, so the task
    methods answer honestly (not found / an empty list) and the card lists search alone.

    Returns the task sweep (expiry, retention and the recovery of tasks whose process died),
    for the hub to run on a timer: a restart is exactly when nobody may call /a2a for a while.
    """
    push = bridge.push if bridge is not None else None
    card = build_agent_card(hub_name=hub_name, hub_url=hub_url, hub_version=hub_version,
                            invoke=bridge is not None, push=push is not None)
    background: set[Any] = set()
    card_bytes = json.dumps(
        card, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    etag = f'"{hashlib.sha256(card_bytes).hexdigest()}"'
    cache_headers = {"Cache-Control": "public, max-age=300", "ETag": etag}

    @router.api_route("/.well-known/agent-card.json", methods=["GET", "HEAD"])
    async def agent_card(request: Request):
        if request.headers.get("if-none-match", "").strip() == etag:
            _count("agent-card", "not_modified")
            return Response(status_code=304, headers=cache_headers)
        _count("agent-card", "ok")
        return JSONResponse(card, headers=cache_headers)

    @router.post("/a2a")
    async def a2a_jsonrpc(
        request: Request,
        a2a_version: str = Header(default="", alias="A2A-Version"),
    ):
        """Count every call by method and outcome, then answer it (see metrics.a2a_requests_total).

        A task answer is counted by the state it reached (``completed``, ``input_required``…),
        so the counter says not only that A2A clients call, but whether they end up paying.
        """
        response = await _a2a_jsonrpc(request, a2a_version)
        method, result = "-", "ok"
        try:
            payload = json.loads(await request.body())
            if isinstance(payload, dict) and isinstance(payload.get("method"), str):
                method = payload["method"]
            answer = json.loads(bytes(response.body))
            error = answer.get("error") if isinstance(answer, dict) else None
            if isinstance(error, dict):
                data = error.get("data") or [{}]
                result = str((data[0] if isinstance(data, list) and data else {}).get("reason") or "error")
            else:
                found = answer.get("result") if isinstance(answer, dict) else None
                # SendMessage wraps the task; GetTask/CancelTask answer with the task itself.
                task = (found.get("task") if isinstance(found, dict) and "task" in found else found)
                state = ((task or {}).get("status") or {}).get("state") if isinstance(task, dict) else None
                if isinstance(state, str) and state.startswith("TASK_STATE_"):
                    result = state[len("TASK_STATE_"):].lower()
        except Exception:  # noqa: BLE001 - a metric must never change an answer
            result = "unparsed"
        _count(method, result)
        return response

    def _ok(request_id: str | int, result: dict[str, Any], *, x402: bool = False) -> JSONResponse:
        headers = {"A2A-Version": A2A_PROTOCOL_VERSION}
        if x402:
            # Echo the extension the answer speaks (A2A extension activation).
            headers["A2A-Extensions"] = X402_EXTENSION_URI
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result}, headers=headers)

    def _task_answer(request_id: str | int, row: dict[str, Any], *, history_length: int | None,
                     envelope: bool = True, include_artifacts: bool = True) -> JSONResponse:
        """A Task answer. SendMessage wraps it (SendMessageResponse is a oneof task|message);
        GetTask and CancelTask return the Task itself."""
        task = tasks_mod.render(row, history_length=history_length, include_artifacts=include_artifacts)
        message = task["status"].get("message")
        metadata = message.get("metadata") if isinstance(message, dict) else None
        speaks_x402 = isinstance(metadata, dict) and any(str(k).startswith("x402.") for k in metadata)
        return _ok(request_id, {"task": task} if envelope else task, x402=speaks_x402)

    async def _a2a_jsonrpc(request: Request, a2a_version: str):
        content_length = request.headers.get("content-length", "").strip()
        if content_length.isdigit() and int(content_length) > MAX_A2A_BODY_BYTES:
            return _json_error(
                None, -32600, "Request payload too large",
                reason="REQUEST_TOO_LARGE", status_code=413,
            )
        raw = await request.body()
        if len(raw) > MAX_A2A_BODY_BYTES:
            return _json_error(
                None, -32600, "Request payload too large",
                reason="REQUEST_TOO_LARGE", status_code=413,
            )
        media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if media_type != "application/json":
            return _json_error(
                None, -32600, "Content-Type must be application/json",
                reason="INVALID_CONTENT_TYPE",
            )
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _json_error(None, -32700, "Invalid JSON payload", reason="JSON_PARSE_ERROR")
        if not isinstance(payload, dict):
            return _json_error(
                None, -32600, "Request payload validation error",
                reason="INVALID_REQUEST",
            )

        request_id = payload.get("id")
        if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
            request_id = None
            return _json_error(
                request_id, -32600, "Request id must be a string or integer",
                reason="INVALID_REQUEST_ID",
            )
        if payload.get("jsonrpc") != "2.0" or not isinstance(payload.get("method"), str):
            return _json_error(
                request_id, -32600, "Request payload validation error",
                reason="INVALID_REQUEST",
            )
        if a2a_version.strip() != A2A_PROTOCOL_VERSION:
            return _json_error(
                request_id, -32009,
                f"A2A protocol version {a2a_version.strip() or '0.3'} is not supported",
                reason="VERSION_NOT_SUPPORTED",
            )

        method = payload["method"]
        params = payload.get("params", {})
        if not isinstance(params, dict):
            return _json_error(
                request_id, -32602, "Invalid parameters", reason="INVALID_PARAMS",
            )

        if method == "SendMessage":
            configuration = params.get("configuration")
            if configuration is not None and not isinstance(configuration, dict):
                return _json_error(
                    request_id, -32602, "Invalid parameters", reason="INVALID_CONFIGURATION",
                )
            configuration = configuration or {}
            asks_invoke = bridge is not None and _asks_for_invoke(params.get("message"))
            push_config: dict[str, str] | None = None
            if configuration.get("taskPushNotificationConfig") is not None:
                if push is None:
                    return _json_error(
                        request_id, -32003, "Push notifications are not supported",
                        reason="PUSH_NOTIFICATION_NOT_SUPPORTED",
                    )
                if not asks_invoke:
                    # A search is answered with a Message: no task, so a webhook would never be
                    # called. Accepting it silently would let the client wait for nothing.
                    return _json_error(
                        request_id, -32602,
                        "push notifications are for tasks; marketplace-search answers with a Message",
                        reason="INVALID_CONFIGURATION",
                    )
                try:
                    # Off the loop: checking the webhook resolves the caller's own host name.
                    push_config = await asyncio.to_thread(a2a_push.parse_config,
                                                          configuration["taskPushNotificationConfig"])
                except a2a_push.PushConfigError as exc:
                    return _json_error(request_id, -32602, str(exc), reason="INVALID_CONFIGURATION")
            immediate = configuration.get("returnImmediately", False)
            if not isinstance(immediate, bool):
                return _json_error(request_id, -32602, "returnImmediately must be a boolean",
                                   reason="INVALID_CONFIGURATION")
            accepted = configuration.get("acceptedOutputModes")
            if accepted is not None and (
                not isinstance(accepted, list)
                or not any(mode in {"text/plain", "application/json"} for mode in accepted)
            ):
                return _json_error(
                    request_id, -32005, "Requested output content type is not supported",
                    reason="CONTENT_TYPE_NOT_SUPPORTED",
                )
            if asks_invoke:
                try:
                    history_length = _optional_int(configuration.get("historyLength"), "historyLength", low=0)
                except ValueError as exc:
                    return _json_error(request_id, -32602, str(exc), reason="INVALID_CONFIGURATION")
                return await _send_invoke(request, request_id, params, history_length,
                                          push_config=push_config, immediate=immediate)
            # A search is answered with a Message at once: returnImmediately is moot for it.
            try:
                intent, kwargs = _search_args(params)
            except LookupError:
                return _json_error(
                    request_id, -32001, "Task not found", reason="TASK_NOT_FOUND",
                )
            except TypeError as exc:
                return _json_error(
                    request_id, -32005, str(exc), reason="CONTENT_TYPE_NOT_SUPPORTED",
                )
            except ValueError as exc:
                return _json_error(
                    request_id, -32602, str(exc), reason="INVALID_PARAMS",
                )
            try:
                result = await search(**kwargs)
            except Exception:
                return _json_error(
                    request_id, -32603, "Marketplace search failed", reason="INTERNAL_ERROR",
                )
            count = len(result.get("matches", [])) if isinstance(result, dict) else 0
            incoming_message = params["message"]
            context_id = incoming_message.get("contextId")
            if not isinstance(context_id, str) or not context_id or len(context_id) > 200:
                context_id = str(uuid.uuid4())
            metadata = {
                "marketProtocol": "aimarket-v2",
                "invokeEndpoint": f"{hub_url.rstrip('/')}{INVOKE_PATH}",
                "mcpEndpoint": f"{hub_url.rstrip('/')}/mcp",
            }
            if bridge is not None:
                metadata["invokeSkill"] = "marketplace-invoke"
            response_message = {
                "messageId": str(uuid.uuid4()),
                "contextId": context_id,
                "role": "ROLE_AGENT",
                "parts": [
                    {
                        "text": f"Found {count} executable market offer{'s' if count != 1 else ''} for: {intent or 'browse'}",
                        "mediaType": "text/plain",
                    },
                    {"data": result, "mediaType": "application/json"},
                ],
                "metadata": metadata,
            }
            return _ok(request_id, {"message": response_message})

        if method in {"GetTask", "CancelTask", "ListTasks"} and bridge is not None:
            try:
                return await _task_method(request, request_id, method, params, raw)
            except ValueError as exc:
                return _json_error(request_id, -32602, str(exc), reason="INVALID_PARAMS")
        if method == "ListTasks":
            return _ok(request_id, {"tasks": [], "nextPageToken": "", "pageSize": 0, "totalSize": 0})
        if method in {"GetTask", "CancelTask"}:
            return _json_error(
                request_id, -32001, "Task not found", reason="TASK_NOT_FOUND",
            )
        if method in {"SendStreamingMessage", "SubscribeToTask", "GetExtendedAgentCard"}:
            return _json_error(
                request_id, -32004, "Operation is not supported",
                reason="UNSUPPORTED_OPERATION",
            )
        if method in {
            "CreateTaskPushNotificationConfig", "GetTaskPushNotificationConfig",
            "ListTaskPushNotificationConfigs", "DeleteTaskPushNotificationConfig",
        } and push is not None:
            try:
                return await _push_method(request, request_id, method, params, raw)
            except a2a_push.PushConfigError as exc:
                return _json_error(request_id, -32602, str(exc), reason="INVALID_PARAMS")
            except ValueError as exc:
                return _json_error(request_id, -32602, str(exc), reason="INVALID_PARAMS")
        if method in {
            "CreateTaskPushNotificationConfig", "GetTaskPushNotificationConfig",
            "ListTaskPushNotificationConfigs", "DeleteTaskPushNotificationConfig",
        }:
            return _json_error(
                request_id, -32003, "Push notifications are not supported",
                reason="PUSH_NOTIFICATION_NOT_SUPPORTED",
            )
        return _json_error(request_id, -32601, "Method not found", reason="METHOD_NOT_FOUND")

    # ── marketplace-invoke ──────────────────────────────────────────────────

    def _sweep(*, force: bool = False) -> None:
        # Housekeeping runs on the request path, and must never be the reason a call fails.
        assert bridge is not None
        try:
            swept = bridge.tasks.sweep(force=force)
        except Exception as exc:  # noqa: BLE001
            logger.warning("a2a: task sweep failed: %s", exc)
            return
        for task_id in swept.get("task_ids") or []:
            _notify(bridge.tasks.get(task_id))
        if not swept.get("ran"):
            return
        try:
            for row in bridge.tasks.stale():
                _notify(_recover_one(row))
        except Exception as exc:  # noqa: BLE001
            logger.warning("a2a: recovering abandoned tasks failed: %s", exc)
        if push is not None and swept.get("deleted"):
            try:
                push.store.prune()
            except Exception as exc:  # noqa: BLE001
                logger.warning("a2a: pruning push configs failed: %s", exc)

    def _recover_one(row: dict[str, Any]) -> dict[str, Any] | None:
        """Move on a task whose process died mid-call, saying what it cost (a2a_tasks lease).

        Nothing was sent, or what was reserved has been released: the task waits again, its
        input kept, and a follow-up with the caller's credentials runs it — the hub never
        stores credentials, so it cannot run the call on its own. Something was captured, or
        the call was paid on a rail the hub cannot read back (x402): the task fails, naming
        the receipts, because the result went down with the process."""
        assert bridge is not None
        row = bridge.tasks.take_stale(row)
        if row is None:
            return None   # renewed meanwhile, or another sweep is recovering it
        now = time.time()
        started = float(row.get("invoke_started") or 0) > 0
        report = {"outcome": "none", "receipts": []}
        if started:
            rail = str(row.get("invoke_rail") or "")
            if rail in ("credits", "trial", "none") and bridge.recover is not None:
                report = bridge.recover(row)
            else:
                report = {"outcome": "unknown", "receipts": []}
        outcome = str(report.get("outcome") or "unknown")
        receipts = [str(r) for r in report.get("receipts") or []]
        meta = tasks_mod.load_json(row.get("metadata_json"), {})
        block = meta.get("aimarket") if isinstance(meta.get("aimarket"), dict) else {}
        meta["aimarket"] = {**block, "recovered": {"outcome": outcome, "receipts": receipts}}
        if outcome in ("none", "released"):
            state = AUTH_REQUIRED
            text = ("The hub restarted " + ("before sending this call" if not started else
                    "while this call ran, before it was charged; what it had reserved was released")
                    + ". Nothing was charged. Send a follow-up on this task with your credentials to run it.")
        elif outcome == "charged":
            state = FAILED
            text = ("The hub restarted while this call ran. It was charged (receipts: " + ", ".join(receipts)
                    + ") but its result was lost with the process. Give these receipt ids to the operator.")
        else:
            state = FAILED
            text = ("The hub restarted while this call ran, and whether it was charged cannot be read back here. "
                    "A charge, if any, is on your receipts and balance; do not assume the call ran.")
        note = _agent_message(row["task_id"], row["context_id"], text, metadata={"aimarket": {"recovered": {
            "outcome": outcome, "receipts": receipts}}})
        moved = bridge.tasks.resolve_stale(row, state=state, status={"state": state, "timestamp": tasks_mod.iso(now),
                                                                     "message": note}, metadata=meta, now=now)
        if moved is not None:
            logger.warning("a2a: recovered abandoned task %s as %s (%s)", row["task_id"], state, outcome)
        return moved

    def _notify(row: dict[str, Any] | None) -> None:
        """Tell a task's webhooks its state (a2a_push). Never fails the caller."""
        if push is None or not row:
            return
        try:
            push.notify(tasks_mod.render(row, history_length=0, include_artifacts=False))
        except Exception as exc:  # noqa: BLE001
            logger.warning("a2a: push for task %s failed: %s", row.get("task_id"), exc)

    def _subscribe(row: dict[str, Any], push_config: dict[str, str] | None) -> None:
        if push is not None and push_config is not None:
            push.store.create(row["task_id"], push_config)

    def _send_principal(request: Request, caller: str) -> str:
        """Who a SendMessage is on behalf of. A binding, not an authentication: the invoke
        itself authenticates (an unknown key is a 401 there, a bad proof a mandate refusal)."""
        assert bridge is not None
        digest = (request.headers.get(MANDATE_HEADER) or "").strip()
        if _is_sri(digest):
            return _principal("mandate", digest)
        key = (request.headers.get("X-API-Key") or "").strip()
        if key:
            account = bridge.resolve_account(key)
            if account:
                return _principal("acct", account)
        # An unknown key identifies nobody, so the task is the caller's by address — and a
        # follow-up with the right key can still continue it.
        from aimarket_hub.mcp_gateway import visitor_for

        return _principal("anon", visitor_for(caller))

    def _read_principal(request: Request, raw: bytes) -> str:
        """Who a GetTask/CancelTask/ListTasks is from, authenticated, or "".

        A mandate holder proves it with a fresh proof over ``POST /a2a`` and this exact
        JSON-RPC body (its nonce is consumed); a credit account with its key.
        """
        assert bridge is not None
        digest = (request.headers.get(MANDATE_HEADER) or "").strip()
        proof = (request.headers.get(PROOF_HEADER) or "").strip()
        if digest and proof and bridge.verify_mandate(digest, proof, "POST", _signed_path(request), raw):
            return _principal("mandate", digest)
        key = (request.headers.get("X-API-Key") or "").strip()
        if key:
            account = bridge.resolve_account(key)
            if account:
                return _principal("acct", account)
        return ""

    def _may_see(row: dict[str, Any], principal: str) -> bool:
        # An anonymous task is held by its unguessable id alone, like /ai-market/v2/jobs/{id};
        # a task someone authenticated for is theirs only.
        owner = str(row.get("principal_hash") or "")
        return owner.startswith("anon:") or (bool(principal) and owner == principal)

    def _forwarded(request: Request) -> dict[str, str]:
        out: dict[str, str] = {}
        for name in _FORWARDED:
            value = (request.headers.get(name) or "").strip()
            if value:
                out[name] = value
        return out

    async def _send_invoke(request: Request, request_id: str | int, params: dict[str, Any],
                           history_length: int | None, *, push_config: dict[str, str] | None = None,
                           immediate: bool = False) -> JSONResponse:
        assert bridge is not None
        caller = bridge.client_address(request) or ""
        if not bridge.allow_request(caller):
            return _json_error(request_id, -32000, "A2A request rate exceeded",
                               reason="RATE_LIMITED", status_code=429)
        try:
            incoming = _parse_message(params)
        except TypeError as exc:
            return _json_error(request_id, -32005, str(exc), reason="CONTENT_TYPE_NOT_SUPPORTED")
        except ValueError as exc:
            return _json_error(request_id, -32602, str(exc), reason="INVALID_PARAMS")
        if any(request.headers.get(h) for h in _JOB_HEADERS):
            return _json_error(
                request_id, -32602,
                f"job headers are not accepted on /a2a: a provider buying inside a job does so at {INVOKE_PATH}",
                reason="INVALID_PARAMS",
            )
        mandated = bool((request.headers.get(MANDATE_HEADER) or "").strip())
        if mandated and not bridge.verify_mandate(
            request.headers.get(MANDATE_HEADER, ""), request.headers.get(A2A_PROOF_HEADER, ""),
            "POST", _signed_path(request), await request.body(),
        ):
            return _json_error(request_id, -32001, "A fresh mandate proof over POST /a2a is required",
                               reason="TASK_NOT_FOUND")
        _sweep()
        if incoming.task_id is not None:
            return await _follow_up(request, request_id, incoming, history_length, caller, mandated,
                                    push_config=push_config, immediate=immediate)
        try:
            invoke = _invoke_from(incoming, mandated=mandated, required=True)
        except ValueError as exc:
            return _json_error(request_id, -32602, str(exc), reason="INVALID_PARAMS")
        assert invoke is not None
        principal = _send_principal(request, caller)
        # No contextId: the messageId itself — what the SDK and ARGUS send as their default.
        # A hashed stand-in made a retry that sent the id on one attempt and not the other two
        # tasks and two charges.
        context_id = incoming.context_id or incoming.message_id
        row, created = bridge.tasks.create(
            principal=principal, context_id=context_id, message_id=incoming.message_id,
            product_id=invoke.product_id, capability_id=invoke.capability_id, source_hub=invoke.source_hub,
            invoke_b64=invoke.b64, invoke_sha256=invoke.sha256, history=[],
        )
        if not created:
            # A retried SendMessage: answer with the task it already started — never a second
            # invoke, which would be a second payment. The same messageId with a different
            # request is a client bug, not a retry, and gets no task.
            if str(row.get("invoke_sha256") or "") != invoke.sha256:
                return _json_error(
                    request_id, -32602, "this messageId was already used for a different request",
                    reason="INVALID_PARAMS",
                )
            try:
                _subscribe(row, push_config)
            except a2a_push.PushConfigError as exc:
                return _json_error(request_id, -32602, str(exc), reason="INVALID_CONFIGURATION")
            if principal.startswith("anon:"):
                # An anonymous principal is an address, and an address is shared (NAT, a
                # proxy pool): a second caller who guessed the messageId and resent the same
                # bytes would be handed the first caller's paid result. The retry still gets
                # the task and its state — never a second run — but not the artifacts.
                return _task_answer(request_id, row, history_length=0, include_artifacts=False)
            return _task_answer(request_id, row, history_length=history_length)
        try:
            _subscribe(row, push_config)
        except a2a_push.PushConfigError as exc:  # pragma: no cover - a fresh task has no configs yet
            return _json_error(request_id, -32602, str(exc), reason="INVALID_CONFIGURATION")
        user = _history_user(incoming, invoke, task_id=row["task_id"], context_id=context_id)
        return await _answer_run(request_id, row, invoke, headers=_forwarded(request), caller=caller,
                                 payment=None, history_user=user, history_length=history_length,
                                 immediate=immediate)

    async def _answer_run(request_id: str | int, row: dict[str, Any], invoke: _Invoke, *,
                          headers: dict[str, str], caller: str, payment: _Payment | None,
                          history_user: dict[str, Any], history_length: int | None, immediate: bool,
                          nonce: str = "") -> JSONResponse:
        """Run the claimed task and answer with its outcome — or, with returnImmediately,
        answer WORKING now and let it run on (its webhooks hear the outcome)."""
        assert bridge is not None
        if immediate and len(background) < MAX_BACKGROUND_INVOKES:
            job = asyncio.get_running_loop().create_task(_run(
                row, invoke, headers=headers, caller=caller, payment=payment,
                history_user=history_user, nonce=nonce))
            background.add(job)
            job.add_done_callback(background.discard)
            return _task_answer(request_id, bridge.tasks.get(row["task_id"]) or row, history_length=history_length)
        finished = await _run(row, invoke, headers=headers, caller=caller, payment=payment,
                              history_user=history_user, nonce=nonce)
        return _task_answer(request_id, finished, history_length=history_length)

    async def _follow_up(request: Request, request_id: str | int, incoming: _Incoming,
                         history_length: int | None, caller: str, mandated: bool, *,
                         push_config: dict[str, str] | None = None, immediate: bool = False) -> JSONResponse:
        assert bridge is not None
        row = bridge.tasks.get(incoming.task_id or "")
        if row is None or not _may_see(row, _send_principal(request, caller)):
            return _json_error(request_id, -32001, "Task not found", reason="TASK_NOT_FOUND")
        if incoming.context_id and incoming.context_id != row["context_id"]:
            return _json_error(request_id, -32602, "contextId does not match the task", reason="INVALID_PARAMS")
        try:
            _subscribe(row, push_config)
        except a2a_push.PushConfigError as exc:
            return _json_error(request_id, -32602, str(exc), reason="INVALID_CONFIGURATION")
        state = str(row["task_state"])
        if incoming.message_id == row.get("last_message_id") or state == WORKING:
            # The same follow-up again, or one arriving while the invoke still runs: the
            # current task is the answer, and nothing is run (or paid) twice.
            return _task_answer(request_id, row, history_length=history_length)
        if state in TERMINAL:
            return _json_error(request_id, -32004, f"task {row['task_id']} is already {state}",
                               reason="UNSUPPORTED_OPERATION")

        if incoming.metadata.get("x402.payment.status") == "payment-rejected":
            note = _agent_message(row["task_id"], row["context_id"], "Canceled: the client declined to pay.",
                                  metadata={"x402.payment.status": "payment-rejected"})
            canceled = bridge.tasks.cancel(
                row, status={"state": CANCELED, "timestamp": tasks_mod.iso(time.time()), "message": note},
                history_add=[_history_user(incoming, None, task_id=row["task_id"], context_id=row["context_id"]),
                             note],
            )
            _notify(canceled)
            return _task_answer(request_id, canceled or bridge.tasks.get(row["task_id"]) or row,
                                history_length=history_length)

        previous = tasks_mod.load_json(row.get("status_json"), {})
        previous_meta = ((previous.get("message") or {}).get("metadata") or {}) if isinstance(previous, dict) else {}
        terms = previous_meta.get("x402.payment.required") if isinstance(previous_meta, dict) else None
        unsettled: _PaymentWithoutSettlement | None = None
        try:
            payment = _payment_from(incoming.metadata, required_terms=terms if isinstance(terms, dict) else None)
        except _PaymentWithoutSettlement as exc:
            payment, unsettled = None, exc
        except ValueError as exc:
            return _json_error(request_id, -32602, str(exc), reason="INVALID_PARAMS")
        try:
            replacement = _invoke_from(incoming, mandated=mandated, required=False)
        except ValueError as exc:
            return _json_error(request_id, -32602, str(exc), reason="INVALID_PARAMS")
        if replacement is not None and (
            replacement.product_id, replacement.capability_id, replacement.source_hub,
        ) != (row["product_id"], row["capability_id"], row["source_hub"]):
            return _json_error(
                request_id, -32602,
                "a follow-up may complete the invoke, not change what is bought: same product_id, "
                "capability_id and source_hub — start a new task for another capability",
                reason="INVALID_PARAMS",
            )

        claimed = bridge.tasks.claim(row["task_id"], message_id=incoming.message_id)
        if claimed is None:
            # Lost to a concurrent follow-up or a cancel, or the task expired: read it back
            # (sweeping first, so an expired task says FAILED rather than still waiting).
            _sweep(force=True)
            return _task_answer(request_id, bridge.tasks.get(row["task_id"]) or row, history_length=history_length)

        invoke = replacement or _Invoke(
            raw=base64.b64decode(str(claimed.get("invoke_body") or "")),
            product_id=str(claimed["product_id"]), capability_id=str(claimed["capability_id"]),
            source_hub=str(claimed["source_hub"]),
        )
        user = _history_user(incoming, replacement, task_id=row["task_id"], context_id=row["context_id"])
        if unsettled is not None:
            meta: dict[str, Any] = {"x402.payment.status": "payment-failed",
                                    "x402.payment.error": "SETTLEMENT_FAILED",
                                    "aimarket": {"error": "payment_not_settled", "detail": str(unsettled)}}
            if isinstance(terms, dict):
                meta["x402.payment.required"] = terms
            note = _agent_message(row["task_id"], row["context_id"],
                                  f"The payment was not accepted: {unsettled}.", metadata=meta)
            finished = bridge.tasks.finish(
                claimed, state=INPUT_REQUIRED,
                status={"state": INPUT_REQUIRED, "timestamp": tasks_mod.iso(time.time()), "message": note},
                metadata=tasks_mod.load_json(claimed.get("metadata_json"), {}),
                history_add=[user, note],
                invoke_b64=invoke.b64, invoke_sha256=invoke.sha256,
            )
            _notify(finished)
            return _task_answer(request_id, finished, history_length=history_length)
        return await _answer_run(request_id, claimed, invoke, headers=_forwarded(request), caller=caller,
                                 payment=payment, history_user=user, history_length=history_length,
                                 immediate=immediate, nonce=str(claimed.get("x402_nonce") or ""))

    async def _keep_lease(task_id: str) -> None:
        """Renew this process's lease on a running task until the call returns."""
        assert bridge is not None
        while True:
            await asyncio.sleep(tasks_mod.LEASE_S / 3)
            try:
                if not bridge.tasks.renew(task_id):
                    return
            except Exception as exc:  # noqa: BLE001 - the next tick tries again
                logger.warning("a2a: renewing the lease of %s failed: %s", task_id, exc)

    async def _run(row: dict[str, Any], invoke: _Invoke, *, headers: dict[str, str], caller: str,
                   payment: _Payment | None, history_user: dict[str, Any], nonce: str = "") -> dict[str, Any]:
        """One invoke through the app, and its outcome recorded on the claimed task.

        ``headers`` are the caller's forwarded headers, read before the answer went: with
        returnImmediately this runs after it, when nothing of the request should be touched."""
        assert bridge is not None
        headers = dict(headers)
        if payment is not None:
            headers["PAYMENT-SIGNATURE"] = payment.header
            # The invoice this task was quoted, unless the payload names its own.
            if not payment.nonce and nonce:
                headers["X-Payment-Nonce"] = nonce
            # Redeeming needs the secret the invoice's nonce commits to (settle.py): the nonce
            # and the transaction are public once mined. Only for THIS task's own invoice — a
            # payload naming another nonce gets none, so a task cannot redeem an invoice some
            # other caller was quoted.
            if nonce and (not payment.nonce or payment.nonce.lower() == nonce.lower()):
                secret = bridge.payment_secret(nonce)
                if secret:
                    headers["X-Payment-Secret"] = secret
        paying = bool(headers.get("X-API-Key") or headers.get(MANDATE_HEADER) or payment is not None)
        trial_exhausted = False
        rail = "x402" if payment is not None else ("credits" if paying else "trial")
        # The call leaves now: from here money may move. Mark it, and keep this process's lease
        # while it runs, so a restart mid-call is recovered from the ledger, not guessed at.
        bridge.tasks.started(row["task_id"], rail=rail)
        renewer = asyncio.get_running_loop().create_task(_keep_lease(row["task_id"]))
        try:
            # Only a PRICED capability takes the trial, exactly as on the MCP gateway: on a
            # free one it would spend an allowance for nothing.
            trial = not paying and bridge.is_priced(invoke.product_id, invoke.capability_id, invoke.source_hub)
            call_headers = dict(headers)
            if trial:
                from aimarket_hub.mcp_gateway import visitor_for

                call_headers[SANDBOX_HEADER] = visitor_for(caller)
            call_headers[TASK_HEADER] = row["task_id"]
            call_headers[INTERNAL_HEADER] = INTERNAL_SECRET
            status_code, answer_headers, body = await bridge.invoke(invoke.raw, call_headers, caller)
            if (trial and status_code == 429 and isinstance(body, dict)
                    and body.get("error") == "trial_quota_exhausted"):
                # A spent allowance carries no price, and "429" reads as "retry later". What the
                # caller needs is the payment gate's answer: the same call without a trial
                # identity is an ordinary unpaid invoke, answered 402 with the terms.
                retry = await bridge.invoke(invoke.raw, {**headers, TASK_HEADER: row["task_id"],
                                                         INTERNAL_HEADER: INTERNAL_SECRET}, caller)
                if retry[0] == 402:
                    status_code, answer_headers, body = retry
                    trial_exhausted = True
        except Exception:  # noqa: BLE001 - the task must not stay WORKING forever
            logger.exception("a2a: invoke of %s for task %s raised", invoke.capability_id, row["task_id"])
            status_code, answer_headers, body = 502, {}, {
                "success": False, "error": "invoke_unavailable",
                "detail": "the hub could not complete the call; check your receipts and balance before retrying",
            }
        finally:
            renewer.cancel()
        approval = _own_approval(status_code, body, headers, invoke)
        try:
            outcome = _outcome(status_code=status_code, headers=_lower(answer_headers), body=body,
                               task_id=row["task_id"], context_id=row["context_id"], invoke=invoke,
                               hub_url=hub_url, payment=payment, trial_exhausted=trial_exhausted,
                               mandated=bool(headers.get(MANDATE_HEADER)), approval=approval)
        except Exception:  # noqa: BLE001 - an answer this code cannot read must still end the task
            logger.exception("a2a: could not map the invoke answer (HTTP %s) for task %s", status_code, row["task_id"])
            outcome = _Outcome(state=FAILED, message=_agent_message(
                row["task_id"], row["context_id"],
                f"The hub answered HTTP {status_code} in a form this bridge could not read; check your "
                "receipts and balance before retrying."))
        finished = bridge.tasks.finish(
            row, state=outcome.state,
            status={"state": outcome.state, "timestamp": tasks_mod.iso(time.time()), "message": outcome.message},
            artifacts=outcome.artifacts, metadata=outcome.metadata,
            history_add=[history_user, outcome.message],
            x402_nonce=outcome.nonce, invoke_b64=invoke.b64, invoke_sha256=invoke.sha256,
            awaiting=outcome.awaiting, waits_until=outcome.waits_until,
        )
        _notify(finished)
        if outcome.awaiting and bridge.approval_lookup is not None:
            # An owner who answered while the call was still running found no task waiting on
            # the request yet (approval_listener reads waiting tasks only). Look once more now
            # that it waits, or the answer would never reach it.
            decided = bridge.approval_lookup(outcome.awaiting)
            if decided is not None and decided.get("status") in ("approved", "denied"):
                approval_listener(bridge)(decided)
                finished = bridge.tasks.get(row["task_id"]) or finished
        return finished

    def _own_approval(status_code: int, body: Any, headers: Mapping[str, str],
                      invoke: _Invoke) -> dict[str, Any] | None:
        """The approval request a 402 names, if it is this hub's own, pending, for this very
        mandate and these very bytes. Anything else — a peer's 402 passed through, a stale
        id — is not a wait for an owner, whatever it says."""
        assert bridge is not None
        if (status_code != 402 or not isinstance(body, dict) or body.get("error") != "approval_required"
                or bridge.approval_lookup is None or not headers.get(MANDATE_HEADER)):
            return None
        claimed = body.get("approval") if isinstance(body.get("approval"), dict) else {}
        record = bridge.approval_lookup(str(claimed.get("approval_id") or ""))
        if (record is None or record.get("mandate") != str(headers.get(MANDATE_HEADER)).strip()
                or record.get("body_sha256") != hashlib.sha256(invoke.raw).hexdigest()
                or record.get("status") != "pending"):
            return None
        return record

    async def _task_method(request: Request, request_id: str | int, method: str, params: dict[str, Any],
                           raw: bytes) -> JSONResponse:
        assert bridge is not None
        _sweep()   # a client polling its tasks is when an abandoned one should be recovered
        principal = _read_principal(request, raw)
        if method == "ListTasks":
            context_id = params.get("contextId") or ""
            if not isinstance(context_id, str) or len(context_id) > 200:
                raise ValueError("contextId must be a string up to 200 characters")
            state = params.get("status") or ""
            if state and state not in tasks_mod.ALL_STATES:
                raise ValueError("status must be a TaskState name, e.g. TASK_STATE_COMPLETED")
            page_size = _optional_int(params.get("pageSize"), "pageSize", low=1, high=MAX_LIST_PAGE) or 50
            history_length = _optional_int(params.get("historyLength"), "historyLength", low=0)
            include_artifacts = params.get("includeArtifacts", False)
            if not isinstance(include_artifacts, bool):
                raise ValueError("includeArtifacts must be a boolean")
            after = _parse_timestamp(params.get("statusTimestampAfter"))
            token = params.get("pageToken") or ""
            offset = 0
            if token:
                try:
                    offset = int(_b64decode(token, "pageToken").decode("ascii").removeprefix("o:"))
                except (ValueError, UnicodeDecodeError) as exc:
                    raise ValueError("pageToken is not one this server issued") from exc
                if offset < 0:
                    raise ValueError("pageToken is not one this server issued")
            if not principal:
                # Only an authenticated principal can list: an anonymous task is reachable by its
                # id alone, and listing "tasks from this address" would hand one caller's tasks
                # to everybody behind the same NAT.
                return _ok(request_id, {"tasks": [], "nextPageToken": "", "pageSize": page_size, "totalSize": 0})
            rows, total = bridge.tasks.list(principal, context_id=context_id, state=state, updated_after=after,
                                            limit=page_size, offset=offset)
            next_offset = offset + len(rows)
            next_token = (
                base64.urlsafe_b64encode(f"o:{next_offset}".encode()).decode().rstrip("=")
                if next_offset < total else ""
            )
            return _ok(request_id, {
                "tasks": [tasks_mod.render(r, history_length=history_length, include_artifacts=include_artifacts)
                          for r in rows],
                "nextPageToken": next_token,
                "pageSize": page_size,
                "totalSize": total,
            })

        task_id = params.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("id is required")
        row = bridge.tasks.get(task_id)
        if row is None or not _may_see(row, principal):
            return _json_error(request_id, -32001, "Task not found", reason="TASK_NOT_FOUND")
        if method == "GetTask":
            history_length = _optional_int(params.get("historyLength"), "historyLength", low=0)
            return _task_answer(request_id, row, history_length=history_length, envelope=False)
        # CancelTask: only a task that is waiting on the client can be canceled. A running
        # invoke has already reserved money; stopping the record would not stop the call.
        if row["task_state"] in INTERRUPTED:
            note = _agent_message(row["task_id"], row["context_id"], "Canceled by the client.")
            canceled = bridge.tasks.cancel(
                row, status={"state": CANCELED, "timestamp": tasks_mod.iso(time.time()), "message": note},
                history_add=[note],
            )
            if canceled is not None:
                _notify(canceled)
                return _task_answer(request_id, canceled, history_length=None, envelope=False)
        return _json_error(request_id, -32002, f"task {task_id} cannot be canceled in its current state",
                           reason="TASK_NOT_CANCELABLE")

    async def _push_method(request: Request, request_id: str | int, method: str, params: dict[str, Any],
                           raw: bytes) -> JSONResponse:
        """The four push notification config methods, under GetTask's rule of who may see a
        task: its authenticated principal, or whoever holds an anonymous task's id."""
        assert bridge is not None and push is not None
        task_id = params.get("taskId")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("taskId is required")
        row = bridge.tasks.get(task_id)
        if row is None or not _may_see(row, _read_principal(request, raw)):
            return _json_error(request_id, -32001, "Task not found", reason="TASK_NOT_FOUND")
        if method == "CreateTaskPushNotificationConfig":
            if row["task_state"] in TERMINAL:
                # Nothing will change any more; a webhook would never be called.
                return _json_error(request_id, -32004, f"task {task_id} is already {row['task_state']}",
                                   reason="UNSUPPORTED_OPERATION")
            stored = push.store.create(task_id, await asyncio.to_thread(a2a_push.parse_config, params))
            return _ok(request_id, a2a_push.render(stored))
        if method == "ListTaskPushNotificationConfigs":
            configs = push.store.list(task_id)
            return _ok(request_id, {"configs": [a2a_push.render(c) for c in configs], "nextPageToken": ""})
        config_id = params.get("id")
        if not isinstance(config_id, str) or not config_id:
            raise ValueError("id is required")
        if method == "GetTaskPushNotificationConfig":
            stored = push.store.get(task_id, config_id)
            if stored is None:
                return _json_error(request_id, -32001, "Push notification config not found",
                                   reason="TASK_NOT_FOUND")
            return _ok(request_id, a2a_push.render(stored))
        if not push.store.delete(task_id, config_id):
            return _json_error(request_id, -32001, "Push notification config not found", reason="TASK_NOT_FOUND")
        return _ok(request_id, {})

    if bridge is None:
        return _never
    return lambda: _sweep(force=True)


def approval_listener(bridge: InvokeBridge) -> Callable[[dict[str, Any]], None]:
    """What the mandate store calls once an owner answers an approval (mandates.md §5.6).

    Every task waiting on that request moves without its client asking: a "no" ends it
    REJECTED; a "yes" leaves it waiting, with a status that says the client may now continue
    (the run itself still needs the agent's own fresh proof — an owner's signature alone never
    makes the hub spend). Either way the task's webhooks are told.
    """

    def on_decision(approval: dict[str, Any]) -> None:
        approval_id = str(approval.get("approval_id") or "")
        status = str(approval.get("status") or "")
        if status not in ("approved", "denied"):
            return
        for row in bridge.tasks.waiting_on(approval_id):
            metadata = tasks_mod.load_json(row.get("metadata_json"), {})
            block = metadata.get("aimarket") if isinstance(metadata.get("aimarket"), dict) else {}
            metadata["aimarket"] = {**block, "approval": approval}
            if status == "approved":
                state = AUTH_REQUIRED
                text = (f"The owner approved request {approval_id}. Send a follow-up on this task with a fresh "
                        "mandate proof over the same invoke bytes to run it (before "
                        f"{approval.get('expires_at') or 'the approval expires'}).")
            else:
                state = REJECTED
                text = f"The owner denied request {approval_id}; the call was not made and nothing was charged."
            note = _agent_message(row["task_id"], row["context_id"], text, metadata={"aimarket": {"approval": approval}})
            moved = bridge.tasks.resolve_waiting(
                row, state=state, status={"state": state, "timestamp": tasks_mod.iso(time.time()), "message": note},
                history_add=[note], metadata=metadata,
            )
            if moved is not None and bridge.push is not None:
                bridge.push.notify(tasks_mod.render(moved, history_length=0, include_artifacts=False))

    return on_decision


def _never() -> None:
    return None


def _lower(headers: Mapping[str, str]) -> dict[str, str]:
    try:
        return {str(k).lower(): str(v) for k, v in headers.items()}
    except Exception:  # noqa: BLE001
        return {}
