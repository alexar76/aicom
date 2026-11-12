"""Independent reduced arithmetic model of the published Base branch.

This does not execute/import Agent402 source or call any network. All case
inputs are synthetic; they are not measured AIMarket counts. Narrow assumptions:
one wallet, one origin, Bazaar is the strongest source, scanGenuine is not higher,
3 payers remain, valid live payTo/domain, no delivery or category failures.
"""
from pathlib import Path
import json,hashlib
ROOT=Path(__file__).parent

def reduced_verdict(gross_calls, router_calls=0, refunded_calls=0, funded_calls=0,
                    net_payers=3, price=.001, minimum=50, ceiling=.05):
    # One-origin special case of evidence-binding.bazaarNet: all deductions are
    # attributable to this origin. A lower scanGenuine cannot raise this count.
    net_calls=max(0,gross_calls-router_calls-refunded_calls-funded_calls)
    # evidence-binding puts the gross figure in selfByWallet on ANY reduction,
    # including an own router buy or a refund, then dispatch uses this held set.
    gross_held=net_calls<gross_calls
    proven=net_calls>=minimum and net_payers>=3
    held_clears=gross_held and gross_calls>=minimum and net_payers>=3
    reason=('eligible' if proven else
            'settlement_self_funded' if held_clears else 'settlement_required')
    trial=(not proven and reason=='settlement_required' and 0<price<=ceiling)
    return {'gross_calls':gross_calls,'gross_payers':net_payers+(1 if router_calls else 0),
            'net_calls':net_calls,'net_payers':net_payers,
            'router_calls_deducted':router_calls,'refund_calls_deducted':refunded_calls,
            'funded_calls_deducted':funded_calls,'reason':reason,
            'unproven_lane':trial,'callable':proven or trial}

cases={
 'below_floor_no_deductions':reduced_verdict(49),
 'one_router_purchase_zero_self_funding':reduced_verdict(50,router_calls=1),
 'one_refund_zero_self_funding':reduced_verdict(50,refunded_calls=1),
 'one_self_funded_payment':reduced_verdict(50,funded_calls=1),
 'net_floor_cleared':reduced_verdict(51,router_calls=1),
}
assert cases['below_floor_no_deductions']['unproven_lane']
assert cases['one_router_purchase_zero_self_funding']['funded_calls_deducted']==0
assert cases['one_router_purchase_zero_self_funding']['reason']=='settlement_self_funded'
assert not cases['one_router_purchase_zero_self_funding']['callable']
assert cases['one_refund_zero_self_funding']['reason']=='settlement_self_funded'
assert cases['net_floor_cleared']['callable']

index=json.loads((ROOT/'index-modelmarket.raw').read_text())
routes=[{k:r.get(k) for k in ['route','price','priceKnown','routerDispatchReason',
                            'routerDispatchByChain','executeViaCallableNow']}
        for r in index['tools'] if r.get('paid')]
old=(ROOT/'old-seller-funding.raw').read_bytes()
current=(ROOT/'src--seller-funding.js.raw').read_bytes()
out={
 'scope':'Reduced independent arithmetic model, synthetic fixtures; not AIMarket counts or upstream execution',
 'synthetic_cases':cases,
 'live_observation':{'origin':index['origin'],'fetched_at':index['fetchedAt'],
   'payToByNetwork':index['payToByNetwork'],'health':index['health'],
   'routable':index['routable'],'paid_routes':routes},
 'policy_comparison':{'funding_source_byte_identical_to_30_oct':old==current,
   'current_sha256':hashlib.sha256(current).hexdigest(),
   'old_source_commit':'48aff2412cd297da40eaadf3f61f25a5b1be2a68',
   'current_source_commit':json.loads((ROOT/'source-pin.json').read_text())['sha']},
 'limits':['No private wallet evidence read','No exact AIMarket deduction attributed',
  'Runtime SOR_MIN_SETTLED_TX/SOR_MIN_DISTINCT_PAYERS env not publicly verified; 50/3 are source defaults',
  'Live unproven ceiling0.05 observed on unrelated route rows, not inferred solely from source',
  'Historical receipt order alone cannot reconstruct the retained pool before or after that transaction'],
}
(ROOT/'analysis.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'synthetic_cases':cases,'paid_routes':len(routes),
                  'policy_comparison':out['policy_comparison']},ensure_ascii=False,indent=2))
