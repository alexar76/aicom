"""The subgraph manifest must agree with the contract it claims to index.

A subgraph fails silently. `eventHandlers[].event` is hashed into topic0 and
used as a log filter: if the parameter list no longer matches the Solidity
declaration, graph-node matches nothing, reports a healthy sync, and serves an
empty dataset forever. That is exactly what happened here — the settlement event
grew from four parameters to five (`recipient` split into `usedRecipient` +
`refundRecipient`, because one field mis-attributed the hub's revenue to the
depositor) and the manifest kept the old signature, and the expiry event was
renamed to `ChannelExpiredAndSettled`.

Everything below is derived from `src/AIMarketEscrow.sol` and the manifest, so a
future contract change cannot leave this subgraph quietly indexing nothing.

Run:  python3 -m pytest contracts/evm/subgraph/tests -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_SUBGRAPH = Path(__file__).resolve().parents[1]
_EVM = _SUBGRAPH.parent
_SOURCE = _EVM / "src" / "AIMarketEscrow.sol"
_MANIFEST = _SUBGRAPH / "subgraph.yaml"
_SCHEMA = _SUBGRAPH / "schema.graphql"
_MAPPING = _SUBGRAPH / "src" / "mapping.ts"


def _strip_comments(src: str) -> str:
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


@pytest.fixture(scope="module")
def source() -> str:
    assert _SOURCE.is_file(), f"contract source missing: {_SOURCE}"
    return _strip_comments(_SOURCE.read_text())


@pytest.fixture(scope="module")
def manifest() -> str:
    assert _MANIFEST.is_file()
    return _MANIFEST.read_text()


def _solidity_events(src: str) -> dict[str, str]:
    """{name: canonical graph-cli signature} for every event the contract declares."""
    out: dict[str, str] = {}
    for name, params in re.findall(r"\bevent\s+(\w+)\s*\((.*?)\)\s*;", src, flags=re.S):
        parts = []
        for raw in (p.strip() for p in params.split(",") if p.strip()):
            words = raw.split()
            # graph-cli writes the `indexed` keyword BEFORE the type
            parts.append(f"indexed {words[0]}" if "indexed" in words else words[0])
        out[name] = f"{name}({','.join(parts)})"
    return out


def _manifest_handlers(text: str) -> dict[str, str]:
    """{event signature: handler} from the eventHandlers block."""
    # `indexed` keywords put spaces inside the signature, so read to end of line
    pairs = re.findall(r"-\s*event:\s*([^\n]+?)\s*\n\s*handler:\s*(\S+)", text)
    return {sig: handler for sig, handler in pairs}


def test_every_bound_signature_matches_the_contract(source, manifest):
    declared = _solidity_events(source)
    assert declared, "no events parsed from the contract — parser broke"
    bound = _manifest_handlers(manifest)
    assert bound, "no eventHandlers parsed from the manifest — parser broke"

    problems = []
    for sig in bound:
        name = sig.split("(", 1)[0]
        if name not in declared:
            problems.append(f"{sig}: no such event on AIMarketEscrow (indexes nothing)")
        elif declared[name] != sig:
            problems.append(f"{sig}: contract declares {declared[name]} (different topic0)")
    assert not problems, "the subgraph would index nothing for:\n  " + "\n  ".join(problems)


def test_settlement_reports_both_payout_legs(source, manifest):
    """Regression for the drift that motivated this file."""
    declared = _solidity_events(source)
    assert declared["ChannelSettled"] == \
        "ChannelSettled(indexed bytes32,uint256,uint256,address,address)"
    assert declared["ChannelSettled"] in _manifest_handlers(manifest)
    # the pre-rework 4-parameter form must not linger anywhere in the manifest
    assert "ChannelSettled(indexed bytes32,uint256,uint256,address)" not in manifest


def test_no_contract_event_is_left_unindexed(source, manifest):
    declared = set(_solidity_events(source))
    bound = {sig.split("(", 1)[0] for sig in _manifest_handlers(manifest)}
    missing = sorted(declared - bound)
    assert not missing, f"the escrow emits events the subgraph never sees: {missing}"


def test_every_handler_exists_in_the_mapping(manifest):
    mapping = _MAPPING.read_text()
    exported = set(re.findall(r"export\s+function\s+(\w+)", mapping))
    for sig, handler in _manifest_handlers(manifest).items():
        assert handler in exported, f"{sig} points at a missing handler {handler}()"


def test_manifest_entities_exist_in_the_schema(manifest):
    schema = _SCHEMA.read_text()
    declared = set(re.findall(r"^type\s+(\w+)\s+@entity", schema, flags=re.M))
    listed = re.search(r"entities:\s*\n((?:\s*-\s*\w+\n)+)", manifest).group(1)
    for name in re.findall(r"-\s*(\w+)", listed):
        assert name in declared, f"manifest lists entity {name} with no schema type"


def test_mapping_only_writes_declared_entities():
    mapping = _MAPPING.read_text()
    schema = _SCHEMA.read_text()
    declared = set(re.findall(r"^type\s+(\w+)\s+@entity", schema, flags=re.M))
    used = set(re.findall(r"new\s+(\w+)\(", mapping)) | set(re.findall(r"(\w+)\.load\(", mapping))
    for name in used - {"Date", "Array"}:
        assert name in declared, f"mapping writes entity {name} that the schema lacks"


def test_channel_status_enum_mirrors_the_contract(source):
    contract = re.search(r"enum\s+ChannelStatus\s*\{([^}]*)\}", source).group(1)
    contract_values = [v.strip() for v in contract.split(",") if v.strip()]
    block = re.search(r"enum\s+ChannelStatus\s*\{([^}]*)\}", _SCHEMA.read_text()).group(1)
    schema_values = block.split()
    assert schema_values == contract_values, (
        "a status the contract can set but the schema cannot store makes the "
        "mapping abort mid-block")

    # graph-node rejects an entity whose enum field holds an undeclared string and
    # aborts the whole block, so every status literal the mapping can write has to
    # be one of these. Only ONE of them is a direct `.status =` assignment — the
    # three terminal ones are handed to the `closeChannel` helper — so scanning
    # assignments alone left "Settled"/"Refunded"/"Expired" unchecked.
    mapping = _MAPPING.read_text()
    written = set(re.findall(r'\.status\s*=\s*"(\w+)"', mapping))
    written |= set(re.findall(r'closeChannel\(\s*\w+\s*,\s*"(\w+)"', mapping))
    for value in written:
        assert value in contract_values, f"mapping writes unknown status {value!r}"
    assert written == set(contract_values), (
        "the scan above did not account for every status the schema declares "
        f"(found {sorted(written)}) — either the mapping stopped writing one, or "
        "it now writes it through a form this test cannot see, which is exactly "
        "how an unchecked typo gets in")


def test_abi_reference_is_a_json_artifact(manifest):
    """graph-cli cannot read Solidity — a `.sol` here fails codegen outright."""
    abi_file = re.search(r"abis:\s*\n(?:\s*#[^\n]*\n)*\s*-\s*name:\s*\w+\s*\n\s*file:\s*(\S+)",
                         manifest).group(1)
    assert abi_file.endswith(".json"), f"ABI reference {abi_file} is not a JSON artifact"
    resolved = (_SUBGRAPH / abi_file).resolve()
    if not resolved.is_file():
        pytest.skip(f"{resolved} not built yet (run `forge build` in contracts/evm)")
    abi = json.loads(resolved.read_text())
    abi = abi["abi"] if isinstance(abi, dict) else abi
    compiled = {e["name"] for e in abi if e.get("type") == "event"}
    for sig in _manifest_handlers(manifest):
        assert sig.split("(", 1)[0] in compiled
