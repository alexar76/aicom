#!/usr/bin/env python3
"""One command for preparation, local signing, execution and automatic waiting."""
import argparse
import asyncio
import getpass
import json
import os

from aimarket_hub.pipeline_client import PipelineHTTPError, PipelinePending, run_pipeline


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('blueprint', nargs='?')
    p.add_argument('--hub')
    p.add_argument('--rpc')
    p.add_argument('--gas-mode', choices=['auto', 'buyer', 'required'], help='auto prefers sponsor; required refuses buyer-paid gas')
    p.add_argument('--price-rpc', help='second same-chain RPC for independent price checks (default: public endpoint)')
    p.add_argument('--max-total-usd', help='all-in service and network budget')
    p.add_argument('--native-usd-ceiling', help='optional extra ETH/USD floor; cannot reduce the live oracle price plus 25%')
    p.add_argument('--trusted-hub-key', help='optional independently pinned Ed25519 Hub key')
    p.add_argument('--trusted-hub-pq-key', help='optional independently pinned ML-DSA-65 Hub key')
    p.add_argument('--accepted-assets', help='JSON file with a buyer-owned USD EIP-3009 asset allowlist')
    p.add_argument('--state', default='pipeline-run.private.json')
    p.add_argument('--execute', action='store_true')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--prompt-key', action='store_true', help='read the key locally without terminal echo')
    p.add_argument('--no-wait', action='store_true')
    p.add_argument('--timeout', type=float, default=180)
    args = p.parse_args()
    if not args.resume and (not args.execute or not args.blueprint or not args.hub or args.max_total_usd is None):
        p.error('new orders require blueprint, --hub, --max-total-usd and --execute')
    signer = None
    secret = getpass.getpass('Wallet key (local only): ') if args.prompt_key else os.getenv('PIPELINE_WALLET_KEY')
    if secret:
        from eth_account import Account
        signer = Account.from_key(secret)
    del secret
    blueprint = json.load(open(args.blueprint)) if args.blueprint else None
    try:
        result = asyncio.run(run_pipeline(blueprint, hub=args.hub, signer=signer,
            rpc_url=args.rpc, price_rpc_url=args.price_rpc, gas_mode=args.gas_mode, accepted_assets=json.load(open(args.accepted_assets)) if args.accepted_assets else None, max_total_usd=args.max_total_usd, native_usd_ceiling=args.native_usd_ceiling,
            state_path=args.state, resume=args.resume, wait=not args.no_wait, timeout_s=args.timeout,
            trusted_hub_key=args.trusted_hub_key, trusted_hub_pq_key=args.trusted_hub_pq_key))
    except PipelinePending as exc:
        print(json.dumps({'status': 'pending', 'state': exc.state_path,
                          'next': 'Repeat this command with --resume and the same --state; omit graph and budget options.'}))
        raise SystemExit(2)
    except PipelineHTTPError as exc:
        print(json.dumps({'error': 'hub_error', 'http_status': exc.status_code, 'detail': exc.detail,
                          'state': exc.state_path, 'next': 'Inspect the existing order before any new purchase.'}))
        raise SystemExit(1)
    except ValueError as exc:
        print(json.dumps({'error': 'client_policy_or_validation', 'detail': str(exc), 'state': args.state}))
        raise SystemExit(1)
    print(json.dumps(result, indent=2))
    if result.get('status') == 'failed':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
