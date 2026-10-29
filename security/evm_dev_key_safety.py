"""Refuse chain mismatches and public wallet keys outside local dev EVMs.

Default Anvil/Hardhat and published unsafe test accounts use hashes only.
Mirrored into the independently installed Lottery and Alien packages.
"""
from __future__ import annotations

import hashlib
import ipaddress
from urllib.parse import urlsplit

PUBLIC_DEV_ACCOUNT_SHA256 = frozenset({
    # Additional public non-Anvil x402 test-log key, confirmed 2026-10-25.
    "eced6ef5b0617bd386e43be38b851ffde01ee07ab8ef7bcfe348e6a08d96be43",
    'dffe1949d232f54161e6facdac629631725dcf4d144e0c3a3147319fcac8a5fb',
    '7eaadf1989ccf0de8d49bd96d97f3677db8342952910f4ac0bf91f6f5f34f679',
    '2f9257defd381b3b2b2743869acadf53db7acf7f19cba39a777c1f75506ad9db',
    'd43a2fdd7e1a616fff304084aacc825703c8192c71921327c2480b7fba6fcc62',
    'e4bee9b01ee93525c83b1530620db035ef28cdae47908d5a3723308f821dc308',
    'b3f716664c5d21e9e6e7c88d708adc70b9f25131a683b4f64b720bb61f2508ca',
    '84b278f5489405efe4edc9bc4242aa248b6d62c4de4eccfb1e24eaf1289cbb81',
    '7045da5eb828f0b06faaf946c1a59828dfed7925ae044736d5db191f76c2c29c',
    '66e04404773de86f7a400e0d332a397a187b984571ee98a14cbeb4ae3279f329',
    '51a2ac341b44b0f8e5db49c1d4aebebd5f0fbef00bb6ea7df1b7b5df25af6e2d',
    '6c066b7bc0bdf86ac58ec817364e95d0ce66322853f4b190d0e82092cc0860e6',
    '346818a17a326b671c06bf21bcfbb3439243e72ea9c05563665223eb7d032f42',
    '610e8a15304cc30b99d70982807ee9a79b334878aeef3ef02a67d6e328fa0092',
    'a52ee2c94495f4143ef039b0cf99577c00a4268bc0dedb71b4204c063616fad8',
    '578fcedd7793706bc8317c0f8af30b2c0e32f14f9727ef36265e194e0dc36a67',
    '84f673496bd6c2101e4760861c9afb7c6bc9181bb279a0642bbfd56d6ffb7656',
    'b29e2c4455bb968716e9c156b13acf13cc1656150a2f39acb9f505375f4d27da',
    'a6a6975e05e9fcee64bc7f54107287bcb851bdacac36bcefe8845c141bb51e68',
    '9b15c397a637f31dd0737a65f60efe171896bd4476c6f0225dd203176e09255a',
    'fb961a822b50a19264a15783a7d83ea830f0461deff1367aac67bf17afc79b51',
})
COMPROMISED_PRIVATE_SHA256 = frozenset({
    "305165ea1814374f4a7f780440c0698322a3218defc44ea99b6381b38f7fa9b9",
})
DEV_CHAIN_ID = 31337
_LOCAL_HOSTS = frozenset({"localhost", "chain", "lottery-chain", "anvil", "host.docker.internal"})
_PRIVATE_V4 = tuple(ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))


def is_public_dev_key(value) -> bool:
    from eth_account import Account

    try:
        account = Account.from_key(value)
        address = account.address.lower()
    except (ValueError, TypeError):
        return False  # The signing library rejects malformed keys at use.
    return (
        hashlib.sha256(address.encode("ascii")).hexdigest() in PUBLIC_DEV_ACCOUNT_SHA256
        or hashlib.sha256(bytes(account.key)).hexdigest() in COMPROMISED_PRIVATE_SHA256
    )


def local_dev_rpc(url: str) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            return False
        if parsed.query or parsed.fragment or not host:
            return False
        if host in _LOCAL_HOSTS:
            return True
        address = ipaddress.ip_address(host)
        return address.is_loopback or any(address in network for network in _PRIVATE_V4)
    except (ValueError, TypeError):
        return False


def actual_chain_id(w3, configured: int) -> int:
    actual = int(w3.eth.chain_id)
    if actual <= 0 or actual != int(configured):
        raise RuntimeError("RPC chain ID does not match the configured signing chain")
    return actual


def require_local_dev_chain(w3, rpc_urls) -> int:
    urls = [rpc_urls] if isinstance(rpc_urls, str) else list(rpc_urls)
    if not urls or not all(local_dev_rpc(url) for url in urls):
        raise RuntimeError("Public development wallet keys require a trusted local/private dev RPC")
    endpoint = getattr(getattr(w3, "provider", None), "endpoint_uri", None)
    if isinstance(endpoint, str) and endpoint and not local_dev_rpc(endpoint):
        raise RuntimeError("Development RPC provider points outside the trusted local/private network")
    return actual_chain_id(w3, DEV_CHAIN_ID)


def require_signing_chain(w3, chain_id: int, rpc_urls, key) -> None:
    actual_chain_id(w3, chain_id)
    if is_public_dev_key(key):
        require_local_dev_chain(w3, rpc_urls)
