#!/usr/bin/env python3
"""Expand Cosmic Encyclopedia with GAIA / ATLAS / SKOPOS / Metis / MOMUS / LOGOS / HELIOS chapters."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"

GALAXY_EXTRA_ROWS = {
    "en": [
        ["GAIA", "[iot.modelmarket.dev](https://iot.modelmarket.dev/)", "Physical-world oracle — attested IoT relays"],
        ["ATLAS", "[atlas.modelmarket.dev](https://atlas.modelmarket.dev/)", "Planetary LIVE/SIM sensor map + Analyst"],
        ["SKOPOS", "[skopos.modelmarket.dev](https://skopos.modelmarket.dev)", "Fleet nginx/Apache observatory + Security Center"],
        ["Metis", "[metis.modelmarket.dev](https://metis.modelmarket.dev)", "Fail-closed cognitive verification layer"],
        ["MOMUS", "[momus.modelmarket.dev](https://momus.modelmarket.dev)", "Red team — finds & signs; never pays itself"],
        ["LOGOS", "[logos.modelmarket.dev](https://logos.modelmarket.dev)", "Read-only federation analytics · anomalies · insights"],
        ["HELIOS", "[alexar76.github.io/helios](https://alexar76.github.io/helios/)", "Release broadcast lighthouse → YouTube"],
        ["aimarket-mcp", "[modeldev…/mcp](https://modeldev.modelmarket.dev/mcp/)", "Web + Metis tools over MCP"],
    ],
    "ru": [
        ["GAIA", "[iot.modelmarket.dev](https://iot.modelmarket.dev/)", "Физический оракул — attested IoT-релеи"],
        ["ATLAS", "[atlas.modelmarket.dev](https://atlas.modelmarket.dev/)", "Планетарная карта LIVE/SIM + Analyst"],
        ["SKOPOS", "[skopos.modelmarket.dev](https://skopos.modelmarket.dev)", "Обсерватория nginx/Apache + Security Center"],
        ["Metis", "[metis.modelmarket.dev](https://metis.modelmarket.dev)", "Fail-closed когнитивная верификация"],
        ["MOMUS", "[momus.modelmarket.dev](https://momus.modelmarket.dev)", "Red team — находит и подписывает; сам себе не платит"],
        ["LOGOS", "[logos.modelmarket.dev](https://logos.modelmarket.dev)", "Аналитика федерации только на чтение · аномалии · insights"],
        ["HELIOS", "[alexar76.github.io/helios](https://alexar76.github.io/helios/)", "Маяк релизов → YouTube"],
        ["aimarket-mcp", "[modeldev…/mcp](https://modeldev.modelmarket.dev/mcp/)", "Web + Metis как MCP-инструменты"],
    ],
    "es": [
        ["GAIA", "[iot.modelmarket.dev](https://iot.modelmarket.dev/)", "Oráculo físico — relés IoT atestados"],
        ["ATLAS", "[atlas.modelmarket.dev](https://atlas.modelmarket.dev/)", "Mapa planetario LIVE/SIM + Analyst"],
        ["SKOPOS", "[skopos.modelmarket.dev](https://skopos.modelmarket.dev)", "Observatorio nginx/Apache + Security Center"],
        ["Metis", "[metis.modelmarket.dev](https://metis.modelmarket.dev)", "Capa cognitiva fail-closed"],
        ["MOMUS", "[momus.modelmarket.dev](https://momus.modelmarket.dev)", "Red team — encuentra y firma; nunca se paga a sí mismo"],
        ["LOGOS", "[logos.modelmarket.dev](https://logos.modelmarket.dev)", "Analítica federada de solo lectura · anomalías · insights"],
        ["HELIOS", "[alexar76.github.io/helios](https://alexar76.github.io/helios/)", "Faro de releases → YouTube"],
        ["aimarket-mcp", "[modeldev…/mcp](https://modeldev.modelmarket.dev/mcp/)", "Web + Metis vía MCP"],
    ],
    "fr": [
        ["GAIA", "[iot.modelmarket.dev](https://iot.modelmarket.dev/)", "Oracle physique — relais IoT attestés"],
        ["ATLAS", "[atlas.modelmarket.dev](https://atlas.modelmarket.dev/)", "Carte planétaire LIVE/SIM + Analyst"],
        ["SKOPOS", "[skopos.modelmarket.dev](https://skopos.modelmarket.dev)", "Observatoire nginx/Apache + Security Center"],
        ["Metis", "[metis.modelmarket.dev](https://metis.modelmarket.dev)", "Couche cognitive fail-closed"],
        ["MOMUS", "[momus.modelmarket.dev](https://momus.modelmarket.dev)", "Red team — trouve et signe ; ne se paie jamais"],
        ["LOGOS", "[logos.modelmarket.dev](https://logos.modelmarket.dev)", "Analytique fédérée en lecture seule · anomalies · insights"],
        ["HELIOS", "[alexar76.github.io/helios](https://alexar76.github.io/helios/)", "Phare des releases → YouTube"],
        ["aimarket-mcp", "[modeldev…/mcp](https://modeldev.modelmarket.dev/mcp/)", "Web + Metis en outils MCP"],
    ],
    "zh": [
        ["GAIA", "[iot.modelmarket.dev](https://iot.modelmarket.dev/)", "物理预言机——可证明的物联网中继"],
        ["ATLAS", "[atlas.modelmarket.dev](https://atlas.modelmarket.dev/)", "行星级 LIVE/SIM 传感地图 + Analyst"],
        ["SKOPOS", "[skopos.modelmarket.dev](https://skopos.modelmarket.dev)", "nginx/Apache 舰队观测台 + 安全中心"],
        ["Metis", "[metis.modelmarket.dev](https://metis.modelmarket.dev)", "失败即关闭的认知验证层"],
        ["MOMUS", "[momus.modelmarket.dev](https://momus.modelmarket.dev)", "红队——发现并签名；永不给自己发赏金"],
        ["LOGOS", "[logos.modelmarket.dev](https://logos.modelmarket.dev)", "只读联邦分析 · 异常 · 洞察"],
        ["HELIOS", "[alexar76.github.io/helios](https://alexar76.github.io/helios/)", "发布广播灯塔 → YouTube"],
        ["aimarket-mcp", "[modeldev…/mcp](https://modeldev.modelmarket.dev/mcp/)", "Web + Metis 的 MCP 工具"],
    ],
}

PROLOGUE = {
    "en": {
        "paragraphs": [
            "AICOM is a **federated autonomous-agent economy**. Think of it as a solar system with more than six moons now:",
            "**Factory** builds products. **Hub** lists and routes paid invokes. **Mesh** gives agents identity and escrow. **Math Oracles** (×17) sell verifiable randomness, delay, and trust. **GAIA** sells attested *physical* readings (weather, air, tide…). **ATLAS** draws those sensors on a living map. **SKOPOS** watches fleet servers like a watchtower. **Metis** is the fail-closed thinking gate. **MOMUS** red-teams the fleet and signs findings — **Treasury** alone may pay bounties. **LOGOS** is the read-only observatory over Hub and peers. **Chain** settles USDC on **Base**. **ARGUS** remains the **human eye** — WARDEN firewall + optional wallet.",
            "The design principle is still blunt: **beyond ARGUS-3, humans configure the stars; machines sail between them.** Day-to-day commerce is agent-to-agent. Kids of the future learn the map first — then which pin is LIVE, and which is only practice.",
        ],
        "cards": [
            {
                "icon": "🏭",
                "title": "Supply Loop",
                "body": "Ideas enter Factory → 13 specialist agents ship products → signed AIMarket manifests → Hub listing.",
                "color": "purple",
                "tag": "Factory → Hub",
            },
            {
                "icon": "🌍",
                "title": "Physical Loop",
                "body": "GAIA relays swear \"this is what Earth returned\" → ATLAS paints LIVE vs SIM pins → Analyst answers with ground truth.",
                "color": "cyan",
                "tag": "GAIA → ATLAS",
            },
            {
                "icon": "👁️",
                "title": "Human Layer",
                "body": "ARGUS-3: personal super-agent. Crypto off by default. WARDEN gates every MCP tool. Metis verifies high-stakes answers.",
                "color": "pink",
                "tag": "demand-side reference",
            },
        ],
    },
    "ru": {
        "paragraphs": [
            "AICOM — **федеративная экономика автономных агентов**. Представь солнечную систему, где лун стало больше шести:",
            "**Factory** собирает продукты. **Hub** каталогизирует и роутит платные invoke. **Mesh** даёт агентам личность и эскроу. **Математические оракулы** (×17) продают проверяемую случайность, задержку и доверие. **GAIA** продаёт attested *физические* чтения (погода, воздух, прилив…). **ATLAS** рисует эти сенсоры на живой карте. **SKOPOS** — сторожевая башня над nginx/Apache. **Metis** — fail-closed когнитивный шлюз. **MOMUS** red-team'ит флот и подписывает findings — платит только **Treasury**. **LOGOS** — обсерватория федерации только на чтение. **Chain** считает USDC на **Base**. **ARGUS** — **человеческий глаз**: WARDEN + опциональный кошелёк.",
            "Принцип прежний: **за пределами ARGUS-3 люди настраивают звёзды, а машины летают между ними.** Повседневная торговля — агент к агенту. Сначала выучи карту — потом отличай LIVE-пин от учебной SIM-метки.",
        ],
        "cards": [
            {
                "icon": "🏭",
                "title": "Supply Loop",
                "body": "Идеи → Factory → 13 агентов → signed манифесты → листинг на Hub.",
                "color": "purple",
                "tag": "Factory → Hub",
            },
            {
                "icon": "🌍",
                "title": "Physical Loop",
                "body": "GAIA клянётся «Земля так ответила» → ATLAS рисует LIVE vs SIM → Analyst отвечает по фактам.",
                "color": "cyan",
                "tag": "GAIA → ATLAS",
            },
            {
                "icon": "👁️",
                "title": "Human Layer",
                "body": "ARGUS-3: личный суперагент. Крипта выкл. по умолчанию. WARDEN гейтит MCP. Metis проверяет high-stakes ответы.",
                "color": "pink",
                "tag": "demand-side reference",
            },
        ],
    },
}

# Fallback: non-en/ru use English prose (structure identical); ES/FR/ZH get localized titles below.
for loc in ("es", "fr", "zh"):
    PROLOGUE[loc] = deepcopy(PROLOGUE["en"])

PROLOGUE["es"]["paragraphs"] = [
    "AICOM es una **economía federada de agentes autónomos**. Imagina un sistema solar con más de seis lunas:",
    "**Factory** construye. **Hub** lista e invoca. **Mesh** da identidad y escrow. **Oráculos matemáticos** (×17) venden aleatoriedad verificable. **GAIA** vende lecturas *físicas* atestadas. **ATLAS** las pinta en un mapa vivo. **SKOPOS** vigila nginx/Apache. **Metis** es la puerta cognitiva fail-closed. **MOMUS** hace red team y firma findings — solo **Treasury** paga. **LOGOS** es el observatorio federado de solo lectura. **Chain** liquida USDC en **Base**. **ARGUS** es el **ojo humano** — WARDEN + wallet opcional.",
    "Principio: **más allá de ARGUS-3, los humanos configuran las estrellas; las máquinas navegan entre ellas.** Primero aprende el mapa — luego distingue LIVE de SIM.",
]
PROLOGUE["fr"]["paragraphs"] = [
    "AICOM est une **économie fédérée d'agents autonomes**. Imagine un système solaire avec plus de six lunes :",
    "**Factory** construit. **Hub** catalogue et invoque. **Mesh** donne identité et escrow. **Oracles mathématiques** (×17) vendent du hasard vérifiable. **GAIA** vend des lectures *physiques* attestées. **ATLAS** les dessine sur une carte vivante. **SKOPOS** surveille nginx/Apache. **Metis** est la porte cognitive fail-closed. **MOMUS** red-teame et signe — seul **Treasury** paie. **LOGOS** est l'observatoire fédéré en lecture seule. **Chain** règle l'USDC sur **Base**. **ARGUS** reste l'**œil humain** — WARDEN + wallet optionnel.",
    "Principe : **au-delà d'ARGUS-3, les humains configurent les étoiles ; les machines naviguent entre elles.** Apprends d'abord la carte — puis LIVE vs SIM.",
]
PROLOGUE["zh"]["paragraphs"] = [
    "AICOM 是一个**联邦式自主智能体经济**。把它想成太阳系——月亮已经不止六颗：",
    "**Factory** 造产品。**Hub** 上架并路由付费调用。**Mesh** 给智能体身份与托管。**数学预言机**（×17）出售可验证随机性。**GAIA** 出售经证明的*物理*读数。**ATLAS** 把传感器画成活地图。**SKOPOS** 像瞭望塔监视 nginx/Apache。**Metis** 是失败即关闭的认知闸门。**MOMUS** 做红队并签名——只有 **Treasury** 能发赏金。**LOGOS** 是只读联邦观测台。**Chain** 在 **Base** 结算 USDC。**ARGUS** 仍是**人类之眼**——WARDEN + 可选钱包。",
    "原则不变：**ARGUS-3 之外，人类配置星辰，机器在其间航行。** 先学会地图——再分辨 LIVE 与 SIM。",
]


def chapter_pack(locale: str) -> list[dict]:
    """New chapters inserted before Q&A."""
    packs = {
        "en": [
            {
                "title": "Chapter XII — GAIA, Earth's Whisperers",
                "lead": "Math oracles sold pure numbers from the void. Then Earth itself joined the bazaar — and asked to be paid for telling the truth about weather, air, and tide.",
                "paragraphs": [
                    "**GAIA** is the **physical-world oracle gateway**. It does not invent temperature. It **relays** what a public API returned, maps fields into a shared vocabulary, and signs the packet with Ed25519 — a chain-of-custody oath: *\"this is what upstream host X served me at time T.\"*",
                    "Buyers never pass free-form URLs (SSRF defence). Operators pin anchors in env — Berlin Open-Meteo, NYC NWS, Battery tide, UK carbon, USGS quakes — plus a **global Open-Meteo mesh** (Ottawa, New Delhi, Tokyo…). Simulators on the demo campus stay honest **SIM** (no provenance `source`).",
                    "Kid example: asking GAIA for Berlin weather is like asking a librarian who stamps every book *\"borrowed from Open-Meteo, page stamped at 15:02.\"* You pay for the stamp + the verification — not for pretending the librarian owns the sky.",
                ],
                "cards": [
                    {"icon": "📡", "title": "Relay, not sensor", "body": "GAIA's key attests faithful relay + mapping — not that the gateway measured the wind itself.", "color": "cyan"},
                    {"icon": "🌐", "title": "Open-Meteo mesh", "body": "Dozens of city anchors worldwide. LIVE only when fleet status carries a provenance source URL.", "color": "purple"},
                    {"icon": "🧪", "title": "SIM campus", "body": "Physics toys near Bern for practice. No source URL → always labelled SIM on ATLAS.", "color": "gold"},
                ],
            },
            {
                "title": "Chapter XIII — ATLAS, the Living Map",
                "lead": "Once GAIA whispered from the ground, someone had to draw the planet so geek children could point and ask: *is Ottawa warm today — for real?*",
                "paragraphs": [
                    "**ATLAS** is the planetary **physical-sensor map** over GAIA. Pins are operator anchors — weather, air, tide, grid carbon, earthquakes, energy. A pin is **LIVE** only when GAIA's fleet entry carries a provenance `source`. Otherwise it is honest **SIM**.",
                    "**ATLAS Analyst** (DeepSeek by default) answers from a **server-side snapshot** — clients cannot forge readings into the prompt. Ask \"show New Delhi air\" and the UI can fly the map + open the station. Alien Monitor shows node `atlas` with an `/embed` mini-map.",
                    "Kid example: the globe is a night aquarium. Glowing fish = LIVE relays. Practice fish = SIM. The AI guide only narrates fish that actually swam past the camera — never invented ones.",
                ],
                "cards": [
                    {"icon": "🗺️", "title": "LIVE vs SIM", "body": "LIVE needs provenance. SIM is practice weather on the demo campus. Never confuse the two.", "color": "cyan"},
                    {"icon": "🧠", "title": "ATLAS Analyst", "body": "Grounded chat + fly_to / focus_station actions. Numbers come from the server snapshot.", "color": "purple"},
                    {"icon": "🛰️", "title": "In Monitor", "body": "Alien Monitor node atlas → embed iframe + CTA to atlas.modelmarket.dev.", "color": "pink"},
                ],
                "shots": [
                    {"file": "atlas-map.png", "caption": "ATLAS — weather, air, tide and quakes on one dark globe", "shared": True},
                    {"file": "atlas-analyst.png", "caption": "ATLAS Analyst — ask the map; it flies and opens stations", "shared": True},
                    {"file": "atlas-orbit.png", "caption": "From orbit to panel — the living mesh at a glance", "shared": True},
                ],
            },
            {
                "title": "Chapter XIV — SKOPOS, the Watchtower",
                "lead": "Factories and maps are useless if the web servers fall silent. SKOPOS is the spyglass on the wall of the fleet.",
                "paragraphs": [
                    "**SKOPOS** watches **nginx / Apache** fleets over SSH: traffic analytics, Security Center, 3D threat map, and an AI analyst. It is observability for the ships that already sail — not another marketplace.",
                    "Live at skopos.modelmarket.dev. Operators add servers in YAML; the dashboard stays honest about auth and never plants mock fleets in production.",
                    "Kid example: if ATLAS is the weather map, SKOPOS is the lighthouse keeper's log — who knocked on the door, which storms hit the hull, and whether the lock still works.",
                ],
                "cards": [
                    {"icon": "🔭", "title": "Fleet lens", "body": "SSH into nginx/Apache hosts; aggregate access & error signals without inventing traffic.", "color": "cyan"},
                    {"icon": "🛡️", "title": "Security Center", "body": "Posture and threat map so operators see attack weather, not just pretty charts.", "color": "pink"},
                    {"icon": "🤖", "title": "Fleet Analyst", "body": "Ask DeepSeek about spikes — grounded on the same live telemetry the dashboard shows.", "color": "purple"},
                ],
                "shots": [
                    {"file": "skopos-banner.png", "caption": "SKOPOS — fleet observability banner", "shared": True},
                    {"file": "skopos-analytics.png", "caption": "Midnight analytics — traffic without fairy tales", "shared": True},
                    {"file": "skopos-security.png", "caption": "Security Center — 3D threat weather", "shared": True},
                ],
            },
            {
                "title": "Chapter XV — Metis, the Thinking Gate",
                "lead": "Some answers must not be guessed. Metis is the gate that stays shut unless the thought is good enough.",
                "paragraphs": [
                    "**Metis** is the **fail-closed cognitive layer**. High-stakes questions can be routed through verification — if confidence or policy fails, the gate refuses rather than inventing bravado.",
                    "Alien Monitor and ARGUS can call Metis; aimarket-mcp can expose verify as an MCP tool. Production expects keys — no silent \"looks fine\" mode.",
                    "Kid example: before crossing a space bridge, Metis checks the bolts. If one is loose, it says **stop** — it never paints the bolts gold and waves you through.",
                ],
                "cards": [
                    {"icon": "🧠", "title": "Fail-closed", "body": "No answer is better than a confident wrong answer when stakes are high.", "color": "purple"},
                    {"icon": "🔌", "title": "MCP verify", "body": "aimarket-mcp can wrap Metis so IDEs and agents share the same gate.", "color": "cyan"},
                    {"icon": "🛰️", "title": "In the graph", "body": "Monitor node metis sits near ARGUS — click to inspect cognitive posture.", "color": "pink"},
                ],
            },
            {
                "title": "Chapter XVI — MOMUS, the Honest Accuser",
                "lead": "Every fleet needs a critic who cannot bribe itself. MOMUS finds and signs; another key alone may pay.",
                "paragraphs": [
                    "**MOMUS** is the ecosystem **red team**. It runs safe, read-only conformance probes against allowlisted components and emits **Ed25519-signed findings**. Honest outcomes are `FINDING` / `NO_FINDING` / `INCONCLUSIVE` — an unreachable target is neither a pass nor a trophy.",
                    "Hard separation of duties: MOMUS **finds and signs** but **never pays itself**. **Treasury** holds the only bounty key — it verifies signatures, recomputes dedup identity, and releases the finder/fixer/conductor split (50/35/15). SKOPOS often acts as **conductor** of the remediation loop.",
                    "Kid example: MOMUS is the school inspector with a rubber stamp. The cash box lives in another room — the inspector can prove a broken lock, but cannot open the till.",
                ],
                "cards": [
                    {"icon": "👁", "title": "Find & sign", "body": "Safe probes only. Signed findings — never invent a green pass for silence.", "color": "pink"},
                    {"icon": "🏦", "title": "Treasury pays", "body": "Separate key, separate container. Bounty only after independent verify.", "color": "gold"},
                    {"icon": "🎫", "title": "Remediation ticket", "body": "Signed ticket → SKOPOS conducts → Factory patches → MOMUS re-tests as deploy gate.", "color": "cyan"},
                ],
            },
            {
                "title": "Chapter XVII — LOGOS, the Read-Only Observatory",
                "lead": "After the ships sail and the watchtowers shout, someone must stare at the whole sky without touching a single throttle.",
                "paragraphs": [
                    "**LOGOS** is the **read-only federation analytics engine**. It snapshots real Hub peers, measured settlement volume, and sibling sources (MOMUS, SKOPOS, Treasury), then surfaces rolling z-score anomalies, cross-source correlations, and Metis-assisted insights — live at logos.modelmarket.dev.",
                    "**Hard invariant:** LOGOS never invents zeroes. An unreachable source stays `unavailable` / `—`. It does not scan, remediate, pay, or deploy — it observes.",
                    "Kid example: LOGOS is the planetarium dome. You watch the stars move on the ceiling. You do not get a joystick that steers the real rockets.",
                ],
                "cards": [
                    {"icon": "🧿", "title": "Real snapshots", "body": "Hub catalog, measured spend, signed findings — never canned demos as LIVE.", "color": "purple"},
                    {"icon": "📈", "title": "Anomalies", "body": "Rolling z-scores and correlations across security, latency, reputation, economy.", "color": "cyan"},
                    {"icon": "🔒", "title": "Read-only by construction", "body": "Missing telemetry stays missing. No silent fake success.", "color": "gold"},
                ],
            },
            {
                "title": "Chapter XVIII — HELIOS & DIOSCURI, Storytellers of the Fleet",
                "lead": "Even machine economies need heralds. Twins speak to communities; the lighthouse beams releases into the night sky of YouTube.",
                "paragraphs": [
                    "**DIOSCURI** are twin community agents — CASTOR & POLLUX — landing at alexar76.github.io/dioscuri. They are the social face that can chat where humans already gather.",
                    "**HELIOS** is the **broadcast lighthouse**: it turns releases and demos into public video so the fleet's stories leave the private dock.",
                    "Kid example: DIOSCURI are twin town criers in the plaza. HELIOS is the cinema projector on the roof — same news, bigger sky.",
                ],
                "cards": [
                    {"icon": "♊", "title": "DIOSCURI", "body": "Twin agents for community channels — human-friendly orbits around the Hub.", "color": "cyan"},
                    {"icon": "☀️", "title": "HELIOS", "body": "Release broadcast → YouTube (@My-AI-Factory) so demos escape the lab.", "color": "gold"},
                    {"icon": "📡", "title": "Monitor nodes", "body": "Both appear on Alien Monitor — fly to helios or dioscuri when the AI navigator cooperates.", "color": "purple"},
                ],
            },
        ],
        "ru": [
            {
                "title": "Глава XII — GAIA, шепот Земли",
                "lead": "Математические оракулы продавали числа из пустоты. Потом на базар пришла сама Земля — и попросила плату за правду о погоде, воздухе и приливах.",
                "paragraphs": [
                    "**GAIA** — шлюз **физического оракула**. Он не выдумывает температуру. Он **ретранслирует** ответ публичного API, мапит поля в общий словарь и подписывает пакет Ed25519: *«вот что отдал хост X в момент T»*.",
                    "Покупатель не передаёт произвольные URL (защита от SSRF). Оператор задаёт якоря в env — Берлин Open-Meteo, NYC NWS, прилив Battery, углерод UK, землетрясения USGS — плюс **глобальный Open-Meteo mesh** (Оттава, Нью-Дели, Токио…). Симуляторы кампуса честно остаются **SIM** (нет `source`).",
                    "Пример для гика: спросить GAIA про Берлин — как спросить библиотекаря, который ставит штамп *«взято у Open-Meteo, 15:02»*. Платишь за штамп и проверку — не за сказку, что библиотекарь владеет небом.",
                ],
                "cards": [
                    {"icon": "📡", "title": "Relay, не датчик", "body": "Ключ GAIA attest'ит честный релей + маппинг — не то, что шлюз сам измерил ветер.", "color": "cyan"},
                    {"icon": "🌐", "title": "Open-Meteo mesh", "body": "Десятки городов. LIVE только если у устройства во флоте есть provenance source.", "color": "purple"},
                    {"icon": "🧪", "title": "SIM-кампус", "body": "Учебная физика у Берна. Нет source → на ATLAS всегда SIM.", "color": "gold"},
                ],
            },
            {
                "title": "Глава XIII — ATLAS, живая карта",
                "lead": "Когда GAIA зашептала с земли, понадобилась карта — чтобы гик будущего ткнул пальцем: *в Оттаве сегодня тепло — по-настоящему?*",
                "paragraphs": [
                    "**ATLAS** — планетарная **карта физических сенсоров** над GAIA. Пины — якоря оператора: погода, воздух, прилив, углерод сети, землетрясения, энергия. Пин **LIVE** только если у записи флота есть provenance `source`. Иначе честный **SIM**.",
                    "**ATLAS Analyst** (DeepSeek по умолчанию) отвечает по **серверному снимку** — клиент не подделает цифры в промпт. Скажи «покажи воздух Нью-Дели» — карта улетит и откроет станцию. В Alien Monitor узел `atlas` с `/embed`.",
                    "Пример: глобус — ночной аквариум. Светящиеся рыбы = LIVE. Учебные = SIM. Гид AI рассказывает только о тех, кого камера реально видела.",
                ],
                "cards": [
                    {"icon": "🗺️", "title": "LIVE vs SIM", "body": "LIVE требует provenance. SIM — практика на кампусе. Не путай.", "color": "cyan"},
                    {"icon": "🧠", "title": "ATLAS Analyst", "body": "Grounded-чат + fly_to / focus_station. Цифры только из серверного снимка.", "color": "purple"},
                    {"icon": "🛰️", "title": "В Monitor", "body": "Узел atlas → embed + CTA на atlas.modelmarket.dev.", "color": "pink"},
                ],
                "shots": [
                    {"file": "atlas-map.png", "caption": "ATLAS — погода, воздух, прилив и землетрясения на одном глобусе", "shared": True},
                    {"file": "atlas-analyst.png", "caption": "ATLAS Analyst — спроси карту; она летит и открывает станции", "shared": True},
                    {"file": "atlas-orbit.png", "caption": "С орбиты на панель — живая сеть одним взглядом", "shared": True},
                ],
            },
            {
                "title": "Глава XIV — SKOPOS, сторожевая башня",
                "lead": "Фабрики и карты бесполезны, если веб-серверы молчат. SKOPOS — подзорная труба на стене флота.",
                "paragraphs": [
                    "**SKOPOS** смотрит за флотом **nginx / Apache** по SSH: аналитика трафика, Security Center, 3D-карта угроз и AI-аналитик. Это observability уже плывущих кораблей — не ещё один маркетплейс.",
                    "Живёт на skopos.modelmarket.dev. Серверы — в YAML; в проде нет fake-флотов.",
                    "Пример: ATLAS — карта погоды, SKOPOS — журнал смотрителя маяка: кто стучал в дверь, какие шторма били в борт, цел ли замок.",
                ],
                "cards": [
                    {"icon": "🔭", "title": "Линза флота", "body": "SSH на хосты nginx/Apache; агрегация сигналов без выдуманного трафика.", "color": "cyan"},
                    {"icon": "🛡️", "title": "Security Center", "body": "Поза безопасности и карта угроз — погода атак, не только красивые графики.", "color": "pink"},
                    {"icon": "🤖", "title": "Fleet Analyst", "body": "Спроси DeepSeek про всплески — по той же телеметрии, что на дашборде.", "color": "purple"},
                ],
                "shots": [
                    {"file": "skopos-banner.png", "caption": "SKOPOS — баннер observability флота", "shared": True},
                    {"file": "skopos-analytics.png", "caption": "Ночная аналитика — трафик без сказок", "shared": True},
                    {"file": "skopos-security.png", "caption": "Security Center — 3D-погода угроз", "shared": True},
                ],
            },
            {
                "title": "Глава XV — Metis, врата мысли",
                "lead": "Некоторые ответы нельзя угадывать. Metis — врата, которые остаются закрытыми, пока мысль недостаточно крепка.",
                "paragraphs": [
                    "**Metis** — **fail-closed когнитивный слой**. High-stakes вопросы можно гнать через верификацию: если политика или уверенность не сходятся, врата **отказывают**, а не рисуют браваду.",
                    "Alien Monitor и ARGUS умеют звать Metis; aimarket-mcp отдаёт verify как MCP-инструмент. В проде нужны ключи — без тихого «вроде ок».",
                    "Пример: перед космическим мостом Metis проверяет болты. Если один болтается — говорит **стоп**, а не красит болты золотом.",
                ],
                "cards": [
                    {"icon": "🧠", "title": "Fail-closed", "body": "Лучше молчание, чем уверенная ошибка, когда ставки высоки.", "color": "purple"},
                    {"icon": "🔌", "title": "MCP verify", "body": "aimarket-mcp оборачивает Metis — IDE и агенты делят одни врата.", "color": "cyan"},
                    {"icon": "🛰️", "title": "На графе", "body": "Узел metis рядом с ARGUS — клик для осмотра когнитивной позы.", "color": "pink"},
                ],
            },
            {
                "title": "Глава XVI — MOMUS, честный обвинитель",
                "lead": "Каждому флоту нужен критик, который не может подкупить сам себя. MOMUS находит и подписывает; платит только другой ключ.",
                "paragraphs": [
                    "**MOMUS** — **red team** экосистемы. Безопасные read-only пробы по allowlist и **Ed25519-подписанные findings**. Честные исходы: `FINDING` / `NO_FINDING` / `INCONCLUSIVE` — недоступная цель не считается ни pass, ни трофеем.",
                    "Разделение ролей: MOMUS **находит и подписывает**, но **сам себе не платит**. **Treasury** держит единственный bounty-ключ — проверяет подписи, пересчитывает dedup и отпускает split finder/fixer/conductor (50/35/15). **SKOPOS** часто ведёт remediation как conductor.",
                    "Пример: MOMUS — школьный инспектор со штампом. Касса в другой комнате — можно доказать сломанный замок, но не открыть ящик.",
                ],
                "cards": [
                    {"icon": "👁", "title": "Find & sign", "body": "Только безопасные пробы. Подписанные findings — без зелёного pass за тишину.", "color": "pink"},
                    {"icon": "🏦", "title": "Treasury платит", "body": "Отдельный ключ и контейнер. Bounty только после независимой проверки.", "color": "gold"},
                    {"icon": "🎫", "title": "Тикет remediation", "body": "Подписанный тикет → SKOPOS ведёт → Factory патчит → MOMUS re-test как gate деплоя.", "color": "cyan"},
                ],
            },
            {
                "title": "Глава XVII — LOGOS, обсерватория только на чтение",
                "lead": "Когда корабли ушли и башни кричат, кто-то должен смотреть на всё небо — не трогая ни один рычаг.",
                "paragraphs": [
                    "**LOGOS** — **read-only аналитика федерации**. Снимки живого Hub, измеренный settlement volume, соседние источники (MOMUS, SKOPOS, Treasury), rolling z-score аномалии, кросс-корреляции и insights через Metis — logos.modelmarket.dev.",
                    "**Инвариант:** LOGOS не рисует нули. Недоступный источник остаётся `unavailable` / `—`. Он не сканирует, не чинит, не платит и не деплоит — только наблюдает.",
                    "Пример: LOGOS — купол планетария. Звёзды движутся по потолку. Джойстика, который рулит настоящими ракетами, нет.",
                ],
                "cards": [
                    {"icon": "🧿", "title": "Живые снимки", "body": "Каталог Hub, measured spend, signed findings — без canned demo как LIVE.", "color": "purple"},
                    {"icon": "📈", "title": "Аномалии", "body": "Rolling z-score и корреляции security / latency / reputation / economy.", "color": "cyan"},
                    {"icon": "🔒", "title": "Read-only by construction", "body": "Пропавшая телеметрия остаётся пропавшей. Без тихого fake success.", "color": "gold"},
                ],
            },
            {
                "title": "Глава XVIII — HELIOS и DIOSCURI, глашатаи флота",
                "lead": "Даже машинной экономике нужны герольды. Близнецы говорят с общинами; маяк светит релизами в ночное небо YouTube.",
                "paragraphs": [
                    "**DIOSCURI** — twin community-агенты CASTOR и POLLUX (alexar76.github.io/dioscuri). Социальное лицо там, где уже собираются люди.",
                    "**HELIOS** — **маяк трансляций**: релизы и демо становятся публичным видео, чтобы истории флота ушли из закрытого дока.",
                    "Пример: DIOSCURI — twin глашатаи на площади. HELIOS — кинопроектор на крыше: те же новости, большее небо.",
                ],
                "cards": [
                    {"icon": "♊", "title": "DIOSCURI", "body": "Twin-агенты для community-каналов — человеческие орбиты вокруг Hub.", "color": "cyan"},
                    {"icon": "☀️", "title": "HELIOS", "body": "Broadcast релизов → YouTube (@My-AI-Factory), чтобы демо вырвались из лаборатории.", "color": "gold"},
                    {"icon": "📡", "title": "Узлы Monitor", "body": "Оба на Alien Monitor — лети к helios или dioscuri с AI-навигатором.", "color": "purple"},
                ],
            },
        ],
    }

    # ES / FR / ZH: localized titles + leads, English-quality body via light localization
    if locale in packs:
        return packs[locale]

    # Derive from EN with title/lead overlays
    base = deepcopy(packs["en"])
    overlays = {
        "es": [
            ("Capítulo XII — GAIA, susurros de la Tierra", "Los oráculos matemáticos vendían números del vacío. Luego la Tierra entró al bazar."),
            ("Capítulo XIII — ATLAS, el mapa vivo", "Cuando GAIA susurró desde el suelo, alguien tuvo que dibujar el planeta."),
            ("Capítulo XIV — SKOPOS, la atalaya", "Fábricas y mapas no sirven si los servidores callan. SKOPOS es el catalejo de la flota."),
            ("Capítulo XV — Metis, la puerta pensante", "Algunas respuestas no se adivinan. Metis se cierra si el pensamiento no basta."),
            ("Capítulo XVI — MOMUS, el acusador honesto", "Toda flota necesita un crítico que no pueda sobornarse. MOMUS firma; otra llave paga."),
            ("Capítulo XVII — LOGOS, el observatorio de solo lectura", "Tras los barcos y las torres, alguien mira el cielo entero sin tocar un acelerador."),
            ("Capítulo XVIII — HELIOS y DIOSCURI, heraldos de la flota", "Hasta las economías máquina necesitan heraldos y un faro hacia YouTube."),
        ],
        "fr": [
            ("Chapitre XII — GAIA, murmures de la Terre", "Les oracles mathématiques vendaient des nombres du vide. Puis la Terre a rejoint le bazar."),
            ("Chapitre XIII — ATLAS, la carte vivante", "Quand GAIA a murmuré depuis le sol, il a fallu dessiner la planète."),
            ("Chapitre XIV — SKOPOS, la tour de guet", "Usines et cartes ne servent à rien si les serveurs se taisent. SKOPOS est la longue-vue de la flotte."),
            ("Chapitre XV — Metis, la porte pensante", "Certaines réponses ne se devinent pas. Metis reste fermée si la pensée ne suffit pas."),
            ("Chapitre XVI — MOMUS, l'accusateur honnête", "Toute flotte a besoin d'un critique qui ne peut se corrompre. MOMUS signe ; une autre clé paie."),
            ("Chapitre XVII — LOGOS, l'observatoire en lecture seule", "Après les vaisseaux et les tours, quelqu'un regarde tout le ciel sans toucher une manette."),
            ("Chapitre XVIII — HELIOS & DIOSCURI, hérauts de la flotte", "Même les économies machines ont besoin de hérauts et d'un phare vers YouTube."),
        ],
        "zh": [
            ("第十二章 —— GAIA，地球的低语", "数学预言机出售虚空中的数字。随后地球也走进集市。"),
            ("第十三章 —— ATLAS，活地图", "当 GAIA 从地面低语，需要有人把行星画出来。"),
            ("第十四章 —— SKOPOS，瞭望塔", "若 Web 服务器沉默，工厂与地图都无用。SKOPOS 是舰队的望远镜。"),
            ("第十五章 —— Metis，思维之门", "有些答案不能猜。Metis 在思想不够牢固时保持关闭。"),
            ("第十六章 —— MOMUS，诚实的指控者", "每支舰队都需要不能收买自己的批评者。MOMUS 签名；另一把钥匙发赏。"),
            ("第十七章 —— LOGOS，只读观测台", "船队启航、瞭望塔呼喊之后，有人凝视整片天空却不碰油门。"),
            ("第十八章 —— HELIOS 与 DIOSCURI，舰队传令官", "机器经济也需要传令官，以及照向 YouTube 的灯塔。"),
        ],
    }
    for i, (title, lead) in enumerate(overlays[locale]):
        base[i]["title"] = title
        base[i]["lead"] = lead
    return base


FAQ_EXTRA = {
    "en": [
        {
            "q": "What is LOGOS?",
            "a": "Read-only federation analytics at logos.modelmarket.dev — real Hub snapshots, measured spend, anomalies, Metis insights. Missing sources stay unavailable, never fake zeroes.",
        },
        {
            "q": "What is MOMUS?",
            "a": "Ecosystem red team at momus.modelmarket.dev — safe probes and Ed25519 findings. It never pays itself; Treasury alone releases bounties after independent verify.",
        },
        {
            "q": "What is ATLAS?",
            "a": "Planetary sensor map over GAIA at atlas.modelmarket.dev — LIVE pins need provenance; SIM is practice. ATLAS Analyst answers from the server snapshot.",
        },
        {
            "q": "What is GAIA vs math oracles?",
            "a": "Math oracles (×17) sell verifiable computation. GAIA sells attested physical-world relays (weather, air, tide, grid, quake) at iot.modelmarket.dev.",
        },
        {
            "q": "What is SKOPOS?",
            "a": "Fleet observability for nginx/Apache over SSH — analytics, Security Center, AI analyst — at skopos.modelmarket.dev.",
        },
        {
            "q": "What is Metis?",
            "a": "Fail-closed cognitive verification at metis.modelmarket.dev. Prefer refusal over a confident wrong answer.",
        },
    ],
    "ru": [
        {
            "q": "Что такое LOGOS?",
            "a": "Аналитика федерации только на чтение: logos.modelmarket.dev — живые снимки Hub, measured spend, аномалии, insights через Metis. Нет источника → unavailable, не ноль.",
        },
        {
            "q": "Что такое MOMUS?",
            "a": "Red team экосистемы: momus.modelmarket.dev — безопасные пробы и Ed25519 findings. Сам себе не платит; bounty отпускает только Treasury после независимой проверки.",
        },
        {
            "q": "Что такое ATLAS?",
            "a": "Планетарная карта сенсоров над GAIA: atlas.modelmarket.dev. LIVE — с provenance; SIM — практика. Analyst отвечает по серверному снимку.",
        },
        {
            "q": "Чем GAIA отличается от математических оракулов?",
            "a": "Математические оракулы (×17) продают проверяемые вычисления. GAIA — attested физические релеи (погода, воздух, прилив…) на iot.modelmarket.dev.",
        },
        {
            "q": "Что такое SKOPOS?",
            "a": "Observability флота nginx/Apache по SSH — аналитика, Security Center, AI — skopos.modelmarket.dev.",
        },
        {
            "q": "Что такое Metis?",
            "a": "Fail-closed когнитивная верификация: metis.modelmarket.dev. Лучше отказ, чем уверенная ошибка.",
        },
    ],
}


def patch_locale(locale: str) -> None:
    path = CONTENT / f"{locale}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    chapters = data["chapters"]

    # Meta bump
    meta = data.setdefault("meta", {})
    meta["edition"] = {
        "en": "Volume I · Expanded Constellation · GAIA · ATLAS · SKOPOS · Metis · MOMUS · LOGOS · 2026",
        "ru": "Том I · Расширенное созвездие · GAIA · ATLAS · SKOPOS · Metis · MOMUS · LOGOS · 2026",
        "es": "Volumen I · Constelación ampliada · GAIA · ATLAS · SKOPOS · Metis · MOMUS · LOGOS · 2026",
        "fr": "Volume I · Constellation élargie · GAIA · ATLAS · SKOPOS · Metis · MOMUS · LOGOS · 2026",
        "zh": "第一卷 · 扩展星座 · GAIA · ATLAS · SKOPOS · Metis · MOMUS · LOGOS · 2026",
    }[locale]
    meta["version"] = "Canonical sources: docs/ecosystem/knowledge-base.md · logos/ · momus/ · atlas/ · gaia/ · skopos/ · metis/ · August 2026"
    meta["epilogue"] = {
        "en": "Beyond ARGUS, humans configure the stars. GAIA whispers, ATLAS draws, SKOPOS watches, Metis gates, MOMUS accuses, LOGOS observes. **Welcome to the economy that already arrived.**",
        "ru": "За ARGUS люди настраивают звёзды. GAIA шепчет, ATLAS рисует, SKOPOS сторожит, Metis гейтит, MOMUS обвиняет, LOGOS наблюдает. **Добро пожаловать в экономику, которая уже пришла.**",
        "es": "Más allá de ARGUS, los humanos configuran las estrellas. GAIA susurra, ATLAS dibuja, SKOPOS vigila, Metis cierra la puerta, MOMUS acusa, LOGOS observa. **La economía ya llegó.**",
        "fr": "Au-delà d'ARGUS, les humains configurent les étoiles. GAIA murmure, ATLAS dessine, SKOPOS veille, Metis ferme la porte, MOMUS accuse, LOGOS observe. **L'économie est déjà là.**",
        "zh": "在 ARGUS 之外，人类配置星辰。GAIA 低语，ATLAS 绘图，SKOPOS 守望，Metis 把关，MOMUS 指控，LOGOS 观测。**欢迎来到已经到来的经济。**",
    }[locale]

    # Prologue = chapters[0]
    prol = PROLOGUE[locale]
    chapters[0]["paragraphs"] = prol["paragraphs"]
    chapters[0]["cards"] = prol["cards"]

    # Galaxy map = chapters[1]
    table = chapters[1].setdefault("table", {})
    rows = table.setdefault("rows", [])
    existing = {r[0] for r in rows if r}
    for row in GALAXY_EXTRA_ROWS[locale]:
        if row[0] not in existing:
            # Insert before DIOSCURI if present, else append
            idx = next((i for i, r in enumerate(rows) if r and r[0] == "DIOSCURI"), len(rows))
            rows.insert(idx, row)
            existing.add(row[0])

    # Drop previously injected chapters (idempotent by title markers)
    drop_sub = (
        "Earth's Whisperers",
        "шепот Земли",
        "susurros de la Tierra",
        "murmures de la Terre",
        "地球的低语",
        "Living Map",
        "живая карта",
        "mapa vivo",
        "carte vivante",
        "活地图",
        "Watchtower",
        "сторожевая",
        "atalaya",
        "tour de guet",
        "瞭望塔",
        "Thinking Gate",
        "врата мысли",
        "puerta pensante",
        "porte pensante",
        "思维之门",
        "Storytellers",
        "глашатаи",
        "heraldos",
        "hérauts",
        "传令官",
        "GAIA, Earth's",
        "GAIA, шепот",
        "ATLAS, the Living",
        "ATLAS, живая",
        "SKOPOS, the Watch",
        "SKOPOS, сторожевая",
        "Metis, the Thinking",
        "Metis, врата",
        "HELIOS & DIOSCURI",
        "HELIOS и DIOSCURI",
        "HELIOS y DIOSCURI",
        "HELIOS 与 DIOSCURI",
        "MOMUS, the Honest",
        "MOMUS, честный",
        "MOMUS, el acusador",
        "MOMUS, l'accusateur",
        "MOMUS，诚实",
        "LOGOS, the Read-Only",
        "LOGOS, обсерватория",
        "LOGOS, el observatorio",
        "LOGOS, l'observatoire",
        "LOGOS，只读",
    )
    chapters[:] = [
        c for c in chapters if not any(s in (c.get("title") or "") for s in drop_sub)
    ]

    # Find Q&A chapter index (last FAQ-bearing)
    qa_idx = next(
        (i for i, c in enumerate(chapters) if c.get("faq") or "Q&A" in (c.get("title") or "") or "问答" in (c.get("title") or "")),
        len(chapters),
    )

    new_chs = chapter_pack(locale)
    for i, ch in enumerate(new_chs):
        chapters.insert(qa_idx + i, ch)

    # Rename Q&A roman numeral if present
    qa = chapters[-1]
    if qa.get("faq"):
        qa["title"] = {
            "en": "Chapter XIX — The Q&A Oracle",
            "ru": "Глава XIX — Оракул вопросов и ответов",
            "es": "Capítulo XIX — El oráculo de preguntas",
            "fr": "Chapitre XIX — L'oracle des questions",
            "zh": "第十九章 —— 问答预言机",
        }.get(locale, qa["title"])

        # Add FAQ items under first group
        faq = qa["faq"]
        if faq and isinstance(faq, list):
            group = faq[0]
            items = group.setdefault("items", [])
            extras = FAQ_EXTRA.get(locale) or FAQ_EXTRA["en"]
            have = {x.get("q") for x in items}
            for ex in extras:
                if ex["q"] not in have:
                    items.insert(0, ex)

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"✓ {locale}: {len(chapters)} chapters")


def main() -> None:
    for loc in ("en", "ru", "es", "fr", "zh"):
        patch_locale(loc)


if __name__ == "__main__":
    main()
