from bs4 import BeautifulSoup
import pathlib,json,re,datetime,decimal
root=pathlib.Path(__file__).parent;token='0x833589fcd6edb6e08f4c7c32d4f71b54bda02913';W='0x1218ff36c5d2e3b6a565cdb1a8b1accfc606ad0a';P='0x77065d81e18ad403bcd6e9a0616b288e16744121';pages={};index=json.loads((root/'explorer-http-index.json').read_text());end=min(datetime.datetime.fromisoformat(x['checked_at_utc'])for x in index);start=end-datetime.timedelta(days=7)
for tag in ['payout','agent402']:
 p=root/'raw'/(tag+'-basescan.html');s=BeautifulSoup(p.read_text(),'html.parser');rows=[];ignored=0
 for tr in s.select('table tbody tr'):
  tx=tr.select_one('a[href^="/tx/"]');blk=tr.select_one('a[href^="/block/"]');tk=tr.select_one('a[href^="/token/"]');amount=tr.select_one('.td_showAmount');date=tr.select_one('.showLocalDate');addresses=tr.select('[data-full-address]');tds=tr.find_all('td',recursive=False)
  if not all([tx,blk,tk,amount,date]) or len(tds)<13:continue
  def addr(td):
   x=td.select_one('[data-full-address]') or td.select_one('[data-clipboard-text^="0x"]')
   if x:return x.get('data-full-address',x.get('data-clipboard-text'))
   x=td.select_one('a[href^="/address/"]')
   return x['href'].split('/address/',1)[1].split('#',1)[0] if x else None
  from_a,to_a=addr(tds[8]),addr(tds[10])
  if not from_a or not to_a:continue
  contract=tk['href'].split('/token/',1)[1].split('?',1)[0].lower()
  if contract!=token:ignored+=1;continue
  stamp=int(date.get_text(strip=True));dt=datetime.datetime.fromtimestamp(stamp,datetime.timezone.utc);v=decimal.Decimal(amount.get('title',amount.get_text(strip=True)).split('|',1)[0].strip().replace(',',''))
  rows.append({'tx':tx['href'].split('/tx/',1)[1],'block':int(blk.get_text()),'timestamp_utc':dt.isoformat(),'timestamp_unix':stamp,'from':from_a,'to':to_a,'value_usdc':str(v),'value_atomic':str(int(v*1000000)),'token':contract})
 pages[tag]={'html_table_rows':len(s.select('table tbody tr')),'ignored_noncanonical_token_rows':ignored,'canonical_usdc_rows':len(rows),'newest':rows[0]['timestamp_utc']if rows else None,'oldest':rows[-1]['timestamp_utc']if rows else None,'rows':rows}
rows=pages['payout']['rows'];window=[x for x in rows if start.timestamp()<=x['timestamp_unix']<=end.timestamp()];incoming=[x for x in window if x['to'].lower()==W];outgoing=[x for x in window if x['from'].lower()==W];pair=[x for x in rows if {x['from'].lower(),x['to'].lower()}=={W,P}];pairwindow=[x for x in pair if start.timestamp()<=x['timestamp_unix']<=end.timestamp()];history=json.loads(pathlib.Path('docs/evidence/agent402-warden-purchase-2026-10-30/buyer-to-agent402-receipt.json').read_text()),json.loads(pathlib.Path('docs/evidence/agent402-warden-purchase-2026-10-30/agent402-to-warden-receipt.json').read_text())
out={'checked_at_utc':end.isoformat(),'requested_rolling_7day_window':{'start_utc':start.isoformat(),'end_utc':end.isoformat()},'scope':'Two successful BaseScan first pages, 50 all-token rows each. URL contractAddress parameter did NOT restrict displayed table; canonical token contract verified locally for every included row. No pagination. Explorer indexed observations, not full RPC logs or call records.','pages':pages,'payout_7day':{'all_usdc_transfer_count':len(window),'incoming_count':len(incoming),'incoming_unique_sender_wallets':sorted(set(x['from'].lower()for x in incoming)),'incoming_usdc':str(sum((decimal.Decimal(x['value_usdc'])for x in incoming),decimal.Decimal(0))),'outgoing_count':len(outgoing),'outgoing_usdc':str(sum((decimal.Decimal(x['value_usdc'])for x in outgoing),decimal.Decimal(0))),'pair_transfers':pairwindow,'rows':window},'pair_transfers_in_payout_page':pair,'historical_receipts':history,'limitations':['Four explorer page GET attempts total:2Blockscout403,2BaseScan200; no pagination requested','Base mainnet RPC returned403; historical receipts independently re-seen in current payout page but not fresh RPC validated','Actual Agent402 scan window and private gross/net ledger are not exposed here; seven days anchored at this retrieval is a comparison, not exact replay of their run','No wallet ownership inferred from transfer events; one transfer does not prove successful capability execution or an organic customer']}
(root/'summary.json').write_text(json.dumps(out,indent=2));print(json.dumps({k:v for k,v in out.items()if k not in ['pages','historical_receipts']},indent=2));print('page scopes',[(k,{x:y for x,y in v.items()if x!='rows'})for k,v in pages.items()])
