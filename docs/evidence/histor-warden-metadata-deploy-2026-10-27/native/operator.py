"""Reviewed operator release through the enrolled signed executor.

Run as root on admin-vps after the exact allowed source branch is pushed.
Existing credentials stay in the enrolled services or process memory. Output and
saved records contain only explicit safe projections, never settings or log tails.
"""

import base64
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

COMMIT = "ce1dd74edc30e7d5775c7583079cc4f9ed5d656f"
BRANCH = "momus/fix-warden-0.22.2-metadata-ce1dd74ed"
FINDING = "operator-warden-metadata-ce1dd74ed"
ROOT = Path("/var/tmp/histor-warden-metadata-ce1dd74ed")
PREVIOUS = "sha256:170a2523716bed3101b1a6420cab17eced83a0096053ba4b90e5ed75d51bddc1"
TRUSTED_BASE = "sha256:befe7e54d444d0d9b2658151725b264fc6bb61dbbdb0927caff60f281ba249d6"
BUILD_DIGEST = "3b6b074cf0be2415a049610d2908787d820b321ae68eb6d4837306dc9f5f16de"
PACKAGE_SHA = "0411601d6ec47d8d14f608a6643a94589e094940dcd93dde36bdcda52a57a34b"
RECIPE_SHA = "4c9460da54a1a0ccdbc7fb446d23aa4b42bea9c8410665b400b5d7e96ac3ef77"

PACKAGE_SCAN = r"""import hashlib,json
from pathlib import Path
p=Path('/app/scanner/node_modules/@aimarket/warden')
files=sorted((p/'dist').glob('*.js'))
h=hashlib.sha256()
for f in files:h.update(f.name.encode()+b'\0'+f.read_bytes()+b'\0')
print(json.dumps({'version':json.loads((p/'package.json').read_text())['version'],
 'packageJsonSha256':hashlib.sha256((p/'package.json').read_bytes()).hexdigest(),
 'distDigest':h.hexdigest(),'jsFiles':len(files)}))
"""
APPLICATION_SCAN = r"""import hashlib,json,histor
from pathlib import Path
roots=[Path('/app/histor'),Path('/app/docs/landing'),
 Path(histor.__file__).resolve().parent,
 Path('/app/scanner/scan.mjs'),Path('/app/scanner/quality')]
files={}
for base in roots:
 for path in ([base] if base.is_file() else base.rglob('*')):
  if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':
   files[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
print(json.dumps(files,sort_keys=True))
"""


def now():
    return datetime.now(UTC).isoformat()


def save(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2) + "\n")


def status(phase, **fields):
    print(json.dumps({"at": now(), "phase": phase, **fields}), flush=True)


def output(argv, *, input_text=None, timeout=90):
    result = subprocess.run(argv, input=input_text, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Native operation failed; command output withheld")
    return result.stdout.strip()


def inside(container, code, payload=None):
    return json.loads(output(
        ["docker", "exec", "-i", container, "python", "-c", code],
        input_text=None if payload is None else json.dumps(payload),
    ))


def health():
    with urlopen("http://127.0.0.1:9490/health", timeout=15) as response:
        value = json.load(response)
    assert value.get("ok") is True and value.get("service") == "histor"
    assert value.get("profile") == "prod" and value.get("store") == "postgresql"
    # The endpoint is public; select only the acceptance fields.
    return {**{key: value.get(key) for key in (
        "ok", "service", "version", "profile", "store", "tree_size",
        "crawl_running",
    )}, "last_crawl_error_present": bool(value.get("last_crawl_error"))}


def current_image():
    return output(["docker", "inspect", "--format", "{{.Image}}", "histor-histor-1"])


def assert_deploy_baseline():
    assert current_image() == PREVIOUS, "Production changed during release"
    assert output(["docker", "image", "inspect", "--format", "{{.Id}}", PREVIOUS]) == PREVIOUS
    assert output(["docker", "image", "inspect", "--format", "{{.Id}}", "histor:warden-remediation-base"]) == TRUSTED_BASE


def archive_public_receipt(channel, image):
    # Public aggregate evidence only. Native authorization/MOMUS independently
    # verify its cryptographic signature; local acceptance rechecks the archive.
    with urlopen("https://histor.modelmarket.dev/security-quality/" + channel + ".json", timeout=30) as response:
        body = response.read(131073)
    assert len(body) <= 131072
    envelope = json.loads(body)
    report = json.loads(base64.b64decode(envelope["payload"], validate=True))
    assert report["imageDigest"] == image and report["buildDigest"] == BUILD_DIGEST
    assert report["status"] == "passed"
    save(channel + "-signed-receipt.json", envelope)


def image_package(image):
    return json.loads(output([
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "python",
        image, "-c", PACKAGE_SCAN,
    ]))


def assert_package(value):
    assert value == {
        "version": "0.22.2", "packageJsonSha256": PACKAGE_SHA,
        "distDigest": BUILD_DIGEST, "jsFiles": 63,
    }, "Candidate package metadata or compiled bytes differ"


def order_proof(order):
    # These are a projection, not a reconstructed/verifiable signed order.
    signature = order.get("signature") or {}
    return {
        **{key: order.get(key) for key in (
            "order_id", "kind", "finding_id", "service", "host", "commit_sha", "branch", "image",
        ) if key in order},
        "signaturePresent": bool(signature.get("value")),
        "signatureAlgorithm": signature.get("algorithm"),
        "projectionOnly": True,
    }


def result_proof(result):
    keys = (
        "built", "deployed", "candidate_running", "image_digest", "image_tag", "commit_sha",
        "branch", "service", "deployed_image", "previous_image", "promoted_image",
        "rollback_available", "rolled_back", "health_gate_failed", "image_mismatch", "refused",
        "dry_run", "returncode", "healthy_after_rollback", "needs_human", "restored_image",
    )
    proof = {key: result[key] for key in keys if key in result}
    tests = result.get("tests")
    if isinstance(tests, dict):
        proof["tests"] = {key: tests[key] for key in ("ran", "passed", "enforced", "blocked", "target") if key in tests}
    # No arbitrary native reason, stdout/stderr, URL, candidate environment or settings.
    return proof


def assert_recipe(cfg):
    spec = cfg.build_map["warden"]
    assert cfg.host == "admin-vps" and "warden" in cfg.service_allowlist
    assert cfg.require_tests and not cfg.dry_run
    assert any(BRANCH.startswith(prefix) for prefix in cfg.branch_prefixes)
    assert spec["dockerfile"] == "warden/deploy/Dockerfile.histor" and spec.get("context", ".") == "."
    assert spec["compose_service"] == "histor" and spec["test_target"] == "test"
    assert spec["test_runner"] == "npm"


def build(hand, cfg):
    assert_deploy_baseline()
    before = health()
    save("health-before.json", before)
    save("previous-image.json", {"imageDigest": PREVIOUS, "trustedBaseDigest": TRUSTED_BASE})
    sign = '''import json,sys
from skopos.remediation.conductor import RemediationConfig
from skopos.remediation.deploy_order import BuildOrder,sign_build_order,Signer
cfg=RemediationConfig.from_env()
assert not cfg.dry_run
p=json.load(sys.stdin)
o=BuildOrder(finding_id=p['finding'],service='warden',host='admin-vps',commit_sha=p['commit'],branch=p['branch'])
print(json.dumps(sign_build_order(o,Signer(cfg.conductor_key_path)).to_dict()))
'''
    order = inside("skopos-remediation", sign, {"finding": FINDING, "commit": COMMIT, "branch": BRANCH})
    assert order["conductor_pubkey"] == cfg.conductor_pubkey
    save("build-order-projection.json", order_proof(order))
    status("native-build-started", sourceCommit=COMMIT, branch=BRANCH, operatorRelease=True, autonomousRepair=False)
    result = hand._executor.execute_build(order)
    save("build-result.json", result_proof(result))
    if not result.get("built") or not result.get("candidate_running"):
        raise RuntimeError("Native build or candidate gate failed")
    assert result["commit_sha"] == COMMIT
    assert result["tests"]["passed"] and result["tests"]["enforced"]
    image = result["image_digest"]
    assert hand.state.built_image(image).commit_sha == COMMIT
    archive_public_receipt("candidate", image)
    recipe = output(["git", "--git-dir", str(Path(cfg.state_dir) / "repo.git"), "show", COMMIT + ":warden/deploy/Dockerfile.histor"])
    assert hashlib.sha256((recipe + "\n").encode()).hexdigest() == RECIPE_SHA
    package = image_package(image)
    assert_package(package)
    labels = json.loads(output(["docker", "image", "inspect", "--format", "{{json .Config.Labels}}", image]))
    assert labels.get("skopos.source.commit") == COMMIT
    live_files = json.loads(output(["docker", "exec", "histor-histor-1", "python", "-c", APPLICATION_SCAN]))
    candidate_files = json.loads(output([
        "docker", "run", "--rm", "--network", "none", "--entrypoint", "python", image, "-c", APPLICATION_SCAN,
    ]))
    assert live_files and live_files == candidate_files, "HISTOR application changed outside WARDEN"
    save("application-preservation.json", {
        "unchangedOutsideWarden": True, "checkedFiles": len(live_files),
        "previousImage": PREVIOUS, "candidateImage": image,
        "manifestSha256": hashlib.sha256(json.dumps(live_files, sort_keys=True).encode()).hexdigest(),
    })
    save("candidate-metadata.json", {"imageDigest": image, "sourceCommit": COMMIT, "recipeSha256": RECIPE_SHA, **package})
    status("native-build-passed", imageDigest=image, sourceCommit=COMMIT, package=package)


def rollback(hand, order_id):
    record = hand.state.get(order_id)
    if record is None or not record.can_roll_back:
        # A refused order may have made no change. Never invent a rollback target.
        unchanged = current_image() == PREVIOUS
        save("rollback-verification.json", {"nativeRecordAvailable": record is not None, "rollbackPossible": False, "previousImageStillRunning": unchanged})
        assert unchanged, "No native rollback record and production is not the prior image"
        health()
        return
    assert record.previous_image == PREVIOUS
    if record.rolled_back_at or record.outcome == "rolled_back":
        restored = current_image() == PREVIOUS
        restored_health = health()
        save("rollback-verification.json", {"alreadyRolledBackByExecutor": True, "restoredPreviousImage": restored, "health": restored_health})
        assert restored, "Native automatic rollback did not restore the previous image"
        return
    sign = '''import json,sys
from skopos.remediation.conductor import RemediationConfig
from skopos.remediation.deploy_order import RollbackOrder,sign_rollback_order,Signer
cfg=RemediationConfig.from_env()
p=json.load(sys.stdin)
o=RollbackOrder(finding_id=p['finding'],service='warden',host='admin-vps',rollback_of=p['order'],reason='Operator metadata release post-deploy verification failed')
print(json.dumps(sign_rollback_order(o,Signer(cfg.conductor_key_path)).to_dict()))
'''
    order = inside("skopos-remediation", sign, {"finding": FINDING, "order": order_id})
    result = hand._executor.execute_rollback(order)
    save("rollback-result.json", result_proof(result))
    restored = current_image() == PREVIOUS
    restored_health = health()
    save("rollback-verification.json", {"restoredPreviousImage": restored, "health": restored_health, "needsHuman": bool(result.get("needs_human"))})
    assert result.get("rolled_back") and not result.get("needs_human") and restored
    status("native-rollback-verified", restoredPreviousImage=True)


def deploy(hand, cfg):
    result = json.loads((ROOT / "build-result.json").read_text())
    assert result["built"] and result["candidate_running"] and result["commit_sha"] == COMMIT
    assert result["tests"]["passed"] and result["tests"]["enforced"]
    image = result["image_digest"]
    assert hand.state.built_image(image).commit_sha == COMMIT
    assert_package(image_package(image))
    assert_deploy_baseline()
    output(["/usr/local/sbin/skopos-warden-quality", "authorize", image])
    retest = '''import asyncio,json,sys
from dataclasses import asdict
from momus.config import MomusConfig
from momus.findings import FindingSigner
from momus.engine.remediation import Retester
from momus.targets.quality import QualityTarget
cfg=MomusConfig.from_env()
p=json.load(sys.stdin)
v=asyncio.run(Retester(FindingSigner(cfg.signing_key_path),http_timeout_s=30).retest(
 QualityTarget('warden','https://histor.modelmarket.dev',candidate=True),
 'warden_release_quality',p['finding'],gated='candidate'))
print(json.dumps(asdict(v)))
'''
    verdict = inside("momus-backend", retest, {"finding": FINDING})
    assert verdict["fixed"] and verdict["outcome"] == "no_finding" and verdict["gated"] == "candidate"
    assert verdict["artifact_digest"] == image and verdict["verifier_pubkey"] == cfg.momus_pubkey
    save("candidate-verdict-projection.json", {
        **{key: verdict[key] for key in ("finding_id", "target", "probe", "fixed", "outcome", "gated", "artifact_digest", "checked_at")},
        "signaturePresent": bool(verdict.get("signature", {}).get("value")), "projectionOnly": True,
    })
    sign = '''import json,sys
from skopos.remediation.conductor import RemediationConfig
from skopos.remediation.deploy_order import DeployOrder,sign_deploy_order,Signer
cfg=RemediationConfig.from_env()
assert not cfg.dry_run
v=json.load(sys.stdin)
o=DeployOrder(finding_id=v['finding_id'],service='warden',host='admin-vps',image=v['artifact_digest'],momus_verdict=v)
print(json.dumps(sign_deploy_order(o,Signer(cfg.conductor_key_path)).to_dict()))
'''
    order = inside("skopos-remediation", sign, verdict)
    assert order["conductor_pubkey"] == cfg.conductor_pubkey
    save("deploy-order-projection.json", order_proof(order))
    before = health()
    save("health-immediately-before-deploy.json", before)
    assert not before["crawl_running"], "Crawler became active before promotion; wait rather than interrupt it"
    assert_deploy_baseline()
    status("native-deploy-started", imageDigest=image, orderId=order["order_id"])
    try:
        result = hand._executor.execute(order)
        save("deploy-result.json", result_proof(result))
        if not result.get("deployed"):
            raise RuntimeError("Native deploy did not pass; see safe result flags")
        assert current_image() == image
        package = json.loads(output(["docker", "exec", "histor-histor-1", "python", "-c", PACKAGE_SCAN]))
        assert_package(package)
        after = health()
        assert after["tree_size"] >= before["tree_size"], "Transparency log size decreased"
        assert after["version"] == before["version"], "HISTOR application version changed"
        record = hand.state.get(order["order_id"])
        assert record and record.can_roll_back and record.previous_image == PREVIOUS
        assert record.deployed_image == image and record.outcome == "deployed"
        save("native-journal-projection.json", record.to_dict())
        save("live-metadata.json", {"imageDigest": image, "sourceCommit": COMMIT, **package})
        save("health-after.json", after)
        archive_public_receipt("latest", image)
    except Exception:
        try:
            rollback(hand, order["order_id"])
        except Exception:
            status("native-rollback-failed", needsHuman=True)
            raise
        raise
    # Existing operator-release precedent advances the reviewed remediation base
    # only after native deploy, image/health checks and live quality binding pass.
    output(["docker", "tag", image, "histor:warden-remediation-base"])
    save("verified.json", {
        "at": now(), "deployed": True, "sourceCommit": COMMIT, "imageDigest": image,
        "previousImage": PREVIOUS, "operatorRelease": True, "autonomousRepair": False,
        "applicationPreserved": True, "trustedBaseAdvanced": True,
    })
    status("native-deploy-verified", imageDigest=image, sourceCommit=COMMIT, version=package["version"])


def main():
    assert os.geteuid() == 0 and ROOT.resolve() == ROOT and not ROOT.is_symlink()
    assert ROOT.is_dir() and ROOT.stat().st_uid == 0
    os.umask(0o077)
    with Path("/run/lock/histor-warden-operator.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        settings = dict(line.split("=", 1) for line in Path("/etc/skopos-deploy-hand/env").read_text().splitlines()
                        if line and not line.startswith("#") and "=" in line)
        os.environ.update(settings)
        sys.path[:0] = settings.get("PYTHONPATH", "").split(os.pathsep)
        from skopos.remediation.node_agent import NodeAgentConfig, NodeAgentDeployHand
        cfg = NodeAgentConfig.from_env()
        assert_recipe(cfg)
        hand = NodeAgentDeployHand(cfg)
        phase = sys.argv[1]
        assert phase in ("build", "deploy")
        (build if phase == "build" else deploy)(hand, cfg)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Exception text/traceback can include native argv or credentials.
        status("operator-failed", errorType=type(error).__name__)
        raise SystemExit(1) from None
