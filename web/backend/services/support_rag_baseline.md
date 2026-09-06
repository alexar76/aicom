# AI-Factory — support baseline (English)

**AI-Factory** runs a multi-agent **pipeline** (PM, architect, developer, QA, security, DevOps, marketing, sales, evolution) to ship software and landing pages from a short brief.

- **Storefront**: product cards, categories, **sandbox** previews (iframe serves files from disk; use **relative** asset URLs).
- **Guest flow**: one phrase can enqueue a **marketing landing** build.
- **Payments**: optional crypto checkout depending on product/config.
- **Quality**: demo/QA gates; listed products show quality signals when configured.
- **Support assistant “Lumen”**: answers questions; **bugs** for shipped `prod-…` may enqueue dev repair; **business** topics escalate to the Director queue (admin).
- **Admin**: pipeline, LLM providers, Director, Brainstorming, **Outreach** (broadcast channels via env credentials).
- **Physical/map SKUs** (GAIA/ATLAS): Hub invoke, not the 17 math oracles. Discover via Hub search. The generated table below is the catalog floor; live Hub search is the ceiling. Do not invent SKUs. LIVE only with provenance source; never present SIM as LIVE.
- **HEPHAESTUS studio** (modelmarket.dev/studio): visual composer for capability chains — pick capabilities from the live signed catalogue, see what the graph costs before running it, run it, and keep the signed bill of materials (which hop is to blame when a chain fails). Reachable at `/studio`; runs are submitted through `/studio/run`.

<!-- BEGIN GENERATED physical-capabilities -->
### Physical and map SKUs

Generated from ATLAS STATION_CATALOG + LAYER_META + PRODUCT_CAPS — do not hand-edit. Run: python3 scripts/sync_knowledge_base.py --write. Live Hub search is the ceiling (GET https://modelmarket.dev/ai-market/v2/search). This table is the floor. Do not invent SKUs absent here or from Hub search. LIVE only with provenance source. Never present SIM as LIVE. Physical/map SKUs are Hub invoke, not oracle_call.

GAIA (iot.modelmarket.dev) — device_id-anchored, ~$0.002 unless noted.

| SKU | layer | example devices | honest limit |
|---|---|---|---|
| gaia.weather.read@v1 | weather (Weather) | om-wx-01, nws-01, cwop-01, metno-01 +31 | operator-anchored device_id; LIVE only with provenance source |
| gaia.air.read@v1 | air (Air quality) | om-aq-01, osm-01, sta-01, sc-01 +22 | operator-anchored device_id; LIVE only with provenance source |
| gaia.tide.read@v1 | tide (Tide) | noaa-tide-01, uhslc-01, noaa-tide-sf, noaa-tide-honolulu +6 | operator-anchored device_id; LIVE only with provenance source |
| gaia.grid.read@v1 | grid (Grid carbon) | uk-grid-01 | operator-anchored device_id; LIVE only with provenance source |
| gaia.quake.read@v1 | quake (Earthquakes) | usgs-quake-01, geonet-01, emsc-01 | operator-anchored device_id; LIVE only with provenance source |
| gaia.river.read@v1 | river (Rivers) | usgs-river-01, eccc-hydro-01, smhi-hydro-01, usgs-river-colorado +6 | operator-anchored device_id; LIVE only with provenance source |
| gaia.marine.read@v1 | marine (Marine) | ndbc-01, om-marine-01, ndbc-monterey, ndbc-sf +11 | operator-anchored device_id; LIVE only with provenance source |
| gaia.fire.read@v1 | fire (Wildfire) | firms-fire-01 | cite NASA FIRMS; not a fire perimeter |
| gaia.radiation.read@v1 | radiation (Radiation) | safecast-01, safecast-tokyo, safecast-sf, safecast-denver +10 | operator-anchored device_id; LIVE only with provenance source |
| gaia.jamming.read@v1 | jamming (GNSS jamming) | cybernews-jam-01 | CyberNews GNSS CC BY 4.0; not GPSJam; not RF sensing |
| gaia.gnss.integrity.read@v1 | gnss (GNSS integrity) | gnss-euref-01, gnss-ga-01 | operator-anchored device_id; LIVE only with provenance source |
| gaia.adsb.read@v1 | traffic (Edge traffic) | feeder-adsb-01 | own-edge dump1090; opt-in; offline until ingest |
| gaia.ais.read@v1 | traffic (Edge traffic) | feeder-ais-01 | own-edge feeder; not Fintraffic public AIS |
| gaia.iot.read@v1 | iot (Edge IoT) | feeder-iot-01 | own-edge Tasmota/TTN/SenML; opt-in |
| gaia.events.read@v1 | events (Natural events) | eonet-01 | operator-anchored device_id; LIVE only with provenance source |
| gaia.spacewx.read@v1 | spacewx (Space weather) | swpc-01 | NOAA SWPC Kp; Boulder pin, planetary index |
| gaia.lightning.read@v1 | lightning (Lightning) | glm-01 | GOES GLM CONUS; not Blitzortung |
| gaia.alerts.read@v1 | alerts (Weather alerts) | nws-alerts-01 | operator-anchored device_id; LIVE only with provenance source |
| gaia.argo.read@v1 | argo (Argo floats) | argo-01 | official GDAC floats; cite DOI 10.17882/42182 |
| gaia.geomag.read@v1 | geomag (Geomagnetism) | usgs-geomag-01, usgs-geomag-brw, usgs-geomag-bsl, usgs-geomag-cmo +10 | USGS F only; not INTERMAGNET |
| gaia.flood.read@v1 | flood (Flood) | nws-flood-01, ea-flood-01 | NWS CAP US and/or UK EA OGL England; not GloFAS; not an in-situ gauge |
| gaia.effis.read@v1 | effis (EFFIS fires) | effis-01 | Copernicus EFFIS EU, CC BY 4.0; not FIRMS |
| gaia.volcano.read@v1 | volcano (Volcanoes) | usgs-volcano-01 | USGS elevated volcanoes; not a global ash forecast |
| gaia.ais.public.read@v1 | ais (Public AIS) | fintraffic-ais-01, kystverket-ais-01 | Fintraffic CC BY 4.0 (FI) or Kystverket NLOD (NO); not own-edge gaia.ais.read |
| gaia.tsunami.read@v1 | tsunami (Tsunami alerts) | nws-tsunami-01, ptwc-01 | NWS CAP and/or PTWC Atom warning product, not a tide gauge; empty = offline |
| gaia.cyclone.read@v1 | cyclone (Tropical cyclones) | nhc-cyclone-01 | NHC/CPHC AL+EP+CP only; not JTWC; not EONET; empty season = offline |
| gaia.adsb.public.read@v1 | adsb (Public ADS-B) | adsb-lol-01 | ADSB.lol ODbL 1.0; isolate derived DB; not own-edge; no OpenSky/ADSBx fallback |
| gaia.smoke.read@v1 | smoke (Smoke) | hms-smoke-01 | full signed polygon rings + holes, not just centroids; qualitative density, not PM2.5 |
| gaia.water_quality.read@v1 | water_quality (Water quality) | usgs-wq-01 (bbox → complete qualified station registry) | fresh (48h default) paginated latest-continuous observations joined to the official USGS monitoring-locations registry; filters and per-series approval/qualifiers; one station = one coordinate |
| gaia.precipitation.read@v1 | precipitation (Precipitation) | imerg-01 + buyer lat/lon | any buyer coordinate; returned IMERG source cell; preliminary |
| gaia.radar.status.read@v1 | radar (NEXRAD status) | nexrad-status-01 (all WSR-88D sites) | all WSR-88D sites returned at their own coordinates; status, not reflectivity |
| gaia.sea_ice.read@v1 | sea_ice (Sea ice) | nsidc-ice-01 + buyer Arctic lat/lon | any Arctic buyer coordinate; returned exact 25-km cell; not for navigation |
| gaia.energy.read@v1 | energy (Energy) | em-01 | operator-anchored device_id; LIVE only with provenance source |
| gaia.atmosphere.read@v1 | atmosphere (Atmosphere) | cams-* + buyer lat/lon | any buyer coordinate; CAMS data CC BY 4.0; commercial hosting required |
| gaia.dart.read@v1 | dart (DART gauges) | noaa-dart-01, dart-* (all 43 active) | all active stations in the NDBC directory; gauge, not a tsunami warning |
| gaia.radnet.read@v1 | radnet (EPA RadNet) | radnet-* (all 140 official monitors) | all 140 official EPA monitor coordinates; cite EPA RadNet |
| gaia.soil_moisture.read@v1 | soil (Soil moisture) | soil-* + buyer lat/lon | any buyer coordinate; returned CLMS source/query cell |
| gaia.solar.read@v1 | solar (Solar irradiation) | solar-* + buyer lat/lon | any buyer coordinate; returned NASA POWER source coordinate |
| gaia.snow.read@v1 | snow (Snowpack) | snow-* + buyer CONUS lat/lon | any buyer coordinate in CONUS; returned exact SNODAS cell |
| gaia.land_temperature.read@v1 | land_temperature (Land temperature) | lst-* + buyer lat/lon | any buyer coordinate; returned Sentinel-3 SLSTR source cell |

GAIA plumbing (not a map pin)

| SKU | artifact |
|---|---|
| gaia.window@v1 | N readings of one device_id in one invoke |
| gaia.verify@v1 | plausibility verdict as a sellable good |
| gaia.fleet.status@v1 | device registry incl. pinned pubkeys — free |

ATLAS composites (atlas.modelmarket.dev) — billable decision artifacts.

| SKU | USD | artifact |
|---|---|---|
| atlas.watchbox.check@v1 | 0.02 | Evaluate an ATLAS watchbox (bbox + layers) against the live fleet snapshot |
| atlas.fire.weather@v1 | 0.08 | FIRMS and/or EFFIS + nearby weather; two lists; not a forecast |
| atlas.smoke.operations@v1 | 0.12 | point-in-polygon against the signed HMS ring + colocated PM2.5/AQI; refuses on a truncated inventory; not measured PM2.5 and not an evacuation order |
| atlas.situation.brief@v1 | 0.06 | defaults include flood/EFFIS/lightning/volcano/alerts/events/AIS/tsunami/cyclone/ADS-B; not spacewx/geomag/argo |
| atlas.nearest.read@v1 | 0.03 | Nearest LIVE ATLAS pin(s) to a lat/lon on allowlisted layers |
| atlas.point.read@v1 | 0.01 | Read one exact clickable ATLAS map object by stable point_id |
| atlas.geomag.window@v1 | 0.05 | SWPC planetary Kp → NOAA state/G-scale + nearest USGS observatory F; total field only, NOT a declination correction and not safety-of-life |
| atlas.pv.irradiance.record@v1 | 0.15 | NASA POWER daily all-sky vs clear-sky + CAMS aerosol/dust at the plant coordinate; a retrospective record of fact, NOT a yield forecast or a soiling-loss model |
| atlas.route.integrity@v1 | 0.25 | per-segment corridor brief: GNSS field + reported interference zones + AIS/ADS-B presence + hazard pins; reported interference is NOT proof of jamming, not safety-of-life |
| atlas.observability.attest@v1 | 0.10 | data-availability attestation: nearest NEXRAD + ARCHIVED status samples in a window; an archive gap is absence of evidence, NOT evidence the radar was down; U.S. only |
| atlas.gnss.degradation.read@v1 | 0.05 | GNSS integrity field for a point, bbox, or route |

Map layers (39): weather=Weather; air=Air quality; tide=Tide; river=Rivers; marine=Marine; grid=Grid carbon; quake=Earthquakes; energy=Energy; fire=Wildfire; radiation=Radiation; jamming=GNSS jamming; gnss=GNSS integrity; traffic=Edge traffic; events=Natural events; spacewx=Space weather; lightning=Lightning; alerts=Weather alerts; argo=Argo floats; geomag=Geomagnetism; iot=Edge IoT; flood=Flood; effis=EFFIS fires; volcano=Volcanoes; ais=Public AIS; tsunami=Tsunami alerts; cyclone=Tropical cyclones; adsb=Public ADS-B; smoke=Smoke; water_quality=Water quality; dart=DART gauges; precipitation=Precipitation; radar=NEXRAD status; atmosphere=Atmosphere; radnet=EPA RadNet; soil=Soil moisture; solar=Solar irradiation; snow=Snowpack; sea_ice=Sea ice; land_temperature=Land temperature

<!-- END GENERATED physical-capabilities -->

<!-- BEGIN GENERATED ecosystem-components -->
### Component registry

Generated from scripts/satellite-map.yaml — do not hand-edit. GitHub org: alexar76.
Run: python3 scripts/sync_knowledge_base.py --write (47 components).

- acex: ACEX — Agent Capital Exchange: listings, CapShares, lending, and AMM for AI agents. · https://alexar76.github.io/aicom/
- ai-service-mesh: AI Service Mesh — autonomous agent discovery, verification, escrow, and payments. · https://service-mesh.modelmarket.dev/
- aicom (profile README): AI-Factory — autonomous pipeline that designs, builds, tests, and publishes products. · https://magic-ai-factory.com/
- aicom-landing: AI landing generator — one prompt → self-contained HTML in ~30-60s (MIT, 20 style presets). · https://magic-ai-factory.com/landing-page-generation/
- aicom-products: Selective catalog of full AI-Factory products (prod-*) — shell from monorepo, trees published on demand. · https://github.com/alexar76/aicom-products
- aicom-wiki (repo aicom.wiki): Documentation wiki for AI-Factory and the AIMarket ecosystem.
- aimarket-agent: Python client for discovering and invoking AIMarket hub capabilities. · https://alexar76.github.io/aicom/
- aimarket-bridges: AIMarket capabilities as native tools for LangChain/LangGraph, CrewAI, AutoGen and Microsoft Agent Framework — signed receipts, per-task budget caps, free trial. The adapter layer for agents built on someone else's framework. · https://modeldev.modelmarket.dev/bridges/
- aimarket-courses: 10 hands-on AIMarket academy courses — orchestration, oracles, MCP security, agent economy (en/ru/es/fr/zh). · https://alexar76.github.io/aimarket-courses/
- aimarket-desktop: 10 desktop & IDE apps for AIMarket — Flutter, Tauri, and VS Code in one Melos monorepo. · https://alexar76.github.io/aicom/
- aimarket-hub: AIMarket Hub — federated capability catalog, channels, invoke API, and plugins. · https://modelmarket.dev/
- aimarket-mcp: Ecosystem MCP gateway — web fetch/search + Metis verify behind one SSRF-hardened MCP endpoint (Streamable-HTTP). Consumed by Metis and ARGUS via the aimarket-web preset. · https://glama.ai/mcp/servers/alexar76/aimarket-mcp
- aimarket-oracle-gateway: MCP server: verifiable oracle services (Platon VRF, Chronos VDF, LUMEN reputation) for AI agents — pay-per-call over the AIMarket protocol, every result independently verifiable. · https://glama.ai/mcp/servers/alexar76/aimarket-oracle-gateway
- aimarket-playground: Zero-setup guided AIMarket golden path: GAIA invoke, Metis verification, signed Hub receipt, and Alien Monitor handoff. · https://play.modelmarket.dev/
- aimarket-plugins: 15 AIMarket hub plugins — TEE escrow, channels, reputation, safety, and more. · https://alexar76.github.io/aicom/
- aimarket-protocol: AIMarket Protocol v2 — open specs, JSON schemas, and test vectors. · https://alexar76.github.io/aicom/
- aimarket-school: AIMarket School — 10 free clip lessons (Try-it + Colab) that on-ramp into the academies. Live portal: edu.modelmarket.dev · https://edu.modelmarket.dev/
- aimarket-sdks: Official AIMarket client SDKs — Dart, TypeScript, and Rust. · https://alexar76.github.io/aicom/
- aimarket-widget: Embeddable AIMarket storefront widget — drop-in JS/CSS for any website. · https://modelmarket.dev/widget/demo
- alien-monitor: Alien Monitor — real-time 3D ecosystem pulse visualizer with AI assistant. · https://monitor.modelmarket.dev/
- argus: ARGUS-3 — wallet-native, security-hardened personal agent; demand-side reference client and the reference host for the WARDEN MCP firewall (@aimarket/warden, a separate package) plus native AIMarket consumer/provider. Owner-locked Telegram, multi-provider, autonomous offline. · https://magic-ai-factory.com/argus/
- argus-wiki (repo argus.wiki): Documentation wiki for ARGUS-3 — install, WARDEN, channels, economy, Arena.
- atlas: Planetary sensor map over GAIA (weather, air, fire, flood, lightning, alerts, EFFIS, volcano, GNSS jamming, and other LIVE/SIM layers) plus Hub-sold composites atlas.situation.brief@v1 (defaults to map layers), atlas.fire.weather@v1 (FIRMS and/or EFFIS), atlas.nearest.read@v1, atlas.watchbox.check@v1. ATLAS maps and sells geo artifacts; GAIA attests raw reads. · https://alexar76.github.io/atlas/
- basanos: Lydian touchstone for ecosystem Solidity. Emits an Ed25519-signed assurance pack (PASS/REVIEW/FAIL) pinned to a commit/tree digest. Learns detector order from allowlisted OSV/GHSA only — intel cannot add detectors or emit scoreBps. Not HEPHAESTUS (forge.modelmarket.dev is that landing), not AgentAuditPool, not MOMUS, not THEMIS. · https://basanos.modelmarket.dev · port 9470
- create-aimarket-agent: Standalone CLI that scaffolds tested AIMarket Protocol v2 capability providers with manifests and Docker packaging. · https://alexar76.github.io/create-aimarket-agent/
- dioscuri: DIOSCURI — one mind, two heavens. Twin community agents: CASTOR rides Telegram, POLLUX holds Discord. Shared GitHub-synced knowledge base (MNEMOSYNE) behind a prompt-injection firewall + moderation shield (AEGIS). · https://alexar76.github.io/dioscuri/
- dolos: DOLOS — dynamic EVM red team for the UNI bubble: fork-isolated exploit txs, Ed25519 findings, sandbox fix-loop only. · https://dolos.modelmarket.dev/
- escrow-signer: HORKOS holds the only key authorized in AIMarketEscrow.authorizedHubs, so the Hub does not — one allowed selector, one escrow, one chain, and the buyer's own EIP-712 signature as the authority for every amount. · https://alexar76.github.io/escrow-signer/
- gaia: Physical oracle: attested gaia.*.read@v1 SKUs (weather, fire/FIRMS, lightning/GLM, flood/NWS CAP, EFFIS, volcano, EONET, SWPC, GNSS jamming, …) plus window/verify. LIVE only with provenance source; Hub search then invoke — not oracle_call. · https://iot.modelmarket.dev · port 9320
- helios: HELIOS — self-hosted broadcast pipeline for the AIMarket ecosystem. Template in, voiced video out, queued to YouTube — private by default until you approve. · https://alexar76.github.io/helios/
- hephaestus: The forge — compose capability chains from the live signed Hub catalogue, estimate cost and latency BEFORE spending, run pipelines through the factory executor, and keep a signed bill of materials with hop-level blame. Studio UI is hub-served; core library is framework-free. · https://modelmarket.dev/studio
- linkedin-profile-coach (repo linked-in-profile-coach): LinkedIn Profile Coach — Flutter desktop/mobile app for 24 LinkedIn sections, AI draft, scoring, and .docx resume support. · https://alexar76.github.io/linked-in-profile-coach/
- logos: Read-only federation intelligence: periodic source snapshots across Hub, MOMUS, Treasury, SKOPOS and Metis, rolling z-score anomaly detection over them, and cross-system correlation. It observes and explains; it never acts on what it finds. · https://logos.modelmarket.dev · port 9460
- lottery: AI-Agent Oracle Lottery — an on-chain lottery that is an economic actor of the AI ecosystem: agents buy tickets, an unbiasable Platon+Chronos oracle beacon draws a LUMEN-reputation-weighted winner. · https://lottery.modelmarket.dev/
- metis: Cognitive verification tier: Understanding Council, fail-closed confidence gate, layered MoA, grounded verifier. Also available to MOMUS as an independent external verifier of a finding. · https://metis.modelmarket.dev
- momus: Adversarial-audit red team. Runs safe, read-only conformance probes against the ecosystem's own components and emits Ed25519-signed findings. It FINDS and SIGNS but can never pay itself — a separate Treasury key releases bounties, and only on independent verification. Honest outcomes: FINDING / NO_FINDING / INCONCLUSIVE (an unreachable target is neither a finding nor a pass). · https://momus.modelmarket.dev · port 9410
- oracles: Verifiable AI-economy oracles — Platon, Chronos, Lattice, Murmuration, Lumen, Colony, and Turing on shared oracle-core. · https://oracles.modelmarket.dev/
- platon: Platon UMBRAL — educational cave app for oracle #1: 32D dynamical shadow oracle with live AIMarket backend and holographic cockpit. · https://oracles.modelmarket.dev/platon/umbral/
- profile (repo alexar76) (profile README): GitHub profile README — ecosystem map for alexar76. · https://github.com/alexar76
- pulse-terminal: Pulse Terminal — ACEX capital markets dashboard with live agent pricing. · https://magic-ai-factory.com/pulse/
- signal-hunt: Federation-native investigation game and educational laboratory over real Hub telemetry: observe measured symptoms, commit a diagnosis, prove it with a reproducible Brier-score verdict. Live data only — no seeded anomalies. · https://hunt.modelmarket.dev
- skopos: Fleet observability dashboard, and the CONDUCTOR of the remediation loop: it receives MOMUS's signed ticket over A2A, drives the AI-Factory to author a patch, asks MOMUS to re-test as the deploy gate, then signs a DeployOrder and publishes it for the addressed node agent to claim. It orders deploys; it never executes one. · https://skopos.modelmarket.dev
- themis: THEMIS — publish-time admission gate for AIMarket: signed approve/review/reject for AI-agent supply-chain procurement (not Metis, not WARDEN). · https://alexar76.github.io/themis/
- theoros: THEOROS — Agent Sovereignty Canon. High-tech theorist persona: seven precepts for verified agent economic actors, cosmic landing, weekly column via DIOSCURI #the-canon. · https://alexar76.github.io/theoros/
- treasury: The only key that can pay a red-team bounty. A separate role with its own key: MOMUS finds and signs, the Treasury verifies the signatures, recomputes the dedup identity, and releases the finder/fixer/conductor split (50/35/15). Default settlement is the simulated UNI vault; real on-chain payout needs a second, explicit opt-in beyond enabling crypto. · https://momus.modelmarket.dev/treasury · port 9411
- use-cases-portal: AIMarket use-cases portal — public wow, onboarding (See·Buy·Publish·Build·Invest), live rails, and 7 direction boards with 12 idea pages (3D previews). Static site, five languages, honest LIVE vs SIM. Live host use.modelmarket.dev; Pages landing (docs/landing/) at alexar76.github.io/use-cases-portal. · https://use.modelmarket.dev/
- warden: WARDEN — MCP security firewall: vets an MCP server's tool definitions against static-scan rules, a signed threat feed, origin and tool-def pinning before any tool reaches the model. Zero-dependency TypeScript library. · https://warden.modelmarket.dev
<!-- END GENERATED ecosystem-components -->
