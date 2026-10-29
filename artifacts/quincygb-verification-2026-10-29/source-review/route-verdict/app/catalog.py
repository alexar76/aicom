"""Catalog-presence lookups: is a resource listed, and does it get paid?

The two lookups mirror exactly the verification steps documented in
~/workspace/platform-signups/x402-bazaar.md (2026-10-15, re-verified
2026-10-21):

- CDP Bazaar: GET https://api.cdp.coinbase.com/platform/v2/x402/discovery/
  merchant?payTo=<wallet> — public, no keys. The merchant endpoint is the
  reliable check (the /discovery/resources and /discovery/search filters
  silently ignore their params, cdp-sdk issue #765). A resource counts as
  listed when one of the merchant's resources matches the checked URL.
- PayAI: GET https://facilitator.payai.network/discovery/listing-status
  ?resource=<url> — 404 means "no catalog row", i.e. not listed.

A failed lookup (network error, 5xx, unparseable body) is reported as
"unknown" — never as "not listed". Absence of evidence is not evidence
of absence, and this service does not fabricate zeros.
"""

from __future__ import annotations

import httpx

CDP_MERCHANT_URL = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/merchant"
PAYAI_LISTING_STATUS_URL = "https://facilitator.payai.network/discovery/listing-status"

_ACTIVITY_INT_KEYS = ("l30DaysUniquePayers", "uniquePayers30d", "unique_payers_30d", "uniquePayers")
_CALLS_INT_KEYS = ("l30DaysTotalCalls", "totalCalls30d", "total_calls_30d", "totalCalls")
_LAST_KEYS = ("lastCalledAt", "last_called_at", "lastActivityAt", "lastActivity")


def _unknown(detail: str) -> dict:
    return {
        "status": "unknown",
        "unique_payers_30d": None,
        "total_calls_30d": None,
        "last_called_at": None,
        "detail": detail,
    }


def _first(mapping: dict, keys: tuple[str, ...]):
    for k in keys:
        if k in mapping and mapping[k] is not None:
            return mapping[k]
    return None


def _activity(entry: dict) -> dict:
    payers = _first(entry, _ACTIVITY_INT_KEYS)
    calls = _first(entry, _CALLS_INT_KEYS)
    last = _first(entry, _LAST_KEYS)
    return {
        "unique_payers_30d": int(payers) if isinstance(payers, (int, float)) else None,
        "total_calls_30d": int(calls) if isinstance(calls, (int, float)) else None,
        "last_called_at": str(last) if last is not None else None,
    }


def _norm_url(url: str) -> str:
    return url.rstrip("/").lower()


async def cdp_bazaar_presence(
    client: httpx.AsyncClient, pay_to: str | None, resource_url: str
) -> dict:
    """Is resource_url cataloged in the CDP Bazaar under this payTo?"""
    if not pay_to:
        return _unknown("No payTo could be parsed from the challenge, so the CDP merchant lookup cannot run.")
    try:
        resp = await client.get(CDP_MERCHANT_URL, params={"payTo": pay_to})
    except httpx.HTTPError as e:
        return _unknown(f"CDP merchant lookup failed: {e}")
    if resp.status_code != 200:
        return _unknown(f"CDP merchant lookup returned HTTP {resp.status_code}.")
    try:
        body = resp.json()
    except ValueError:
        return _unknown("CDP merchant lookup returned a non-JSON body.")
    resources = body.get("resources") if isinstance(body, dict) else None
    if not isinstance(resources, list):
        return _unknown("CDP merchant lookup returned an unexpected shape.")
    for entry in resources:
        if not isinstance(entry, dict):
            continue
        entry_url = entry.get("resource")
        if isinstance(entry_url, str) and _norm_url(entry_url) == _norm_url(resource_url):
            return {"status": "listed", **_activity(entry), "detail": "Resource found in the CDP Bazaar under its payTo wallet."}
    total = (body.get("pagination") or {}).get("total")
    return {
        "status": "not_listed",
        "unique_payers_30d": None,
        "total_calls_30d": None,
        "last_called_at": None,
        "detail": f"payTo wallet has {total if total is not None else len(resources)} CDP Bazaar resources; this URL is not among them.",
    }


async def payai_presence(client: httpx.AsyncClient, resource_url: str) -> dict:
    """Does PayAI's index hold a catalog row for resource_url?"""
    try:
        resp = await client.get(PAYAI_LISTING_STATUS_URL, params={"resource": resource_url})
    except httpx.HTTPError as e:
        return _unknown(f"PayAI listing-status lookup failed: {e}")
    if resp.status_code == 404:
        return {
            "status": "not_listed",
            "unique_payers_30d": None,
            "total_calls_30d": None,
            "last_called_at": None,
            "detail": "PayAI reports no catalog row for this resource (it catalogs only its own facilitator's settlements).",
        }
    if resp.status_code != 200:
        return _unknown(f"PayAI listing-status returned HTTP {resp.status_code}.")
    try:
        body = resp.json()
    except ValueError:
        return _unknown("PayAI listing-status returned a non-JSON body.")
    if not isinstance(body, dict):
        return _unknown("PayAI listing-status returned an unexpected shape.")
    return {"status": "listed", **_activity(body), "detail": "PayAI holds a catalog row for this resource."}
