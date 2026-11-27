"""Read the current Japan pilot quote from Tutu's public MCP endpoint."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx


_ENDPOINT = "https://tutuesim.com/mcp"
_PROTOCOL_VERSION = "2025-06-18"
_QUOTE_TIMEOUT_S = 10
_MAX_RESPONSE_BYTES = 256 * 1024
_PLAN_ID = "JP-1-7"
_SOURCE = "aimarket"


class TutuQuoteUnavailable(RuntimeError):
    """Tutu could not provide a usable checkout quote for the pilot plan."""


def _json(data: bytes | str) -> Any:
    return json.loads(data, parse_float=Decimal)


async def _response_message(response: httpx.Response, request_id: int) -> Any:
    content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
    if content_type not in {"application/json", "text/event-stream"}:
        raise TutuQuoteUnavailable("Tutu returned an unsupported MCP response format")

    buffer = bytearray()
    event_data: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > _MAX_RESPONSE_BYTES:
            raise TutuQuoteUnavailable("Tutu MCP response exceeded the size limit")
        buffer.extend(chunk)
        if content_type == "application/json":
            continue

        # The stream may stay open once it has sent the reply to this request.
        while (end := buffer.find(b"\n")) != -1:
            line = bytes(buffer[:end]).removesuffix(b"\r")
            del buffer[:end + 1]
            if line.startswith(b"data:"):
                event_data.append(line[5:].removeprefix(b" "))
            elif not line and event_data:
                message = _json(b"\n".join(event_data))
                if isinstance(message, dict) and message.get("id") == request_id:
                    return message
                event_data.clear()

    if content_type == "application/json":
        return _json(bytes(buffer))
    raise TutuQuoteUnavailable("Tutu MCP stream closed before the requested reply")


async def _post(
    client: httpx.AsyncClient, method: str, headers: dict[str, str],
    *, request_id: int | None = None, params: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], httpx.Headers]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if request_id is not None:
        payload["id"] = request_id
    if params is not None:
        payload["params"] = params

    async with client.stream("POST", _ENDPOINT, json=payload, headers=headers) as response:
        response.raise_for_status()
        if request_id is None:
            if response.status_code != 202:
                raise TutuQuoteUnavailable("Tutu did not accept the MCP initialization notification")
            return {}, response.headers

        message = await _response_message(response, request_id)
        if (not isinstance(message, dict) or message.get("jsonrpc") != "2.0"
                or type(message.get("id")) is not int or message["id"] != request_id
                or "error" in message or not isinstance(message.get("result"), dict)):
            raise TutuQuoteUnavailable("Tutu returned an invalid MCP reply")
        return message["result"], response.headers


async def _search_plans() -> dict[str, Any]:
    headers = {
        "Accept": "application/json, text/event-stream",
        "User-Agent": "AIMarket-Hub/1.0",
    }
    async with asyncio.timeout(_QUOTE_TIMEOUT_S), httpx.AsyncClient(
        timeout=5, follow_redirects=False, trust_env=False,
    ) as client:
        result, response_headers = await _post(
            client, "initialize", headers, request_id=1, params={
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "aimarket-hub", "version": "1"},
            },
        )
        if result.get("protocolVersion") != _PROTOCOL_VERSION:
            raise TutuQuoteUnavailable("Tutu did not negotiate the expected MCP version")
        headers["MCP-Protocol-Version"] = _PROTOCOL_VERSION
        session = response_headers.get("MCP-Session-Id")
        if session is not None:
            if not 0 < len(session) <= 256 or any(not "!" <= char <= "~" for char in session):
                raise TutuQuoteUnavailable("Tutu returned an invalid MCP session ID")
            headers["MCP-Session-Id"] = session

        await _post(client, "notifications/initialized", headers)
        result, _ = await _post(
            client, "tools/call", headers, request_id=2, params={
                "name": "search_plans",
                "arguments": {"country": "JP", "gb": 1, "days": 7, "lang": "en",
                              "src": _SOURCE, "limit": 8},
            },
        )
        return result


def _checkout_url(value: Any) -> str:
    if (not isinstance(value, str) or len(value) > 2048
            or any(ord(char) <= 32 or ord(char) == 127 or char == "\\" for char in value)):
        raise TutuQuoteUnavailable("Tutu did not return a usable checkout URL")
    url = urlsplit(value)
    if (url.scheme != "https" or url.netloc != "tutuesim.com"
            or url.path != "/en/esim/japan/" or url.fragment):
        raise TutuQuoteUnavailable("Tutu checkout URL does not match the pilot destination")

    query = parse_qsl(url.query, keep_blank_values=True, max_num_fields=32)
    if len(query) != 2:
        raise TutuQuoteUnavailable("Tutu checkout URL contains unexpected parameters")
    if [item for key, item in query if key == "plan"] != [_PLAN_ID]:
        raise TutuQuoteUnavailable("Tutu checkout URL does not select the pilot plan")
    if [item for key, item in query if key == "src"] != [_SOURCE]:
        raise TutuQuoteUnavailable("Tutu checkout URL does not use the pilot attribution tag")
    return value


def _exact_price(value: Any) -> str:
    if type(value) not in (int, Decimal):
        raise TutuQuoteUnavailable("Tutu did not return a numeric USD price")
    price = Decimal(value)
    # Keep fixed-point rendering bounded even if a JSON number uses an exponent.
    if (not price.is_finite() or price.is_signed()
            or not -32 <= price.as_tuple().exponent <= 32 or price.adjusted() > 32):
        raise TutuQuoteUnavailable("Tutu returned an invalid USD price")
    return format(price, "f")


def _quote(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("isError", False) is not False:
        raise TutuQuoteUnavailable("Tutu search_plans reported an error")
    if "structuredContent" in result:
        data = result["structuredContent"]
    else:
        content = result.get("content")
        if (not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict)
                or content[0].get("type") != "text" or not isinstance(content[0].get("text"), str)):
            raise TutuQuoteUnavailable("Tutu did not return a structured quote")
        data = _json(content[0]["text"])
    if (not isinstance(data, dict) or data.get("currency") != "USD"
            or data.get("coverage") != ["JP"] or not isinstance(data.get("plans"), list)):
        raise TutuQuoteUnavailable("Tutu returned unexpected quote currency or coverage")

    matches = [plan for plan in data["plans"]
               if isinstance(plan, dict) and plan.get("plan_id") == _PLAN_ID]
    if len(matches) != 1:
        raise TutuQuoteUnavailable("Tutu did not return one quote for the pilot plan")
    plan = matches[0]
    if plan.get("type") != "data" or plan.get("data") != "1 GB" or plan.get("days") != 7:
        raise TutuQuoteUnavailable("Tutu plan details do not match the pilot plan")
    return {
        "seller": "Tutu eSIM",
        "plan_id": _PLAN_ID,
        "country": "JP",
        "data_gb": 1,
        "validity_days": 7,
        "price": _exact_price(plan.get("price_usd")),
        "currency": "USD",
        "checkout_url": _checkout_url(plan.get("buy_url")),
        "fetched_at": datetime.now(UTC).isoformat(),
    }


async def fetch_tutu_quote() -> dict[str, Any]:
    """Return the current Tutu Japan 1 GB / 7 day quote and merchant checkout link."""
    try:
        return _quote(await _search_plans())
    except (httpx.HTTPError, TimeoutError, ValueError, ArithmeticError, RecursionError) as exc:
        raise TutuQuoteUnavailable("Tutu's public MCP quote is unavailable") from exc
