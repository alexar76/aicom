#!/usr/bin/env python3
"""Replace one container preserving state, network attachments and runtime policy.

Requires an explicit HTTP health URL and runs on the Docker host. Secrets remain
in memory and in a root-only rollback snapshot. On failure the previous container
is restored. This does not rebuild images or change monetary configuration.

Containers that borrow this one's network namespace (THEMIS runs with
--network container:modelmarket-hub) are recreated inside the new container, and
restarted inside the restored one on rollback: a namespace dies with its owner,
and a borrower left behind keeps reporting healthy while nothing can reach it.
Repeat --health for every URL that must answer, e.g. the hub and THEMIS's 9460.
--dry-run prints the planned docker commands, env values redacted, and stops.
"""
import argparse
import copy
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

from service_env import filtered

ROLLBACK_ROOT = Path("/root/security-rollbacks")
# Settings a container inherits from its image when it leaves them unset.
IMAGE_DEFAULTS = ("WorkingDir", "User", "Healthcheck", "StopSignal")


class DockerConnection(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("localhost", timeout=90)

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect("/var/run/docker.sock")


def api(method, path, body=None):
    conn = DockerConnection()
    try:
        conn.request(method, "/v1.47" + path,
                     json.dumps(body).encode() if body is not None else None,
                     {"Content-Type": "application/json"})
        response = conn.getresponse()
        raw = response.read()
        # 304 means already started or already stopped: the state that was asked for.
        if response.status >= 300 and response.status != 304:
            # Docker may reflect the create request, which contains credentials.
            raise RuntimeError(f"Docker {method} {path.split('?')[0]} failed: HTTP {response.status}")
        return json.loads(raw) if raw else None
    finally:
        conn.close()


def health(url, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError("Health check failed")


def settled(container, timeout=90):
    """Wait until a recreated container runs and, if it has one, passes its healthcheck."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = api("GET", f"/containers/{container}/json")["State"]
        if not state["Running"] and not state.get("Restarting"):
            raise RuntimeError(f"{container} exited")
        status = (state.get("Health") or {}).get("Status")
        if status == "unhealthy":
            raise RuntimeError(f"{container} is unhealthy")
        if not state.get("Restarting") and status in (None, "healthy"):
            return
        time.sleep(1)
    raise RuntimeError(f"{container} did not become healthy")


def borrowers(old):
    """Running containers that live in old's network namespace."""
    refs = {old["Id"], old["Name"].lstrip("/")}
    found = []
    for summary in api("GET", "/containers/json"):
        mode = (summary.get("HostConfig") or {}).get("NetworkMode", "")
        ref = mode.split(":", 1)[1] if mode.startswith("container:") else ""
        if ref in refs or (len(ref) >= 12 and old["Id"].startswith(ref)):
            found.append(api("GET", f"/containers/{summary['Id']}/json"))
    return found


def create_body(info, factory_export=None):
    """A create request that reproduces info's config, volumes, networks and policy."""
    config = copy.deepcopy(info["Config"])
    host = copy.deepcopy(info["HostConfig"])
    config["Image"] = info["Image"]
    # Docker fills Hostname with the short ID, or with the joined container's names
    # under container: networking (where setting one is refused). Others were chosen.
    shared = host["NetworkMode"].startswith("container:")
    if shared or host.get("UTSMode") == "host" or config.get("Hostname") == info["Id"][:12]:
        config.pop("Hostname", None)
    if shared or not config.get("Domainname"):
        config.pop("Domainname", None)
    if shared:
        # The image's EXPOSE shows up here, and Docker refuses exposed ports on a
        # container that has no network of its own. The image adds them back.
        config.pop("ExposedPorts", None)
    # Always reattach the exact volumes: no anonymous replacement of existing data.
    host["Binds"] = []
    # tmpfs mounts hold no data and never become Binds, so keep them as declared.
    host["Mounts"] = [m for m in host.get("Mounts") or [] if m.get("Type") == "tmpfs"]
    for mount in info["Mounts"]:
        if mount["Type"] == "tmpfs":
            continue  # Kept above, or by HostConfig.Tmpfs.
        source = mount.get("Name") if mount["Type"] == "volume" else mount["Source"]
        if factory_export and mount["Destination"] == "/factory_data":
            source = str(factory_export.resolve())
            if not (Path(source) / "state/pipeline.json").is_file():
                raise RuntimeError("Factory catalog export not prepared")
            if (Path(source) / "secrets").exists() or (Path(source) / "config").exists():
                raise RuntimeError("Refusing a Factory directory with secrets/config")
        host["Binds"].append(f"{source}:{mount['Destination']}:{'rw' if mount['RW'] else 'ro'}")
    endpoints = {}
    for name, net in info["NetworkSettings"]["Networks"].items():
        aliases = [a for a in (net.get("Aliases") or []) if a not in (info["Id"][:12], info["Id"])]
        endpoints[name] = {"Aliases": aliases} if name not in ("bridge", "host", "none") else {}
        if net.get("IPAMConfig"):
            endpoints[name]["IPAMConfig"] = net["IPAMConfig"]
    # IDs in NetworkMode become stale when a Compose network is recreated.
    if host["NetworkMode"] not in ("host", "none", "default", "bridge") and not shared:
        if host["NetworkMode"] not in endpoints and endpoints:
            host["NetworkMode"] = next(iter(endpoints))
    config["HostConfig"] = host
    config["NetworkingConfig"] = {"EndpointsConfig": endpoints}
    return config


def rebase(config, old_image, image):
    """Point config at image, dropping what it only inherited from old_image.

    A container's inspected config is its image's defaults merged with what was
    chosen at run time. Carrying the old image's PATH, Cmd or labels forward would
    override the new image's own, so a value equal to the old image's goes and
    Docker fills in the new one. Values that differ were chosen, and stay.
    """
    base = old_image.get("Config") or {}
    image_env = dict(e.partition("=")[::2] for e in base.get("Env") or [])
    env = config.get("Env") or []
    # The last assignment is the one the process sees.
    last = dict(e.partition("=")[::2] for e in env)
    inherited = sorted(k for k, v in last.items() if k in image_env and image_env[k] == v)
    config["Env"] = [e for e in env if e.partition("=")[0] not in inherited]
    image_labels = base.get("Labels") or {}
    config["Labels"] = {k: v for k, v in (config.get("Labels") or {}).items()
                        if image_labels.get(k) != v}
    exposed = base.get("ExposedPorts") or {}
    config["ExposedPorts"] = {p: v for p, v in (config.get("ExposedPorts") or {}).items()
                              if p not in exposed}
    for key in IMAGE_DEFAULTS:
        if (config.get(key) or None) == (base.get(key) or None):
            config.pop(key, None)
    # Docker takes the image's Cmd only when neither Entrypoint nor Cmd is set.
    if (config.get("Entrypoint") or None) == (base.get("Entrypoint") or None):
        config.pop("Entrypoint", None)
        if (config.get("Cmd") or None) == (base.get("Cmd") or None):
            config.pop("Cmd", None)
    config["Image"] = image
    return inherited


class Run:
    """Issue Docker API calls, or under --dry-run only list the docker commands."""

    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.commands = []

    def __call__(self, command, method, path, body=None):
        self.commands.append(command)
        return None if self.dry_run else api(method, path, body)

    def wait(self, command, check, *args):
        self.commands.append(command)
        if not self.dry_run:
            check(*args)


def forward(run, units, urls):
    main, borrowed = units[0], units[1:]
    created = run(f"docker create --name {main['candidate']} <create[{main['name']}]>", "POST",
                  "/containers/create?name=" + urllib.parse.quote(main["candidate"]), main["body"])
    main["created"] = created["Id"] if created else main["candidate"]
    for unit in borrowed:
        unit["body"]["HostConfig"]["NetworkMode"] = "container:" + main["created"]
        created = run(f"docker create --name {unit['candidate']} <create[{unit['name']}]>", "POST",
                      "/containers/create?name=" + urllib.parse.quote(unit["candidate"]), unit["body"])
        unit["created"] = created["Id"] if created else unit["candidate"]
    # Borrowers stop first: their namespace goes away with the container they borrow.
    for unit in borrowed + [main]:
        run(f"docker stop -t 30 {unit['name']}", "POST", f"/containers/{unit['info']['Id']}/stop?t=30")
        unit["stopped"] = True
    for unit in units:
        run(f"docker rename {unit['name']} {unit['previous']}", "POST",
            f"/containers/{unit['info']['Id']}/rename?name={unit['previous']}")
        unit["renamed"] = True
        run(f"docker rename {unit['candidate']} {unit['name']}", "POST",
            f"/containers/{unit['created']}/rename?name={unit['name']}")
        unit["named"] = True
    for unit in units:
        run(f"docker start {unit['name']}", "POST", f"/containers/{unit['created']}/start")
    for url in urls:
        run.wait(f"wait for {url} to answer 200", health, url)
    for unit in borrowed:
        run.wait(f"wait for {unit['name']} to run healthy", settled, unit["created"])


def rollback(units, urls, stamp):
    """Undo whatever forward() got through. Every step is tried even when an earlier
    one fails, so one stuck container cannot keep the old service down."""
    errors = []

    def attempt(what, method, path):
        try:
            api(method, path)
            return True
        except Exception as exc:
            errors.append(f"{what}: {exc}")
            return False

    main, borrowed = units[0], units[1:]
    for unit in borrowed[::-1] + [main]:
        if unit.get("created") and not attempt(f"remove {unit['candidate']}", "DELETE",
                                               f"/containers/{unit['created']}?force=true"):
            # It will not go: stop it and give the name back to the old container.
            attempt(f"stop {unit['candidate']}", "POST", f"/containers/{unit['created']}/stop?t=10")
            if unit.get("named"):
                attempt(f"rename {unit['candidate']} aside", "POST",
                        f"/containers/{unit['created']}/rename?name={unit['name']}-failed-{stamp}")
        if unit.get("renamed"):
            attempt(f"rename {unit['previous']} back", "POST",
                    f"/containers/{unit['info']['Id']}/rename?name={unit['name']}")
    if main.get("stopped"):
        attempt(f"start {main['name']}", "POST", f"/containers/{main['info']['Id']}/start")
    # A restarted owner has a fresh namespace; borrowers must join it again.
    for unit in borrowed:
        if unit.get("stopped") or main.get("stopped"):
            attempt(f"restart {unit['name']}", "POST", f"/containers/{unit['info']['Id']}/restart?t=30")
    if any(unit.get("stopped") for unit in units):
        for url in urls:
            try:
                health(url)
            except Exception as exc:
                errors.append(f"health {url}: {exc}")
    return errors


def redacted(body):
    body = copy.deepcopy(body)
    body["Env"] = [e.partition("=")[0] + "=<redacted>" for e in body.get("Env") or []]
    return body


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name")
    ap.add_argument("--health", required=True, action="append",
                    help="URL that must answer 200; repeat for each (e.g. THEMIS on 9460)")
    ap.add_argument("--image")
    ap.add_argument("--service", choices=["hub", "factory", "grafana", "atlas", "frontend"])
    ap.add_argument("--factory-export", type=Path)
    ap.add_argument("--env-output", type=Path)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the planned docker commands and change nothing")
    args = ap.parse_args()
    old = api("GET", f"/containers/{args.name}/json")
    if not old["State"]["Running"]:
        raise RuntimeError("Original container is not running")
    deps = borrowers(old)
    for url in args.health:
        health(url, 5)
    stamp = str(time.time_ns())
    config = create_body(old, args.factory_export)
    inherited = []
    if args.image:
        api("GET", f"/images/{args.image}/json")  # Refuse before anything stops.
        inherited = rebase(config, api("GET", f"/images/{old['Image']}/json"), args.image)
    if args.service:
        config["Env"] = filtered(args.service, config.get("Env", []))
    units = [{"info": old, "name": args.name, "body": config}]
    units += [{"info": d, "name": d["Name"].lstrip("/"), "body": create_body(d)} for d in deps]
    for unit in units:
        unit["candidate"] = unit["name"] + "-candidate-" + stamp
        unit["previous"] = unit["name"] + "-security-prev-" + stamp
    removed = sorted({e.split("=", 1)[0] for e in old["Config"]["Env"]} -
                     {e.split("=", 1)[0] for e in config["Env"]} - set(inherited))
    run = Run(args.dry_run)
    if args.dry_run:
        forward(run, units, args.health)
        print(json.dumps({"dry_run": True, "container": args.name, "image": config["Image"],
                          "removed_env_names": removed, "image_env_names": inherited,
                          "borrowers": [u["name"] for u in units[1:]], "commands": run.commands,
                          "create": {u["name"]: redacted(u["body"]) for u in units}}, indent=2))
        return
    backup_dir = ROLLBACK_ROOT / (args.name + "-" + stamp)
    backup_dir.mkdir(parents=True, mode=0o700)
    snapshot = backup_dir / "inspect.json"
    for path, info in [(snapshot, old)] + [(backup_dir / f"inspect-{u['name']}.json", u["info"])
                                           for u in units[1:]]:
        path.write_text(json.dumps(info))
        path.chmod(0o600)
    try:
        forward(run, units, args.health)
    except Exception:
        errors = rollback(units, args.health, stamp)
        print(json.dumps({"rolled_back": not errors, "rollback_errors": errors}), file=sys.stderr)
        raise
    if args.env_output:
        args.env_output.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(args.env_output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(config["Env"]) + "\n")
    print(json.dumps({"container": args.name, "healthy": True, "image": config["Image"],
                      "previous_container": units[0]["previous"], "removed_env_names": removed,
                      "image_env_names": inherited,
                      "borrowers": {u["name"]: u["previous"] for u in units[1:]},
                      "snapshot": str(snapshot)}))


if __name__ == "__main__":
    main()
