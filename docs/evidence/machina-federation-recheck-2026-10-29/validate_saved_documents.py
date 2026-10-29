"""Offline schema and signature diagnosis for saved public GET responses.

Run from the aicom root with PYTHONPATH=aimarket-hub. No signing key is
created, no request is made, and no production admission state is changed.
"""

import base64
import copy
import datetime
import json
import pathlib

from aimarket_hub import validator
from aimarket_hub.signing import Signer, pqc_required, signature_shape_problem

OUT = pathlib.Path(__file__).resolve().parent


def load(name):
    return json.loads((OUT / (name + ".json")).read_text())["json"]


if __name__ == "__main__":
    discovery = load("discovery-aimarket")
    manifest = load("manifest-advertised")
    dossier = load("hub-assay")
    # These methods need no instance state; skip key-generating __init__.
    verifier = object.__new__(Signer)
    canonical = verifier.manifest_canonical(manifest)
    signature = manifest.get("signature")
    raw_value = signature if isinstance(signature, str) else signature.get("value", "")
    key = discovery["signer_public_key"]
    wrapped = copy.deepcopy(manifest)
    wrapped["signature"] = {"algorithm": "ed25519", "public_key": key, "value": raw_value}
    compact_document = json.dumps(
        {k: v for k, v in manifest.items() if k != "signature"},
        sort_keys=True,
        separators=(",", ":"),
    )
    report = {
        "validated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "Offline validation of saved GET responses; no live sandbox probes or production assay reruns",
        "jsonschema_available": validator._HAS_JSONSCHEMA,
        "pqc_required_by_local_policy": pqc_required(),
        "discovery_schema_errors": validator.validate_well_known(discovery),
        "manifest_schema_errors": validator.validate_manifest(manifest),
        "signature_shape_problem": signature_shape_problem(signature),
        "advertised_public_key_bytes": len(base64.b64decode(key)),
        "raw_signature_bytes": len(base64.b64decode(raw_value)),
        "manifest_signature_valid": verifier.verify_manifest_signature(manifest, key),
        "raw_signature_valid_for_required_canonical": verifier.verify(key, raw_value, canonical),
        "raw_signature_valid_for_compact_sorted_document": verifier.verify(key, raw_value, compact_document),
        "wrapping_only_schema_errors": validator.validate_manifest(wrapped),
        "wrapping_only_signature_valid": verifier.verify_manifest_signature(wrapped, key),
        "required_canonical": canonical,
        "tools_count": len(manifest.get("tools", [])),
        "all_tools_have_input_schema": all(
            isinstance(tool.get("input_schema"), dict) for tool in manifest.get("tools", [])
        ),
        "generated_at": manifest.get("generated_at"),
        "production_dossier_ran_at": dossier.get("ran_at"),
        "production_dossier_verdict": dossier.get("verdict"),
    }
    (OUT / "local-validation.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    (OUT / "manifest-canonical.txt").write_text(canonical)
    print(json.dumps(report, indent=2, ensure_ascii=False))
