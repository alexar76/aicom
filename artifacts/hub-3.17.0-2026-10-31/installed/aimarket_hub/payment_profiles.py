"""Buyer-owned payment allowlists. A Hub cannot authorize a new asset for its buyer."""
from __future__ import annotations
import re

# Native USDC addresses: https://developers.circle.com/stablecoins/usdc-contract-addresses
USDC = {
    8453: '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913',
    1: '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
}
CHAIN_NAMES = {8453: 'base', 1: 'ethereum'}
DEFAULT_ASSETS = [dict(chain_id=chain, token_contract=address, decimals=6,
                       eip712_name='USD Coin', eip712_version='2',
                       usd_pegged=True, authorization='EIP-3009') for chain,address in USDC.items()]


def asset_policy(assets=None):
    """Explicit custom profiles replace the defaults; only audited USD EIP-3009 assets.

    This assertion is the buyer's policy, not proof of a peg or token implementation.
    Non-USD assets require a separate conversion protocol and are never guessed here.
    """
    rows = DEFAULT_ASSETS if assets is None else assets
    if not isinstance(rows,list) or not rows:
        raise ValueError('accepted_assets must be a nonempty explicit allowlist')
    clean=[]
    for a in rows:
        if (not isinstance(a,dict) or type(a.get('chain_id')) is not int or a['chain_id'] not in CHAIN_NAMES
                or not re.fullmatch(r'0x[0-9a-fA-F]{40}',a.get('token_contract',''))
                or int(a['token_contract'],16)==0 or type(a.get('decimals')) is not int or not 0<=a['decimals']<=18
                or not isinstance(a.get('eip712_name'),str) or not a['eip712_name']
                or not isinstance(a.get('eip712_version'),str) or not a['eip712_version']
                or a.get('usd_pegged') is not True or a.get('authorization')!='EIP-3009'):
            raise ValueError('asset policy requires a supported chain and explicit USD EIP-3009 metadata')
        clean.append({k:a[k] for k in DEFAULT_ASSETS[0]})
        clean[-1]['token_contract']=a['token_contract'].lower()
    identities=[(a['chain_id'],a['token_contract']) for a in clean]
    if len(set(identities))!=len(clean):raise ValueError('duplicate asset policy')
    return clean


def check_terms(terms, assets=None):
    for a in asset_policy(assets):
        if (terms['chain_id']==a['chain_id'] and terms['token_contract'].lower()==a['token_contract']
                and all(terms[k]==a[k] for k in ('decimals','eip712_name','eip712_version'))):
            return a
    raise ValueError('payment terms are outside the buyer asset allowlist')


def quote_asset(quote):
    return quote['offers'][0]['terms'] if quote['offers'] else None
