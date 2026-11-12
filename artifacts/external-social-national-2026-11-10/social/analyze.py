# -*- coding: utf-8 -*-
"""Offline social evidence attribution and identity-based reply deltas."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import html as htmlmod
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT / "artifacts/external-signals-2026-11-09/audience/raw"
rows = [r for filename in ["native-initial-index.json", "native-followup-index.json", "native-new-article-index.json"]
        for r in json.loads((HERE / filename).read_text())]
bykey = {r["key"]: r for r in rows}


def body(key):
    return (HERE / bykey[key]["body_file"]).read_text()


def data(key):
    return json.loads(body(key))


def evidence(key):
    return bykey[key]


def save(name, obj):
    (HERE / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)

    def handle_data(self, text):
        if not self.skip:
            self.parts.append(text)


queries = []
for p in sorted(HERE.glob("search-*.json")):
    d = json.loads(p.read_text())
    for q in d["args"]["search_query"]:
        ident = len(queries) + 1
        queries.append({"id": ident, "query": q, "response_file": p.name,
                        "role": "index_control_not_independent_social_evidence" if ident in {27,28} else "targeted_social_or_community_search",
                        "batch_error": d["result"].get("isError", False), "batch_empty": "Empty search results" in str(d["result"]),
                        "limit": "Combined response does not establish exhaustive per-query execution; platform non-indexing and search broadening remain possible."})
save("query-index.json", queries)


def hn_comments(node):
    if node.get("type") == "comment":
        yield node
    for child in node.get("children", []):
        yield from hn_comments(child)


hn_prior_path = ROOT / "artifacts/external-social-regional-2026-11-09/social/raw/hn-item.raw"
hn_old = {x["id"]: x for x in hn_comments(json.loads(hn_prior_path.read_text()))}
hn_new = {x["id"]: x for x in hn_comments(data("hn-known-thread"))}
hn_delta = {"thread": "https://news.ycombinator.com/item?id=50193565", "baseline": str(hn_prior_path.relative_to(ROOT)),
            "current_evidence": evidence("hn-known-thread"), "baseline_comment_ids": sorted(hn_old), "current_comment_ids": sorted(hn_new),
            "new_comment_ids": sorted(set(hn_new)-set(hn_old)), "removed_comment_ids": sorted(set(hn_old)-set(hn_new)),
            "comments": [{"id": x["id"], "author": x["author"], "created_at": x["created_at"], "url": "https://news.ycombinator.com/item?id="+str(x["id"]),
                          "ownership": "owner_account" if x["author"] == "alex_artamokhov" else "external_account_not_verified_person_or_customer"} for x in hn_new.values()]}
save("hn-thread-delta.json", hn_delta)


def bsky_walk(node):
    if not isinstance(node, dict):
        return
    if isinstance(node.get("post"), dict) and node["post"].get("uri"):
        yield node["post"]
    for child in node.get("replies", []):
        yield from bsky_walk(child)


own_did = "did:plc:u63726gke7rdfrsrtuz3hqzd"
old_feed = json.loads((BASE / "bsky-feed.raw").read_text())
new_feed = data("bsky-author-feed")
old_uris = {x["post"]["uri"] for x in old_feed["feed"]}
new_uris = {x["post"]["uri"] for x in new_feed["feed"]}
bsky = {"feed_evidence": evidence("bsky-author-feed"), "baseline_feed": str((BASE/"bsky-feed.raw").relative_to(ROOT)),
        "baseline_post_uris": sorted(old_uris), "current_post_uris": sorted(new_uris),
        "added_post_uris": sorted(new_uris-old_uris), "absent_from_current_feed_uris": sorted(old_uris-new_uris),
        "current_cursor": new_feed.get("cursor"), "selected_threads": []}
for component, rkey in [("Metis","3mqhdmkivr22l"), ("GAIA","3mrujtbjd3s2u"), ("Hub","3mvlenuwosk2a"), ("ARGUS","3mpwbmfa2ds2j")]:
    key = "bsky-thread-" + component.lower()
    old_path = BASE / ("bsky-thread-"+rkey+".raw")
    old = {x["uri"]:x for x in bsky_walk(json.loads(old_path.read_text()).get("thread")) if not x["uri"].endswith("/"+rkey)}
    new = {x["uri"]:x for x in bsky_walk(data(key).get("thread")) if not x["uri"].endswith("/"+rkey)}
    bsky["selected_threads"].append({"component": component, "source_url": "https://bsky.app/profile/alexar76.bsky.social/post/"+rkey,
        "baseline": str(old_path.relative_to(ROOT)), "current_evidence": evidence(key),
        "baseline_reply_uris": sorted(old), "current_reply_uris": sorted(new),
        "new_reply_uris": sorted(set(new)-set(old)), "removed_reply_uris": sorted(set(old)-set(new)),
        "new_external_reply_uris": [u for u in set(new)-set(old) if new[u]["author"]["did"] != own_did],
        "replies": [{"uri":u,"author_did":x["author"]["did"],"author_handle":x["author"]["handle"],"created_at":x["record"]["createdAt"],
                     "is_owner":x["author"]["did"]==own_did} for u,x in new.items()],
        "limit": "Four selected complete returned trees, depth10; other public/quote/private conversations not comprehensively re-read."})
save("bsky-reply-delta.json", bsky)


def dev_flat(items):
    for x in items:
        yield x
        yield from dev_flat(x.get("children", []))


articles = data("dev-own-articles")
old_articles = json.loads((BASE / "devto-articles.raw").read_text())
article_map = {a["id"]: a for a in articles}
old_article_map = {a["id"]: a for a in old_articles}
dev = {"metadata_evidence": evidence("dev-own-articles"), "baseline_metadata": str((BASE/"devto-articles.raw").relative_to(ROOT)),
       "baseline_article_ids": sorted(old_article_map), "current_article_ids": sorted(article_map),
       "new_own_articles": [{"id": a["id"], "url":a["url"], "published_at":a["published_at"], "author":a["user"]["username"]}
                            for aid,a in article_map.items() if aid not in old_article_map], "selected_threads": []}
for key, aid in [("marketplace",4951998), ("x402",4804987), ("multica",4980592), ("metis",4125941), ("new-firewall",4993722), ("new-ard",4993724)]:
    old_path = BASE / ("devto-comments-"+str(aid)+".raw")
    current = {x["id_code"]:x for x in dev_flat(data("dev-comments-"+key))}
    prior_available = old_path.exists()
    old = {x["id_code"]:x for x in dev_flat(json.loads(old_path.read_text()))} if prior_available else None
    new_ids = sorted(set(current)-set(old)) if old is not None else None
    dev["selected_threads"].append({"article_id":aid, "article_url":article_map[aid]["url"], "evidence":evidence("dev-comments-"+key),
        "baseline_reply_id_snapshot_available":prior_available, "baseline_file":str(old_path.relative_to(ROOT)) if prior_available else None,
        "baseline_comment_ids":sorted(old) if old is not None else None, "current_comment_ids":sorted(current),
        "new_comment_ids":new_ids, "removed_comment_ids":sorted(set(old)-set(current)) if old is not None else None,
        "new_external_comment_ids":[u for u in new_ids if current[u]["user"]["username"].lower()!='alexar76'] if new_ids is not None else None,
        "current_external_comments":[{"id":u,"author":x['user']['username'],"created_at":x['created_at'],"url":article_map[aid]['url']+'#comment-'+u}
                                     for u,x in current.items() if x['user']['username'].lower()!='alexar76'],
        "limit":"ID-based delta only where prior reply snapshot exists; no metadata-counter substitution for missing baseline."})
save("dev-comment-delta.json", dev)

tg_body = body("telegram-own-channel")
old_tg_body = (BASE / "telegram-channel.raw").read_text()
tg_ids = list(dict.fromkeys(re.findall(r'data-post="([^"]+)"', tg_body)))
old_tg_ids = list(dict.fromkeys(re.findall(r'data-post="([^"]+)"', old_tg_body)))
tg_new = [u for u in tg_ids if u not in old_tg_ids]
tg = {"evidence": evidence("telegram-own-channel"), "baseline":str((BASE/"telegram-channel.raw").relative_to(ROOT)),
      "baseline_visible_post_ids":old_tg_ids, "current_visible_post_ids":tg_ids, "new_visible_own_post_ids":tg_new,
      "absent_from_visible_window_not_proven_deleted":[u for u in old_tg_ids if u not in tg_ids],
      "new_posts":[], "public_discussion_markup_present":"tgme_widget_message_discussion" in tg_body,
      "classification":"owner_controlled_broadcast_distribution_not_reader_replies", "limit":"Twenty visible posts; older window entries absent are not deletions. No closed discussion-group/login view read."}
for ident in tg_new:
    fragment = tg_body.split('data-post="'+ident+'"',1)[1].split('data-post="',1)[0]
    dates = re.findall(r'<time[^>]+datetime="([^"]+)"',fragment)
    tg['new_posts'].append({'post_id':ident,'url':'https://t.me/'+ident,'published_at':dates[0] if dates else None})
save("telegram-own-distribution.json", tg)

quincy = data("quincygb-outside-article")
qcomments = list(dev_flat(data("quincygb-outside-comments")))
qrecords = []
for x in qcomments:
    txt = re.sub('<[^>]+>',' ',htmlmod.unescape(x['body_html']))
    markers = re.findall(r'(?i)alexar76|modelmarket\.dev|attestedmemory\.net|\bAIMarket\b|PingBlip|\bHISTOR\b|\bWARDEN\b|aimarket-metis|@aimarket/',txt)
    assert not markers
    qrecords.append({'id':x['id_code'],'author':x['user']['username'],'created_at':x['created_at'],
                     'url':quincy['url']+'#comment-'+x['id_code'],'exact_ecosystem_marker_matches':markers,
                     'classification':'historical_reader_comment_about_Quincys_bug_not_attributed_product_feedback_for_our_ecosystem'})
novelty = {}
for token in [quincy['url']] + [x['id'] for x in qrecords]:
    r = subprocess.run(['rg','-l','-F',token,'docs','artifacts','-g','*.md','-g','*.json','-g','*.raw','-g','*.txt',
                        '-g','!artifacts/external-social-national-2026-11-10/**'],cwd=ROOT,capture_output=True,text=True)
    novelty[token]={'prior_matches':r.stdout.splitlines()[:20],'rg_exit':r.returncode,
                    'scope':'Prior docs/artifacts selected text formats; whole current social/national pass excluded.'}
save('novelty-check.json',novelty)
outside = {'article_url':quincy['url'],'author':quincy['user']['username'],'published_at':quincy['published_at'],
           'article_evidence':evidence('quincygb-outside-article'),'comments_evidence':evidence('quincygb-outside-comments'),
           'article_classification':'known_foreign_operator_post_mentions_AIMarket_outreach_not_new_adoption',
           'article_novelty':'Known Oct29 article capture; reconfirmed, not newly published.',
           'reader_comments':qrecords,'reader_comment_novelty':'IDs absent in checked prior baseline, but both events Oct25 and neither body names our ecosystem.',
           'scope':'Two newly documented primary comment reads, not two new AICOM mentions/reviews/users.'}
save('quincy-outside-discussion.json',outside)

hn_searches = [{'evidence':evidence(k),'query':data(k).get('query'),'hits':data(k).get('nbHits'),
                'scope':'Exact quoted package/domain query over public HN index; not all brands or unindexed discussions.'}
               for k in bykey if k.startswith('hn-search-')]
mastodon = [{'evidence':evidence(k),'statuses_returned':len(data(k).get('statuses',[])),
             'scope':'One public instance search; not all fediverse/remote/private posts.'}
            for k in ['mastodon-attested','mastodon-metis']]
lob = Text();lob.feed(body('lobsters-domain'))
lob_text = ' '.join(' '.join(lob.parts).split())

integrity=[]
for r in rows:
    b=(HERE/r['body_file']).read_bytes()
    integrity.append({'key':r['key'],'bytes_match':len(b)==r['bytes'],'sha256_match':hashlib.sha256(b).hexdigest()==r['sha256']})
assert all(x['bytes_match'] and x['sha256_match'] for x in integrity)
save('capture-integrity.json',integrity)

findings = {'date_client':'2026-11-10','generated_at_utc':datetime.now(timezone.utc).isoformat(),
 'baseline':['artifacts/external-social-regional-2026-11-09/social/report.ru.md','artifacts/external-social-regional-deeper-2026-11-09/social/report.ru.md',
             'artifacts/external-links-2026-11-10/social/report.ru.md','artifacts/external-links-deeper-2026-11-10/reviews/summary.md',
             'artifacts/external-components-2026-11-10/products/summary.md'],
 'counts':{'web_query_strings':len(queries),'platform_targeted_queries':sum(x['role']=='targeted_social_or_community_search' for x in queries),
           'index_controls':2,'web_batches':8,'native_or_primary_GETs':len(rows),'http_statuses':dict(Counter(str(r['status']) for r in rows)),
           'new_attributed_independent_social_posts':0,'new_confirmed_reviews':0,'new_confirmed_adoptions':0,
           'hn_new_comment_ids':len(hn_delta['new_comment_ids']),
           'bsky_new_external_reply_uris_in_four_threads':sum(len(x['new_external_reply_uris']) for x in bsky['selected_threads']),
           'dev_new_external_comment_ids_in_two_ID_baselines':sum(len(x['new_external_comment_ids'] or []) for x in dev['selected_threads'] if x['baseline_reply_id_snapshot_available']),
           'new_own_DEV_articles':len(dev['new_own_articles']),'new_visible_own_Telegram_posts':len(tg_new),
           'newly_primary_read_historical_outside_reader_comments_not_attributed_to_us':len(qrecords)},
 'identity_rule':'Exact namespace/domain/repository/product in context; homonyms and incidental history/Bitwarden matches excluded. Accounts are not verified people, customers or independent owners.',
 'coverage':{'X_Twitter':'Targeted indexed search only; no login/native account search. No new attributable outside result in returned sample.',
             'LinkedIn':'Indexed posts/profile search with product markers; no authenticated feed or private comments.',
             'Reddit':{'evidence':evidence('reddit-attested'),'status':'403 unread; not zero mentions'},
             'Bluesky':{'search_evidence':evidence('bsky-search-attested'),'search_status':'403 unread','feed_and_reply_delta':'bsky-reply-delta.json'},
             'Mastodon':mastodon,'HN':{'searches':hn_searches,'known_thread_delta':'hn-thread-delta.json'},
             'Lobsters':{'evidence':evidence('lobsters-domain'),'visible_result':'0 stories for selected domain query; page says punctuation stripped','scope':'Search stories only, not all comments'},
             'Telegram':{'native_own_channel':'telegram-own-distribution.json','other_channel_indexes':'Queries29/30 cover t.me/s,TGStat,Telemetr; no new attributable result in returned combined response.'},
             'YouTube':'Targeted indexed external-author searches only; no logged-in comments/Analytics or new audience metrics.',
             'DEV':{'own_thread_deltas':'dev-comment-delta.json','known_foreign_post':'quincy-outside-discussion.json'},
             'Hashnode_HackerNoon':'Exact product/domain query31; no new attributable publication in returned response. Own blogs/copies are not independent reviews.'},
 'known_external_contact':{'HN':{'comment_id':50205750,'author':'ITAltitudes','created_at':'2026-10-23T07:55:37Z','url':'https://news.ycombinator.com/item?id=50205750',
                               'classification':'known_external_technical_question_about_polling','novelty':'unchanged IDs/content context; not a new November reply'},
                          'DEV':'Known Marketplace/Textokit/AgentEmbassy discussions retained; selected ID snapshots unchanged, no global claim for all76 articles.'},
 'outside_historical_comments':outside,
 'own_distribution':{'DEV_new_articles':dev['new_own_articles'],'Telegram_new_visible_posts':tg['new_posts'],'Bluesky_added_own_post_uris':bsky['added_post_uris'],
                     'scope':'Own publishing and broadcast IDs, not independent responses or user acquisition.'},
 'search_limit':'Seven targeted combined batches empty; control/known-contact batch returned old catalog and Quincy sources. Search success/empty is not exhaustive platform coverage.',
 'limits':['All32 queries and26 GET are bounded public research, not the whole internet or closed groups.',
           'Comment deltas use IDs/URIs. Metadata counters are not substituted where prior reply snapshots are absent.',
           'Four selected Bluesky trees and six own DEV threads read; all remaining lifetime discussions not re-read.',
           'Bluesky search/Reddit403 left unknown; no bypass, login, consent or CAPTCHA execution.',
           'Telegram older posts leave a20post window; absence from this page is not deletion.',
           'Two newly read Quincy comments have no exact project identity and are excluded from direct ecosystem feedback.'],
 'external_writes':False,'github_writes':False,'github_CORE_requests':0,'messages':False,'logins':False,'payments_or_tools_call':False,'foreign_code_execution':False,
 'capture_integrity':'capture-integrity.json'}
save('findings.json',findings)
print(json.dumps(findings['counts'],ensure_ascii=False))
