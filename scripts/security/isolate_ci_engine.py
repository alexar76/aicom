#!/usr/bin/env python3
"""Isolate the CI Docker API without restarting Gitea or interrupting builds.

Run on the CI host. The compose file is backed up locally with mode 0600.
No environment values or credentials are emitted. Roll back live network changes
on failure. Requires PyYAML and a Docker CLI. Refuses to run during a build.

The compose file is edited in place, not re-serialised: PyYAML reads YAML 1.1,
where an unquoted `222:22` is the number 13342, while Compose reads YAML 1.2.
Only the three networks entries change, and `docker compose config` must agree
that nothing else did. --dry-run prints the planned commands and the compose diff.
"""
import argparse
import copy
import difflib
import json
import os
from pathlib import Path
import subprocess
import time

import yaml


def docker(*args, input=None, cwd=None):
    return subprocess.check_output(["docker", *args], stderr=subprocess.PIPE,
                                   input=input, cwd=cwd).decode().strip()


def _entry(mapping, key):
    """(key node, value node) of key in a composed block, or (None, None)."""
    if not isinstance(mapping, yaml.MappingNode):
        raise RuntimeError(f"Refusing: expected a mapping around {key!r}")
    for k, v in mapping.value:
        if isinstance(k, yaml.ScalarNode) and k.value == key:
            # An alias points at text elsewhere in the file; splicing there is wrong.
            if v.start_mark.index < k.end_mark.index:
                raise RuntimeError(f"Refusing: {key!r} is a YAML alias; edit it by hand")
            return k, v
    return None, None


def _end(text, node):
    """Where a node's own text ends. Block collections' marks run on to the next
    token, past comments, so follow the last child down to a scalar."""
    while isinstance(node, (yaml.MappingNode, yaml.SequenceNode)) and node.flow_style is not True:
        node = node.value[-1][1] if isinstance(node, yaml.MappingNode) else node.value[-1]
    end = node.end_mark.index
    while text[end - 1] in " \t\r\n":
        end -= 1
    return end


def _set(text, mapping, key, value):
    """An edit that makes mapping[key] = value, wherever the entry is now. Values are
    written as JSON: one reading in YAML 1.1 and 1.2, and a JSON file stays JSON."""
    k, v = _entry(mapping, key)
    if k is None:
        return _add(text, mapping, key, value)
    end = _end(text, v)
    if end < v.start_mark.index:
        raise RuntimeError(f"Refusing: {key!r} ends in a YAML alias; edit it by hand")
    return (k.end_mark.index, end, ": " + json.dumps(value))


def _add(text, collection, key, value=None):
    """An edit that adds `key: value` to a mapping, or the item `key` to a sequence."""
    mapping = isinstance(collection, yaml.MappingNode)
    if collection.flow_style is True:
        item = json.dumps(key) + (": " + json.dumps(value) if mapping else "")
        if not collection.value:
            at = collection.end_mark.index - 1  # before the closing bracket
            return (at, at, item)
        at = _end(text, collection.value[-1][1] if mapping else collection.value[-1])
        return (at, at, ", " + item)
    # Block style: a new first entry, at the column of the current first one.
    at = collection.value[0][0].start_mark if mapping else collection.start_mark
    item = f"{key}: {json.dumps(value)}" if mapping else f"- {key}"
    return (at.index, at.index, item + "\n" + " " * at.column)


def edit_compose(text, network):
    """The compose text with runner-dind moved onto the dedicated network."""
    root = yaml.compose(text, Loader=yaml.SafeLoader)
    _, services = _entry(root, "services")
    _, engine = _entry(services, "runner-dind")
    _, runner = _entry(services, "act_runner")
    if engine is None or runner is None:
        raise RuntimeError("Refusing: runner-dind and act_runner must both be services")
    edits = [_set(text, engine, "networks", {"runner_engine": {"aliases": ["runner-dind"]}})]
    _, nets = _entry(runner, "networks")
    if nets is None or (isinstance(nets, yaml.ScalarNode) and nets.tag.endswith(":null")):
        edits.append(_set(text, runner, "networks", ["default", "runner_engine"]))
    elif isinstance(nets, yaml.SequenceNode):
        if "runner_engine" not in [n.value for n in nets.value if isinstance(n, yaml.ScalarNode)]:
            edits.append(_add(text, nets, "runner_engine"))
    elif isinstance(nets, yaml.MappingNode):
        if _entry(nets, "runner_engine")[0] is None:
            edits.append(_add(text, nets, "runner_engine", None))
    else:
        raise RuntimeError("Refusing: act_runner networks is neither a list nor a mapping")
    external = {"external": True, "name": network}
    _, top = _entry(root, "networks")
    if top is None or (isinstance(top, yaml.ScalarNode) and top.tag.endswith(":null")):
        edits.append(_set(text, root, "networks", {"runner_engine": external}))
    else:
        edits.append(_set(text, top, "runner_engine", external))
    for start, end, new in sorted(edits, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def compose_json(path, text):
    """Compose's own reading of text, as if it were the file at path."""
    return json.loads(docker("compose", "--project-directory", str(path.parent), "-f", "-",
                             "config", "--format", "json", input=text.encode(), cwd=path.parent))


def check_compose(before, after, network):
    """Refuse an edit that changes anything but the three networks entries."""
    a, b = copy.deepcopy(before), copy.deepcopy(after)
    engine = b["services"]["runner-dind"].pop("networks", None) or {}
    runner = b["services"]["act_runner"].pop("networks", None) or {}
    ours = (b.get("networks") or {}).pop("runner_engine", None) or {}
    if (list(engine) != ["runner_engine"] or "runner_engine" not in runner
            or ours.get("name") != network or not ours.get("external")):
        raise RuntimeError("Refusing: the edited compose file does not attach the engine network")
    a["services"]["runner-dind"].pop("networks", None)
    # No networks key means the default network.
    runner_before = a["services"]["act_runner"].pop("networks", None) or {"default": None}
    runner.pop("runner_engine")
    if runner != runner_before:
        raise RuntimeError("Refusing: the edit would change act_runner's other networks")
    # `default` leaves the top level when no service uses it any more.
    if "default" not in (b.get("networks") or {}):
        (a.get("networks") or {}).pop("default", None)
    changed = sorted(k for k in set(a) | set(b) if k != "services" and a.get(k) != b.get(k))
    changed += sorted(f"services.{s}" for s in set(a["services"]) | set(b["services"])
                      if a["services"].get(s) != b["services"].get(s))
    if changed:
        raise RuntimeError("Refusing: the compose edit would also change " + ", ".join(changed))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("compose", type=Path)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the planned commands and the compose diff; change nothing")
    args = ap.parse_args()
    path = args.compose.resolve()
    original = path.read_bytes()
    config = yaml.safe_load(original)
    services = config["services"]
    engine = services["runner-dind"].get("container_name", "gitea-runner-dind")
    runner = services["act_runner"].get("container_name", "act_runner")
    info = json.loads(docker("inspect", engine))[0]
    runner_info = json.loads(docker("inspect", runner))[0]
    project = info["Config"]["Labels"]["com.docker.compose.project"]
    network = project + "_runner_engine"
    previous = list(info["NetworkSettings"]["Networks"])
    if any(p.get("HostPort") for entries in info["NetworkSettings"]["Ports"].values()
           for p in (entries or [])):
        raise RuntimeError("Refusing: Docker engine has published ports")
    # The runner's client is an independent check that DNS and the API work.
    probe = ["exec", runner, "sh", "-c", "wget -q -T 5 -O - http://runner-dind:2375/_ping"]
    if docker(*probe) != "OK":
        raise RuntimeError("Runner cannot reach its engine before isolation")
    active = json.loads(docker("exec", runner, "sh", "-c",
                              "wget -q -T 5 -O - 'http://runner-dind:2375/containers/json'"))
    if active:
        raise RuntimeError("CI jobs are active; retry after they finish")
    # Decide and verify the compose edit before any live change.
    text = original.decode()
    edited = edit_compose(text, network)
    check_compose(compose_json(path, text), compose_json(path, edited), network)
    existing = docker("network", "ls", "--format", "{{.Name}}").splitlines()
    plan = [] if network in existing else [["network", "create", network]]
    plan += [["network", "connect", "--alias", alias, network, container]
             for container, current, alias in ((engine, info, "runner-dind"),
                                               (runner, runner_info, "act_runner"))
             if network not in current["NetworkSettings"]["Networks"]]
    plan += [["network", "disconnect", old, engine] for old in previous if old != network]
    if args.dry_run:
        diff = difflib.unified_diff(text.splitlines(), edited.splitlines(), str(path), str(path),
                                    n=0, lineterm="")
        print(json.dumps({"dry_run": True, "isolated": engine, "network": network,
                          "commands": ["docker " + " ".join(step) for step in plan],
                          "compose_diff": list(diff)}, indent=2))
        return
    backup = path.with_name(path.name + ".security-backup-" + str(time.time_ns()))
    with backup.open("xb") as f:
        os.chmod(backup, 0o600)
        f.write(original)
    added = []
    removed = []
    try:
        if network not in existing:
            docker("network", "create", network)
        members = json.loads(docker("network", "inspect", network))[0].get("Containers", {})
        if any(c["Name"] not in (engine, runner) for c in members.values()):
            raise RuntimeError("Unexpected container on the dedicated engine network")
        for container, current, alias in (
            (engine, info, "runner-dind"), (runner, runner_info, "act_runner")
        ):
            if network not in current["NetworkSettings"]["Networks"]:
                docker("network", "connect", "--alias", alias, network, container)
                added.append(container)
        for old in previous:
            if old != network:
                docker("network", "disconnect", old, engine)
                removed.append(old)
        if docker(*probe) != "OK":
            raise RuntimeError("Runner lost engine access")
        path.write_bytes(edited.encode())
        docker("compose", "-f", str(path), "config", "--quiet")
    except Exception:
        path.write_bytes(original)
        for old in removed:
            docker("network", "connect", "--alias", "runner-dind", old, engine)
        for container in reversed(added):
            docker("network", "disconnect", network, container)
        raise
    print(json.dumps({"isolated": engine, "network": network, "runner_ping": "OK",
                      "compose_persisted": True, "backup": str(backup)}))


if __name__ == "__main__":
    main()
