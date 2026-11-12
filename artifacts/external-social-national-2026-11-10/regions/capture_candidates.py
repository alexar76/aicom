"""Public regional candidate/native reads; no consent action, auth or GitHub API."""
import importlib.util,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
helper=ROOT.parents[1]/'external-components-2026-11-10/core/capture_public.py'
spec=importlib.util.spec_from_file_location('local_capture',helper);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.ROOT=ROOT
sources={
 'italian-aimarket-faq':'https://ai-market.it/faq',
 'habr-public-rss':'https://habr.com/ru/rss/search/?q=%22modelmarket.dev%22&target_type=posts&order=relevance',
 'radyz-native-aimarket':'https://radyz.cz/wp-json/wp/v2/search?search=AIMarket&per_page=100',
 'agentstacklist-trending':'https://agentstacklist.com/trending/'
}
if __name__=='__main__':
 rows=m.run(sources,'primary-index.json')
 for row in rows:
  summary={k:v for k,v in row.items() if k in ['id','status','bytes','complete','error','content_type']}
  if row.get('status')==200:
   text=(ROOT/row['body_path']).read_text();summary['markers']={v:bool(re.search(re.escape(v),text,re.I)) for v in ['alexar76','modelmarket.dev','attestedmemory.net','PingBlip','aimarket-bridges','SYMMARTYS','HEPHAESTUS','Emberline','Tideline']}
   if row['id']=='habr-public-rss':summary['rss_like']=bool(re.search(r'<rss\b|<feed\b',text,re.I))
   if row['id']=='radyz-native-aimarket':summary['json']=json.loads(text)
  print(json.dumps(summary,ensure_ascii=False))
