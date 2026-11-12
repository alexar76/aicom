"""Build an evidence index and bounded audit findings from captured public bytes."""
from pathlib import Path
from hashlib import sha256
from datetime import datetime, timezone
from html.parser import HTMLParser
import json, re

P=Path(__file__).resolve().parent
B=P.parents[1]/'external-signals-2026-11-09'/'code'
indexes=['http-index.json','extra-http-index.json','v1-http-index.json','hf-http-index.json','hf-row-http-index.json']
rows=[r for name in indexes for r in json.loads((P/name).read_text())]
by={r['key']:r for r in rows}
checks=[]
for r in rows:
 b=(P/r['body_file']).read_bytes() if r.get('body_file') else b''
 checks.append({'key':r['key'],'status':r.get('status'),'bytes_match':len(b)==r.get('bytes'),'sha256_match':sha256(b).hexdigest()==r.get('sha256'),'truncated':r.get('truncated')})

def load(name):return json.loads((P/(name+'.raw')).read_text())
acs=load('acs-comments');oldacs=json.loads((B/'acs38-comments.raw').read_text())
newacs=[c for c in acs if c['id'] not in {c['id'] for c in oldacs}]
fixture=load('crawlcheck-fixture')['baseline_cases'][0]['lock']['jcs_v1']['extras_sha256']
record=load('histor-crawlcheck')['servers'][0]
main=lambda s:re.search(r'<main\b.*?</main>',s,re.S).group()
comparison={
 'acs_saved_count_9nov':len(oldacs),'acs_saved_count_10nov':len(acs),
 'acs_new_comments':[{'id':c['id'],'author':c['user']['login'],'created_at':c['created_at'],'url':c['html_url']} for c in newacs],
 'rugsnare_readme_same_bytes_as_9nov':(P/'rugsnare-readme.raw').read_bytes()==(B/'rugsnare-readme.raw').read_bytes(),
 'crawlcheck_fixture_same_bytes_as_9nov':(P/'crawlcheck-fixture.raw').read_bytes()==(B/'crawlcheck-vectors.raw').read_bytes(),
 'crawlcheck_spec_main_same_as_9nov':main((P/'crawlcheck-spec.raw').read_text())==main((B/'crawlcheck-spec.raw').read_text()),
 'fixture_extras_digest':fixture,'histor_extras_digest':record['toolExtrasDigest'],
 'fixture_matches_current_histor_extras':fixture==record['toolExtrasDigest'],
 'histor_record_lastObserved':record['lastObserved'],
 'hf_changes_returned_rows':len(load('hf-changes-one-row').get('rows',[])),
 'hf_changes_truncated_cells':load('hf-changes-one-row')['rows'][0]['truncated_cells'],
 'hf_page_DatasetGenerationError_occurrences':(P/'hf-dataset-page.raw').read_text().count('DatasetGenerationError'),
}
F=[]
def finding(id,source_key,source_url,component,classification,ownership,delta,observation,targets=None,dates=None,confidence='high',extra_evidence=None):
 r=by[source_key]
 F.append({'id':id,'component':component,'source_url':source_url,'source_capture_key':source_key,'source_http_status':r['status'],'checked_at_utc':r['retrieved_at_utc'],'classification':classification,'ownership':ownership,'confidence':confidence,'delta_vs_fresh_baseline':delta,'observation_ru':observation,'targets':targets or [],'event_dates':dates or [],'evidence_files':[r['body_file']]+(extra_evidence or [])})

finding('T01','acs-comments','https://github.com/GenAI-Security-Project/agent-control-standard/issues/38#issuecomment-6757834108','HISTOR MTL/1','external_technical_reply','third_party_account_kenneives','new_comment_after_9nov','kenneives исправил своё прежнее описание MTL/1: по его сообщению MTL/1 1.1 одинаково обрабатывает дроби и целые >2^53 с профилем AgentAvow; остаются 1e400 и отсутствующий description. Это признание технической поправки, не принятие стандарта, dependency или новый backlink.',[{'kind':'mention_reply','target':'alexar76 / HISTOR MTL/1 1.1','html_backlink':False}],['2026-11-10T03:07:41Z'])
finding('T02','hf-dataset-page','https://huggingface.co/datasets/alexar76/histor-mcp-tool-definitions','HISTOR dataset','self_published_external_platform','alexar76_on_huggingface','previous_viewer_error_not_reproduced','В HTML отсутствует прежняя DatasetGenerationError. is-valid показывает viewer=true; splits перечисляет восемь configs с failed=[] и pending=[]. Чтение changes/train offset=0 length=1 вернуло HTTP200 и одну строку без truncated cells. Полный датасет и все строки не проверены; HTML по-прежнему помечает viewer-partial.',[{'kind':'html_href','target':'https://histor.modelmarket.dev','html_backlink':True},{'kind':'html_href','target':'https://github.com/alexar76/histor','html_backlink':True}],extra_evidence=['hf-viewer-is-valid.raw','hf-viewer-splits.raw','hf-changes-one-row.raw'])
finding('T03','histor-house-page','https://theagentforge.io/t/github.com%2Falexar76%2Fhistor','HISTOR','external_automated_handshake','third_party_house_tester','new_current_version_since_saved_9nov_api','Текущая первичная page JSON содержит house-tester для 0.6.1 от 9 ноября и прежний 0.5.2. У нового отчёта taskCategory=mcp-handshake, ownerHouse=true, один owner, corroborated=false, verdict=insufficient. Это обновлённый автоматический тест одного оператора; поисковый снимок всё ещё показывает 0.5.2.',[{'kind':'identifier','target':'github.com/alexar76/histor','html_backlink':False}],['2026-11-09T07:04:13.251Z'],extra_evidence=['histor-house-check.raw'])
finding('T04','crawlcheck-spec','https://crawlcheck.io/spec/mcp-lockfile#jcs-v1','HISTOR extras digest','external_format_compatibility','third_party_crawlcheck','reconfirmed_existing_case','Основной текст спецификации и fixture не изменились с 9 ноября. Extras fixture буквально равен текущему toolExtrasDigest HISTOR для CrawlCheck. На этой странице нет href на наш домен; совместимость и влияние подтверждены прежним внешним ответом, а не новой ссылкой.',[{'kind':'compatible_value','target':'HISTOR toolExtrasDigest','html_backlink':False}],['2026-11-07'],extra_evidence=['crawlcheck-fixture.raw','histor-crawlcheck.raw','registry-comments.raw','owasp-comments.raw'])
finding('T05','rugsnare-readme','https://github.com/Paraphern/rugsnare','HISTOR dataset','external_dataset_citation_and_reported_reuse','third_party_paraphern','same_bytes_as_9nov','README содержит прямую DOI-ссылку и предметный разбор HISTOR: автор сравнивает свой watch corpus с датасетом. README побайтово совпадает со вчерашним. Это известное независимое цитирование/сообщение об использовании данных; runtime-интеграция из README не установлена.',[{'kind':'markdown_link','target':'https://doi.org/10.5281/zenodo.23512760','html_backlink':True}],['snapshot 2026-09-24 through 2026-10-20'])
finding('T06','scraperwatch-slash','https://scraperwatch.com/mcp-changes/','HISTOR','external_comparison_backlink','third_party_scraperwatch','reconfirmed_historical_comparison','Раздел Outside check сохраняет точный HTML href на HISTOR и сопоставление записей за 31 октября/1 ноября. Ниже опубликована поправка robots parser 2 ноября, и издатель предупреждает, что прежние counts до удаления. Без завершающего слеша source GET вернул 308; адрес со слешем 200.',[{'kind':'html_href','target':'https://histor.modelmarket.dev','html_backlink':True}],['2026-11-01','2026-11-02'])
finding('T07','agentavow-v1-readme','https://github.com/AgentAvow/AgentAvow/blob/main/docs/standards/tool-manifest-digest-vectors-v1/README.md','HISTOR','promised_link_not_observed','third_party_agentavow','no_added_link_in_checked_readmes','8 ноября kenneives просил разрешения сослаться на независимую сверку. 10 ноября в issue добавлен наш ответ, не новый внешний ответ. В текущих main README и v1 README нет HISTOR/alexar76/modelmarket URL. Обещание не считается уже размещённой ссылкой; весь репозиторий на содержимое не прочитан.',[],['2026-11-08T00:00:33Z','2026-11-10T17:58:32Z'],extra_evidence=['agentavow-readme.raw','agentavow-comments.raw'])
finding('T08','canopii-histor','https://index.canopii.dev/server/io.github.alexar76/histor','HISTOR','external_automated_catalog_backlink','third_party_canopii','first_primary_capture_of_prior_search_candidate','Карточка доступна и содержит точный HTML href к репозиторию HISTOR. URL уже был в поисковых материалах 9 ноября; первым обнаружением его не объявляем. Версия 0.6.1 и собственный детерминированный score каталога не доказывают использование tools/call или безопасность.',[{'kind':'html_href','target':'https://github.com/alexar76/histor','html_backlink':True}],['structured datePublished 2026-10-31T11:26:30.208Z','structured dateModified 2026-11-05T06:49:52.767Z'])
finding('T09','mcpwatch-histor','https://mcpwatch-zeta.vercel.app/servers/io.github.alexar76__histor/','HISTOR','search_candidate_unavailable','third_party_mcpwatch','direct_get_404','Поисковый кандидат при прямом чтении ответил HTTP404. Это отказ данной внешней карточки в одном срезе; доступность самого HISTOR из него не выводится.')
finding('T10','openalex','https://openalex.org/W7223029314','HISTOR dataset','metadata_indexing','third_party_index_of_author_deposit','zero_indexed_citations_reconfirmed','OpenAlex возвращает cited_by_count=0 для concept DOI, связанного с HISTOR. Нулевой счётчик этой записи не исключает GitHub README и другие неиндексированные цитирования.',[{'kind':'api_metadata_url','target':'https://doi.org/10.5281/zenodo.23512759','html_backlink':False}])
finding('T11','pr14','https://github.com/basitalisandhu/agent-skills-state-2026/pull/14','HISTOR','own_submission_unmerged','alexar76_submission_on_external_repo','unchanged_open','PR14 остаётся open, merged=false; updated_at по-прежнему 28 октября. Текущий main README не содержит HISTOR или alexar76. Это наше непринятое предложение, не принятая внешняя ссылка.',[],['2026-10-28T09:48:32Z'],extra_evidence=['skills-readme.raw'])
finding('T12','heldfast-readme','https://github.com/rufat325/heldfast','HISTOR','outbound_relation_only_in_checked_file','third_party_heldfast','no_histor_reference_in_checked_readme','В прочитанном полном README heldfast нет HISTOR, alexar76 или нашего URL. Наше сопоставление с heldfast не превращается автоматически во входящую ссылку от heldfast. Отсутствие по всему репозиторию/сайту не заявляется.')

doc={'written_at_utc':datetime.now(timezone.utc).isoformat(),'scope_ru':'Технические входящие ссылки и независимые упоминания HISTOR/WARDEN; дельта к 9 ноября и утреннему срезу 10 ноября.','read_only':True,'public_get_count':len(rows),'http_status_counts':{str(k):sum(r.get('status')==k for r in rows) for k in sorted({r.get('status') for r in rows})},'web_search_query_count':16,'web_open_count':3,'findings':F,'comparison':comparison,'limits_ru':['Публичные аккаунты третьих сторон не являются доказательством человеческой личности или коммерческой независимости.','Произвольный интернет, закрытые репозитории/аналитика, полный GitHub code search и production-исполнение чужого кода не охвачены.','Перепечатки, автокаталоги, авторские submissions, независимый технический ответ и использование пакета различаются.','Downloads HF=295 на момент API-чтения — платформенный счётчик в окне, не 295 независимых пользователей; метрики каталогов не считаются собственной телеметрией.','Не отправлялись сообщения, GitHub writes, платежи, tools/call; чужие пакеты не устанавливались.']}
(P/'findings.json').write_text(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
verification={'captures':checks,'comparison':comparison,'all_capture_hashes_and_lengths_match':all(c['bytes_match'] and c['sha256_match'] and not c['truncated'] for c in checks)}
(P/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'captures':len(rows),'http_status_counts':doc['http_status_counts'],'verification_ok':verification['all_capture_hashes_and_lengths_match'],'comparison':comparison},ensure_ascii=False,indent=2))
