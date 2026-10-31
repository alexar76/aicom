// Read-only Base receipts and local payload integrity; no signing/sending.
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../../../scripts/delivery-survey/package.json',import.meta.url));
const {createPublicClient,http,decodeEventLog,parseAbi}=require('viem');
const {base}=require('viem/chains');
const root=new URL('./',import.meta.url);
const row=JSON.parse(readFileSync(new URL('paid-result.json',root),'utf8'));
const raw=readFileSync(new URL('paid-response.body',root));
const data=JSON.parse(raw),receipt=data.receipt;
const client=createPublicClient({chain:base,transport:http('https://mainnet.base.org',{timeout:20000,retryCount:1})});
const abi=parseAbi(['event Transfer(address indexed from, address indexed to, uint256 value)']);
const usdc='0x833589fcd6edb6e08f4c7c32d4f71b54bda02913';
const txs=[['buyer-to-agent402',row.settle.transaction],['agent402-to-warden',receipt.settleTx]];
const checks=[];
for(const [name,hash] of txs){
 const r=await client.getTransactionReceipt({hash});
 const transfers=r.logs.filter(l=>l.address.toLowerCase()===usdc).flatMap(l=>{
  try {const e=decodeEventLog({abi,data:l.data,topics:l.topics});return [{from:e.args.from,to:e.args.to,value_atomic:String(e.args.value),log_index:l.logIndex}];}catch{return [];}
 });
 const block=await client.getBlock({blockNumber:r.blockNumber});
 const fact={name,tx:hash,status:r.status,block_number:String(r.blockNumber),timestamp_utc:new Date(Number(block.timestamp)*1000).toISOString(),gas_used:String(r.gasUsed),effective_gas_price_wei:String(r.effectiveGasPrice),transaction_sender:r.from,transfers};
 writeFileSync(new URL(name+'-receipt.json',root),JSON.stringify(fact,null,2)+'\n');checks.push(fact);
}
const expectedRef='sha256:'+createHash('sha256').update(JSON.stringify({nonce:row.signed.nonce,slug:receipt.slug,ts:receipt.ts})).digest('hex');
const payer=row.signed.from.toLowerCase(),payee=row.signed.to.toLowerCase();
const result={
 checked_at_utc:new Date().toISOString(),http_status:row.status,request_count_signed:1,
 response_hash_matches:createHash('sha256').update(raw).digest('hex')===row.response.sha256,
 call_ref_matches:receipt.callRef===expectedRef,
 buyer_paid_001_usdc:checks[0].status==='success'&&checks[0].transfers.some(t=>t.from.toLowerCase()===payer&&t.to.toLowerCase()===payee&&t.value_atomic==='10000'),
 upstream_paid_0001_usdc:checks[1].status==='success'&&checks[1].transfers.some(t=>t.to.toLowerCase()===payer&&t.value_atomic==='1000'),
 correct_seller:receipt.seller==='https://modelmarket.dev'&&receipt.route==='POST https://modelmarket.dev/x402/warden-scan'&&receipt.external===true,
 seller_proof:receipt.sellerProof,engine:data.result?.engine,
 fixture_verdict:{blocked:data.result?.verdict?.blockedTools,allowed:data.result?.verdict?.allowedTools,allow:data.result?.verdict?.allow,score:data.result?.verdict?.score},
 buyer_debit_usdc:'0.01',upstream_credit_to_same_wallet_usdc:'0.001',net_wallet_cost_usdc:'0.009',buyer_gas_transaction:checks[0].transaction_sender.toLowerCase()===payer,
 classification:'explicitly user-requested paid test; not organic independent demand',
 transactions:checks.map(x=>({name:x.name,hash:x.tx,status:x.status}))
};
writeFileSync(new URL('receipt-verification.json',root),JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result,null,2));
if(!result.response_hash_matches||!result.call_ref_matches||!result.buyer_paid_001_usdc||!result.upstream_paid_0001_usdc||!result.correct_seller)process.exitCode=1;

