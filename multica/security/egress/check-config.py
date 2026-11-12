#!/usr/bin/env python3
"""Validate the merged Compose JSON from stdin and exact-host allowlist, without printing environment values."""
import argparse
import json
import ipaddress
import re
import stat
import sys
from pathlib import Path


def allowlist_hosts(text):
    hosts = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        # Deliberately support only exact ASCII DNS names, not arbitrary regex.
        if not re.fullmatch(r'\^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\\\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)+\$', line):
            raise ValueError('allowlist must contain only ^exact\\.host$ entries')
        host = line[1:-1].replace('\\.', '.')
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise ValueError('allowlist entries must be DNS hosts, not numeric IP literals')
        if len(host) > 253 or any(len(part) > 63 for part in host.split('.')):
            raise ValueError('allowlist DNS name exceeds DNS length limits')
        hosts.append(host)
    if not hosts:
        raise ValueError('allowlist is empty; approve exact hosts before deployment')
    return hosts


def check(config, allowlist, require_root_owned=True):
    allowlist_hosts(allowlist.read_text())
    info = allowlist.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise ValueError('allowlist must be a regular non-symlink file')
    if require_root_owned and (info.st_uid != 0 or info.st_mode & 0o022):
        raise ValueError('allowlist must be root-owned and not writable by group/others')
    if require_root_owned:
        for parent in allowlist.absolute().parents:
            parent_info = parent.lstat()
            if not stat.S_ISDIR(parent_info.st_mode) or parent_info.st_uid != 0 or parent_info.st_mode & 0o022:
                raise ValueError('allowlist parent directories must be root-owned and not writable by group/others')
    services = config.get('services', {})
    daemon = services.get('daemon', {})
    networks = daemon.get('networks', {})
    if set(networks) != {'qa_agent'}:
        raise ValueError('daemon must join only qa_agent')
    if networks['qa_agent'].get('ipv4_address') != '10.250.0.10':
        raise ValueError('daemon IPv4 address does not match firewall template')
    if daemon.get('ports') or daemon.get('privileged') or daemon.get('cap_add') or daemon.get('devices') or daemon.get('use_api_socket'):
        raise ValueError('daemon has published ports or elevated device/capability access')
    if daemon.get('network_mode') or daemon.get('pid') == 'host' or daemon.get('ipc') == 'host':
        raise ValueError('daemon must not share host namespaces')
    if daemon.get('user') != '1000:1000' or 'ALL' not in daemon.get('cap_drop', []):
        raise ValueError('daemon must run as uid 1000 with all capabilities dropped')
    if daemon.get('dns') != ['127.0.0.1'] or daemon.get('sysctls', {}).get('net.ipv6.conf.all.disable_ipv6') != '1':
        raise ValueError('daemon DNS/IPv6 settings differ from the template')
    for volume in daemon.get('volumes', []):
        if any('docker.sock' in str(volume.get(key, '')) or 'containerd.sock' in str(volume.get(key, '')) for key in ['source', 'target']):
            raise ValueError('daemon must not mount a container-engine socket')
        if volume.get('type') == 'bind' and str(Path(volume.get('source', '')).resolve()) in ['/', '/proc', '/sys', '/dev', '/run', '/var/run']:
            raise ValueError('daemon must not mount host root/system directories')
    for service in [daemon, services.get('egress', {})]:
        options = [str(option).replace('=', ':') for option in service.get('security_opt', [])]
        if not any(option in ['no-new-privileges:true', 'no-new-privileges'] for option in options) or 'no-new-privileges:false' in options:
            raise ValueError('no-new-privileges must be enabled')
    env = daemon.get('environment', {})
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        if env.get(key) != 'http://egress:8888':
            raise ValueError('daemon proxy environment differs from the template')
    for key in ['NO_PROXY', 'no_proxy']:
        if env.get(key) != 'backend,localhost,127.0.0.1':
            raise ValueError('NO_PROXY must not contain arbitrary domains or CIDRs')
    for key in ['ALL_PROXY', 'all_proxy']:
        if env.get(key) not in ['', None]:
            raise ValueError('unexpected alternate proxy')
    for name, internal, subnet, bridge in [('qa_agent', True, '10.250.0.0/24', 'br-multica-qa'), ('qa_egress_out', False, '10.251.0.0/24', 'br-multica-out')]:
        net = config.get('networks', {}).get(name, {})
        if bool(net.get('internal')) != internal or net.get('enable_ipv6') is not False:
            raise ValueError('QA network isolation/IPv6 settings differ from the template')
        if net.get('ipam', {}).get('config') != [{'subnet': subnet}] or net.get('driver_opts', {}).get('com.docker.network.bridge.name') != bridge:
            raise ValueError('QA subnets/bridge names do not match the firewall template')
    egress = services.get('egress', {})
    if set(egress.get('networks', {})) != {'qa_agent', 'qa_egress_out'}:
        raise ValueError('egress has unexpected networks')
    for name, address in [('qa_agent', '10.250.0.20'), ('qa_egress_out', '10.251.0.20')]:
        if egress['networks'][name].get('ipv4_address') != address:
            raise ValueError('egress addresses do not match the firewall template')
    if not egress.get('read_only') or egress.get('user') != '65534:65534' or egress.get('ports'):
        raise ValueError('egress must be nonroot/read-only and unpublished')
    if egress.get('privileged') or egress.get('cap_add') or egress.get('devices') or 'ALL' not in egress.get('cap_drop', []):
        raise ValueError('egress must not have elevated capability/device access')
    if egress.get('sysctls', {}).get('net.ipv6.conf.all.disable_ipv6') != '1':
        raise ValueError('egress IPv6 must be disabled for this template')
    resolvers = egress.get('dns', [])
    if len(resolvers) != 1 or not ipaddress.IPv4Address(resolvers[0]).is_global:
        raise ValueError('egress must use one public approved IPv4 DNS resolver')
    mounts = [v for v in egress.get('volumes', []) if v.get('target') == '/etc/tinyproxy/allow']
    if len(egress.get('volumes', [])) != 1 or len(mounts) != 1 or not mounts[0].get('read_only') or Path(mounts[0].get('source', '')).resolve() != allowlist.resolve():
        raise ValueError('egress allowlist mount does not match the validated read-only file')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allowlist', type=Path, required=True)
    parser.add_argument('--allow-nonroot-owner', action='store_true', help='local config validation only; not deployment acceptance')
    args = parser.parse_args()
    try:
        check(json.load(sys.stdin), args.allowlist, not args.allow_nonroot_owner)
    except (ValueError, OSError, TypeError, AttributeError):
        # Input can include credentials. Never echo the JSON, path or parser excerpt.
        parser.exit(2, 'egress configuration rejected; inspect settings locally without sharing environment values\n')
    print('egress merged configuration accepted' + (' (local owner check skipped)' if args.allow_nonroot_owner else ''))


if __name__ == '__main__':
    main()
