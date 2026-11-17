import json, subprocess, time, datetime, os
IDS = {"mom-fa8250468f2c4d5a": "ai-service-mesh client_ip", "mom-5f53ba285a7f4cb3": "metis tools/aimarket",
       "mom-f83d29f3cf254806": "aimarket-zk plugin", "mom-a977e0c832c34e79": "skopos a2a_ingress (core)",
       "mom-fdf6fd889ef7492b": "web providers probe", "mom-5ae46e61c5e84605": "web invoke_v2",
       "mom-5a38279368ae41a1": "web search_v2"}
JOBS = "/var/lib/docker/volumes/momus-deploy_skopos-remediation-data/_data/remediation/jobs.jsonl"
REPO = "/var/lib/docker/volumes/gitea_gitea-data/_data/git/repositories/alexar76/aicom.git"
env = {**os.environ, "GIT_CONFIG_GLOBAL": "/etc/momus-code-checkout.gitconfig", "GIT_CONFIG_NOSYSTEM": "1"}
seen_state, seen_br = {}, set()
end = time.time() + 7200
pos = os.path.getsize(JOBS)
ap_since = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
while time.time() < end:
    now = datetime.datetime.utcnow().strftime("%H:%M:%SZ")
    out = subprocess.run(["journalctl", "-u", "skopos-autopilot", "--since", ap_since, "--no-pager", "-o", "cat"],
                         capture_output=True, text=True).stdout
    ap_since = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    for line in out.splitlines():
        if any(i in line for i in IDS) or "aicom-source" in line and ("dispatch" in line.lower() and "severities" not in line):
            print(now, "AUTOPILOT", line[:230], flush=True)
    with open(JOBS) as fh:
        fh.seek(pos); chunk = fh.read(); pos = fh.tell()
    for line in chunk.splitlines():
        try: j = json.loads(line)
        except ValueError: continue
        fid = j.get("finding_id")
        if fid in IDS:
            st = (j.get("state"), j.get("attempts"))
            if seen_state.get(fid) != st:
                seen_state[fid] = st
                note = ((j.get("history") or [{}])[-1] or {}).get("note", "") if isinstance(j.get("history"), list) else ""
                print(now, "JOB", IDS[fid], j.get("state"), "attempt", j.get("attempts"), str(note)[:200], flush=True)
    br = subprocess.run(["git", "--git-dir", REPO, "for-each-ref", "--format=%(refname:short) %(objectname:short)",
                         "refs/heads/momus/fix-mom-*"], capture_output=True, text=True, env=env).stdout.split("\n")
    for b in br:
        if b and any(i in b for i in IDS) and b not in seen_br:
            seen_br.add(b); print(now, "BRANCH", b, flush=True)
    terminal = {f for f, s in seen_state.items() if s[0] in ("done", "escalated")}
    if len(terminal) >= 7:
        print(now, "all seven terminal", flush=True); break
    time.sleep(60)
print("watch end", datetime.datetime.utcnow().strftime("%H:%M:%SZ"), {IDS[k]: v for k, v in seen_state.items()}, flush=True)
