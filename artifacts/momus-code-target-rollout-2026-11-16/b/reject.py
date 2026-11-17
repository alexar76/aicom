"""Record the reviewer rejections of 2026-11-16 (artifacts/momus-code-target-rollout-2026-11-16/README.md). Runs inside
skopos-remediation; the operator token is read from the environment and never printed."""
import json, os, urllib.request

REASON = ("After the check it resolves the name a second time (getaddrinfo, or a helper around it) and connects to "
          "that new answer, which no check examined: the same DNS-rebinding gap. It also requests https://<ip> with "
          "no Host and no sni_hostname, so TLS fails. Resolve once, check every address, connect to one that passed, "
          "keep the name in Host and sni_hostname, as aimarket-mcp pin_target does.")
REJECT = [("mom-5f53ba285a7f4cb3", "momus/fix-mom-5f53ba285a7f4cb3-2"),
          ("mom-5a38279368ae41a1", "momus/fix-mom-5a38279368ae41a1-2"),
          ("mom-5ae46e61c5e84605", "momus/fix-mom-5ae46e61c5e84605-2")]
for fid, branch in REJECT:
    body = json.dumps({"verdict": "rejected", "branch": branch, "reason": REASON}).encode()
    req = urllib.request.Request(f"http://127.0.0.1:9402/remediation/jobs/{fid}/review", data=body, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "x-skopos-operator": os.environ["SKOPOS_OPERATOR_TOKEN"]})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            out = json.loads(r.read())
            print(fid, r.status, out.get("state"), out.get("review", {}).get("branch"))
    except urllib.error.HTTPError as e:
        print(fid, e.code, e.read().decode()[:200])
