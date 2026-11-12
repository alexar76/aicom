"""Build source-to-target link inventory and integrity check from captured bytes."""
import collections, datetime, hashlib, json
from pathlib import Path
from urllib.parse import urljoin,urlparse

ROOT=Path(__file__).resolve().parent
rows=json.loads((ROOT/'verification.json').read_text())+json.loads((ROOT/'verification-followup.json').read_text())+[json.loads((ROOT/'verification-method.json').read_text())]
index={r['id']:r for r in rows}
def ours(u):
    p=urlparse(u);h=(p.hostname or '').lower()
    return h in ('modelmarket.dev','attestedmemory.net','magic-ai-factory.com','independentai.network') or h.endswith(('.modelmarket.dev','.attestedmemory.net')) or (h in ('github.com','raw.githubusercontent.com','huggingface.co') and p.path.startswith(('/alexar76/','/datasets/alexar76/')))

specs=[
('mcpindex-hub','automatic_registry_description_assessment','new_exact_url_primary_confirmed','Карточка Hub имеет прямую nofollow-ссылку на репозиторий. Дата создания карточки не установлена. Публичный verdict API: PARTIAL/REVIEW, description-level, no-conformance; 90/100 относится к отдельному индексу зрелости.'),
('mcpindex-gateway','automatic_registry_description_assessment','new_exact_url_primary_confirmed','Вторая карточка того же домена, с прямой nofollow-ссылкой на aimarket-mcp; две страницы не являются двумя независимыми аудиториями.'),
('mcpbeat-weather','search_only_observer_candidate','new_exact_url_not_primary_confirmed','Поисковая выдача описывает собственный handshake/tools-list мониторинг GAIA. Прямой GET 403, web.open cache miss: текущая страница и её href не подтверждены; датированные показатели не принимаются за наше измерение.'),
('protocolprobe-weather','search_only_observer_candidate','known_search_only','URL уже был в поисковых ответах 9 ноября. Новый GET 403, web.open cache miss; первичное подтверждение страницы в этом проходе отсутствует.'),
('a2aregistry-hub','external_protocol_observer','known_reconfirmed','Карточка A2A Registry доступна, содержит прямые ссылки на endpoint и agent card. История probe включает 10 ноября; сведения об успешных task probes являются заявлениями наблюдателя и здесь не воспроизводились.'),
('tracevero-gateway','automatic_registry_listing','known_reconfirmed','Копирует сведения MCP Registry с точной ссылкой на репозиторий; сама методика страницы предупреждает, что чтения endpoint/репозитория она не выполняет.'),
('lightnow-hub','automatic_registry_listing','catalog_reconfirmed_not_claimed_new','Машинная карточка Hub с README и многими ecosystem href. Каталожная доступность не доказывает применение или независимое техническое ревью.'),
('odel-attested','automatic_catalog_with_observer_claim','known_reconfirmed','Доступны карточка Attested Memory и точные внешние ссылки. Даты Odel относятся к октябрьскому чтению; новое наблюдение сегодня не заявляется.'),
('odel-hub','automatic_catalog_with_observer_claim','known_reconfirmed','Карточка Hub доступна с прямыми ссылками. Скопированные из README кейсы оплаты не становятся независимыми клиентскими свидетельствами.'),
('odel-plugins','automatic_catalog_with_observer_claim','known_reconfirmed','Карточка MCP Packager доступна с точными ссылками на наш repo и документацию; AI risk labels издателя не являются нашим аудитом безопасности.'),
('apis-attested','generated_api_profile','known_reconfirmed','Профиль Attested Memory, созданный 2 ноября из MCP Registry, доступен. Генерированные API contracts/skills не считаются независимыми интеграциями.'),
('glama-weather','external_metadata_observer_and_catalog','known_reconfirmed','GAIA connector имеет ссылки на repo и hosted endpoint. Названия инструментов и собственный рейтинг Glama не устанавливают исполнение платных вызовов.'),
('glama-gateway','automatic_repository_catalog','known_reconfirmed','Карточка aimarket-mcp с прямыми внешними ссылками доступна; это распространение метаданных и документации.'),
('libhunt-gaia','automatic_repository_and_article_aggregation','known_reconfirmed','LibHunt GAIA доступен и ссылается на repo/страницы. Похожие проекты и упоминания в авторских статьях не являются внедрением GAIA.'),
('mcprepository-author','automatic_catalog_author_index','known_reconfirmed','Публичный авторский каталог доступен. Ссылки на наши компоненты сохранены; число карточек не интерпретируется как аудитория.'),
('hlido-passport','external_public_surface_evaluation','known_reconfirmed_historical','Паспорт доступен; исходный обзор датирован 5 августа, срок следующей проверки 5 ноября уже прошёл. Это не новая ноябрьская оценка.'),
('hlido-scorecard','external_public_surface_evaluation_artifact','known_reconfirmed_historical','Публичный scorecard внешнего GitHub аккаунта ссылается на alexar76.github.io/aicom. Датирован августом; реальные клиенты и runtime тесты самим файлом не установлены.'),
('industrial-requirements','external_source_dependency','known_reconfirmed','В текущем requirements по-прежнему точный git pin на alexar76/aimarket-hub@2310569f1e4e50e1062d80725bd69ae313042a69. Это сильный исходниковый сигнал, но не доказательство текущей работающей deployment.'),
('industrial-discovery','external_protocol_peer_unavailable','known_failure_reconfirmed','Прежний Railway discovery вновь возвращает HTTP404; это повторяет 9 ноября. Историческую совместимость октября нельзя выдавать за актуальную доступность.'),
('agent-exec-discovery','external_protocol_peer','known_reconfirmed','Discovery доступен, объявляет 19 tools и точный manifest_url /ai-market/manifest. В нём нет прямой HTML backlink на нас; это протокольная связь.'),
('agent-exec-manifest-advertised','external_signed_manifest_compatibility','known_reconfirmed','Объявленный manifest доступен, 19 tools. Подпись офлайн проверена нашим Hub canonicalizer; изменение description отвергается. Это совместимость снимка под объявленным ключом, без invoke/покупки/аттестации оператора.'),
('bracha-readme','excluded_homonym','known_exclusion_reconfirmed','Полные README и requirements получены. Точных ссылок alexar76/modelmarket.dev и зависимости на наш пакет в этих двух файлах не найдено; используется иной namespace/endpoint. Вывод ограничен прочитанными файлами.'),
('sep163-readme','excluded_homonym','known_exclusion_reconfirmed','Полные README и requirements получены. В них нет точного alexar76/modelmarket.dev; проект относится к Telegram lead/marketing workflow. Не считается нашим adopter.'),
('completeaitraining-gateway','third_party_explanatory_catalog','known_reconfirmed','Карточка AIMarket MCP содержит прямые nofollow ссылки на профиль и repo; известна октябрьскому baseline. Утверждения official/by same team отражают текст каталога, не установленную авторизацию.')]

findings=[];edges=[]
for ident,kind,baseline,note in specs:
    r=index[ident];links=[]
    for item in r.get('ecosystem_href',[]):
        target=urljoin(r['final_url'],item['href'])
        if ours(target) and target not in [x['target_url'] for x in links]:links.append({'target_url':target,'rel':item.get('rel'),'evidence_kind':'html_a_href'})
    if ident=='industrial-requirements':links.append({'target_url':'https://github.com/alexar76/aimarket-hub.git@2310569f1e4e50e1062d80725bd69ae313042a69','evidence_kind':'requirements_git_pin'})
    if ident=='hlido-scorecard':links.append({'target_url':r['json']['agent_url'],'evidence_kind':'json_agent_url'})
    finding={'id':ident,'source_url':r['source_url'],'checked_at_utc':r['retrieved_at_utc'],'source_status':r.get('status'),'classification':kind,'baseline':baseline,'ownership':'external domain or external GitHub account; operator identity/independence not attested','confidence':'medium_search_only' if 'search_only' in kind else 'high_for_bounded_observation','first_publication_at':None,'note_ru':note,'source_targets':links,'evidence_body':r.get('body_path'),'body_sha256':r.get('sha256')}
    findings.append(finding)
    edges.extend({'source_id':ident,'source_url':r['source_url'],**l} for l in links)

qa=[]
for r in rows:
    b=(ROOT/r['body_path']).read_bytes()
    assert len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'] and r['complete']
    qa.append({'id':r['id'],'status':r['status'],'length_matches':True,'sha256_matches':True,'complete':r['complete']})
result={'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'Broad alexar76 ecosystem excluding WARDEN/HISTOR; public search and GET only. Incremental comparison to 2026-11-09 and earlier 2026-11-10 baseline.','search_batches':5,'search_queries':20,'public_get_count':len(rows),'http_statuses':dict(collections.Counter(str(r['status']) for r in rows)),'new_primary_confirmed_exact_urls':['mcpindex-hub','mcpindex-gateway'],'new_search_only_candidate':'mcpbeat-weather','new_runtime_adoption_confirmed':False,'records':findings,'limits':['Search is bounded, not a full backlink index or census.','No user identities, paying customers, package install counts or independent operators inferred from catalog presence.','Two HTTP403 responses and web cache misses are access limits, not absence.','Guessed /ai-market/v2/manifest and /docs/methodology 404 are not broken advertised links; advertised routes were followed and 200.','Initial sandbox DNS failures were an execution-environment restriction; final GETs use permitted network access.']}
(ROOT/'findings.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
(ROOT/'source-target-links.json').write_text(json.dumps(edges,ensure_ascii=False,indent=2)+'\n')
(ROOT/'capture-integrity.json').write_text(json.dumps(qa,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'findings':len(findings),'get_count':len(rows),'status_counts':result['http_statuses'],'direct_html_edges':sum(x['evidence_kind']=='html_a_href' for x in edges),'all_edges':len(edges),'verified_bodies':len(qa)},indent=2))
