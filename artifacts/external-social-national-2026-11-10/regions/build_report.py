"""Analyze bounded regional search/read captures offline, without executing page code."""
import datetime,hashlib,html,json,re,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
queries=json.loads((ROOT/'queries.json').read_text())
rows=json.loads((ROOT/'primary-index.json').read_text());by_id={r['id']:r for r in rows}
def body(ident):return (ROOT/by_id[ident]['body_path']).read_text()
markers=['alexar76','modelmarket.dev','attestedmemory.net','PingBlip','aimarket-bridges','SYMMARTYS','HEPHAESTUS','Emberline','Tideline']
rare=['An AI Agent Bought a Domain','I unzipped the sample fire brief','Price the chain before hop three bills you','Our Multica agents now work in an agent market']
rss=ET.fromstring(body('habr-public-rss'));items=rss.findall('./channel/item')
assert rss.tag=='rss' and not items
assert json.loads(body('radyz-native-aimarket'))==[]
italian=body('italian-aimarket-faq');trending=body('agentstacklist-trending')
italian_markers={s:bool(re.search(re.escape(s),html.unescape(italian),re.I)) for s in markers}
trending_markers={s:bool(re.search(re.escape(s),html.unescape(trending),re.I)) for s in markers+rare}
assert not any(italian_markers.values()) and not any(trending_markers.values())

prior=[];skipped=[];old_queries={}
def walk(value,path):
 if isinstance(value,dict):
  for k,v in value.items():
   if k in ('q','query','search_query','query_text') and isinstance(v,str):old_queries.setdefault(v,[]).append(path)
   walk(v,path)
 elif isinstance(value,list):
  for v in value:walk(v,path)
for name in (ROOT/'previous-query-files.txt').read_text().splitlines():
 path=REPO/name
 try:
  if path.stat().st_size>2_000_000:skipped.append({'path':name,'reason':'larger_than_2MB_for_query_field_scan'});continue
  value=json.loads(path.read_text());walk(value,name);prior.append(name)
 except Exception as exc:skipped.append({'path':name,'reason':type(exc).__name__})
novelty={'method':'Literal query text comparison against structured q/query/search_query/query_text fields; domains may differ. This is not a claim of semantic novelty or exhaustive historical-source comparison.','baseline_files_read':len(prior),'distinct_prior_query_strings':len(old_queries),'skipped':skipped,'queries':[{'id':q['id'],'query':q['q'],'literal_seen_before':q['q'] in old_queries,'prior_paths':old_queries.get(q['q'],[])[:12]} for q in queries]}
(ROOT/'query-novelty.json').write_text(json.dumps(novelty,ensure_ascii=False,indent=2)+'\n')

query_index=[];batches=[]
for i in range(1,8):
 p=ROOT/f'search-{i:02}.json';d=json.loads(p.read_text());r=d['result'];state='empty_batch' if isinstance(r,str) and r.startswith('Empty search results') else 'response_received' if isinstance(r,str) else 'tool_error_or_unknown'
 batches.append({'file':p.name,'captured_at_utc':d['captured_at_utc'],'status':state,'submitted_query_count':len(d['queries'])})
 for q in d['queries']:query_index.append({**q,'batch_file':p.name,'batch_status':state,'individual_query_completeness':'not_certified_by_combined_response'})
(ROOT/'query-index.json').write_text(json.dumps({'queries':query_index,'batches':batches},ensure_ascii=False,indent=2)+'\n')

findings=[
 {'id':'habr-public-rss','source_url':by_id['habr-public-rss']['url'],'class':'native_search_result_not_a_publication','author':None,'article_date':None,'feed_declared_pubDate':rss.findtext('./channel/pubDate'),'checked_at_utc':by_id['habr-public-rss']['retrieved_at_utc'],'status':200,'rss_item_count':len(items),'exact_source_targets':[],'novelty':'New read path: ordinary public RSS succeeds without consent; no new article found in this exact feed.','confidence':'high_for_received_XML_only','limits':'modelmarket.dev is present only in query/channel title and description. Zero items is not zero posts across Habr; no banner clicked, no consent action or UI used.'},
 {'id':'radyz-native-aimarket','source_url':by_id['radyz-native-aimarket']['url'],'class':'native_search_result_not_a_publication','author':None,'article_date':None,'checked_at_utc':by_id['radyz-native-aimarket']['retrieved_at_utc'],'status':200,'returned_records':0,'exact_source_targets':[],'novelty':'Additional exact keyword check of known publisher, not new external coverage.','confidence':'high_for_this_API_query_only','limits':'Earlier control showed WordPress search misses a known ecosystem source link located outside indexed content. Empty native result does not prove absence of references.'},
 {'id':'italian-aimarket-faq','source_url':by_id['italian-aimarket-faq']['url'],'class':'unattributed_homonym_candidate_JS_shell','publisher_metadata':'Bizpower SRLS','author':None,'article_date':None,'checked_at_utc':by_id['italian-aimarket-faq']['retrieved_at_utc'],'status':200,'exact_markers_in_received_HTML':italian_markers,'exact_source_targets':[],'novelty':'Newly checked false-positive candidate, not a newly attributed ecosystem mention.','confidence':'metadata_and_shell_only','limits':'HTML declares ai-market.it canonical and Bizpower publisher; rendered FAQ resides in JS and was not read. No account, JS code, consent or signup flow executed. No full-site unrelatedness claim.'},
 {'id':'agentstacklist-trending','source_url':by_id['agentstacklist-trending']['url'],'class':'excluded_thematic_fallback_in_received_page','author':None,'article_date':None,'checked_at_utc':by_id['agentstacklist-trending']['retrieved_at_utc'],'status':200,'exact_markers_and_rare_titles_in_received_HTML':trending_markers,'exact_source_targets':[],'novelty':'Primary false-positive check, not ecosystem news.','confidence':'high_for_complete_received_bytes','limits':'No exact tested ecosystem marker/title in2.41MB saved page. Does not rule out other pages, historical versions or unrendered account views.'},
 {'id':'known-aggregation-and-catalog-search-hits','class':'known_automatic_or_copied_content','author':'Original own DEV articles remain alexar76 where identified; aggregator authorship not established here.','article_date':None,'source_urls':['https://www.libhunt.com/posts/1567497-our-multica-agents-now-work-in-an-agent-market-they-buy-remember-review-sellers-and-sell-their-own-work','https://wpnews.pro/news/i-opened-a-live-agent-marketplace-the-receipts-were-the-product','https://shortsingh.com/article/developer-launches-live-ai-agent-marketplace-with-metered-calls-and-public-recei','https://agenstry.com/agents/modelmarket.dev','https://agenteconomy.report/s/modelmarket.dev','https://karatum.com/ratings/kt_03befd45aaa86be2de6ceff9','https://www.a2a-registry.org/agent/dev.modelmarket.modelmarketdev?tab=reviews','https://apis.io/providers/attestedmemory-net/'],'novelty':'Known operators/pages in accumulated baseline; fresh crawl/search visibility does not establish new national author, review or use.','confidence':'current_search_only_plus_historical_baseline','limits':'These pages were not re-fetched in this branch. Language of query or localized UI does not identify operator nationality. No claimed new reader comments, ratings or counts.'},
 {'id':'own-and-generic-term-exclusions','class':'excluded_own_content_or_unattributed_terms','source_urls':['https://pypi.org/project/create-aimarket-agent/','https://alexar76.github.io/themis/','https://github-wiki-see.page/m/alexar76/aicom/wiki/Ecosystem','https://attestedmemory.com/'],'novelty':'No independent ecosystem attribution established.','confidence':'search_only','limits':'Own package/Wiki/tutorial pages, generic attested-memory research and unrelated Emberline/Tideline naming pages are not counted as national reviews. attestedmemory.com is not equated with our .net solely by its name; no primary read of it here.'}
]
regions=[]
for region in ['RU','UA','DE','FR','ES/LatAm','PT/BR','PL','CZ','NL','IT']:
 aliases=set(region.split('/'))
 selected=[q for q in query_index if aliases.intersection(q['region'].split('/'))]
 regions.append({'region':region,'query_ids':[q['id'] for q in selected],'requested_domains':sorted({d for q in selected for d in q.get('domains',[])}),'status':'no_new_attributed_independent_region_source_in_received_results','limits':'Combined search outputs are bounded; private groups, logins and full national internet not covered.'})
qa=[]
for row in rows:
 b=(ROOT/row['body_path']).read_bytes();assert row['complete'] and len(b)==row['bytes'] and hashlib.sha256(b).hexdigest()==row['sha256']
 qa.append({'id':row['id'],'url':row['url'],'status':row['status'],'bytes':len(b),'sha256':row['sha256'],'complete':True,'length_matches':True,'sha256_matches':True})
summary={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'submitted_web_query_shapes':len(queries),'batches':len(batches),'empty_batches':sum(x['status']=='empty_batch' for x in batches),'batch_errors_or_unknown':sum(x['status']=='tool_error_or_unknown' for x in batches),'literal_query_repeats_in_read_baseline':sum(q['literal_seen_before'] for q in novelty['queries']),'primary_get_count':len(rows),'http_status_counts':{str(x):sum(r['status']==x for r in rows) for x in sorted({r['status'] for r in rows})},'new_independent_regional_review_or_discussion_confirmed':False,'new_foreign_runtime_adoption_confirmed':False,'github_CORE_calls':0,'consent_actions':0,'regional_coverage':regions,'baseline':['artifacts/external-social-regional-2026-11-09/europe-cis/report.ru.md','artifacts/external-social-regional-deeper-2026-11-09/regions/report.ru.md','artifacts/external-links-2026-11-10/regions/report.ru.md','artifacts/external-links-2026-11-10/social/report.ru.md','artifacts/external-links-2026-11-10/review.ru.md','artifacts/external-links-deeper-2026-11-10/report.ru.md','artifacts/external-components-2026-11-10/products/summary.md'],'limits':['No Habr consent banner action. Only ordinary public RSS GET.','No messages, publications, login, account changes, payments, packages, GitHub API or foreign-code execution.','No national/global absence conclusion; exact record counts belong only to received native responses.']}
(ROOT/'findings.json').write_text(json.dumps({'summary':summary,'findings':findings},ensure_ascii=False,indent=2)+'\n')
(ROOT/'capture-integrity.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n')
(ROOT/'verification.json').write_text(json.dumps({'primary_capture_count':len(qa),'all_complete':all(r['complete'] for r in qa),'all_lengths_and_sha256_match':all(r['length_matches'] and r['sha256_matches'] for r in qa),'habr_valid_rss':rss.tag=='rss','habr_item_count':len(items),'radyz_exact_keyword_records':0,'italian_received_HTML_exact_marker_count':sum(italian_markers.values()),'trending_received_HTML_exact_marker_or_title_count':sum(trending_markers.values()),'source_records':qa},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
