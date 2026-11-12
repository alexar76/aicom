#!/usr/bin/env python3
"""Print a reviewed firewall installation plan; never executes host commands."""
import argparse
import ipaddress
import sys


def ipv4(value):
    try:
        return str(ipaddress.IPv4Address(value))
    except ipaddress.AddressValueError as exc:
        raise argparse.ArgumentTypeError("expected an IPv4 address") from exc


def render(backend, dns_ip):
    if backend != "iptables":
        raise ValueError("nftables backend needs a separately reviewed inet input/forward table; no DOCKER-USER plan emitted")
    if not ipaddress.IPv4Address(dns_ip).is_global:
        raise ValueError("this template requires a public approved IPv4 DNS resolver")
    commands = [
        "#!/bin/sh", "set -eu",
        "# Review before running as root on the Linux host, while QA tasks are stopped.",
        "# This plan is for the matching compose.egress.yaml addresses/interfaces only.",
        '[ "$(id -u)" = 0 ] || { echo "root required" >&2; exit 1; }',
        'command -v iptables >/dev/null', 'command -v ip6tables >/dev/null',
        'iptables -w -S DOCKER-USER >/dev/null',
        'if command -v nft >/dev/null && nft list table ip docker-bridges >/dev/null 2>&1; then echo "Docker nftables backend detected; refuse iptables plan" >&2; exit 1; fi',
        '[ "$(cat /proc/sys/net/bridge/bridge-nf-call-iptables)" = 1 ] || { echo "bridge netfilter must be enabled and persisted" >&2; exit 1; }',
        'for chain in MCQA_INPUT MCQA_FORWARD; do if iptables -w -S "$chain" >/dev/null 2>&1; then echo "MCQA chain exists; review existing installation instead of overwriting it" >&2; exit 1; fi; done',
        'for chain in MCQA6_INPUT MCQA6_FORWARD; do if ip6tables -w -S "$chain" >/dev/null 2>&1; then echo "MCQA6 chain exists; review existing installation instead of overwriting it" >&2; exit 1; fi; done',
        'iptables -w -N MCQA_INPUT', 'iptables -w -N MCQA_FORWARD',
        # Host sockets, including bridge gateways and host public addresses, are INPUT.
        'iptables -w -A MCQA_INPUT -s 10.250.0.0/24 -j DROP',
        'iptables -w -A MCQA_INPUT -s 10.251.0.0/24 -j DROP',
        'iptables -w -A MCQA_INPUT -j RETURN',
        # RETURN retains the rest of Docker/host policy; no broad ACCEPT.
        'iptables -w -A MCQA_FORWARD -s 10.250.0.10 -d 10.250.0.20 -p tcp --dport 8888 -j RETURN',
        'iptables -w -A MCQA_FORWARD -s 10.250.0.10 -d 10.250.0.30 -p tcp --dport 8080 -j RETURN',
        'iptables -w -A MCQA_FORWARD -s 10.250.0.10 -j DROP',
        'iptables -w -A MCQA_FORWARD -s 10.250.0.20 -d 10.250.0.10 -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN',
        'iptables -w -A MCQA_FORWARD -s 10.250.0.20 -j DROP',
        'iptables -w -A MCQA_FORWARD -s 10.250.0.30 -d 10.250.0.10 -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN',
        'iptables -w -A MCQA_FORWARD -s 10.250.0.30 -j DROP',
        'iptables -w -A MCQA_FORWARD -s 10.251.0.20 -d ' + dns_ip + ' -p udp --dport 53 -j RETURN',
        'iptables -w -A MCQA_FORWARD -s 10.251.0.20 -d ' + dns_ip + ' -p tcp --dport 53 -j RETURN',
    ]
    # An approved DNS name resolving to a private/metadata/host address is not an exemption.
    for network in ['0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
                    '169.254.0.0/16', '172.16.0.0/12', '192.168.0.0/16',
                    '198.18.0.0/15', '224.0.0.0/4', '240.0.0.0/4']:
        commands.append('iptables -w -A MCQA_FORWARD -s 10.251.0.20 -d ' + network + ' -j DROP')
    commands += [
        'iptables -w -A MCQA_FORWARD -s 10.251.0.20 -p tcp --dport 443 -j RETURN',
        'iptables -w -A MCQA_FORWARD -s 10.251.0.20 -p tcp -j REJECT --reject-with tcp-reset',
        'iptables -w -A MCQA_FORWARD -s 10.251.0.20 -j DROP',
        'iptables -w -A MCQA_FORWARD -j RETURN',
        'ip6tables -w -N MCQA6_INPUT', 'ip6tables -w -N MCQA6_FORWARD',
    ]
    for chain in ['MCQA6_INPUT', 'MCQA6_FORWARD']:
        for interface in ['br-multica-qa', 'br-multica-out']:
            commands.append('ip6tables -w -A ' + chain + ' -i ' + interface + ' -j DROP')
        commands.append('ip6tables -w -A ' + chain + ' -j RETURN')
    commands += [
        'iptables -w -I INPUT 1 -j MCQA_INPUT',
        'iptables -w -I DOCKER-USER 1 -j MCQA_FORWARD',
        'ip6tables -w -I INPUT 1 -j MCQA6_INPUT',
        'ip6tables -w -I FORWARD 1 -j MCQA6_FORWARD',
        '# Persist these dedicated chains with the host firewall manager, after Docker starts.',
        '# Re-run the probes after recreation, restart and reboot; this script does not persist rules.',
    ]
    return '\n'.join(commands) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', required=True, choices=['iptables', 'nftables'])
    parser.add_argument('--dns-ip', required=True, type=ipv4)
    args = parser.parse_args()
    try:
        sys.stdout.write(render(args.backend, args.dns_ip))
    except ValueError as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
