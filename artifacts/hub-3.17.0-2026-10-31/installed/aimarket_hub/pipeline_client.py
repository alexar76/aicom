"""One durable client operation: prepare, sign locally, invoke and resume.

Paid execution supports buyer-pinned USD EIP-3009 assets on Base and Ethereum.
The all-in budget uses fresh cross-checked Chainlink ETH/USD + 25%, bounded gas,
100x Base L1 fees where applicable and a $0.05 reserve. L1 fees and exchange rates cannot be hard-capped by an EIP-1559 signature.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import tempfile
import time
from decimal import Decimal
from pathlib import Path

import httpx

from aimarket_hub.native_price import native_price
from aimarket_hub.pipeline_lock import FileLock, wallet_lease
from aimarket_hub.payment_profiles import asset_policy, check_terms, quote_asset, USDC
from aimarket_hub.pipeline_verification import verify_document, verify_result
from aimarket_hub.pipeline_payments import authorization_data, payment_transaction, validate_transaction
from aimarket_hub.studio_paid import PreflightRequest, ordered_graph, _json

BASE_USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
GAS_LIMIT = 300_000


class PipelinePending(RuntimeError):
    """The saved order is pending; resume this file, never create a replacement."""

    def __init__(self, state_path, result=None):
        self.state_path, self.result = str(state_path), result
        super().__init__(f"Order pending; resume {state_path}")


class PipelineBudgetError(ValueError):
    pass


class PipelineHTTPError(RuntimeError):
    def __init__(self, response, state_path):
        self.status_code, self.state_path = response.status_code, str(state_path)
        try:
            self.detail = response.json()
        except ValueError:
            self.detail = {"detail": "Hub returned a non-JSON error"}
        super().__init__(f"Hub HTTP {self.status_code}; inspect detail and resume {state_path}; never replace an uncertain order")


def _http_ok(response, path):
    if response.status_code >= 400:
        raise PipelineHTTPError(response, path)


def _positive(value, name, *, zero=False):
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f"{name} must be a finite number") from exc
    if not number.is_finite() or number < 0 or (not zero and number == 0):
        raise ValueError(f"{name} must be {'non-negative' if zero else 'positive'} and finite")
    return number


def _save(path: Path, state: dict):
    if path.is_symlink():
        raise ValueError("recovery file cannot be a symlink")
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(state, stream, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


async def _rpc(client, url, method, params):
    # Public RPCs can throttle even a small order. Retry the identical request,
    # never replacing an invoice or signing a different payment to recover it.
    for attempt in range(3):
        delay = 0.5 * 2**attempt
        try:
            response = await client.post(url, json={"jsonrpc": "2.0", "id": 1,
                                                   "method": method, "params": params}, timeout=10)
        except httpx.TransportError:
            if attempt == 2:
                raise ValueError(f"RPC unavailable for {method}; resume the saved order") from None
        else:
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == 2:
                    raise ValueError(f"RPC HTTP {response.status_code} for {method}; resume the saved order")
                try:
                    suggested = float(response.headers.get("Retry-After", "0"))
                    if math.isfinite(suggested):
                        delay = max(delay, min(5, suggested))
                except ValueError:
                    pass
            else:
                if response.status_code >= 400:
                    # Do not expose a credential-bearing RPC URL in an exception.
                    raise ValueError(f"RPC HTTP {response.status_code} for {method}")
                value = response.json()
                if value.get("error"):
                    raise ValueError(f"RPC refused {method}")
                return value["result"]
        await asyncio.sleep(delay)


def _check_quote(quote, nodes, accepted_assets=None):
    if not quote.get("ready"):
        raise ValueError(f"Graph refused: {quote.get('blockers', [])}")
    graph = ordered_graph([n.model_dump(exclude_none=True) for n in PreflightRequest(nodes=nodes).nodes])
    if quote.get("graph_digest") != hashlib.sha256(_json(graph).encode()).hexdigest():
        raise ValueError("prepared graph differs from the requested graph")
    steps, offers = quote["steps"], quote["offers"]
    if len(steps) != len(graph):
        raise ValueError("prepared graph has a different step count")
    for node, step in zip(graph, steps):
        if any(step.get(k) != node.get(k) for k in ("id", "product_id", "capability_id", "source_hub")):
            raise ValueError("prepared step differs from the requested listing")
    paid = [s for s in steps if s["terms"]]
    if [s["id"] for s in offers] != [s["id"] for s in paid]:
        raise ValueError("prepared payment offers differ from the graph")
    for offer, step in zip(offers, paid):
        if offer["terms"] != step["terms"]:
            raise ValueError("payment offer differs from the quoted terms")
        terms = offer["terms"]
        check_terms(terms, accepted_assets)
        if (int(terms["amount_units"]) <= 0
                or int(terms["seller_units"]) < 0 or int(terms["fee_units"]) < 0
                or int(terms["seller_units"]) + int(terms["fee_units"]) != int(terms["amount_units"])):
            raise ValueError("invalid payment allocation")
        if offer["authorization"] != authorization_data(offer, quote["wallet"]):
            raise ValueError("authorization differs from the quoted terms")
    assets = {(s['terms']['chain_id'], s['terms']['token_contract'].lower(), s['terms']['decimals']) for s in offers}
    if len(assets)>1: raise ValueError('mixed assets require separate orders')
    if sum(int(s["terms"]["amount_units"]) for s in offers) != int(quote["total_units"]):
        raise ValueError("prepared total differs from step amounts")


def _service_cost(asset,service):
    fields = {"service_usd":str(service), "service_token_amount":str(service),
              "token_contract":asset["token_contract"], "chain_id":asset["chain_id"]}
    if USDC.get(asset['chain_id']) == asset['token_contract'].lower(): fields['service_usdc']=str(service)
    return fields


async def _budget(client, state):
    offers = state["quote"]["offers"]
    if not offers:
        return {"service_usdc": "0", "conservative_total_usd": "0"}
    asset = quote_asset(state["quote"])
    if state["quote"].get("gas_sponsorship", {}).get("enabled"):
        service = Decimal(state["quote"]["total_units"]) / 10**asset["decimals"]
        if service > Decimal(state["max_total_usd"]):
            raise PipelineBudgetError("Service price exceeds the buyer budget")
        return {**_service_cost(asset,service), "buyer_gas_usd": "0", "conservative_total_usd": str(service)}
    from eth_utils import keccak
    rpc = state["rpc_url"]
    if int(await _rpc(client, rpc, "eth_chainId", []), 16) != asset["chain_id"]:
        raise ValueError("RPC differs from the approved payment chain")
    selector = keccak(text="getL1FeeUpperBound(uint256)")[:4].hex()
    l1 = 0
    if asset['chain_id'] == 8453:
        l1 = int(await _rpc(client, rpc, "eth_call", [{
            "to": "0x420000000000000000000000000000000000000F",
            "data": "0x" + selector + format(2048, "064x")}, "latest"]), 16)
    if l1 < 0:
        raise ValueError("invalid L1 fee estimate")
    fees = state.get("fees")
    if fees is None:
        price = int(await _rpc(client, rpc, "eth_gasPrice", []), 16)
        if price <= 0:
            raise ValueError("invalid gas price")
        fees = state["fees"] = {"gas": GAS_LIMIT, "max_fee": 2 * price,
                                "priority_fee": min(price, 1_000_000)}
    price_check = await native_price(client, rpc, _rpc, secondary=state.get("price_rpc_url"),
                                     floor=state.get("native_usd_ceiling"), chain_id=asset["chain_id"])
    ceiling = Decimal(price_check["native_usd_ceiling"])
    native_bound = len(offers) * (fees["gas"] * fees["max_fee"] + 100 * l1)
    service = Decimal(state["quote"]["total_units"]) / 10**asset["decimals"]
    bound = service + Decimal(native_bound) / 10**18 * ceiling + Decimal("0.05")
    if bound > Decimal(state["max_total_usd"]):
        raise PipelineBudgetError(f"Conservative cost ${bound} exceeds budget ${state['max_total_usd']}")
    return {**_service_cost(asset,service), "native_fee_bound_wei": str(native_bound),
            "native_usd_ceiling": str(ceiling), "native_price": price_check, "l1_upper_bound_wei": str(l1),
            "l1_multiplier": 100, "extra_reserve_usd": "0.05",
            "conservative_total_usd": str(bound), "checked_at": time.time()}


async def _sign(client, state, signer):
    quote, offers = state["quote"], state["quote"]["offers"]
    transactions = {}
    asset = quote_asset(quote)
    sponsored = bool(quote.get("gas_sponsorship", {}).get("enabled"))
    if sponsored:
        from eth_account.messages import encode_typed_data
        from aimarket_hub.pipeline_payments import validate_authorization
        if signer is None or signer.address.lower() != quote["wallet"].lower():
            raise ValueError("the original wallet signer is required before payment signing")
        authorizations = {}
        for offer in offers:
            if time.time() + 30 >= min(quote["expires_at"], offer["invoice"]["expires_at"]):
                raise ValueError("prepared offer is too close to expiry; no order submitted")
            signature = "0x" + signer.sign_message(encode_typed_data(full_message=offer["authorization"])).signature.hex().removeprefix("0x")
            validate_authorization(offer, quote["wallet"], signature)
            authorizations[offer["id"]] = signature
    elif offers:
        from eth_account.messages import encode_typed_data
        from eth_utils import to_checksum_address
        if signer is None or signer.address.lower() != quote["wallet"].lower():
            raise ValueError("the original wallet signer is required before payment signing")
        rpc, wallet = state["rpc_url"], quote["wallet"]
        nonce = int(await _rpc(client, rpc, "eth_getTransactionCount", [wallet, "pending"]), 16)
        if nonce != int(await _rpc(client, rpc, "eth_getTransactionCount", [wallet, "latest"]), 16):
            raise ValueError("wallet has other pending transactions")
        balance = int(await _rpc(client, rpc, "eth_call", [{"to": asset["token_contract"],
            "data": "0x70a08231" + wallet[2:].zfill(64)}, "latest"]), 16)
        native = int(await _rpc(client, rpc, "eth_getBalance", [wallet, "latest"]), 16)
        if balance < int(quote["total_units"]) or native < int(state["budget_check"]["native_fee_bound_wei"]):
            raise ValueError("insufficient USDC or native balance")
        state["balances_before"] = {"usdc_units": str(balance), "native_wei": str(native)}
        state["nonce_start"] = nonce
        fees, hashes = state["fees"], {}
        for i, offer in enumerate(offers):
            if time.time() + 30 >= min(quote["expires_at"], offer["invoice"]["expires_at"]):
                raise ValueError("prepared offer is too close to expiry; no order submitted")
            signature = signer.sign_message(encode_typed_data(full_message=offer["authorization"])).signature
            tx = payment_transaction(offer, wallet, "0x" + signature.hex().removeprefix("0x"))
            estimate = int(await _rpc(client, rpc, "eth_estimateGas", [
                {k: hex(v) if isinstance(v, int) else v for k, v in tx.items()}]), 16)
            if estimate > fees["gas"]:
                raise ValueError("payment exceeds the client gas limit")
            tx.pop("from")
            tx.update(to=to_checksum_address(tx["to"]), type=2, chainId=asset["chain_id"], nonce=nonce+i,
                      gas=fees["gas"], maxFeePerGas=fees["max_fee"], maxPriorityFeePerGas=fees["priority_fee"])
            raw = "0x" + signer.sign_transaction(tx).raw_transaction.hex().removeprefix("0x")
            validated = validate_transaction(offer, wallet, raw)
            transactions[offer["id"]], hashes[offer["id"]] = raw, validated["tx_hash"]
        state["tx_hashes"] = hashes
    state["request"] = {"product_id": "hephaestus", "capability_id": "pipeline.run@v1", "source_hub": "local",
        "input": {"run_id": quote["run_id"], "access_token": quote["access_token"], **({"authorizations": authorizations} if sponsored else {"transactions": transactions})}}
    state["phase"] = "submitted"


async def run_pipeline(blueprint=None, *, hub=None, signer=None, max_total_usd=None,
                       rpc_url=None, native_usd_ceiling=None, price_rpc_url=None, state_path="pipeline-run.private.json",
                       resume=False, wait=True, timeout_s=180, poll_interval_s=2, gas_mode=None, accepted_assets=None,
                       client: httpx.AsyncClient | None = None, trusted_hub_key=None, trusted_hub_pq_key=None):
    """Return the root response, including failed orders; raise PipelinePending on timeout.

    Use resume=True with the same private state file after interruption. Completed
    responses are returned locally. Never run concurrent transactions from this wallet.
    Supplying client is useful for managed transports/tests; it remains caller-owned.
    """
    if not math.isfinite(timeout_s) or timeout_s <= 0 or not math.isfinite(poll_interval_s) or poll_interval_s <= 0:
        raise ValueError("timeout and polling interval must be positive and finite")
    path = Path(state_path).absolute()
    path.parent.mkdir(parents=True, exist_ok=True)
    file_lock = FileLock(str(path) + ".lock")
    wallet_lock, lease_path, state, coordinator = None, None, None, None
    try:
        if path.is_symlink():
            raise ValueError("recovery file cannot be a symlink")
        if resume:
            state = json.loads(path.read_text())
            if state.get("version") != 1:
                raise ValueError("unsupported recovery file version")
            if hub is not None and hub.rstrip("/") != state["hub"]:
                raise ValueError("resume cannot change the hub")
            if any(v is not None for v in (blueprint, max_total_usd, native_usd_ceiling, price_rpc_url, gas_mode, accepted_assets)):
                raise ValueError("resume uses the saved graph, RPC and budget; omit overrides")
            if rpc_url is not None:
                # The one value a resume may add: a paid order prepared without an RPC used to be
                # a dead end, because the check ran after the recovery file was saved and resume
                # refused every override. Only when none was saved and nothing is signed yet.
                if state.get("rpc_url"):
                    raise ValueError("resume uses the saved RPC; omit rpc_url")
                if state.get("phase") not in ("preparing", "prepared"):
                    raise ValueError("rpc_url can be added only before the order is signed")
                state["rpc_url"] = rpc_url
                _save(path, state)
            if trusted_hub_key is not None and trusted_hub_key != state.get("trusted_hub_key"):
                raise ValueError("resume cannot change the pinned Hub key")
            if trusted_hub_pq_key is not None and trusted_hub_pq_key != state.get("trusted_hub_pq_key"):
                raise ValueError("resume cannot change the pinned PQ key")
            if state.get("phase") == "completed" and state.get("trusted_hub_key"):
                verify_result(state["result"], state)
                if state.get('wallet_coordination')=='postgres' and os.environ.get('AIMARKET_WALLET_DATABASE_URL'):
                    from aimarket_hub.wallet_coordinator import record_completed
                    await record_completed(state)
                return state["result"]
        else:
            if path.exists():
                raise ValueError("recovery file exists; use resume=True")
            if gas_mode not in (None, "auto", "buyer", "required"):
                raise ValueError("gas_mode must be auto, buyer or required")
            limit = _positive(max_total_usd, "max_total_usd", zero=True)
            ceiling = str(_positive(native_usd_ceiling, "native_usd_ceiling")) if native_usd_ceiling is not None else None
            if not hub or not blueprint or "nodes" not in blueprint:
                raise ValueError("hub and blueprint.nodes are required")
            nodes = [n.model_dump(exclude_none=True) for n in PreflightRequest(nodes=blueprint["nodes"]).nodes]
            state = {"version": 1, "phase": "preparing", "hub": hub.rstrip("/"), "nodes": nodes,
                "wallet": signer.address.lower() if signer else "0x" + "00" * 20,
                "wallet_coordination": "postgres" if os.environ.get("AIMARKET_WALLET_DATABASE_URL") else "local",
                "gas_mode": gas_mode or "auto", "max_total_usd": str(limit), "rpc_url": rpc_url, "native_usd_ceiling": ceiling,
                "price_rpc_url": price_rpc_url, "accepted_assets": asset_policy(accepted_assets),
                "trusted_hub_key": trusted_hub_key, "trusted_hub_pq_key": trusted_hub_pq_key}
            _save(path, state)
        owned = client is None
        client = client or httpx.AsyncClient(timeout=120)
        try:
            if state["phase"] == "preparing":
                response = await client.post(state["hub"] + "/studio/prepare-pipeline", json={
                    "nodes": state["nodes"], "wallet": state["wallet"], "gas_mode": state.get("gas_mode", "buyer"),
                    "max_budget_usd": float(state["max_total_usd"])})
                _http_ok(response, path)
                quote = response.json()
                _check_quote(quote, state["nodes"], state.get("accepted_assets"))
                state["trusted_hub_key"] = state.get("trusted_hub_key") or quote["signer_public_key"]
                state["trusted_hub_pq_key"] = state.get("trusted_hub_pq_key") or quote["signature"].get("pq_public_key")
                verify_document(quote, state["trusted_hub_key"], state["trusted_hub_pq_key"])
                if quote["wallet"].lower() != state["wallet"]:
                    raise ValueError("prepared wallet differs from the buyer")
                sponsorship = quote.get("gas_sponsorship", {})
                if sponsorship.get("enabled"):
                    if state.get("gas_mode") == "buyer" or sponsorship.get("buyer_fee_units") != "0":
                        raise ValueError("gas sponsorship differs from buyer approval")
                    if any(int(o["terms"]["fee_units"]) for o in quote["offers"]):
                        raise ValueError("the existing splitter cannot use gas sponsorship")
                elif state.get("gas_mode") == "required" and quote["offers"]:
                    raise ValueError("the Hub did not offer required gas sponsorship")
                state.update(quote=quote, phase="prepared")
                _save(path, state)
            if not state.get("trusted_hub_key"):
                # Compatibility for pre-verification recovery files: pin over HTTPS before reading results.
                manifest = await client.get(state["hub"] + "/.well-known/ai-market.json")
                manifest.raise_for_status()
                doc = manifest.json()
                state["trusted_hub_key"] = doc["signer_public_key"]
                state["trusted_hub_pq_key"] = doc["signature"].get("pq_public_key")
                verify_document(doc, state["trusted_hub_key"], state["trusted_hub_pq_key"])
                _save(path, state)
            # A second host may hold a pre-signing copy after the original order
            # completed and released its shared reservation. Read before signing.
            if resume and state['phase']=='prepared':
                response=await client.get(state['hub']+f"/studio/paid-runs/{state['quote']['run_id']}/pipeline",
                    headers={'X-Studio-Run-Token':state['quote']['access_token']})
                _http_ok(response,path)
                answer=response.json();verify_result(answer,state)
                if answer.get('status') in ('completed','failed'):
                    state.update(phase='completed',verified=True,result=answer);_save(path,state)
                    if state.get('wallet_coordination')=='postgres' and os.environ.get('AIMARKET_WALLET_DATABASE_URL'):
                        from aimarket_hub.wallet_coordinator import record_completed
                        await record_completed(state)
                    return answer
            sponsored = bool(state["quote"].get("gas_sponsorship", {}).get("enabled"))
            if state["quote"]["offers"] and not sponsored:
                if state.get('wallet_coordination') == 'postgres':
                    from aimarket_hub.wallet_coordinator import WalletCoordinator
                    coordinator = await WalletCoordinator.acquire(state,client,_rpc)
                    _save(path,state)
                else:
                    if os.environ.get('AIMARKET_WALLET_DATABASE_URL'):
                        raise ValueError('existing local order must finish before switching wallet coordination')
                    wallet_lock, lease_path = await wallet_lease(state, path, _save, client, _rpc)
            if state["quote"]["offers"] and not sponsored and not state["rpc_url"]:
                raise ValueError(f"paid execution requires rpc_url; the order is kept: resume {path} with rpc_url=...")
            if state["phase"] == "prepared":
                state["budget_check"] = await _budget(client, state)
                await _sign(client, state, signer)
                if coordinator: await coordinator.checkpoint(state)
                _save(path, state)  # Durable bundle BEFORE any root invoke, including timeout retries.
            deadline = time.monotonic() + timeout_s
            # A previous request may have finished. Read before RPC/budget checks on resume.
            read_status = resume
            failures = 0
            while True:
                retry_after = poll_interval_s
                try:
                    if read_status:
                        response = await client.get(state["hub"] + f"/studio/paid-runs/{state['quote']['run_id']}/pipeline",
                            headers={"X-Studio-Run-Token": state["quote"]["access_token"]})
                    else:
                        state["budget_check"] = await _budget(client, state)
                        if coordinator: await coordinator.checkpoint(state)
                        _save(path, state)
                        response = await client.post(state["hub"] + "/ai-market/v2/invoke", json=state["request"])
                    if response.status_code >= 500 or response.status_code == 429:
                        try:
                            delay = float(response.headers.get("Retry-After", "0"))
                            if math.isfinite(delay):
                                retry_after = max(retry_after, min(60, delay))
                        except ValueError:
                            pass
                        raise httpx.TransportError("temporary Hub failure; retain the original order")
                    _http_ok(response, path)
                    answer = response.json()
                    failures = 0
                    verify_result(answer, state)
                    state["result"] = answer
                    if answer.get("status") in ("completed", "failed"):
                        state["phase"], state["verified"] = "completed", True
                        if coordinator: await coordinator.checkpoint(state)
                        _save(path, state)
                        return answer
                    _save(path, state)
                    if (answer.get("status") == "reconciliation_required"
                            and answer.get("recovery", {}).get("action") != "resume_same_run"):
                        raise PipelinePending(path, answer)
                    # Busy requests are polled read-only, never unlocked by the client.
                    read_status = bool(answer.get("busy"))
                except httpx.TransportError:
                    failures += 1
                    retry_after = max(retry_after, min(30, poll_interval_s * 2 ** min(failures, 8)))
                    read_status = True
                    # No replacement payment, quote or wallet nonce after a lost response.
                    pass
                if not wait:
                    return state.get("result") or {"status": "pending", "trace_id": state["quote"]["run_id"]}
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PipelinePending(path, state.get("result"))
                await asyncio.sleep(min(retry_after, remaining))
        finally:
            if owned:
                await client.aclose()
    finally:
        if coordinator: await coordinator.close(state)
        if wallet_lock:
            # A failure after signing retains ownership: unbroadcast authorizations may still be valid.
            if state.get("phase") in ("preparing", "prepared") or (state.get("verified") and state.get("result", {}).get("success")):
                lease_path.unlink(missing_ok=True)
            wallet_lock.close()
        file_lock.close()
