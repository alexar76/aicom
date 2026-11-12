"""Build the ACEX fingerprint-gap report from saved local and public bytes only."""
import datetime,hashlib,json,urllib.parse
from pathlib import Path
ROOT=Path(__file__).resolve().parent
TEAM=ROOT.parent/'root'
REPO=ROOT.parents[2]
fingerprints=json.loads((ROOT/'fingerprints.json').read_text())
queries=json.loads((ROOT/'queries.json').read_text())
own=json.loads((ROOT/'primary-index.json').read_text())
shared=[]
for name in ['plan-2-search-index.json','plan-4-exact-search-index.json']:
 for row in json.loads((TEAM/name).read_text()):
  if row['key'] in ['readme-acex','imports-acex','contract-audit-pool','contract-listing','config-jupiter']:
   raw=(TEAM/row['file']).read_bytes();assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'] and not row['truncated']
   body=json.loads(raw);assert row['status']==200 and body['total_count']==0 and body['incomplete_results'] is False
   shared.append({**row,'query':urllib.parse.parse_qs(urllib.parse.urlparse(row['url']).query)['q'][0],'data':body,'evidence_index':'../root/'+name,'evidence_body':'../root/'+row['file']})
assert len(shared)==5
integrity=[]
for row in own:
 b=(ROOT/row['body_path']).read_bytes();assert row['complete'] and len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256']
 integrity.append({'scope':'own_primary_capture','id':row['id'],'path':row['body_path'],'status':row['status'],'bytes':len(b),'sha256':row['sha256'],'complete':True,'length_matches':True,'sha256_matches':True})
for row in shared:
 integrity.append({'scope':'shared_root_capture_not_a_new_GET','id':row['key'],'path':row['evidence_body'],'status':row['status'],'bytes':row['bytes'],'sha256':row['sha256'],'complete':True,'length_matches':True,'sha256_matches':True})
local=[]
for row in fingerprints['sources']:
 p=REPO/row['path'];raw=p.read_bytes();local.append({'path':row['path'],'captured_sha256':row['sha256'],'current_sha256':hashlib.sha256(raw).hexdigest(),'unchanged_at_report_build':hashlib.sha256(raw).hexdigest()==row['sha256']})

dimensions=[]
for dim in ['python','evm','solana','audit','http','config','terms']:
 selected=[q for q in queries if q['dimension']==dim]
 dimensions.append({'dimension':dim,'queries':[{'id':q['id'],'q':q['q'],'status':'executed','batch':'search-'+str((queries.index(q)//4)+1).zfill(2)+'.json'} for q in selected],'matched_candidates':['fastly-own-acex-doc'] if dim in ('python','config') else ['pypi-acex-homonym','unattributed_simple_indexes'] if dim=='audit' else [],'actual_foreign_import_call_config_confirmed':False,'status':'bounded_no_attributable_foreign_source','limits':'Received search results do not cover all source code, private configurations, direct HTTP usage or unindexed deployments.'})
coverage={'built_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'component':'ACEX','gap_closed':'Prior coverage only had acex-capital Solana manifest; now includes real Python modules and imports, audit names, EVM contract identifiers/addresses, Solana program declarations, HTTP/WS/SSE routes, client config keys and Jupiter supplier direction.','local_source_file_count':len(local),'web_query_count':len(queries),'shared_github_search_count':len(shared),'own_primary_get_count':len(own),'own_http_status_counts':{str(x):sum(r['status']==x for r in own) for x in sorted({r['status'] for r in own})},'github_api_called_by_this_branch':False,'new_independent_runtime_integration_confirmed':False,'new_independent_code_or_configuration_confirmed':False,'dimensions':dimensions,'github_searches':shared,'limits':['GitHub searches executed by root only; this branch did not consume api.github.com. CORE quota was not assumed restored.','All five received README/commit search responses200,total_count0,incomplete_results=false. This is not full authenticated code search.','HTTP response Date headers precede root capture timestamps; both are preserved in shared source indexes. No index-freshness guarantee inferred.','Only two concrete false-positive GETs were justified; empty matches were not expanded to meet a numerical target.','No installations, publishing, messages, auth, payments, tools/call or execution of foreign code.']}
homonym=json.loads((ROOT/'homonym-analysis.json').read_text())
findings={'coverage_summary':{k:v for k,v in coverage.items() if k not in ['dimensions','github_searches']},'baseline':['artifacts/external-components-2026-11-10/core/coverage.json','artifacts/external-components-2026-11-10/core/fingerprints.json','artifacts/external-links-deeper-2026-11-10/code/findings.json'],'records':[
 {'id':'expanded-local-acex-fingerprints','class':'fingerprint_scope_correction_not_external_adoption','novelty':'new coverage beyond Solana crate-only fingerprint','sources':fingerprints['own_consumers'],'source_targets':[{'source_path':r['path'],'target_module':i['module'],'symbols':i['names'],'line':i['line']} for r in fingerprints['own_consumers'] for i in r['imports']],'note':'Hub and Factory are own consumers. These actual local imports justify Python-targeted search but are not foreign integrations. Root ACEX has no standalone Python package manifest.'},
 {'id':'pypi-acex-homonym','class':'excluded_other_project_identity','source_url':'https://pypi.org/pypi/acex/json','source_targets':[{'source_field':'info.project_urls.Repository','target':'https://github.com/acex-labs/acex'}],'registry_version':homonym['version'],'identity':homonym['summary'],'exact_ecosystem_markers_in_metadata':homonym['exact_ecosystem_markers_in_metadata'],'note':'Different ACE-X backend/project repository; declared dependency metadata has no aimarket coordinate. Do not treat PyPI acex as our ACEX distribution or use its users/downloads as ours. Metadata-only exclusion, not a full code audit or assertion about every possible relationship.','novelty':'false-positive namespace clarified; no integration','confidence':'high_for_registry_identity_fields'},
 {'id':'fastly-own-doc-search-hit','class':'search_only_own_document_mirror_candidate','source_url':'https://ithub.global.ssl.fastly.net/alexar76/acex/blob/main/docs/jupiter-routing.md','expected_upstream':'https://github.com/alexar76/acex/blob/main/docs/jupiter-routing.md','current_direct_status':503,'note':'Search snippet reproduces our acex.integrations.jupiter example at an alexar76 source path. Direct body503 is an access failure, so current content is not primary-confirmed. Neither the search copy nor the proxy hostname establishes foreign use.','novelty':'excluded copied-own context','confidence':'search_only'},
 {'id':'exact-search-zero','class':'bounded_negative_search_results','sources':[{'query':r['query'],'url':r['url'],'status':r['status'],'data':r['data']} for r in shared],'note':'No attributable foreign import/call/config candidate emerged from the exact repo, namespace, contract-name and config queries. Does not rule out source files not indexed by README/commit search.','novelty':'previously skipped repo query now answered; additional fingerprint queries checked','confidence':'bounded_API_result'},
 {'id':'outbound-jupiter-boundary','class':'directionality_not_adoption','source_path':'acex/integrations/jupiter.py','source_targets':[{'source_function':'fetch_jupiter_quote','target':'https://quote-api.jup.ag/v6/quote','direction':'our client -> Jupiter supplier'},{'source_function':'build_swap_plan','target':'https://quote-api.jup.ag/v6/swap','direction':'our generated plan -> Jupiter supplier'}],'note':'Our integration with Jupiter is not evidence that Jupiter or another operator uses ACEX. Declared contract addresses and Solana program ID likewise do not establish external invocation.'}
]}
(ROOT/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2)+'\n')
(ROOT/'findings.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2)+'\n')
(ROOT/'capture-integrity.json').write_text(json.dumps({'primary_and_shared':integrity,'local_source_fingerprints':local},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'local_source_files':len(local),'local_hashes_unchanged':sum(r['unchanged_at_report_build'] for r in local),'web_queries':len(queries),'own_GET':len(own),'shared_search_GET':len(shared),'primary_bodies_verified':len(integrity)},indent=2))
