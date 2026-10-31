// Public quotes only. No wallet key or signed request is loaded here.
import { readFileSync,writeFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { guardedRequest,read402,terms,usdcOffer,buildRequest } from '../../../scripts/delivery-survey/lib.mjs';
const root=new URL('./',import.meta.url);
const plan=JSON.parse(readFileSync(new URL('plan.json',root),'utf8'));
const rows=[];
async function capture(name,request){
 const res=await guardedRequest(request,{userAgent:'aimarket-agent402-purchase-audit/0.1 (user-requested test)',timeoutMs:30000,maxBytes:2000000});
 const raw=Buffer.from(res.body||'');writeFileSync(new URL(name+'.body',root),raw);
 const row={name,url:request.url,method:request.method,request_body:request.body??null,at_utc:new Date().toISOString(),status:res.status??null,error:res.error??null,headers:res.headers??{},sha256:createHash('sha256').update(raw).digest('hex'),bytes:raw.length,body_file:name+'.body'};
 rows.push(row);return {res,raw};
}
const route=await capture('route-quote',{url:'https://agent402.tools/api/route?q=WARDEN&include=external&top=10',method:'GET',headers:{accept:'application/json'},body:null});
const parsed=JSON.parse(route.raw);
const match=parsed.results?.find(x=>x.url===plan.body.target);
if(!match||match.executeViaCallableNow!==true||match.executeVia?.price!=='$0.01')throw Error('target_not_currently_offered_at_approved_price');
const manifest=await capture('agent402-manifest',{url:'https://agent402.tools/.well-known/x402',method:'GET',headers:{accept:'application/json'},body:null});
const entry={resource:plan.url,input:{method:'POST',bodyType:'json',body:plan.body}};
const req=buildRequest(entry);
const probe=await capture('unpaid-execute',req);
const read=read402(probe.res);
if(probe.res.status!==402||!read.ok)throw Error('expected_readable_402');
const offer=usdcOffer(read.required.accepts,10000n);
if(!offer)throw Error('no_approved_base_usdc_offer');
const approved=terms(offer);
if(approved.amount!=='10000'||approved.network!=='eip155:8453'||approved.domain.name!=='USD Coin'||String(approved.domain.version)!=='2')throw Error('unapproved_terms');
if((offer.extra?.assetTransferMethod??'eip3009')!=='eip3009')throw Error('not_eip3009');
const manifestJson=JSON.parse(manifest.raw);
const manifestText=JSON.stringify(manifestJson).toLowerCase();
if(!manifestText.includes(approved.payTo))throw Error('payee_not_present_in_official_manifest');
writeFileSync(new URL('approved-terms.json',root),JSON.stringify({at_utc:new Date().toISOString(),approved,payment_required:read.required,route:match,key_loaded:false,signed:false},null,2)+'\n');
writeFileSync(new URL('preflight-http-index.json',root),JSON.stringify(rows,null,2)+'\n');
console.log(JSON.stringify({ready:true,key_loaded:false,signed:false,approved,route:{target:match.url,lane:match.executeViaLane,upstream_price:match.price,router_price:match.executeVia.price}},null,2));

