// Exactly one user-authorized Agent402 purchase, capped at 0.01 USDC.
// Never logs/persists a private key or the payment signature; no approval/permit.
import {readFileSync,writeFileSync,appendFileSync,existsSync} from 'node:fs';
import {homedir} from 'node:os';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {payingClient,buyOne,guardedRequest,chargedOnChain,checkPayload,buildRequest} from '../../../scripts/delivery-survey/lib.mjs';
const require=createRequire(new URL('../../../scripts/delivery-survey/package.json',import.meta.url));
const {privateKeyToAccount}=require('viem/accounts');
const {createPublicClient,http,parseAbi}=require('viem');
const {base}=require('viem/chains');
const root=new URL('./',import.meta.url);
const plan=JSON.parse(readFileSync(new URL('plan.json',root),'utf8'));
const approved=JSON.parse(readFileSync(new URL('approved-terms.json',root),'utf8')).approved;
const cap=10000n;
const endpoint='https://agent402.tools/api/route/execute';
const payee='0x77065d81e18ad403bcd6e9a0616b288e16744121';
const payer='0x1218ff36c5d2e3b6a565cdb1a8b1accfc606ad0a';
if(plan.authorized_calls!==1||plan.max_total_atomic!=='10000'||plan.url!==endpoint||plan.method!=='POST'||plan.body.target!=='https://modelmarket.dev/x402/warden-scan'||plan.body.include!=='external'||plan.body.maxUsd!==0.001)throw Error('unapproved_plan');
if(approved.amount!=='10000'||approved.payTo!==payee||approved.network!=='eip155:8453'||approved.asset!=='0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'||approved.domain.name!=='USD Coin'||String(approved.domain.version)!=='2')throw Error('unapproved_payment_terms');
const entry={resource:endpoint,input:{method:'POST',bodyType:'json',body:plan.body},listed:approved};
const request=buildRequest(entry);
if(request.url!==endpoint||request.method!=='POST'||request.body!==JSON.stringify(plan.body))throw Error('request_mismatch');
const journal=new URL('payment-authorization.jsonl',root);
const results=new URL('paid-result.json',root);
if(existsSync(journal)||existsSync(results))throw Error('prior_attempt_exists_do_not_resign_or_retry');
if(!process.argv.includes('--execute')){console.log(JSON.stringify({plan_valid:true,key_loaded:false,signed:false,budget_atomic:'10000'}));process.exit(0);}
const secret=JSON.parse(readFileSync(homedir()+'/.aicom-base-deployer-v4.json','utf8'));
const account=privateKeyToAccount(secret.accounts[0].private_key);
for(const k of Object.keys(secret))delete secret[k];
if(account.address.toLowerCase()!==payer)throw Error('wrong_payer');
const rpc=createPublicClient({chain:base,transport:http('https://mainnet.base.org',{timeout:20000,retryCount:1})});
if(await rpc.getChainId()!==8453)throw Error('wrong_rpc_chain');
const usdc='0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913';
const balanceAbi=parseAbi(['function balanceOf(address) view returns (uint256)']);
const before=await rpc.readContract({address:usdc,abi:balanceAbi,functionName:'balanceOf',args:[account.address]});
const preflight={at_utc:new Date().toISOString(),payer:account.address,payee,balance_sufficient:before>=cap,budget_atomic:'10000',authorized_calls:1,signed:false};
writeFileSync(new URL('payer-preflight.json',root),JSON.stringify(preflight,null,2)+'\n');
if(before<cap)throw Error('insufficient_usdc');
let sentSigned=false;
const send=async(req,options)=>{
 if(req.url!==endpoint||req.method!=='POST'||req.body!==JSON.stringify(plan.body))throw Error('refuse_other_request');
 const h=Object.entries(req.headers).find(([k])=>k.toLowerCase()==='payment-signature');
 if(h){
  if(sentSigned)throw Error('one_signature_only');
  const payload=JSON.parse(Buffer.from(h[1],'base64').toString('utf8'));
  const signed=checkPayload(payload,{payer:account.address,approved});
  const expiry=Number(signed.valid_before),now=Math.floor(Date.now()/1000);
  if(expiry<=now||expiry>now+360)throw Error('unapproved_authorization_lifetime');
  appendFileSync(journal,JSON.stringify({call_id:'agent402-warden-1',at_utc:new Date().toISOString(),signed})+'\n');
  sentSigned=true;
 }
 return guardedRequest(req,{...options,userAgent:'aimarket-agent402-purchase-audit/0.1 (explicitly user-requested test, not organic demand)'});
};
console.log(JSON.stringify({stage:'paying_once',payer:account.address,max_usdc:'0.01',target:plan.body.target}));
const client=payingClient(account,'$0.01');
const result=await buyOne(entry,approved,{http:client,payer:account.address,cap,budgetLeft:cap,send});
const row={call_id:'agent402-warden-1',at_utc:new Date().toISOString(),...result};
if(result.response?.body_b64){
 const raw=Buffer.from(result.response.body_b64,'base64');writeFileSync(new URL('paid-response.body',root),raw);
 row.response.sha256=createHash('sha256').update(raw).digest('hex');
}
writeFileSync(results,JSON.stringify(row,null,2)+'\n');
console.log(JSON.stringify({stage:'paid_response',verdict:row.verdict,status:row.status??null,signed_atomic:row.signed?.value??'0',settle:row.settle??null,response_bytes:row.response?.bytes??0}));
const chain=await chargedOnChain([row],args=>rpc.readContract(args));
const after=await rpc.readContract({address:usdc,abi:balanceAbi,functionName:'balanceOf',args:[account.address]});
writeFileSync(new URL('chain-verification.json',root),JSON.stringify({at_utc:new Date().toISOString(),authorization:chain,balance_before_atomic:String(before),balance_after_atomic:String(after),balance_net_change_atomic:String(after-before)},null,2)+'\n');
console.log(JSON.stringify({stage:'chain_verification',authorization:chain,balance_net_change_atomic:String(after-before)}));

