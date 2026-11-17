# Public texts: Agent Capital Exchange (not ACEX), AIMarket Work Receipt — live 2026-11-15 ~20:10–20:35Z

Owner, 2026-11-15: «ACEX — делай», «Да, выкатывай», AWR «да». Why: ACEX OY (Finland) is on the OFAC SDN list
(2020-09-23, E.O. 13694) and in US SAM exclusions; "Agent Capital Exchange" has no OpenSanctions match. "Agent Work
Receipt" is a generic phrase an unrelated v0.1 schema (useorgx) also uses. Source: main ffdc10e22, db2c06de7, bda43242f.
Code identifiers (acex_*, DeployACEX, /acex, awr/v2, awr:mtl:1) and on-chain records are unchanged.

| Surface | Host | What changed | Rollback |
|---|---|---|---|
| modeldev.modelmarket.dev/encyclopedia/{en,ru,es,fr,zh}/ | factory-vps | ACEX patched in the live HTML text nodes (not in script/style/code/pre); the live head (title, meta description) kept. Checked: patched live = fresh build except 4 head runs; 0 ACEX left, 7× full name per language | `tar -xzf /root/modeldev-encyclopedia-pre-acex-20261115.tgz -C /var/www/modeldev.modelmarket.dev` |
| attestedmemory.net (system node label) | attested, /opt/aicom/saas-landing (Caddy aicom-edge-1, ro mount) | index.html = main ffdc10e22 (live was exactly main before) | `cp -p /opt/aicom/saas-landing/index.html.pre-acex-20261115 /opt/aicom/saas-landing/index.html` |
| magic-ai-factory.com/pulse/ | factory-vps, container pulse-terminal | image aicom-security:pulse-terminal-acex-20261115 = FROM pulse-terminal-os-20261031 with the static files of a main build (app source identical to the live build's except the texts); bundle index-CeufKgOn.js | `docker rm -f pulse-terminal && docker rename pulse-terminal-prev pulse-terminal && docker start pulse-terminal` |
| @Argis3Bot (ARGUS knowledge) | attested, container argus | image aicom-security:argus-acex-text-20261115 = FROM argus-warden-0270-20261115 + dist/ecosystem/knowledge.js from main (7 lines differ: 6 ACEX, 1 newer mcp-tool-set-digest line); no purchase in progress; healthy, @Argis3Bot online | `cp -p /root/argus/docker-compose.roster.yml.before-argus-acex-text-20261115 /root/argus/docker-compose.roster.yml && docker compose --project-directory /root/argus -f /root/argus/docker-compose.yml -f /root/argus/docker-compose.roster.yml up -d --no-deps --no-build argus` |
| use.modelmarket.dev locales (AWR label) | competing-lab, /var/www/use.modelmarket.dev/locales | 5 locale files = main bda43242f (live was exactly main before) | `tar -xzf /root/use-locales-pre-awr-20261115.tgz -C /var/www/use.modelmarket.dev/locales` |

Not live yet: GitHub profile SVG/READMEs and satellite docs (mirror, colleague); PyPI `awr` and crates `awr`
descriptions (next release of each); ARGUS knowledge in the npm package (next ARGUS release — 0.4.0 went out at
17:42:34Z with the earlier text).
