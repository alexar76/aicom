#!/usr/bin/env python3
"""Run bounded no-credential network probes in an existing QA daemon; never deploy or change firewall rules."""
import argparse
import ipaddress
import json
import secrets
import socket
import struct
import subprocess
from pathlib import Path
from urllib.parse import urlsplit


def public_url(value):
    url = urlsplit(value)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.port not in [None, 443]:
        raise argparse.ArgumentTypeError('expected a public HTTPS health URL without credentials/query/fragment')
    return value


def backend_url(value):
    url = urlsplit(value)
    if url.scheme != 'http' or url.hostname != 'backend' or url.port != 8080 or url.username or url.password or url.query or url.fragment:
        raise argparse.ArgumentTypeError('expected http://backend:8080/health without credentials/query/fragment')
    return value


def numeric_ip(value):
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError('expected a numeric IP address') from exc


def port(value):
    number = int(value)
    if number < 1 or number > 65535:
        raise argparse.ArgumentTypeError('port must be 1..65535')
    return number


def reachable(host, port):
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def dns_control(server):
    transaction = secrets.token_bytes(2)
    packet = transaction + struct.pack('!HHHHH', 0x0100, 1, 0, 0, 0)
    packet += b'\x07example\x07invalid\x00' + struct.pack('!HH', 1, 1)
    family = socket.AF_INET6 if ipaddress.ip_address(server).version == 6 else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_DGRAM) as client:
            client.settimeout(3)
            client.sendto(packet, (server, 53))
            data, _ = client.recvfrom(512)
            return len(data) >= 12 and data[:2] == transaction and data[2] & 0x80 != 0
    except OSError:
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--container', required=True)
    parser.add_argument('--receiver-ip', required=True, type=numeric_ip, help='actual Docker gateway with a controlled listening receiver')
    parser.add_argument('--receiver-port', default=9999, type=port)
    parser.add_argument('--direct-ip', required=True, type=numeric_ip, help='controlled reachable public IPv4 TCP endpoint')
    parser.add_argument('--direct-port', default=443, type=port)
    parser.add_argument('--ipv6', type=numeric_ip, help='controlled reachable public IPv6 TCP endpoint, if available')
    parser.add_argument('--external-dns', required=True, type=numeric_ip)
    parser.add_argument('--allow-url', required=True, type=public_url)
    parser.add_argument('--port-test-host', required=True, help='temporary approved controlled DNS host with listeners on 80 and 8443')
    parser.add_argument('--backend-url', default='http://backend:8080/health', type=backend_url)
    args = parser.parse_args()
    if not ipaddress.ip_address(args.direct_ip).is_global or ipaddress.ip_address(args.direct_ip).version != 4:
        parser.error('--direct-ip must be a public IPv4 address')
    if args.ipv6 and (not ipaddress.ip_address(args.ipv6).is_global or ipaddress.ip_address(args.ipv6).version != 6):
        parser.error('--ipv6 must be a public IPv6 address')
    # A disconnected control channel must not turn an absent receiver into a false pass.
    controls = [(args.receiver_ip, args.receiver_port), (args.direct_ip, args.direct_port), (args.direct_ip, 22),
                (args.port_test_host, 80), (args.port_test_host, 8443)]
    if args.ipv6:
        controls.append((args.ipv6, args.direct_port))
    if not all(reachable(host, tcp_port) for host, tcp_port in controls) or not dns_control(args.external_dns):
        parser.exit(3, 'inconclusive: a controlled receiver is not reachable from the host; no acceptance recorded\n')
    config = dict(proxy='http://egress:8888', receiverIp=args.receiver_ip, receiverPort=args.receiver_port,
                  directIp=args.direct_ip, directPort=args.direct_port, ipv6=args.ipv6,
                  externalDns=args.external_dns, allowUrl=args.allow_url, portTestHost=args.port_test_host,
                  backendUrl=args.backend_url, dnsNonce='multica-egress-' + secrets.token_hex(12))
    source = Path(__file__).with_name('probe.mjs').read_text()
    source += '\nconsole.log(JSON.stringify(await runProbes(' + json.dumps(config) + ')));\n'
    try:
        run = subprocess.run(['docker', 'exec', '-i', args.container, 'node', '--input-type=module'],
                             input=source, text=True, capture_output=True, timeout=55, check=False)
        result = json.loads(run.stdout)
        if run.returncode or not isinstance(result, dict) or not isinstance(result.get('checks'), list):
            raise ValueError('invalid result')
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.exit(2, 'egress probe execution failed; no acceptance recorded\n')
    # The child only emits boolean results, not headers, bodies, URLs or environment values.
    result['scope'] = 'TCP/proxy checks only; separately verify authoritative DNS logs, output gate and a real QA job'
    result['ipv6_live_checked'] = bool(args.ipv6)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result.get('passed') else 1)


if __name__ == '__main__':
    main()
