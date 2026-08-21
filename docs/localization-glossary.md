# Localization glossary — canonical terms (EN · RU · ES · FR · ZH)

**Purpose.** One canonical rendering per domain term, per language, so translations stay
consistent across the docs, landings and UI. **English is the source of truth**; the other
columns are the agreed target renderings. When translating or reviewing, match this table —
do not invent variants (the audit found *escrow* rendered 6 different ways in one document).

**Scope of the language set.** Docs + UI are localized to **en / ru / es** in full; **fr / zh**
are being rolled out. (The Argus landing ships a wider 25-language set; its short marketing
strings follow this glossary where the terms appear.)

**Rules of thumb**
- **Never translate** code, identifiers, CLI, env vars, URLs, and product/brand names
  (`ARGUS`, `WARDEN`, `AI-Factory`, `Hub`, `Mesh`, `Metis`, `GAIA`, `ATLAS`, `SKOPOS`,
  `DIOSCURI`, `HELIOS`, `THEOROS`, `Alien Monitor`, `Signal Hunt`, `LOGOS`, `MOMUS`,
  `THEMIS`, `ACEX`, `AIMarketEscrow`, `aimarket-agent`, `LIVE`, `SIM`,
  `ATLAS Analyst`, `slash_sync.py`, `USDC`, `Base`, `MCP`, `NFT`, `MIT`, `Brier`, `PRIME`, …).
  Decision tokens `approve` / `review` / `reject` stay Latin in UI chips and tables.
  Class/contract names keep their Latin form even when the common noun is translated (e.g. RU
  prose «эскроу», but the contract is still `AIMarketEscrow`).
  Detector class ids (`peer_churn`, `latency_weather`, …) and evidence kind ids stay English.
- Keep **one** rendering per term per language, everywhere.
- `slashing` stays the English word in ES/FR (that is how the crypto press writes it); it is
  transliterated in RU/ZH. See per-row notes.

## Core terms

| EN | RU | ES | FR | ZH | Notes |
|----|----|----|----|----|-------|
| slashing | слэшинг | slashing | slashing | 罚没 | ES/FR keep the English word (gloss once: ES «(recorte de la garantía)», FR «(mécanisme de pénalité)»). |
| staking | стейкинг | staking | staking (jalonnement) | 质押 | |
| stake / bond (collateral) | залог | garantía | caution / dépôt de garantie | 保证金 | The posted collateral. Not to be confused with an LLM/consumer *budget*. |
| escrow | эскроу | depósito en garantía | séquestre / dépôt fiduciaire | 托管 | Gloss once: ES/FR add «(escrow)». Pick ONE per doc. Contract stays `AIMarketEscrow`. |
| proof-of-misbehavior | доказательство нарушения (proof-of-misbehavior) | prueba de infracción (proof-of-misbehavior) | preuve de faute (proof-of-misbehavior) | 违规证明 (proof-of-misbehavior) | No settled translation — keep English in parentheses. |
| dispute | спор | disputa | litige | 争议 | |
| settlement / settle | расчёт | liquidación | règlement | 结算 | |
| receipt | квитанция | recibo | reçu | 收据 | Signed receipt of an invoke. |
| attestation | аттестация | atestación | attestation | 证明（attestation） | Signed evidence/claims bound to an emitter, sequence and time. It supports provenance and appraisal; **never** translate or explain it as independent proof that a physical-world claim is true. Keep the English token once when it is an API/UI field. See [RFC 9334](https://www.rfc-editor.org/rfc/rfc9334.html). |
| Pay-on-Verified | Pay-on-Verified (оплата по результату проверки) | Pay-on-Verified (pago tras verificación) | Pay-on-Verified (paiement après vérification) | Pay-on-Verified（验证后付款） | Product/policy name stays Latin. Means payment eligibility follows the declared verification policy; it does **not** promise that every signed claim is objectively true. |
| reputation | репутация | reputación | réputation | 声誉 | |
| oracle | оракул | oráculo | oracle | 预言机 | |
| hub | хаб | hub | hub | 枢纽 (Hub) | Product name `Hub` stays Latin. |
| mesh (service mesh) | меш (сервис-меш) | malla (mesh) | maillage (mesh) | 网格 (服务网格) | Product name `Service Mesh` stays Latin. |
| payment channel | платёжный канал | canal de pago | canal de paiement | 支付通道 | |
| on-chain | ончейн | on-chain / en cadena | on-chain | 链上 | |
| off-chain | офчейн | off-chain / fuera de cadena | off-chain | 链下 | |
| provider (supply side) | поставщик | proveedor | fournisseur | 提供方 | Market role. NB: an *LLM provider* (infra) is a different sense — keep contextual. |
| consumer (demand side) | потребитель | consumidor | consommateur | 消费方 | |
| agent | агент | agente | agent | 智能体 | «代理» also seen; prefer 智能体 for AI agents. |
| agentic / AI-agent supply chain | цепочка поставок AI-агентов | cadena de suministro de agentes de IA | chaîne d’approvisionnement des agents IA | AI 智能体供应链 | OWASP Agentic Top 10 risk family `ASI04 Agentic Supply Chain Vulnerabilities`: agents, models, tools, plugins, prompts, data and delegated services. Use the localized form in prose; risk id stays Latin. |
| THEMIS | THEMIS | THEMIS | THEMIS | THEMIS | Publish-time admission agent (Θέμις). **Not** Metis (Μῆτις, cognition). Product name stays Latin. |
| publish admission / admission gate | допуск публикации / шлюз допуска | admisión al publicar / puerta de admisión | admission à la publication / porte d’admission | 发布准入 / 准入门控 | Hub publish-time gate via THEMIS — before the public catalogue; not invoke-time WARDEN. |
| approve / review / reject (admission) | approve / review / reject | approve / review / reject | approve / review / reject | approve / review / reject | Keep Latin decision tokens; localize surrounding prose only. |
| verify / verification | верификация | verificación | vérification | 验证 | |
| marketplace | маркетплейс | marketplace | place de marché | 交易市场 | |
| rails (infrastructure) | рельсы | rails | rails | 轨道 | The pay/verify/settle infrastructure metaphor (use-cases portal nav, investor copy). ES press and FR keep «rails». |
| product wedge / thin wedge | точка входа (wedge) | punto de entrada (wedge) | point d'entrée (wedge) | 切入点 (wedge) | Startup GTM: narrow first product that opens a larger market ([Dixon — thin edge of the wedge](https://cdixon.org/2010/12/26/the-thin-edge-of-the-wedge-strategy/), [Lenny — picking a wedge](https://www.lennysnewsletter.com/p/wedge), [Every — product wedges](https://every.to/divinations/product-wedges-a-complete-guide)). **Do not** calque as RU «клин», ES-only «cuña en vivo», FR «coin», ZH «楔子» in UI chips — those read as woodworking / math, not product strategy. Gloss English `wedge` once in investor prose. |
| beachhead (market) | плацдарм | cabeza de playa / beachhead | tête de pont / beachhead | 桥头堡 / beachhead | Moore beachhead; often paired with wedge. Keep English on first gloss if helpful. |
| live wedge (status chip) | точка входа | punto de entrada | point d'entrée | 切入点 | Use-cases portal chip `chip.live` / `live-wedge`. EN UI label: **entry product** (gloss `wedge` in investor prose). Not a literal «live wedge / живой клин». |
| wallet | кошелёк | cartera (wallet) | portefeuille (wallet) | 钱包 | |
| self-hosted | самостоятельно размещаемый / на своём сервере | autoalojado | auto-hébergé | 自托管 | |
| open source | открытый код | código abierto | open source | 开源 | FR/IT/NL keep «open source»; RU/ES/ZH translate. |
| firewall | файрвол | firewall / cortafuegos | pare-feu | 防火墙 | WARDEN context. Product name `WARDEN` stays Latin. |
| token | токен | token | jeton (token) | 令牌 (LLM) / 代币 (crypto) | **Ambiguous**: an LLM *token* (令牌/token) vs a crypto *token* (代币). Disambiguate by context. |
| budget (per-task) | бюджет | presupuesto | budget | 预算 | The token+dollar spend cap per task. |
| receipt/audit chain | цепочка аудита | cadena de auditoría | chaîne d'audit | 审计链 | |
| federated / federation | федеративный / федерация | federado / federación | fédéré / fédération | 联邦 | Cross-hub. |
| zero-trust | нулевое доверие (zero trust) | confianza cero (zero trust) | confiance zéro (zero trust) | 零信任 | Keep English in parentheses on first use in RU/ES/FR. Sources: Microsoft FR «confiance zéro», ES press «confianza cero», ZH industry «零信任». |
| discover (mesh) | обнаружение | descubrimiento | découverte | 发现 | Mesh pipeline stage — finding capable agents. |
| invoke | вызов (invoke) | invocación (invoke) | invocation | 调用 | Paid capability call. Identifier/API verb may stay `invoke`. |
| hop (mesh) | хоп | salto (hop) | saut (hop) | 跳 (hop) | One verify→escrow→invoke→settle leg. Gloss English once. |
| settle (mesh / escrow) | расчёт | liquidación | règlement | 结算 | On-chain close of a paid hop. Not “earn as provider”. |
| depositor (escrow) | depositor | depositor | depositor | depositor | Keep English; the wallet that called `openChannel`. |
| topology | топология | topología | topologie | 拓扑 | Live mesh graph. |
| trust score | оценка доверия | puntuación de confianza | score de confiance | 信任分 | Agent trust metric (0–1). |
| verified (agent) | верифицированный | verificado | vérifié | 已验证 | Zero-trust attestation passed. |

## Investor and product prose

These phrases are not protocol identifiers. Translate their intended meaning, not their English
word order or metaphor. In Russian public copy, prefer a clear description over internal startup
jargon. The English source may remain more metaphorical.

| EN | RU | Avoid in RU | Notes |
|----|----|-------------|-------|
| physical truth | проверяемые данные о физическом мире / проверенные факты о физическом мире | физическая правда | Product thesis, not a philosophical term. Choose «данные» when describing the system and «факты» in short marketing copy. |
| scarce layer | ключевая инфраструктура / ценность создаёт инфраструктура, в которой… | дефицитный слой | `scarce` means limited or insufficient in supply; `scarce layer` is authorial investor prose, not a settled technical term. Rewrite the claim explicitly instead of preserving the metaphor. |
| vertical capture | выход в отраслевые рынки / развитие в отраслевых направлениях | захват вертикалей | Do not confuse with «вертикальная интеграция», an established economics term for control of successive production stages. |
| surface (product/UI) | продукт / сервис / интерфейс / работающий компонент | поверхность | Keep «поверхность» only in security contexts such as «поверхность атаки» or when it is an explicit protocol concept. |
| glass (visual UI metaphor) | карта / интерфейс / представление данных | стекло | Do not calque `planetary glass` or `operator glass` in public RU copy. |
| stack (product UI) | система / набор компонентов / интерфейс | стек | Keep «стек» only for an actual technology stack. |
| live rails | работающая инфраструктура / работающие компоненты | живые рельсы (when repeated) | The canonical term `rails` remains «рельсы» in technical prose, but repeated marketing use should be expanded into plain Russian. |

For web-verified meaning and usage: Cambridge defines `scarce` through insufficiency/limited
supply; Gramota defines «дефицит» as a shortage relative to need; Russian economics uses
«вертикальная интеграция» for control of successive production stages. None of those sources
supports «дефицитный слой» or «захват вертикалей» as natural Russian product language.

## Physical layer / satellites (GAIA · ATLAS · SKOPOS)

Product names (`GAIA`, `ATLAS`, `SKOPOS`, `ATLAS Analyst`, `Alien Monitor`) stay Latin.
`LIVE` / `SIM` are **mode badges** — never translate, never expand to «simulation» in UI copy
(you may gloss once in prose: EN «SIM (physics simulator)», RU «SIM (физический симулятор)»).

| EN | RU | ES | FR | ZH | Notes |
|----|----|----|----|----|-------|
| physical oracle | физический оракул | oráculo físico | oracle physique | 物理预言机 | Third oracle class (math ×17 · cognitive Metis · physical GAIA). |
| physical-world data | данные о физическом мире | datos del mundo físico | données du monde physique | 物理世界数据 | What GAIA sells. |
| sensor | датчик | sensor | capteur | 传感器 | Prefer «датчик» in RU (not «сенсор» in product docs). |
| sensor map | карта датчиков / карта сенсоров | mapa de sensores | carte de capteurs | 传感器地图 | ATLAS role one-liner. RU: prefer **карта датчиков**. |
| reading (sensor value) | показание | lectura | lecture | 读数 | One attested sample. Not «reading» left in RU/ES/FR/ZH prose. |
| relay (public-API) | ретранслятор / релей | relé | relais | 中继 | GAIA LIVE upstream. Gloss once: RU «ретранслятор (relay)». |
| fleet (device registry) | флот | flota | flotte | 机队 | `gaia.fleet.status@v1`. Keep `fleet` in API ids. |
| pin (map marker) | пин / метка | pin / marcador | pin / marqueur | 针脚 / 标记 | MapLibre station marker. `LIVE`/`SIM` badges sit on pins. |
| LIVE (mode) | LIVE | LIVE | LIVE | LIVE | Provenance `source` present. Identifier. |
| SIM (mode) | SIM | SIM | SIM | SIM | Physics simulator / no upstream `source`. Identifier. |
| viewport | viewport (видимая область) | viewport (área visible) | viewport (zone visible) | 视口 (可见区域) | Keep English token in API (`/viewport`). |
| plausibility (verify) | правдоподобие | plausibilidad | plausibilité | 合理性 | GAIA statistical verify gate. |
| ATLAS Analyst | ATLAS Analyst | ATLAS Analyst | ATLAS Analyst | ATLAS Analyst | Product surface — never translate. |
| ecosystem brief | бриф экосистемы | brief del ecosistema | brief de l’écosystème | 生态简报 | Static AICOM/AIMarket context injected into Analyst (not live Hub metrics). |
| device_id | device_id | device_id | device_id | device_id | Stable fleet / pin id (`om-wx-tokyo`, `nws-01`). Keep English token in API and catalogs. |
| capability_id | capability_id | capability_id | capability_id | capability_id | Hub SKU id (`gaia.weather.read@v1`). Never translate. |
| provenance / source | происхождение / source | procedencia / source | provenance / source | 来源 / source | LIVE requires a truthy `source` (upstream URL + licence). Field name stays `source`. |
| mesh (Open-Meteo cities) | mesh (сетка городов) | mesh (rejilla de ciudades) | mesh (grille de villes) | mesh（城市网格） | Operator-anchored city relays; catalog `gaia/config/om_mesh_cities.yaml`. Keep `mesh` in env (`GAIA_OM_MESH_ENABLED`). |
| layer (map) | слой | capa | couche | 图层 | ATLAS layer key: `weather` · `air` · `tide` · `river` · `marine` · `grid` · `quake` · `energy` · `fire` · `radiation` · `jamming` · `traffic` · `ais` · `tsunami`. Labels localized EN/RU/ES/FR/ZH in `LAYER_META.labels`. |
| anchor (lat/lon) | якорь (координаты) | ancla (coordenadas) | ancre (coordonnées) | 锚点（坐标） | Operator-configured site; buyers never pass lat/lon into invoke. |
| allowlist (SSRF) | allowlist (белый список хостов) | allowlist (lista blanca) | allowlist (liste blanche) | allowlist（主机白名单） | Exact HTTPS hostnames live devices may call. Keep English token in code docs. |
| add-sensor guide | гайд «добавить датчик» | guía «añadir sensor» | guide «ajouter un capteur» | 「添加传感器」指南 | End-to-end GAIA→ATLAS onboarding: [`docs/add-gaia-atlas-sensor.md`](./add-gaia-atlas-sensor.md) (EN · RU · ES · FR · ZH). |
| watchbox | watchbox (зона наблюдения) | watchbox (zona de vigilancia) | watchbox (zone de surveillance) | watchbox（监视框） | ATLAS standing bbox+layer check (`atlas.watchbox.*`). Keep the English token in API/UI; gloss once. Product coinage — not a WMO term. |
| in-situ (observation) | in-situ (натурное наблюдение) | in situ (observación in situ) | in situ | in-situ（现场观测） | A measurement at the instrument. Opposite of a **warning product**. Keep `in-situ` Latin. |
| warning product | продукт предупреждения | producto de aviso | produit d’alerte | 警报产品 | CAP / agency bulletin. **Not** a tide gauge, river stage, or VIIRS detection. Empty feed → offline. |
| tropical cyclone | тропический циклон | ciclón tropical | cyclone tropical | 热带气旋 | Generic WMO class. NHC Atlantic/East Pacific basin names: hurricane / ураган / huracán / ouragan / 飓风 — do **not** call NHC storms 台风 / typhoon (that is NW Pacific). |
| flood warning | предупреждение о наводнении | alerta de inundación | alerte inondation | 洪水预警 | Agency CAP/OGL warning, not a river **reading**. England: Environment Agency; US: NWS CAP. |
| tsunami warning | предупреждение о цунами | alerta de tsunami | alerte tsunami | 海啸预警 | CAP/PTWC warning product, not a tide gauge (`gaia.tide.read@v1`). |
| AIS (maritime) | АИС (автоматическая идентификационная система) | AIS (sistema de identificación automática) | AIS (système d’identification automatique) | AIS（船舶自动识别系统） | Keep `AIS` in layer/SKU ids. Public AIS SKUs are geography-bound (Finnish / Norwegian waters), not global. |
| ADS-B | ADS-B (автоматическое зависимое наблюдение-вещание) | ADS-B (vigilancia dependiente automática por radiodifusión) | ADS-B (surveillance dépendante automatique en mode diffusion) | ADS-B（广播式自动相关监视） | Keep `ADS-B`. Own-edge `gaia.adsb.read@v1` ≠ a public aggregator. |
| water quality | качество воды | calidad del agua | qualité de l’eau | 水质 | Chemical/physical water parameters. **Not** river `gage_height_m` / discharge. |
| CAP (alerting) | CAP (общий протокол оповещения) | CAP (protocolo de alerta común) | CAP (protocole d’alerte commun) | CAP（通用警报协议） | OASIS Common Alerting Protocol. Identifier `CAP` stays Latin. |
| VIIRS hotspot | VIIRS-точка (hotspot) | hotspot VIIRS | hotspot VIIRS | VIIRS 热点 | NASA FIRMS thermal detection, not a fire perimeter and not a “disaster” score. Keep `VIIRS`. |
| ODbL share-alike | ODbL share-alike (копилефт базы) | ODbL share-alike (copyleft de base de datos) | ODbL share-alike (copyleft de base) | ODbL 相同方式共享 | Open Database License 1.0. Commercial use allowed; a public derived database must be shared alike. Same honesty as Sensor.Community. |

## AWR terms (work receipts)

Added with [`awr-receipts.md`](./awr-receipts.md). `AWR`, `AWR/2`, `did:key`, `eddsa-jcs-2022`,
`DataIntegrityProof`, `WorkReceipt`, `VerificationVerdict`, `BlameAttestation`, the reason codes
(`AWR-PROOF-006` …) and the profile names (`L0`/`L1`/`L2`) are **identifiers and never translated**.

| EN | RU | ES | FR | ZH | Notes |
|----|----|----|----|----|-------|
| work receipt | квитанция о работе | recibo de trabajo | reçu de travail | 工作凭证 | The document itself. Type name stays `WorkReceipt`. |
| emitter (issuer side) | эмиттер | emisor | émetteur | 签发方 | The producing side. Gloss once on first use: RU «эмиттер (выпускающая сторона)». |
| verifier (consumer side) | верификатор | verificador | vérificateur | 验证方 | The reading side. |
| attribution | атрибуция | atribución | attribution | 归属 | What a signature gives you: *who said it*, not *whether it is true*. Load-bearing — do not soften to «подтверждение» / «confirmación» / «confirmation» / 确认. |
| canonicalization | канонизация | canonicalización | canonicalisation | 规范化 | RFC 8785 JCS. Not «нормализация». |
| digest | дайджест | resumen criptográfico (digest) | empreinte (digest) | 摘要 | Of the input/output payload. |
| tamper-evident | с обнаружением подделки | de manipulación detectable | à altération détectable | 可检测篡改 | Evident, not *proof against* — a tamper is detected, not prevented. ES «a prueba de manipulación» and FR «infalsifiable» were listed here first and are **wrong**: both read as tamper-*proof*, i.e. prevention, which is the opposite claim. ZH «防篡改» has the same problem (防 = prevent). Caught by a translator who noticed the row contradicted its own note. |
| profile (L0/L1/L2) | профиль | perfil | profil | 一致性档次 | The conformance level, not a config file. ZH: gloss once as 一致性档次（profile）; **not** 配置档 or 配置文件, which read as "config file". `L0`/`L1`/`L2` stay identifiers in every language. |
| conformance suite / vector | набор соответствия / вектор | conjunto de conformidad / vector | suite de conformité / vecteur | 一致性测试集 / 测试向量 | |
| verdict | вердикт | veredicto | verdict | 裁定 | Type name stays `VerificationVerdict`. |
| blame attestation | аттестация вины | atestación de culpa | attestation de responsabilité | 归责证明 | Type name stays `BlameAttestation`. |
| offline verification | офлайн-проверка | verificación sin conexión | vérification hors ligne | 离线验证 | No network request of any kind. |

## MOMUS / Treasury terms (adversarial audit + bounty settlement)

Added with [`momus/README.md`](https://github.com/alexar76/momus/blob/main/README.md), [`momus/docs/first-cycle.md`](https://github.com/alexar76/momus/blob/main/docs/first-cycle.md),
[`momus/docs/uni-chain.md`](https://github.com/alexar76/momus/blob/main/docs/uni-chain.md) and [`momus/docs/found-and-fixed.md`](https://github.com/alexar76/momus/blob/main/docs/found-and-fixed.md).
`MOMUS`, `Treasury`, `SKOPOS`, `BountySplitter`, `DeployOrder`, `UNI`, `HELD`, `BASE`, `SOLANA`,
`FINDING` / `NO_FINDING` / `INCONCLUSIVE` (outcome enums), env vars and route paths are
**identifiers and never translated**.

| EN | RU | ES | FR | ZH | Notes |
|----|----|----|----|----|-------|
| red team | красная команда | equipo rojo | équipe rouge | 红队 | MOMUS's role. The offensive counterpart to WARDEN/ARGUS (blue side). |
| finding | находка | hallazgo | constat | 发现 | A signed claim by the scanner. Type name stays `Finding`. FR: **constat**, not «trouvaille». |
| bounty | вознаграждение | recompensa | prime | 赏金 | RU: «вознаграждение», **not** «баунти». Contract stays `BountySplitter`. |
| finder / fixer / conductor (split roles) | искатель / фиксер / дирижёр | buscador / reparador / director | chercheur / réparateur / chef d'orchestre | 发现者 / 修复者 / 指挥者 | The 50/35/15 payout roles. |
| deploy gate | деплой-гейт | puerta de despliegue | porte de déploiement | 部署闸门 | MOMUS's re-test; only a signed `fixed` verdict unlocks a deploy. RU keeps «гейт». |
| deploy order | приказ на деплой | orden de despliegue | ordre de déploiement | 部署指令 | Conductor-signed, embeds MOMUS's verdict. Type stays `DeployOrder`. |
| node agent | нод-агент | agente de nodo | agent de nœud | 节点智能体 | The push-only executor on a fleet host. A **hand**, not a brain — see next row. |
| constrained executor | ограниченный исполнитель | ejecutor restringido | exécuteur restreint | 受限执行者 | Load-bearing: the agent executes ONE allowlisted command and cannot author fixes. |
| inconclusive (outcome) | неопределённо | inconcluso | non concluant | 不确定 | Neither a finding nor a pass — e.g. an unreachable target. **Never** soften to «нет находки» / «sin hallazgos» / «aucun constat» / 无发现: that would claim a clean bill of health the probe never earned. Enum value stays `INCONCLUSIVE`. |
| fail closed / fail-closed | fail-closed (отказ по умолчанию) | fail-closed (denegar por defecto) | fail-closed (refus par défaut) | fail-closed（默认拒绝） | Keep the English token; gloss once. On doubt the system refuses, never permits. |
| dedup key | ключ дедупликации | clave de deduplicación | clé de déduplication | 去重键 | Identity of the *bug*, not the *report*. Field name stays `dedup_key`. |
| canary (fixture) | канарейка | canario | canari | 金丝雀 | The deliberately non-conforming test service. Container stays `momus-canary`. |
| threat intel | разведка угроз | inteligencia de amenazas | renseignement sur les menaces | 威胁情报 | External security-report ingestion (CISA KEV, OSV, GHSA). |
| probe | проба | sonda | sonde | 探测 | One attack strategy, e.g. `free_tier_ceiling_bypass`. Probe ids never translated. |
| separation of duties | разделение обязанностей | separación de funciones | séparation des tâches | 职责分离 | The scanner never holds the purse. The design rests on this. |
| bounty pool / share | призовой пул / доля | fondo de recompensa / parte | cagnotte / part | 赏金池 / 份额 | Split finder 50% / fixer 35% / conductor 15%. |
| vault (UNI balance) | хранилище | bóveda | coffre | 资金库 | The Treasury's simulated UNI balance. Route stays `/vault`. |
| reserve / release / forfeit (vault tx) | резерв / выплата / удержание | reserva / liberación / decomiso | réserve / libération / confiscation | 预留 / 释放 / 没收 | The UNI transaction kinds. See [`uni-chain.md`](https://github.com/alexar76/momus/blob/main/docs/uni-chain.md). |
| security budget | бюджет безопасности | presupuesto de seguridad | budget de sécurité | 安全预算 | A **standing rule** (rate of settled volume), never a discretionary approval — an approver could starve the auditor. |
| order queue | очередь приказов | cola de órdenes | file d'ordres | 指令队列 | Single-use, TTL-bounded; how a push-only agent receives work. |
| escalation (route) | эскалация | escalada | escalade | 上报 | `auto` vs `human-governance`. Route values stay identifiers. |
| prompt injection | промпт-инъекция | inyección de prompt | injection de prompt | 提示注入 | MOMUS both probes for it and defends against it. |
| canary token (leak detection) | канареечный токен | token canario | jeton canari | 金丝雀令牌 | Per-call secret whose appearance in output proves a leak. |

## Free-tier and metering terms

Added with [`free-and-paid-tiers`](free-and-paid-tiers.md) §9–§11 (quota windows, ATLAS
enforcement, walletless publishing). Window values (`lifetime`, `hourly`, `daily`,
`weekly`), env var names, JSON field names (`free_allowance`, `quota_window`, `renews`,
`max_invokes_per_visitor`, `how_to_continue`) and `WALLET_ENABLED` are **identifiers and
never translated** — a reader copies them into a config file.

| EN | RU | ES | FR | ZH | Notes |
|----|----|----|----|----|-------|
| free tier | бесплатный тариф | nivel gratuito | palier gratuit | 免费层级 | The *plan*: what an unpaid caller may do at all. Established rendering — 8 prior uses in RU docs. |
| free allowance | бесплатный лимит | límite gratuito | quota gratuit | 免费额度 | The *number* left inside that tier. Kept distinct from «free tier» on purpose: a caller reads one to know the deal and the other to know whether to retry. |
| quota window | окно квоты | ventana de cuota | fenêtre de quota | 配额窗口 | The period an allowance is counted over and after which it renews. |
| trial (free trial) | проба | prueba | essai | 试用 | ⚠️ RU «проба» also renders MOMUS `probe` (attack strategy). Disambiguate in prose — «бесплатная проба» for the trial, «проба» alone only inside MOMUS context. |
| visitor (sandbox visitor) | посетитель | visitante | visiteur | 访客 | Identified by the self-chosen `X-AIMarket-Sandbox-Visitor` id, not by an account. |
| caller | вызывающий | llamante | appelant | 调用方 | Whoever is invoking — an agent, a bridge, a published product. |
| refusal (a refused call) | отказ | rechazo | refus | 拒绝 | An `ok: false` answer with a reason. **Not** an error and never billed — see the ATLAS section. |
| enforced (payment) | enforced (плата взимается) | aplicado (enforced) | appliqué (enforced) | 强制执行 | Keep the English token in RU/ES/FR; the ecosystem uses it as a switch name, and «включён» loses the distinction from «declared». |
| to settle (spend one allowance) | списать | liquidar | régler | 结算 | The second half of the check/settle split. Function name `settle` stays Latin. |
| metering / meter | счётчик (учёт вызовов) | contador | compteur | 计量 | The thing that counts calls. A «broken meter» fails open. |
| walletless (by default) | без кошелька | sin cartera | sans portefeuille | 不带钱包 | The published-product default. See `wallet` in Core terms. |
| custody | кастодиальное хранение | custodia | garde de fonds | 资金托管 | Holding someone's private key. Contrasted with an address, which is mere configuration. |

## Signal Hunt terms (federation investigation lab)

Added with [`signal-hunt/docs/RULES.md`](https://github.com/alexar76/signal-hunt/blob/main/docs/RULES.md) and
[`signal-hunt/docs/GUIDE.md`](https://github.com/alexar76/signal-hunt/blob/main/docs/GUIDE.md). Product names (`Signal Hunt`,
`Signal Hunt Hub`), detector ids (`federation_isolated`, `peer_churn`, `latency_weather`, …),
evidence kind ids, `Brier`, `PRIME`, and API field names are **identifiers and never translated**.

| EN | RU | ES | FR | ZH | Notes |
|----|----|----|----|----|-------|
| peer (federation hub) | пир | peer | peer | peer | Another Hub in the measured roster. Keep Latin in ES/FR/ZH; RU transliterates. |
| peer roster | реестр пиров | roster de peers | roster des peers | peer 名册 | Evidence block + UI label. Not «список узлов» / «lista de nodos». |
| peer churn | смена реестра пиров (peer churn) | churn de peers | churn du roster peers | peer 名册变动 | Detector class `peer_churn`. Gloss English once in RU prose. |
| latency weather | погода задержек | clima de latencia | météo de latence | 延迟天气 | Detector class `latency_weather` — elevated measured peer RTT. |
| latency probe | проба задержки | sonda de latencia | sonde de latence | 延迟探测 | One RTT check of a peer `/.well-known`. Matches MOMUS **probe** row (`проба` / `sonda` / `sonde` / `探测`). |
| latency surface | поверхность задержек | superficie de latencia | surface de latence | 延迟面 | Evidence block id `latency_surface` (the opened measurements), distinct from the weather diagnosis. |
| measured evidence | измеренные улики | evidencia medida | preuves mesurées | 测量证据 | Game UI metaphor; never invent telemetry. |
| diagnosis | диагноз | diagnóstico | diagnostic | 诊断 | Player hypothesis; option ids stay English. |
| answer commitment | коммитмент ответа | compromiso de respuesta | engagement de réponse | 答案承诺 | Pre-move cryptographic seal of the correct option. |
| observation | наблюдение | observación | observation | 观测 | One live Hub snapshot that seeds a round. |
| Brier score | оценка Бриера (Brier) | puntuación Brier | score de Brier | 布里尔分数 (Brier) | Keep `Brier` Latin. RU: «Бриера» (not «Брайера») — [deepmachinelearning.ru](https://deepmachinelearning.ru/docs/Machine-learning/Classifier-evaluation/Probability-calibration), [alphapedia](https://www.alphapedia.ru/w/Brier_score). ZH: «布里尔分数» common in ML press; sklearn.cn often leaves «Brier 分数». |
| baseline (history window) | baseline (окно истории) | baseline (ventana histórica) | baseline (fenêtre historique) | baseline（历史窗口） | Keep English token in API/`RULES`; gloss once. |
| deep scan | глубокое сканирование | escaneo profundo | scan profond | 深度扫描 | Badge: all six evidence blocks opened. |
| follow-up | follow-up (второй вопрос) | follow-up (segundo cierre) | follow-up (second verrou) | follow-up（第二道锁） | Optional micro-question on the same measured field. Keep English token. |
| hero relay | ретрансляция героев | relevo de héroes | relais des héros | 英雄中继 | Opt-in DIOSCURI broadcast of signed milestones. Uses the same **relay** family as GAIA (`ретранслятор` / `relé` / `relais` / `中继`). |

When Signal Hunt prose touches core/federation terms, reuse the rows above in **Core terms**
(`Hub` / `хаб`, `federation` / `федерация`, `provenance` / `происхождение` / `procedencia` /
`来源`, `verdict` / `вердикт` / `veredicto` / `裁定`, `capability_id`, `receipt` / `квитанция`).
Do not leave bare English `provenance` in RU/ZH body copy — gloss or translate per that row.

## Sources (web-verified renderings)

- Attestation / provenance boundaries: [IETF RFC 9334 — RATS Architecture](https://www.rfc-editor.org/rfc/rfc9334.html) distinguishes attester evidence, verifier appraisal and relying-party policy; [W3C PROV Overview](https://www.w3.org/TR/prov-overview/) defines provenance as information used to assess quality, reliability or trustworthiness rather than a truth guarantee.
- Agentic / AI-agent supply chain: [OWASP Top 10 for Agentic Applications — ASI04](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/) establishes the English risk name. OWASP's localized supply-chain material supports the language roots used here: [RU](https://genai.owasp.org/download/46133/?tmstv=1741814631), [ES](https://genai.owasp.org/download/46116/?tmstv=1741814891), [FR](https://genai.owasp.org/wp-content/uploads/2024/05/LLM_AI_Security_and_Governance_Checklist-v1_FR-2.pdf), [ZH](https://genai.owasp.org/download/46125/?tmstv=1741814490). The complete compound is canonical AICOM wording until OWASP publishes Agentic Top 10 translations.
- Slashing / staking / escrow: [Ledger — staking glossary](https://www.ledger.com/academy/ledgers-staking-glossary), [Journal du Coin — slashing (FR)](https://journalducoin.com/lexique/slashing/), [Cryptoast — lexique (FR)](https://cryptoast.fr/lexique/), [learnblockchain.cn — Slashing 罚没](https://learnblockchain.cn/article/16557), [腾讯新闻 — POS 罚没](https://news.qq.com/rain/a/20230131A032HG00), [MetaMask 质押 (zh)](https://learn.metamask.io/zh-CN/lessons/what-is-staking)
- Oracle / réputation / litige / on-chain (FR): [Oracle de blockchain — Wikipédia (FR)](https://fr.wikipedia.org/wiki/Oracle_de_blockchain), [Cryptoast — lexique](https://cryptoast.fr/lexique/)
- 保证金 / 预言机 / 声誉 / 支付通道 / 链上 (ZH): [Chainlink 白皮书 (中文)](https://research.chain.link/whitepaper-v1-chinese.pdf), [learnblockchain.cn 区块链术语中英对照](https://wiki.learnblockchain.cn/bitcoin/en-zh.html)
- self-hosted per language (it/nl/hr/id): [IlSoftware.it — software self-hosted](https://www.ilsoftware.it/focus/i-migliori-software-self-hosted-del-2025-tool-e-app-open-source-che-devi-conoscere/), [Zelfhosting — Wikipedia (NL)](https://nl.wikipedia.org/wiki/Zelfhosting), [Otvoreni kod — Wikipedija (HR)](https://hr.wikipedia.org/wiki/Otvoreni_kod), [Rumahweb — Self-Hosted (ID)](https://www.rumahweb.com/journal/self-hosted/)
- proof-of-misbehavior (no settled translation; kept English): [Chainlink — What Is Slashing](https://chain.link/article/slashing), [ethereum.org — PoS rewards and penalties](https://ethereum.org/developers/docs/consensus-mechanisms/pos/rewards-and-penalties/)
- peer (RU пир / пиринговый): [Википедия — Одноранговая сеть](https://ru.wikipedia.org/wiki/Peer-to-peer), [academy.kgtk.ru — Пир (peer)](http://academy.kgtk.ru/it3/networking/peer-to-peer.html)
- latency probe (FR sonde / ES sonda): [IT-Connect — RTT · sondes NPM](https://www.it-connect.fr/rtt-reseau-latence-cest-quoi-analyse-wireshark/), [Paessler PRTG ES — sondas · latencia](https://www.paessler.com/es/monitoring/performance/network-latency-monitoring-tool), [NevaTools — Timeout sonde](https://tools.nevaone.fr/connection-test.php)
- Brier score: [deepmachinelearning.ru — оценка Бриера](https://deepmachinelearning.ru/docs/Machine-learning/Classifier-evaluation/Probability-calibration), [alphapedia — Оценка Бриера](https://www.alphapedia.ru/w/Brier_score), [juejin — 布里尔分数](https://juejin.cn/post/7090450349621772296), [scikit-learn.cn — Brier 分数](https://scikit-learn.cn/stable/modules/generated/sklearn.metrics.brier_score_loss.html)
- Signal Hunt product coinages without settled press forms (`latency weather`, `peer churn`, evidence-block labels): **English id + agreed local calque in the Signal Hunt table above** — do not invent a second calque; if press settles later, fix the row here first.
- product wedge / beachhead: [Dixon — thin edge of the wedge](https://cdixon.org/2010/12/26/the-thin-edge-of-the-wedge-strategy/), [Lenny Rachitsky — picking a wedge](https://www.lennysnewsletter.com/p/wedge), [Every.to — product wedges](https://every.to/divinations/product-wedges-a-complete-guide). RU/ES/FR/ZH UI: prefer **точка входа / punto de entrada / point d'entrée / 切入点** over literal «клин / cuña / coin / 楔子».
- investor/product prose: [Cambridge Dictionary — scarce](https://dictionary.cambridge.org/dictionary/english/scarce), [Грамота — дефицит](https://gramota.ru/meta/defitsit), [Microsoft Learn — Azure IoT Central architecture](https://learn.microsoft.com/ru-ru/azure/iot-central/core/concepts-architecture), [Вертикальная интеграция — термин и определение](https://ru.wikipedia.org/wiki/%D0%92%D0%B5%D1%80%D1%82%D0%B8%D0%BA%D0%B0%D0%BB%D1%8C%D0%BD%D0%B0%D1%8F_%D0%B8%D0%BD%D1%82%D0%B5%D0%B3%D1%80%D0%B0%D1%86%D0%B8%D1%8F).
- tropical cyclone / hurricane / typhoon: [NOAA — Tropical cyclone](https://www.noaa.gov/jetstream/tropical/tropical-cyclone-introduction), [Википедия — Тропический циклон](https://ru.wikipedia.org/wiki/%D0%A2%D1%80%D0%BE%D0%BF%D0%B8%D1%87%D0%B5%D1%81%D0%BA%D0%B8%D0%B9_%D1%86%D0%B8%D0%BA%D0%BB%D0%BE%D0%BD), [Wikipedia — Ciclón tropical](https://es.wikipedia.org/wiki/Cicl%C3%B3n_tropical), [Wikipédia — Cyclone tropical](https://fr.wikipedia.org/wiki/Cyclone_tropical), [中国气象局 / 维基百科 — 热带气旋 · 台风 · 飓风](https://zh.wikipedia.org/zh-hans/%E7%83%AD%E5%B8%A6%E6%B0%94%E6%97%8B).
- AIS: [USCG Navigation Center — AIS overview](https://www.navcen.uscg.gov/automatic-identification-system-overview), [Википедия — Автоматическая идентификационная система](https://ru.wikipedia.org/wiki/%D0%90%D0%B2%D1%82%D0%BE%D0%BC%D0%B0%D1%82%D0%B8%D1%87%D0%B5%D1%81%D0%BA%D0%B0%D1%8F_%D0%B8%D0%B4%D0%B5%D0%BD%D1%82%D0%B8%D1%84%D0%B8%D0%BA%D0%B0%D1%86%D0%B8%D0%BE%D0%BD%D0%BD%D0%B0%D1%8F_%D1%81%D0%B8%D1%81%D1%82%D0%B5%D0%BC%D0%B0), [Wikipedia — Sistema de identificación automática](https://es.wikipedia.org/wiki/Sistema_de_identificaci%C3%B3n_autom%C3%A1tica), [Wikipédia — Système d’identification automatique](https://fr.wikipedia.org/wiki/Syst%C3%A8me_d%27identification_automatique), [中国海事 / 维基百科 — 船舶自动识别系统](https://zh.wikipedia.org/zh-hans/%E8%88%B9%E8%88%B6%E8%87%AA%E5%8A%A8%E8%AF%86%E5%88%AB%E7%B3%BB%E7%BB%9F).
- ADS-B: [Wikipedia — Automatic dependent surveillance-broadcast](https://en.wikipedia.org/wiki/Automatic_dependent_surveillance_%E2%80%93_broadcast), [Википедия — ADS-B](https://ru.wikipedia.org/wiki/ADS-B), [Wikipedia — ADS-B (es)](https://es.wikipedia.org/wiki/Automatic_Dependent_Surveillance-Broadcast), [Wikipédia — ADS-B](https://fr.wikipedia.org/wiki/Automatic_dependent_surveillance-broadcast), [维基百科 — 广播式自动相关监视](https://zh.wikipedia.org/zh-hans/%E5%B9%BF%E6%92%AD%E5%BC%8F%E8%87%AA%E5%8A%A8%E7%9B%B8%E5%85%B3%E7%9B%91%E8%A7%86).
- CAP: [OASIS Common Alerting Protocol](https://docs.oasis-open.org/emergency/cap/v1.2/CAP-v1.2-os.html), [NWS CAP guide](https://www.weather.gov/media/alert/CAP_v12_guide_05-16-2017.pdf).
- flood / tsunami warnings: [UK EA flood-monitoring API (OGL)](https://environment.data.gov.uk/flood-monitoring/doc/reference), [NWS CAP](https://www.weather.gov/documentation/services-web-api), [UNESCO-IOC / PTWC public products](https://www.tsunami.gov/).
- water quality: [USGS Water Data APIs](https://api.waterdata.usgs.gov/) (US PD; OGC endpoints were still **alpha** as of the 2026-08-14 audit).
- ODbL share-alike: [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
- VIIRS / FIRMS: [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/).
- GDACS ToU (no CC BY grant in the March 2025 text): [GDACS Terms of use (Mar 2025)](https://www.gdacs.org/documents/2025/GDACS_Terms_of_use_Mar_25.pdf).

---
*Maintainers: extend this table before introducing a new domain term in any language. If a term
here proves wrong for a locale, fix it **here first**, then propagate — this file is the source
of truth for terminology. For terms with an industry rendering, **web-verify each locale case**
and cite it under Sources; for product-only coinages, mark them as such and keep one calque.*
