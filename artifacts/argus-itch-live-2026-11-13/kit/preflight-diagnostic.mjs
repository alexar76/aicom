import { readFileSync } from "node:fs";
import { createLasoCheckoutCard } from "./dist/checkout/laso-card.js";
const read = name => readFileSync(process.env[name], "utf8").trim();
let source = readFileSync("/app/dist/checkout/itch-browser.js", "utf8")
 .replace('"playwright-core"', '"file:///app/node_modules/playwright-core/index.mjs"')
 .replace('"./zip.js"', '"file:///app/dist/checkout/zip.js"');
source = source.replace('const { close, context, page } = state;', String.raw`const {close,context,page}=state;
const classify=value=>{
  try {
    const u=new URL(value);
    const publicNames = new Set(["co-working-startup-office-icon-pack","purchase","checkout","stripe","v1","tokens","tax-preview"]);
    return {host:u.hostname,shape:u.pathname.split("/").map(part=>!part||publicNames.has(part)?part:"[opaque]").join("/")};
  } catch {return{host:"nonhttp"};}
};
page.on("request", r => { if (r.isNavigationRequest()||r.method()==="POST"||r.url().includes("tax-preview")) console.log(JSON.stringify({request:r.method(),...classify(r.url()),nav:r.isNavigationRequest()})); });
page.on("response", r => { if (r.request().isNavigationRequest()||r.request().method()==="POST") console.log(JSON.stringify({response:r.status(),...classify(r.url())})); });
page.on("pageerror",()=>console.log(JSON.stringify({pageError:true}))); `);
source=source.replace('preparationPosted = true;', 'console.log(JSON.stringify({prepareRequestAllowed:true}));preparationPosted = true;');
source=source.replace('delete headers.referer;', String.raw`delete headers.referer;
if (purpose === "prepare-navigation") {
 delete headers.cookie;
 headers.referer = PURCHASE;
}`);
source=source.replace('const status = response.status();', String.raw`const status = response.status();
if(purpose.startsWith("prepare")) {
 const location=response.headers().location;
 let first=null,host=null,root=false,depth=null;
 try { const target=new URL(location,url);host=target.hostname;root=target.pathname==="/";const parts=target.pathname.split("/");depth=parts.filter(Boolean).length;const path=parts[1];first=/^[a-z_.-]{2,22}$/.test(path)?path:"[opaque]"; }catch{}
 const cookies=(await context.cookies(["https://aiimperium.itch.io","https://itch.io"])).map(({name,domain})=>({name,domain}));
 const setCookie=(await response.headersArray()).filter(h=>h.name.toLowerCase()==="set-cookie").map(h=>h.value.split("=")[0]);
 console.log(JSON.stringify({purpose,status,nextHost:host,nextSegment:first,root,depth,hadRequestCookies:Boolean(headers.cookie),cookies,setCookie}));
}`);
source=source.replace('    throw sanitize(error, "checkout_changed", false, signal);',String.raw`    const msg=String(error?.message??"");const hints=["cardNumber","pay_btn","Timeout","stripe","checkout redirect","checkout URL","product changed","vat_view","input[type","billing","unexpected Stripe form","terms","page unavailable"]; console.log(JSON.stringify({diagnostic:hints.filter(h=>msg.toLowerCase().includes(h.toLowerCase())),type:error?.name}));throw sanitize(error, "checkout_changed", false, signal);`);
const signal=AbortSignal.timeout(50_000);
try {
 const {openItchCheckout}=await import("data:text/javascript;base64,"+Buffer.from(source).toString("base64"));
 const laso=createLasoCheckoutCard({id:read("ARGUS_ITCH_LASO_CARD_ID_FILE"),token:async()=>read("ARGUS_ITCH_LASO_SESSION_FILE")});
 const {billing}=await laso.read(signal);
 const s=await openItchCheckout({email:read("ARGUS_ITCH_RECEIPT_EMAIL_FILE"),billing,browserWsEndpoint:read("ARGUS_ITCH_BROWSER_WS_FILE"),signal});
 console.log(JSON.stringify({totalCents:s.totalCents,chargeSent:false}));
 await s.close();
} catch(e) { console.log(JSON.stringify({code:e.code??e.name??"preflight_unavailable",chargeSent:false}));process.exitCode=1; }
