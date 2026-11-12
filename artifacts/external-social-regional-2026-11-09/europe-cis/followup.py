from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
from fetch import get
ROOT=Path(__file__).parent
TASKS={
 'radyz-native-domain':'https://radyz.cz/wp-json/wp/v2/search?search=modelmarket.dev&per_page=20',
 'radyz-native-identity':'https://radyz.cz/wp-json/wp/v2/search?search=alexar76&per_page=20',
 'radyz-known-post':'https://radyz.cz/wp-json/wp/v2/posts/11796',
 'radyz-known-comments':'https://radyz.cz/wp-json/wp/v2/comments?post=11796&per_page=100',
}
if __name__=='__main__':
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(get,TASKS.items()))
 (ROOT/'followup-index.json').write_text(json.dumps(rows,indent=2)+'\n');print(json.dumps(rows,indent=2))
