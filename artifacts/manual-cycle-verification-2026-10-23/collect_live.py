"""Collect only nonsecret evidence of the user's completed production test."""
import json
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
INPUT = HERE.parent / 'manual-esim-cycle-2026-10-23'
saved = json.loads((INPUT / 'delivery.json').read_text())
profile = saved['delivery']['esim_tran_no']
nonce = saved['delivery']['receipt']['nonce']
node = r'''
import {readFile} from 'node:fs/promises';
import {supplierFromEnv} from './src/config.js';
import {asSupplier} from './src/supplier.js';
const profile=process.env.AUDIT_PROFILE;
const nonce=process.env.AUDIT_NONCE;
const all=JSON.parse(await readFile('/data/orders.json','utf8'));
const matches=Object.entries(all).filter(([,r])=>r.profileId===profile || r.nonce===nonce);
if(matches.length!==1) throw Error('Expected exactly one production order for profile/payment');
const [id,r]=matches[0];
const supplier=asSupplier(supplierFromEnv(process.env));
const profiles=await supplier.profiles({profileId:profile});
const orderProfiles=await supplier.profiles({orderRef:r.orderRef});
const balance=await supplier.balance();
const rawBalance=supplier.client ? await supplier.client.balance() : null;
const samePayer=Object.values(all).filter(x=>x.payer?.toLowerCase()===r.payer?.toLowerCase() && x.at>=r.at);
const budgets=Object.entries(all).filter(([k])=>k.startsWith('refund-budget:')).flatMap(([k,x])=>x.refunds?.[profile]?[{wallet:k.slice(14),...x.refunds[profile]}]:[]);
const rawProfiles=supplier.client ? await supplier.client.profiles({esimTranNo:profile}) : [];
const rawSafe=rawProfiles.map(x=>Object.fromEntries(Object.entries(x).filter(([k,v])=>/price|cost|refund|cancel|orderNo|transactionId|esimStatus|smdpStatus/i.test(k) && (typeof v==='string'||typeof v==='number'||v===null))));
const health=await (await fetch('http://127.0.0.1:9490/healthz')).json();
const output={order:{transactionId:id,profileId:r.profileId,offerId:r.offerId,costUsd:r.costUsd,priceUsd:r.priceUsd,payer:r.payer,nonce:r.nonce,at:r.at,orderRef:r.orderRef,procurement:r.procurement,released:r.released,settlement:r.settlement,refund:r.refund},
same_payer_orders_since_test:samePayer.map(x=>({transactionId:x.transactionId,profileId:x.profileId,at:x.at,released:x.released,settlement_status:x.settlement?.status,refund_status:x.refund?.status})),
refund_budget_entries:budgets,supplier_order_profiles_count:orderProfiles.length,profiles:profiles.map(x=>({profileId:x.profileId,orderRef:x.orderRef,state:x.state,installed:x.installed,dataUsedBytes:x.dataUsedBytes,activated:x.activated})),supplier_financial_fields:rawSafe,
supplier_balance_usd:balance?.usd,supplier_balance_detail:rawBalance,health:{ok:health.ok,provider_pubkey:health.provider_pubkey,paid_orders:health.paid_orders,refunds:health.refunds,reconciliation:health.reconciliation},merchant:process.env.PAY_TO};
// Settlement checkpoints contain public authorization terms but no signature is needed in evidence.
if(output.order.settlement) output.order.settlement=Object.fromEntries(Object.entries(output.order.settlement).filter(([k])=>['status','transaction','tx','network','reason','at','last_check','outcome','checkpoint','reconciliation'].includes(k)));
if(output.order.settlement?.checkpoint) output.order.settlement.checkpoint=Object.fromEntries(Object.entries(output.order.settlement.checkpoint).filter(([k])=>['from','to','nonce','validAfter','validBefore','amount','fromBlock','nextBlock'].includes(k)));
console.log(JSON.stringify(output));
'''
command = ['docker','exec','-i','-e','AUDIT_PROFILE='+profile,'-e','AUDIT_NONCE='+nonce,
           'esim-test-rails','node','--input-type=module','-']
raw = subprocess.check_output(['ssh','-o','BatchMode=yes','factory-vps',shlex.join(command)],input=node,text=True)
output = json.loads(raw)
(HERE/'production-evidence.json').write_text(json.dumps(output,indent=2)+'\n')
print(json.dumps({'profile':profile,'matching_orders':1,'orders_for_payer_since_test':len(output['same_payer_orders_since_test']),
                  'procurement':output['order']['procurement'],'settlement':output['order']['settlement'],
                  'refund_status':output['order']['refund']['status'],'refund_tx':output['order']['refund'].get('transaction'),
                  'profiles':output['profiles'],'supplier_balance_usd':output['supplier_balance_usd'],
                  'supplier_financial_fields':output['supplier_financial_fields'],'refund_budget_entries':output['refund_budget_entries']}))
