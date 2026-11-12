# -*- coding: utf-8 -*-
"""Build a bounded component-coverage report from captured evidence only."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone
import json

P=Path(__file__).resolve().parent
inv=json.loads((P/'inventory.json').read_text())
queries=json.loads((P/'query-log.json').read_text())['queries']
captures=[r for f in sorted(P.glob('sources-*-index.json')) for r in json.loads(f.read_text())]
by={r['key']:r for r in captures}
def body(k):return json.loads((P/(k+'.raw')).read_text())
def evidence(k):
 r=by[k];return {x:r[x] for x in ['url','status','retrieved_at_utc','body_file','bytes','sha256','truncated']}
checks=[]
for r in captures:
 b=(P/r['body_file']).read_bytes();checks.append({'key':r['key'],'length_ok':len(b)==r['bytes'],'sha256_ok':sha256(b).hexdigest()==r['sha256'],'truncated':r['truncated']})

baseline_path=P.parents[1]/'external-links-deeper-2026-11-10'/'code'/'github-searches.json'
old=next(x for x in json.loads(baseline_path.read_text()) if x.get('query_kind')=='repositories' and 'in:readme' in x.get('query',''))
new=body('github-external-readmes')
oldnames={x['full_name'] for x in old['items']};newnames={x['full_name'] for x in new['items']}
delta={'baseline':str(baseline_path),'baseline_retrieved_at_utc':old['retrieved_at_utc'],'old_names':sorted(oldnames),'current_names':sorted(newnames),'added':sorted(newnames-oldnames),'removed':sorted(oldnames-newnames)}
attribution=json.loads((P/'oracle-core-dependent-attribution.json').read_text())
legacy=body('emporion-legacy-metadata')['info']
for a in attribution:
 if a['name']=='aimarket-emporion':
  a.update(classification='internal_legacy_package',pypi_project_urls=legacy.get('project_urls'),pypi_home_page=legacy.get('home_page'),evidence='emporion-legacy-metadata.raw')
(P/'oracle-core-dependent-attribution.json').write_text(json.dumps(attribution,ensure_ascii=False,indent=2)+'\n')

graph_keys={'oracle_gateway':'oracle-gateway-dependents','mcp_gateway':'mcp-gateway-dependents','oracles_platon':'oracle-core-dependents'}
commit_keys={'metis':'commits-metis-origin','atlas':'commits-atlas-origin','gaia':'commits-iot-origin','hestia':'commits-forge-hestia-origins','hephaestus':'commits-forge-hestia-origins'}
rows=[]
for i,x in enumerate(inv):
 k=graph_keys.get(x['id'],x['id']+'-dependents')
 graph={'state':'not_applicable_private_package','reason':'local package.json private:true; no published npm adoption inference'}
 if k in by:
  graph={'state':'indexed_version_graph' if by[k]['status']==200 else 'version_graph_unavailable','source':evidence(k),'package':x['package'],'version':x['version']}
  if by[k]['status']==200:graph['counts']=body(k)
 if x['id']=='oracles_platon':graph['platon_alias']={'package':'aimarket-platon','version':'0.1.6','source':evidence('platon-dependents'),'counts':body('platon-dependents')}
 q=[{**a,'search_response_file':'search-%02d.json'%((j//4)+1)} for j,a in enumerate(queries) if a['family']==x['id']]
 row={'family':x['id'],'fingerprints':x,'queries':q,'web_result_state':'no_independent_code_or_substantive_review_confirmed_in_returned_batches','shared_readme_search':{'source':evidence('github-external-readmes'),'query':'alexar76 in:readme -user:alexar76','total_count':new['total_count'],'incomplete_results':new['incomplete_results'],'scope':'README discovery only; not code search'},'dependency_graph':graph,'result_state':'no_new_external_runtime_or_review_confirmed','novelty':'No newly confirmed independent integration in this pass; known sources/homonyms/catalogs excluded.'}
 if x['id'] in commit_keys:
  ck=commit_keys[x['id']];row['http_origin_commit_message_search']={'source':evidence(ck),'total_count':body(ck)['total_count'],'incomplete_results':body(ck)['incomplete_results'],'scope':'commit messages only, not complete code search'}
 if x['id']=='momus':row['candidate_exclusion']='igor-holt/momus README expressly disclaims alexar76 red-team satellite; known homonym, not integration';row['internal_dependent']={'name':'aimarket-treasury','source':evidence('momus-dependent-names')}
 if x['id']=='oracles_platon':row['internal_dependents']={'count':20,'attribution_file':'oracle-core-dependent-attribution.json','scope':'19 exact local project names; legacy EMPORION owned project URLs; not20external adopters'}
 rows.append(row)

findings=[
 {'id':'A01','families':['oracles_platon'],'classification':'internal_dependency_graph_not_external_adoption','confidence':'high for captured graph and package attribution; graph counts indicative','sources':[evidence(k) for k in ['oracle-core-dependents','oracle-core-dependent-names','emporion-legacy-metadata']],'observation_ru':'Версия aimarket-oracle-core0.6.4 имеет20 direct dependents в этом графе. Все20 относятся к экосистеме:19имён буквально совпали с local pyproject metadata, legacy aimarket-emporion ссылается на github.com/alexar76/emporion. Это не20 внешних внедрений. Platon0.1.6 graph показывает0.','novelty':'Current bounded attribution of known internal graph; no new independent operator'},
 {'id':'A02','families':['momus'],'classification':'internal_dependency','confidence':'high','sources':[evidence(k) for k in ['momus-dependents','momus-dependent-names']],'observation_ru':'Единственный direct dependent MOMUS0.2.0 — aimarket-treasury0.1.0, наш отдельный payer. Внешний dependent не установлен.','novelty':'Reconfirmed internal relation'},
 {'id':'A03','families':['momus'],'classification':'known_homonym_excluded','confidence':'high for explicit README wording; no beneficial-owner verification','sources':[evidence(k) for k in ['momus-candidate-meta','momus-candidate-commit','momus-candidate-readme','momus-candidate-tree']],'public_url':'https://github.com/igor-holt/momus/blob/1ac416e4c2e2f92c23209db977166eccafcde2be/README.md','pinned_commit':'1ac416e4c2e2f92c23209db977166eccafcde2be','commit_date':body('momus-candidate-commit')['commit']['committer']['date'],'observation_ru':'Genesis Conductor MOMUS Igor Holt прямо пишет, что не является alexar76 red-team satellite. Его README попадает в identity search именно из-за этого различения. Не интеграция и не новый кандидат: исключение было известно в октябре.','novelty':'Known October exclusion, primary re-read only'},
 {'id':'A04','families':['metis','hestia','atlas','gaia','oracle_gateway','mcp_gateway','logos','skopos','oracles_platon'],'classification':'bounded_zero_indexed_reverse_dependencies','confidence':'high for version-scoped API fields only','observation_ru':'Девять прочитанных package-version graphs вернули0 dependents: METIS, HESTIA, ATLAS, GAIA, оба gateway, LOGOS, SKOPOS и Platon alias. Это индексированные зависимости конкретных версий, не число пользователей и не исключение HTTP calls.','source_keys':['metis-dependents','hestia-dependents','atlas-dependents','gaia-dependents','oracle-gateway-dependents','mcp-gateway-dependents','logos-dependents','skopos-dependents','platon-dependents'],'novelty':'Current graph snapshot, no independent adoption confirmed'},
 {'id':'A05','families':['argus','themis','basanos','dolos'],'classification':'dependency_index_gap','confidence':'high for404; no usage inference','sources':[evidence(k) for k in ['argus-dependents','themis-dependents','basanos-dependents','dolos-dependents']],'observation_ru':'Текущие version graphs ARGUS0.3.6, THEMIS0.1.0, BASANOS0.1.0 и DOLOS0.1.0 ответили404. Это отсутствие данного ответа индекса; нулевое использование из него не выводится.','novelty':'Scope limitation'},
 {'id':'A06','families':['hephaestus','argus','themis','oracle_gateway','mcp_gateway'],'classification':'fingerprint_disambiguation','confidence':'high for local metadata','observation_ru':'HEPHAESTUS package private:true. ARGUS и oracle gateway — stdio packages. modelmarket.dev/mcp — maintained hosted Hub interface, не доказательство запуска aimarket-mcp package. Для THEMIS standalone public API origin в прочитанном README не установлен. Общий Hub URL без specific capability/package недостаточен для attribution.','evidence_file':'inventory.json','novelty':'Audit precision, not an external finding'},
 {'id':'A07','families':[x['id'] for x in inv],'classification':'bounded_external_discovery','confidence':'bounded','sources':[evidence(k) for k in ['github-external-readmes','commits-metis-origin','commits-iot-origin','commits-atlas-origin','commits-forge-hestia-origins']],'observation_ru':'README full_name sets12/12 совпадают с самым свежим baseline; added/removed пусты. Четыре commit-message запроса по Metis/IOT/ATLAS/Hestia+Forge origins дали0 при incomplete_results=false. Возвращённые web batches в основном содержат собственные статьи, зеркала, каталоги, package diff indexes и одноимённые проекты; нового независимого review/code candidate не подтверждено.','novelty':'No new independent code/review confirmed'}
]
coverage={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'families_count':len(rows),'web_queries':30,'github_search_queries':5,'total_targeted_query_executions':35,'primary_gets':len(captures),'scope_excludes':'HISTOR; auto-catalog counts are not adoption','readme_set_delta':delta,'families':rows}
(P/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2)+'\n')
doc={'checked_at_utc':coverage['checked_at_utc'],'scope':'15agent/oracle families; public read only','findings':findings,'new_independent_runtime_confirmed':False,'new_independent_review_confirmed':False,'primary_gets':len(captures),'status_counts':{str(s):sum(r['status']==s for r in captures) for s in sorted({r['status'] for r in captures})},'limits':['Search/README/commit-message discovery is not authenticated global code search.','HTTP integrations can exist with no package dependency; origin strings were included in per-family web queries and5priority origins also in4commit queries.','Absence in returned batches is not proof of absence on the internet or in private/unindexed code.','Version-scoped deps.dev counts are indicative;404is not0users.','Third-party identities and beneficial ownership were not independently verified.','No packages installed, foreign code run, authentication used, messages sent, external writes, invokes, or payments.']}
(P/'findings.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
verification={'capture_checks':checks,'all_lengths_and_hashes_match':all(x['length_ok'] and x['sha256_ok'] for x in checks),'all_bodies_complete':not any(x['truncated'] for x in checks),'family_count':len(rows),'all15covered':len(rows)==15 and len({x['family'] for x in rows})==15 and all(len(x['queries'])==2 for x in rows),'readme_set_delta':delta}
(P/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'families':len(rows),'gets':len(captures),'status_counts':doc['status_counts'],'integrity':verification['all_lengths_and_hashes_match'],'all15covered':verification['all15covered'],'readme_added':delta['added'],'readme_removed':delta['removed']},ensure_ascii=False,indent=2))
