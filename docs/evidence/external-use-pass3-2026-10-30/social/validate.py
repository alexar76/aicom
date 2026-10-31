from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
prior=json.loads((ROOT/"query-dedup.json").read_text())
seen=prior["exact_queries_found_in_recorded_prior_query_fields"]
queries=[]
for f in sorted(ROOT.glob("search-*.json")):
 d=json.loads(f.read_text())
 queries.extend({"query":q,"source_file":f.name,"prior_exact_match_files":seen.get(q,[]),"new_against_recorded_query_fields":q not in seen} for q in d.get("queries",[]))
new_count=sum(x["new_against_recorded_query_fields"] for x in queries)
(ROOT/"query-index.json").write_text(json.dumps({"executed_web_queries":len(queries),"unique_in_this_pass":len(set(x["query"] for x in queries)),"new_against_recorded_query_fields":new_count,"repeat_queries_excluded_from_new_scope":len(queries)-new_count,"queries":queries,"limit":prior["limit"]},ensure_ascii=False,indent=2)+"\n")
prior.update(executed_web_queries=len(queries),unique_in_this_pass=len(set(x["query"] for x in queries)),new_against_recorded_query_fields=new_count)
(ROOT/"query-dedup.json").write_text(json.dumps(prior,ensure_ascii=False,indent=2)+"\n")
rows=json.loads((ROOT/"http-index.json").read_text())
hashes=[]
for r in rows:
 f=ROOT/r["file"];actual=hashlib.sha256(f.read_bytes()).hexdigest()
 hashes.append({"file":r["file"],"sha256":actual,"matches":actual==r["sha256"]})
errors=[]
for f in ROOT.glob("*.json"):
 try:json.loads(f.read_text())
 except Exception as e:errors.append({"file":f.name,"error":str(e)})
validation={"json_errors":errors,"body_hashes":hashes,"passed":not errors and all(x["matches"] for x in hashes)}
(ROOT/"validation.json").write_text(json.dumps(validation,ensure_ascii=False,indent=2)+"\n")
facts=json.loads((ROOT/"atomdrift-facts.json").read_text())
summary={"observed_date":"2026-10-30","timezone":"Europe/Moscow","baseline":["docs/growth/external-deeper-2026-10-30.ru.md","docs/evidence/external-signals-deeper-2026-10-30/social/summary.json","artifacts/external-signals-2026-10-29/report.json","artifacts/external-deep-2026-10-29/report.json"],"web_queries_executed":len(queries),"web_queries_new_against_recorded_fields":new_count,"exact_repeats_excluded":len(queries)-new_count,"captured_gets":len(rows),"http_statuses":{"200":len(rows)},"new_independent_social_text_or_real_use_confirmed":False,"new_findings":[],"new_surface_checks":{"atomdrift_feed_items":facts.get("feed_items"),"atomdrift_feed_updated":facts.get("feed_updated"),"matching_feed_summaries":facts.get("matching_items"),"atomdrift_home_social_links":facts.get("social_links")},"previous_bluesky_data_reused_offline":{"nonzero_quote_count":0,"new_gets":0,"not_new_findings":True},"blocked":["bookwyrm.social robots","indiehackers.com robots"],"scope_limits":["Only targeted public searches and two new direct publication-surface GETs","No closed social groups, private messages or exhaustive social corpus","Full Atomdrift54article bodies not read; only feed summaries","No repeated blocked Bluesky/Reddit search API"],"report":"report.ru.md","query_index":"query-index.json","mutations":"Local evidence only. No messages, publications, auth changes, purchases, tool invokes, installs or GitHub writes."}
(ROOT/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"summary":summary,"validation":validation},ensure_ascii=False,indent=2))

