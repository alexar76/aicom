"""Assemble component coverage from bounded captures; no network or foreign code execution."""
import datetime,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
inventory=json.loads((ROOT/'fingerprints.json').read_text())
queries=json.loads((ROOT/'queries.json').read_text())
captures=[]
for path in ['package-metadata-index.json','reverse-dependency-index.json','named-dependency-index.json','github-search-index.json','foreign-source-index.json','foreign-code-index.json']:
 captures+=json.loads((ROOT/path).read_text())
index={r['id']:r for r in captures}
def data(ident):return json.loads((ROOT/index[ident]['body_path']).read_text())
published=json.loads((ROOT/'published-version-scopes.json').read_text())
pub_by_name={r['name']:r for r in published}
hub_names=data('hub-dependent-names');agent_names=data('agent-dependent-names')
plugin_names={f['name'] for c in inventory['components'] if c['component_id']=='plugins' for f in c['fingerprints']}
assert {v['package']['name'] for v in hub_names['directSample']}==plugin_names
assert len(hub_names['directSample'])==hub_names['directCount']==hub_names['totalCount']==15
assert agent_names['totalCount']==1 and agent_names['directSample'][0]['package']['name']=='aimarket-bridges'
old=json.loads((ROOT.parents[2]/'docs/evidence/external-mentions-2026-10-26/enterprise-factory.json').read_text())
head=data('enterprise-factory-head')[0]['sha']
assert head==old['branches']['fork']['head_sha']

checks={
'hub':['aimarket-hub-pypi','aimarket-hub-pypi-dependents','hub-dependent-names'],
'python-agent':['aimarket-agent-pypi','aimarket-agent-pypi-dependents','agent-dependent-names'],
'sdk-typescript':['sdk-npm','sdk-npm-dependents'],
'sdk-dart':['sdk-dart','dart-dependent-search'],
'sdk-rust':['sdk-rust-reverse'],
'plugins':['aimarket-mcp-packager-pypi','aimarket-tee-pypi','aimarket-mcp-packager-pypi-dependents','aimarket-tee-pypi-dependents','hub-dependent-names'],
'widget':['widget-npm','widget-npm-dependents'],
'bridges':['aimarket-bridges-pypi','aimarket-bridges-pypi-dependents'],
'service-mesh':['ai-service-mesh-pypi'],
'treasury':['aimarket-treasury-pypi','aimarket-treasury-pypi-dependents'],
'factory':['enterprise-factory-repo','enterprise-factory-head','enterprise-redaction-pinned','undercode-factory']}
notes={
'hub':('known_observers_and_internal_dependencies','Known ProtocolProbe/MCPBeat/Odel/Tracevero/Glama search results; no new attributable foreign import. Current named graph contains our fifteen plugins.'),
'protocol':('no_new_attributable_source_in_bounded_search','Own specification, own IETF draft and copied Wiki surfaced; exact external README query returned zero. Historical compatible peers are baseline, not re-counted.'),
'python-agent':('internal_dependency_only_in_checked_graph','One named dependent is our aimarket-bridges; own package metadata and catalog copies do not establish third-party adoption.'),
'sdk-typescript':('no_external_dependent_in_checked_version_graph','Npm @aimarket/agent0.4.0 graph zero. Own aliases and other projects using aimarket tokens are excluded.'),
'sdk-dart':('official_reverse_search_empty_version_difference_noted','Official pub.dev dependent query packages=[]; latest published0.3.0 differs from local0.4.0. This is not an integration or a claim that every private Flutter app was searched.'),
'sdk-rust':('official_reverse_index_empty','Crates.io reverse_dependencies total0. Own docs.rs release docs are first-party package documentation, not an independent review.'),
'plugins':('own_package_family_and_derived_catalogs','All fifteen exact package names queried in three groups. Existing copied awesome/catalog surfaces excluded. Packager and TEE own-version graphs zero; other thirteen reverse graphs not individually queried.'),
'widget':('no_external_embed_or_dependency_confirmed','Own npm README/demo and Wiki copies only in received results; npm0.1.2 graph and exact GitHub README query zero.'),
'bridges':('no_external_import_or_dependent_confirmed','Exact import query, external README query and current version graph add no new attributable foreign code. Bridges consuming Agent is internal.'),
'service-mesh':('no_new_foreign_source_pypi_coordinate_unavailable','Exact repo query surfaced only own/copy/awesome metadata; external README query zero. PyPI ai-service-mesh JSON404 at capture time, despite local manifest/map coordinate; not a runtime outage finding.'),
'acex':('web_only_github_search_skipped_after_throttle','Exact repo URL web search returned own Wiki/topic references. Planned GitHub query skipped after public throttle, so no GitHub negative claimed.'),
'pulse':('web_only_github_search_skipped_after_throttle','Exact repo URL web search returned own/copy context only. Package is private:true locally. Planned GitHub query skipped after throttle.'),
'escrow-signer':('own_page_and_topic_mirrors_only_github_skipped','Exact repo URL and HORKOS/escrow-policy-signer searched; own page and topic mirrors are not independent validation. Planned GitHub query skipped after throttle.'),
'treasury':('web_and_version_graph_checked_github_blocked','Exact aimarket-treasury searched, PyPI0.1.4 current graph zero; GitHub search403 is an access limit, not zero results.'),
'factory':('known_derivative_source_reconfirmed_no_runtime_claim','Enterprise Factory has historical separate changes beyond a clone; current head equals26Oct. Read one pinned redaction implementation. Undercode current GET403; known8Oct release coverage is not hands-on evidence.'),
'products':('no_new_attributable_foreign_product_case','Exact aicom-products repo URL searched; own topic/Wiki references do not establish an outside shipped product or customer.')}
matched={
'hub':['https://protocolprobe.com/mcp/servers/io.github.alexar76/aimarket-hub','https://mcpbeat.com/mcp-servers/alexar76/aimarket-hub/'],
'plugins':['https://anclum.com/zh/s/alexar76-aimarket-plugins/','https://githubhelp.com/michielinksee/awesome-mcp-servers-2','https://githubhelp.com/doteyeso-ops/awesome-mcp-servers'],
'service-mesh':['https://awesome.ecosyste.ms/projects?keyword=escrow'],
'escrow-signer':['https://alexar76.github.io/escrow-signer/','https://githubhelp.com/topic/transaction-signing'],
'treasury':['https://public.aquapi.aquaveo.com/aquaveo/stable/%2Bsimple/'],
'factory':['https://github.com/th3artfuldodger/enterprise-factory','https://undercodenews.com/aicom-factory-just-updated-video/']}
coverage=[]
for component in inventory['components']:
 cid=component['component_id'];selected=[q for q in queries if cid in q['component'].split(',')]
 github=[r for r in captures if r.get('component')==cid]
 source_ids=checks.get(cid,[])+[r['id'] for r in github]
 row={**component,'web_queries':[{'query_id':q['id'],'query':q['q'],'status':'executed','batch_file':'search-'+str((queries.index(q)//4)+1).zfill(2)+'.json'} for q in selected],'github_queries':[{'query':r['query'],'status':r['status'],'total_count':r.get('total_count'),'incomplete_results':r.get('incomplete_results'),'evidence_id':r['id']} for r in github],'matched_candidates':[{'url':u,'state':'known or copied metadata; see note; not automatically new adoption'} for u in matched.get(cid,[])],'source_checks':[{'evidence_id':ident,'url':index[ident]['url'],'status':index[ident].get('status'),'checked_at_utc':index[ident]['retrieved_at_utc']} for ident in source_ids],'status':notes[cid][0],'note':notes[cid][1]}
 publication=[]
 for fingerprint in component['fingerprints']:
  name=fingerprint['name'];verified=pub_by_name.get(name)
  if cid=='sdk-dart':
   verified={'id':'sdk-dart','system':'pub.dev','name':'aimarket_agent','version':data('sdk-dart')['latest']['version']}
  if cid=='sdk-rust':verified=None
  publication.append({'name':name,'local_version':fingerprint['local_version'],'registry_metadata_verified':bool(verified),'published_latest_version':verified['version'] if verified else None,'registry_system':verified['system'] if verified else None,'evidence_id':verified['id'] if verified else None,'local_version_matches_verified_latest':fingerprint['local_version']==verified['version'] if verified else None})
 row['publication_checks']=publication
 row['published_version_verified']=None if cid=='plugins' else any(p['registry_metadata_verified'] for p in publication)
 row['publication_verification_scope']='Partial: latest metadata verified for packager and TEE only,2of15 plugin distributions; see publication_checks.' if cid=='plugins' else 'Name and latest-version verified from captured successful registry metadata where available. This flag does not assert local/latest equality; see publication_checks. Rust reverse index alone does not verify its current published version.'
 if cid in ('acex','pulse','escrow-signer'):row['github_queries'].append({'status':'not_executed_after_treasury403','query':'"'+component['repo_url'].replace('https://','')+'" in:readme -user:alexar76'})
 if cid=='plugins':
  row['package_coverage']=[{'package':f['name'],'local_version':f['local_version'],'import_patterns':f['import_fingerprints'],'query_group':'plugins-settlement' if f['name'] in ['aimarket-tee','aimarket-channels','aimarket-reputation','aimarket-safety','aimarket-auction'] else 'plugins-data' if f['name'] in ['aimarket-data-cap','aimarket-dataset','aimarket-nft','aimarket-orchestrator','aimarket-personas'] else 'plugins-remaining','own_reverse_graph_checked':f['name'] in ['aimarket-mcp-packager','aimarket-tee'],'matched_as_own_hub_dependent':True} for f in component['fingerprints']]
 coverage.append(row)

findings=[
{'id':'hub-internal-graph','components':['hub','plugins'],'class':'internal_package_dependency','novelty':'current version scope; no new external adoption','source_url':index['hub-dependent-names']['url'],'targets':hub_names['directSample'],'target_version':'aimarket-hub@3.19.0','count':15,'ownership':'Every named distribution matches local own plugin manifest identity; not15 outside customers. Older representative dependent versions are graph nodes, not observed installed clients.','confidence':'high_for_named_snapshot'},
{'id':'agent-internal-graph','components':['python-agent','bridges'],'class':'internal_package_dependency','novelty':'current version scope; no new external adoption','source_url':index['agent-dependent-names']['url'],'targets':agent_names['directSample'],'target_version':'aimarket-agent@2.6.2','ownership':'aimarket-bridges is our own distribution.','confidence':'high_for_named_snapshot'},
{'id':'zero-graphs','components':['sdk-typescript','widget','bridges','treasury','plugins','sdk-rust','sdk-dart'],'class':'bounded_reverse_index_result','novelty':'current package graph verification, not new audience','checks':[{'id':ident,'url':r['url'],'data':data(ident)} for ident,r in index.items() if ident.endswith('-dependents') and data(ident).get('dependentCount')==0]+[{'id':'sdk-rust-reverse','url':index['sdk-rust-reverse']['url'],'data':data('sdk-rust-reverse')},{'id':'dart-dependent-search','url':index['dart-dependent-search']['url'],'data':data('dart-dependent-search')}],'limits':'Version-scoped or registry-index bounded, excludes unrecorded/private/runtime/non-package uses.','confidence':'high_for_bounded_API_response'},
{'id':'mesh-pypi-unavailable','components':['service-mesh'],'class':'distribution_coordinate_observation','novelty':'current HTTP check; not external adoption','source_url':index['ai-service-mesh-pypi']['url'],'status':404,'local_coordinate':'ai-service-mesh0.1.0','limits':'Exact PyPI JSON404 does not prove the service or repository is unavailable. No reverse graph zero inferred.','confidence':'high_for_exact_GET'},
{'id':'dart-version-scope','components':['sdk-dart'],'class':'distribution_version_observation','novelty':'current metadata, not external adoption','source_url':index['sdk-dart']['url'],'published_version':data('sdk-dart')['latest']['version'],'local_version':'0.4.0','limits':'Own release distribution metadata; no defect, user or rollout inferred.','confidence':'high_for_exact_registry_response'},
{'id':'enterprise-factory','components':['factory'],'class':'derivative_source','novelty':'known26Oct; head unchanged; no new artifact','source_url':'https://github.com/th3artfuldodger/enterprise-factory','parent':'alexar76/aicom','current_head':head,'last_push_utc':data('enterprise-factory-repo')['pushed_at'],'known_compare_at_2026_10_26':{'ahead_by':old['comparison']['ahead_by'],'behind_by':old['comparison']['behind_by'],'base_sha':old['comparison']['base_sha'],'merge_base_sha':old['comparison']['merge_base_sha']},'pinned_source_url':'https://github.com/th3artfuldodger/enterprise-factory/blob/'+head+'/core/security_redaction.py','source_evidence_id':'enterprise-redaction-pinned','ownership':'External GitHub account. Historical author strings name Everett Trimble but are not verified identity/human provenance.','limits':'Historical extra commits establish separate source work, not successful tests, running deployment, paying clients or new activity since26Oct. Ahead/behind counts belong to26Oct comparison and were not recalculated against today parent.','confidence':'high_for_source_and_head; runtime_unverified'},
{'id':'undercode','components':['factory'],'class':'historical_release_coverage_not_hands_on','novelty':'known26Oct, article8Oct; current GET403','source_url':index['undercode-factory']['url'],'current_status':403,'evidence_id':'undercode-factory','limits':'Current article body not read due403. Historical attribution and AI disclosure are from26Oct baseline, corroborated only by current search snapshot; not new hands-on review.','confidence':'historical_primary_plus_current_search_only'},
{'id':'long-tail-search-limits','components':['protocol','bridges','widget','service-mesh','treasury','acex','pulse','escrow-signer'],'class':'bounded_search_result','novelty':'new targeted coverage, no integration found','records':[{'component':r['component'],'query':r['query'],'status':r['status'],'total_count':r.get('total_count'),'incomplete_results':r.get('incomplete_results')} for r in captures if r.get('component')],'not_executed_after403':['acex','pulse','escrow-signer'],'limits':'Four200/0 READMEs, treasury403, three planned GitHub searches skipped. Definite identity matching required because GitHub tokenizes hyphens. No full authenticated code search performed.','confidence':'bounded_only'}]
qa=[]
for r in captures:
 body=(ROOT/r['body_path']).read_bytes();assert r['complete'] and len(body)==r['bytes'] and hashlib.sha256(body).hexdigest()==r['sha256']
 qa.append({'id':r['id'],'url':r['url'],'status':r['status'],'body_path':r['body_path'],'bytes':r['bytes'],'sha256':r['sha256'],'complete':True,'length_matches':True,'sha256_matches':True})
summary={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'families':len(coverage),'plugin_distributions':len(plugin_names),'executed_search_strings':24+sum('component' in r for r in captures),'web_queries':24,'github_search_attempts':sum('component' in r for r in captures),'github_search_successful':sum('component' in r and r['status']==200 for r in captures),'primary_get_count':len(captures),'http_status_counts':{str(s):sum(r['status']==s for r in captures) for s in sorted({r['status'] for r in captures})},'new_external_runtime_or_dependency_confirmed':False,'new_independent_core_review_confirmed':False,'baseline':['artifacts/external-links-2026-11-10/review.ru.md','artifacts/external-links-deeper-2026-11-10/report.ru.md','docs/growth/external-mentions-2026-10-26.ru.md','artifacts/external-signals-2026-11-09/report.ru.md'],'limits':['No HISTOR/WARDEN research in this branch.','No downloads used as adoption counts.','No authenticated accounts, publishing, operator messages, package installation, payments, invokes or foreign code execution.','GitHub quota403 stopped queue; no retry or identity/network change.','Public search/index coverage is not a global absence claim.']}
(ROOT/'coverage.json').write_text(json.dumps({'summary':summary,'components':coverage},ensure_ascii=False,indent=2)+'\n')
(ROOT/'findings.json').write_text(json.dumps({'summary':summary,'findings':findings},ensure_ascii=False,indent=2)+'\n')
(ROOT/'capture-integrity.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
