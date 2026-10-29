import asyncio,json,math,os,sys
sys.path.insert(0,'/app/backend')
import hub_discovery
from hub_affiliation import apply_hub_affiliation
from ecosystem_layout import local_ecosystem_radius,node_position
PRIMARY='https://operator.example'
BASE='http://127.0.0.1:9083'
os.environ['ALIEN_ECOSYSTEM_PROFILE']='generic'
os.environ['ALIEN_PUBLIC_HUB_URL']=PRIMARY
os.environ['ALIEN_DISCOVERY_ENABLED']='1'
hub_discovery.url_is_safe=lambda *a,**kw: True

def discover(declaration,url='https://unseen.example.net'):
    fetched=[]
    async def get(client,target,**kw):
        fetched.append(target)
        if target==BASE+'/ai-market/v2/federation/peers':
            return {'peers':[{'url':url,'name':'New Catalogue','capabilities_count':0,'trust_score':.265}],'pending':[]}
        if target==BASE+'/.well-known/ai-market.json':
            return {'hub_url':PRIMARY,'hub_version':'3.16.1'}
        if target==url+'/.well-known/ai-market.json':
            return {'name':'New Catalogue',**declaration}
        return None
    hub_discovery._get_json=get
    result=asyncio.run(hub_discovery.discover_async(BASE))
    assert not result['errors'],result
    apply_hub_affiliation(result['nodes'],primary_hub_url=PRIMARY)
    node=next(n for n in result['nodes'] if n.get('url')==url)
    return node,result['nodes'],fetched

checks=[]
for url in ('https://unseen.example.net','https://new.operator.example'):
    for role in ({'role':'hub'},{'federation':{'role':'hub'}}):
        for proto in ({},{'protocol_versions':['mcp']},{'protocol_versions':['vfuture']}):
            node,nodes,fetched=discover({**role,**proto,'peers':[]},url)
            assert (node['group'],node['role'],node['icon'])==('peer_hub','hub','hub'),node
            assert node['hub']['id']==node['id'],node
            assert node['status']=='idle',node
            assert node['metrics']['capabilities']==0,node
            assert url+'/ai-market/v2/health' not in fetched,fetched
            centre=node_position('hub')
            distance=math.dist([node['position'][k] for k in ('x','y','z')],[centre[k] for k in ('x','y','z')])
            assert distance>local_ecosystem_radius(),node
            checks.append('explicit hub / '+url+' / '+str(proto))
for declaration in ({'role':'provider','hub_version':'3.0','protocol_versions':['v2']},{'federation':{'role':'service'},'hub_version':'3.0','protocol_versions':['v2']},{'node_version':'aimarket-node 1.0','protocol_versions':['v2']}):
    node,_,_=discover(declaration)
    assert node['group']!='peer_hub' and node['hub']['id']=='hub',node
    checks.append('service stays service')
node,_,fetched=discover({'protocol_versions':['v1','mcp'],'manifest_url':'https://agent-exec.448c.org/ai-market/manifest'},'https://agent-exec.448c.org')
assert node['group']=='peer_hub' and node['hub']['id']==node['id'],node
assert 'https://agent-exec.448c.org/health' in fetched
checks.append('legacy agent-exec')
node,nodes,_=discover({'role':'hub','ecosystem':{'nodes':[{'id':'child','name':'Provider','role':'provider','url':'https://provider.example.net','capabilities_count':1}]}})
child=next(n for n in nodes if n.get('url')=='https://provider.example.net')
assert child['hub']==node['hub'] and child['hub']['id']!=child['id'],child
checks.append('provider inherits parent hub')
print(json.dumps({'status':'passed','cases':len(checks),'checks':checks}))
