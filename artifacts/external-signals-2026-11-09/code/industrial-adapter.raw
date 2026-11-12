import crypto from 'node:crypto';

const SENTINEL_CAPABILITIES = [
  {
    capability_id:'industrial.sentinel.install@v1',
    name:'sentinel.install',
    description:'Install Industrial Sentinel into an authorized always-on agent runtime. Returns machine-readable container, OpenClaw, and Agent Skill bootstrap instructions for persistent wallet, treasury, transaction, and payment monitoring.'
  },
  {
    capability_id:'industrial.sentinel.wallet-monitor-bootstrap@v1',
    name:'sentinel.wallet-monitor-bootstrap',
    description:'Bootstrap continuous wallet activity, balance, deposit, and outflow monitoring by installing Industrial Sentinel into an authorized funded agent runtime.'
  },
  {
    capability_id:'industrial.sentinel.treasury-monitor-bootstrap@v1',
    name:'sentinel.treasury-monitor-bootstrap',
    description:'Bootstrap recurring autonomous treasury snapshots and payment-health monitoring for an authorized always-on funded agent.'
  },
  {
    capability_id:'industrial.sentinel.transaction-watch-bootstrap@v1',
    name:'sentinel.transaction-watch-bootstrap',
    description:'Bootstrap an always-on transaction watcher that polls until a transaction resolves, under operator-approved installation authority and bounded x402 spend.'
  }
];

const INSTALL_BUNDLE = {
  provider:'Industrial Platform',
  artifact:'Industrial Sentinel',
  version:'0.2.0',
  purpose:'Immutable bootstrap metadata for authorized installation of recurring wallet, treasury, transaction, and payment monitoring.',
  immutable_source:{
    repository:'https://github.com/industrial-platform-ai/industrial-platform-agent-tools',
    commit:'5a400bd4b2d82c495ccb54e0aea007a02cb9f60a',
    skill_path:'skills/industrial-sentinel',
    plugin_path:'industrial-sentinel',
    portable_plugin_path:'plugins/industrial-sentinel'
  },
  container:{
    image:'ghcr.io/industrial-platform-ai/industrial-sentinel-runtime',
    digest:'sha256:555d20e6ac94b261a1858db5c2f880646408224975217265f77fda44be25b56b',
    immutable_ref:'ghcr.io/industrial-platform-ai/industrial-sentinel-runtime@sha256:555d20e6ac94b261a1858db5c2f880646408224975217265f77fda44be25b56b'
  },
  openclaw:{
    plugin_id:'industrial-sentinel',
    version:'0.2.0',
    marketplace_repository:'industrial-platform-ai/industrial-platform-agent-tools',
    source_commit:'5a400bd4b2d82c495ccb54e0aea007a02cb9f60a'
  },
  agent_skill:{
    id:'industrial-platform-ai/industrial-platform-agent-tools/industrial-sentinel',
    repository:'https://github.com/industrial-platform-ai/industrial-platform-agent-tools',
    path:'skills/industrial-sentinel',
    source_commit:'5a400bd4b2d82c495ccb54e0aea007a02cb9f60a',
    catalog:'https://www.skills.sh/industrial-platform-ai/industrial-platform-agent-tools/industrial-sentinel'
  },
  authorization:{
    installation_requires_operator_authority:true,
    wallet_configuration_is_separate:true,
    payment_authorization_granted_by_this_capability:false,
    never_bypass_permission_controls:true
  },
  payment:{
    protocol:'x402',
    network:'Base',
    asset:'USDC',
    note:'The bootstrap never receives or authorizes a wallet. A separately authorized installed runtime may be configured by its operator for bounded paid cycles.'
  },
  supply_chain:{
    immutable_refs_only:true,
    unpinned_remote_install_commands:false
  },
  recurring_jobs:[
    {kind:'wallet-monitor',route:'/agent/wallet-monitor',max_usd:0.005},
    {kind:'transaction-watch',route:'/agent/transaction-watch',max_usd:0.003},
    {kind:'treasury-snapshot',route:'/agent/treasury-snapshot',max_usd:0.01},
    {kind:'pretrade-context',route:'/agent/pretrade',max_usd:0.01}
  ]
};

const OUTPUT_SCHEMA = {
  type:'object',
  required:['provider','artifact','version','immutable_source','container','openclaw','agent_skill','authorization','payment','supply_chain','recurring_jobs'],
  properties:{
    provider:{type:'string'},
    artifact:{type:'string'},
    version:{type:'string'},
    purpose:{type:'string'},
    immutable_source:{type:'object'},
    container:{type:'object'},
    openclaw:{type:'object'},
    agent_skill:{type:'object'},
    authorization:{type:'object'},
    payment:{type:'object'},
    supply_chain:{type:'object'},
    recurring_jobs:{type:'array'}
  },
  additionalProperties:true
};

function stableJson(value) {
  if (Array.isArray(value)) return '['+value.map(stableJson).join(',')+']';
  if (value && typeof value==='object') {
    return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+stableJson(value[k])).join(',')+'}';
  }
  return JSON.stringify(value);
}

function pythonStyleJson(value) {
  // AIMarket manifest_canonical hashes Python json.dumps(..., sort_keys=True)
  // whose default separators include one space after ':' and ','.
  if (Array.isArray(value)) return '['+value.map(pythonStyleJson).join(', ')+']';
  if (value && typeof value==='object') {
    return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+': '+pythonStyleJson(value[k])).join(', ')+'}';
  }
  return JSON.stringify(value);
}

function signingIdentity() {
  const raw=String(process.env.AIMARKET_ED25519_PRIVATE_KEY_PEM_B64||'').trim();
  if(!raw) throw new Error('AIMARKET_ED25519_PRIVATE_KEY_PEM_B64 is required');
  const privateKey=crypto.createPrivateKey(Buffer.from(raw,'base64').toString('utf8'));
  const publicKey=crypto.createPublicKey(privateKey);
  const spki=publicKey.export({type:'spki',format:'der'});
  const rawPublic=spki.subarray(spki.length-32);
  return {
    privateKey,
    publicKeyB64:rawPublic.toString('base64'),
    sign(text){return crypto.sign(null,Buffer.from(text,'utf8'),privateKey).toString('base64');}
  };
}

function manifestCanonical(manifest) {
  const toolsHash=crypto.createHash('sha256').update(pythonStyleJson(manifest.tools||[]),'utf8').digest('hex');
  const byHubHash=crypto.createHash('sha256').update(pythonStyleJson(manifest.by_hub||{}),'utf8').digest('hex');
  return 'capabilities_count:'+(manifest.capabilities_count||0)
    +'|generated_at:'+(manifest.generated_at||'')
    +'|protocol_version:'+(manifest.protocol_version||'v1')
    +'|tools_hash:'+toolsHash
    +'|by_hub_hash:'+byHubHash;
}

function receiptCanonical(receipt) {
  return 'nonce:'+(receipt.nonce||'')
    +'|product_id:'+(receipt.product_id||'')
    +'|capability_id:'+(receipt.capability_id||'')
    +'|price_usd:'+(receipt.price_usd??0)
    +'|timestamp:'+(receipt.timestamp||'')
    +'|success:'+(receipt.success?1:0)
    +'|latency_ms:'+(receipt.latency_ms??0);
}

function signObject(obj, identity) {
  const body={};
  for (const [k,v] of Object.entries(obj)) if(k!=='signature') body[k]=v;
  const canonical=stableJson(body);
  return {algorithm:'ed25519',public_key:identity.publicKeyB64,value:identity.sign(canonical)};
}

function signedManifest(origin,identity) {
  const generatedAt=new Date().toISOString().replace(/\.\d{3}Z$/,'Z');
  const tools=SENTINEL_CAPABILITIES.map(cap=>({
    name:'industrial-sentinel.'+cap.capability_id,
    display_name:cap.name,
    description:cap.description,
    input_schema:{type:'object',additionalProperties:true},
    output_schema:OUTPUT_SCHEMA,
    price_per_call_usd:0,
    access_mode:'public_free',
    offerable:true,
    p50_latency_ms:5,
    success_rate_30d:1,
    reputation_basis:'measured',
    observations_30d:0,
    product_id:'industrial-sentinel',
    capability_id:cap.capability_id,
    source_hub:'local',
    source_hub_name:'Industrial Platform Sentinel',
    routed_price_usd:0,
    routing_fee_bps:0,
    trust_score:0.5,
    route_status:'live',
    invoke_url:origin+'/ai-market/v2/invoke'
  }));
  const manifest={
    protocol_version:'v2',
    generated_at:generatedAt,
    base_url:origin,
    total_capabilities:tools.length,
    local_capabilities:tools.length,
    federated_capabilities:0,
    hubs_indexed:1,
    capabilities_count:tools.length,
    tools,
    by_hub:{}
  };
  manifest.signature={
    algorithm:'ed25519',
    public_key:identity.publicKeyB64,
    value:identity.sign(manifestCanonical(manifest))
  };
  return manifest;
}

function wellKnown(origin,identity) {
  const wk={
    name:'Industrial Platform Sentinel',
    description:'Install-once autonomous treasury and payment monitoring for authorized funded agents. AIMarket capabilities bootstrap Sentinel; recurring paid work settles directly through Industrial Platform x402 routes.',
    protocol_versions:['v2'],
    hub_version:'sentinel-federation-1.0.0',
    manifest_url:origin+'/ai-market/v2/manifest',
    products_count:1,
    capabilities_count:SENTINEL_CAPABILITIES.length,
    federated_capabilities_count:0,
    supported_chains:['base'],
    supported_tokens:['USDC'],
    payment_configured:false,
    payment_rails:{
      free_bootstrap:{enabled:true,note:'Federation bootstrap is free; installed Sentinel uses the operator-owned wallet for bounded recurring x402 calls.'}
    },
    payment_testnet:false,
    signer_public_key:identity.publicKeyB64,
    federation:{crawl_interval_s:3600,routing_fee_bps:0,min_trust_score:0.3,seed_list:[]},
    peers:[],
    observed_hubs:[],
    categories:['agent-tooling','treasury','wallet','payments','monitoring','x402'],
    ecosystem:{
      version:1,
      relationship:'independent-provider',
      product:'industrial-sentinel',
      nodes:[{id:'industrial-sentinel',name:'Industrial Sentinel',role:'provider',url:origin,capabilities_count:SENTINEL_CAPABILITIES.length,categories:['treasury','wallet','payments','monitoring']}]
    }
  };
  wk.signature=signObject(wk,identity);
  return wk;
}

export function registerAIMarketFederation(app,{origin}) {
  const identity=signingIdentity();

  app.get('/.well-known/ai-market.json',(_req,res)=>{
    res.set('Cache-Control','no-store').json(wellKnown(origin,identity));
  });

  app.get(['/ai-market/v2/manifest','/ai-market/manifest'],(_req,res)=>{
    res.set('Cache-Control','no-store').json(signedManifest(origin,identity));
  });

  app.post('/ai-market/v2/invoke',(req,res)=>{
    const started=Date.now();
    const body=req.body&&typeof req.body==='object'?req.body:{};
    const cap=SENTINEL_CAPABILITIES.find(x=>x.capability_id===body.capability_id);
    if(body.product_id!=='industrial-sentinel'||!cap) {
      return res.status(404).json({success:false,error:'unknown_capability',protocol_version:'v2'});
    }
    const receipt={
      nonce:crypto.randomUUID(),
      product_id:'industrial-sentinel',
      capability_id:cap.capability_id,
      price_usd:0,
      timestamp:new Date().toISOString().replace(/\.\d{3}Z$/,'Z'),
      success:true,
      latency_ms:Math.max(0,Date.now()-started)
    };
    receipt.signature={
      algorithm:'ed25519',
      public_key:identity.publicKeyB64,
      value:identity.sign(receiptCanonical(receipt))
    };
    res.json({
      success:true,
      result:INSTALL_BUNDLE,
      receipt,
      protocol_version:'v2'
    });
  });

  app.get('/ai-market/v2/search',(req,res)=>{
    const intent=String(req.query.intent||'').toLowerCase();
    const tools=signedManifest(origin,identity).tools.filter(t=>{
      if(!intent) return true;
      const hay=(t.name+' '+t.display_name+' '+t.description).toLowerCase();
      return intent.split(/\s+/).filter(Boolean).some(token=>hay.includes(token));
    });
    res.json({intent:req.query.intent||'',count:tools.length,results:tools,protocol_version:'v2'});
  });
}

export { INSTALL_BUNDLE };
