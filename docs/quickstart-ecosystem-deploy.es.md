# Desplegar todo el ecosistema — guía rápida desde cero

Un runbook por niveles para levantar el ecosistema público completo sobre un VPS Ubuntu limpio.
Envuelve los scripts de despliegue existentes — **no** introduce un nuevo motor de despliegue.
Empieza en el nivel que necesites y detente ahí; cada nivel se apoya en el anterior.

Para la referencia de nivel operativo (redespliegues parciales, el peligro del redespliegue del
Hub, el orden manual exacto de los pasos), consulta **[`deploy-ecosystem.md`](./deploy-ecosystem.md)**.

---

## 1. Qué es "el ecosistema"

| Componente | Qué hace | Contenedor / proceso |
|-----------|--------------|---------------------|
| **Factory** | Construye y publica productos de IA (el stack Compose `aicom-app`) | `aicom-app-1` |
| **Hub** | Hub de federación de AIMarket Protocol v2 — discovery, channels, invoke, settle | `modelmarket-hub` |
| **Mesh** | API de service-mesh que conecta los productos entre sí | `aicom-mesh-api` |
| **ARGUS-3** | Agente personal + firewall MCP WARDEN (cliente de referencia) | `argus` / `:8787` |
| **Alien Monitor** | Visualizador 3D del ecosistema (modos UNIVERSE / TEST / REAL) + terminal **Pulse** | `alien-monitor`, Pulse |
| **Lottery relayer** | Relayer UNI para Monitor LIVE (opcional; paso puede WARN) | `:9195` |
| **Ecosystem landing** | Mapa público en [modeldev.modelmarket.dev](https://modeldev.modelmarket.dev) | nginx / paso 7 |
| **Oracles** | Diecisiete oráculos en [oracles.modelmarket.dev](https://oracles.modelmarket.dev) (+ UMBRAL) | **host separado (L4)** |
| **On-chain** (opcional) | Contratos de Base-mainnet: Escrow, NFT de capability, Agent Lottery | despliegue con Foundry |

**No incluido en `deploy_ecosystem.sh`:** Metis, DIOSCURI, HELIOS — por separado; ver [§Qué no incluye un VPS](#9-qué-no-incluye-un-vps).

Los cuatro niveles de onboarding:

| Nivel | Objetivo | Un solo comando |
|-------|------|-------------|
| **L1** | Probarlo en local (solo Factory) | `./scripts/quickstart.sh` |
| **L2** | Autohospedar **core fleet** en un VPS | `./scripts/quickstart_ecosystem.sh` o `./scripts/deploy_ecosystem.sh` |
| **L3** | Producción pública (DNS + TLS + verify) | `./scripts/quickstart_ecosystem.sh --public-url https://…` |
| **L4** | Host de oráculos (**máquina separada** por defecto) | `./scripts/setup-oracles-platon-on-host.sh` |

El modelo de autenticación para *consumir* el Hub es **Ed25519** (el SDK firma cada invoke; la clave
de la cartera (wallet) es una semilla Ed25519 de 32 bytes, no una clave de Ethereum). secp256k1/EIP-712 es
opcional y solo se usa para los débitos de channel on-chain. Consulta la
[documentación del SDK de AIMarket](https://github.com/alexar76/aimarket-sdks/blob/main/docs/en.md) y el
[agente Python](https://github.com/alexar76/aimarket-agent/blob/main/docs/en.md) (stateless, sin cartera) para el lado del consumidor.

---

## 2. Requisitos previos

En el VPS Ubuntu de destino, antes de cualquier nivel:

- **Docker Engine + Compose v2** (`docker compose`, no el antiguo `docker-compose`).
- **nginx** — terminación TLS y proxy inverso (niveles 3–4).
- **Registros DNS A/AAAA** apuntando al host donde ejecutas (nivel 3+):
  - `magic-ai-factory.com`, `www.magic-ai-factory.com` → host de Factory
  - `modelmarket.dev`, `www.modelmarket.dev` → host de Factory
  - `oracles.modelmarket.dev` → **host de oráculos** (`oracles.modelmarket.dev`), directamente (sin proxy de factory)
- **Un `.env` poblado** en la raíz del repo. Copia `.env.example` y define al menos una clave de LLM:

```bash
cp .env.example .env
# then set, e.g.:
#   DEEPSEEK_API_KEY=...
#   ANTHROPIC_API_KEY=...
# optional port overrides:
#   AICOM_PORT_FRONTEND=9080
#   AICOM_PORT_API=9081
```

Para las claves de LLM, prefiere secretos en archivo (`data/secrets/llm/<provider>_api_key` + el
overlay `docker-compose.secrets.yml`) antes que entradas `environment:` en línea — consulta los
comentarios en `.env.example`.

---

## 3. Nivel 1 — Probarlo en local

Solo Factory. Construye la imagen, levanta el stack y encola un producto de demostración de extremo a extremo:

```bash
./scripts/quickstart.sh                      # build + run + landing demo
./scripts/quickstart.sh --no-build           # reuse the existing image
./scripts/quickstart.sh "Your product idea"  # full_software profile from your idea
```

Qué hace: `./run.sh` (build) → run → `./demo.sh --no-open` (encola un producto de demostración).
Sigue el progreso en **Admin → Pipeline** en `http://localhost:9080`. En
`docs/sample-output/build-replay-spliteasy.json` hay una repetición de un build de muestra sin Docker.

---

## 4. Nivel 2 — Core fleet en un VPS

**Wrapper recomendado** (preflight Docker + `.env` + deploy):

```bash
./scripts/quickstart_ecosystem.sh
./scripts/quickstart_ecosystem.sh --skip-verify
./scripts/quickstart_ecosystem.sh --public-url https://…
```

Llama a **`scripts/deploy_ecosystem.sh`**. Orden de pasos:

1. **Factory** — `./scripts/deploy.sh`
2. **Hub** — `./scripts/deploy_hub.sh`
3. **Mesh** — `./scripts/deploy_mesh.sh`
4. **ARGUS-3** — `./scripts/deploy_argus.sh` (`:8787`)
5. **Alien Monitor + Pulse** — `./scripts/deploy_alien_monitor.sh`
6. **Relayer UNI** — `./scripts/deploy_lottery_uni.sh` (no fatal)
7. **Ecosystem landing** — `./scripts/deploy_ecosystem_landing.sh` (no fatal)

Luego calentamiento de Factory y `./scripts/verify_ecosystem_full.sh` (**17+ checks**) salvo `--skip-verify`.

### Puertos (host)

| Servicio | Puerto de host | Salud / entrada |
|---------|-----------|----------------|
| Factory API | `:9081` | `GET /api/health` |
| Factory UI (frontend) | `:9080` | `GET /` |
| Hub | `:9083` | `GET /.well-known/ai-market.json` |
| Mesh | `:8090` | `GET /v1/stats` |
| ARGUS | `:8787` | `GET /health` |
| Alien Monitor | `:9100` | `GET /api/health` |
| Terminal Pulse | `:5199` | `GET /` |
| Relayer de la lotería UNI | `:9195` | `GET /healthz` |
| Ecosystem landing | nginx | `https://modeldev.modelmarket.dev/` (tras TLS L3) |

> **El puerto público de la UI es `:9080`, no el antiguo `:8080`.** nginx hace de proxy del dominio
> público hacia `127.0.0.1:9080`.

Flags:

```bash
./scripts/deploy_ecosystem.sh --skip-verify   # faster; skips the smoke suite (not for prod)
```

---

## 5. Nivel 3 — Producción pública

### 5.1 Apuntar el DNS

Los registros A/AAAA de `magic-ai-factory.com`, `www.magic-ai-factory.com`, `modelmarket.dev`
y `www.modelmarket.dev` deben resolver a este host **antes** de emitir los certificados.

### 5.2 Desplegar con la URL pública incorporada

```bash
./scripts/deploy_ecosystem.sh --public-url https://magic-ai-factory.com
```

`--public-url` se reenvía a `deploy.sh` para que `NEXT_PUBLIC_SITE_URL` quede definido en el build
de Next.js (Open Graph, sitemap, metadatos del lado del servidor). Si TLS aún no está activo, puedes
usar primero `http://magic-ai-factory.com` y luego reconstruir la imagen de la app cuando HTTPS esté listo.

### 5.3 Pasos únicos de TLS (ejecutar como root)

**vhost del Hub + AIMarket Hub + Let's Encrypt** para `modelmarket.dev`:

```bash
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-modelmarket-ssl.sh
```

Esto instala `deploy/nginx/modelmarket.dev.conf`, construye `modelmarket-hub:latest` desde el
contexto de la **raíz del repo**, ejecuta el hub en `127.0.0.1:9083`, habilita `certbot.timer` y
emite el certificado para `modelmarket.dev` + `www.modelmarket.dev`.

**vhost de Factory** para `magic-ai-factory.com` (según [`production-domain.md`](./production-domain.md)):

```bash
sudo cp deploy/nginx/magic-ai-factory.com.conf /etc/nginx/sites-available/magic-ai-factory.com
sudo ln -sf /etc/nginx/sites-available/magic-ai-factory.com /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

sudo certbot --nginx \
  -d magic-ai-factory.com -d www.magic-ai-factory.com \
  --non-interactive --agree-tos --redirect \
  -m YOUR_EMAIL@example.com
```

Una vez que HTTPS esté activo, define `NEXT_PUBLIC_SITE_URL=https://magic-ai-factory.com` en `.env`
y reconstruye para que el bundle lo recoja:

```bash
docker compose build app --no-cache
docker compose up -d
```

El Alien Monitor público se sirve en `https://magic-ai-factory.com/monitor/` (nginx hace de proxy de
`/monitor/` → `127.0.0.1:9100`; `deploy_alien_monitor.sh` parchea el vhost de Certbot en vivo si falta el bloque).

### 5.4 Verificar

```bash
./scripts/verify_ecosystem_full.sh
```

Espera **`17/17 PASS`**.

---

## 6. Nivel 4 — Host de oráculos

Los oráculos se ejecutan en una **máquina aparte** (`oracles.modelmarket.dev`). **`deploy_ecosystem.sh` NO
despliega oráculos ni Platon** — `oracles/` y `platon/` en este monorepo son réplicas de archivo del
stack externo. Configúralos en el host de Platon y luego fedéralos desde el host de Factory.

### 6.1 En el host de Platon (`oracles.modelmarket.dev`, como root)

La app de Platon ya debe estar escuchando en `127.0.0.1:8080` con
`PUBLIC_URL=https://oracles.modelmarket.dev`. Luego:

```bash
sudo CERTBOT_EMAIL=you@example.com ./scripts/setup-oracles-platon-on-host.sh
```

Esto instala `deploy/nginx/oracles.modelmarket.dev.conf`, verifica Platon en
`127.0.0.1:8080/api/health` y emite el certificado para `oracles.modelmarket.dev`.

### 6.2 Desde el host de Factory — federar

```bash
./scripts/announce-platon-oracles.sh
```

Esto lee el token de admin (`data/secrets/aimarket_admin_token.txt`), hace POST a
`/ai-market/v2/federation/announce` en el hub local (`:9083`) con la URL well-known de Platon y la
clave pública del firmante, y luego dispara un crawl de federación.

Verifica el host de oráculos:

```bash
curl -s https://oracles.modelmarket.dev/.well-known/ai-market.json | jq '{hub_url, manifest_url, capabilities_count}'
curl -s https://oracles.modelmarket.dev/api/health | jq '{status, kappa, order_parameter}'
```

Los diecisiete oráculos (Platon, Chronos, Lattice, Murmuration, Lumen, Colony, Turing, Percola, Fermat, Ablation, Landauer, Sortes, Gauss, Aestus, Betti, Kantor, Fourier) y el bucle
económico están documentados en [`oracles/docs/en.md`](https://github.com/alexar76/oracles/blob/main/docs/en.md).

---

## 7. Opcional — On-chain (Base, chain 8453)

Se mantiene **separado** de la orquestación de contenedores. Estos despliegan contratos Solidity en
Base mainnet con Foundry. Ambos hacen por defecto un dry run sin gas; pasa `broadcast` para gastar gas real.

**Núcleo del ecosistema** — FakeUSDT + `AIMarketEscrow` + `AIMarketCapabilityNFT`
(ACEX se excluye a propósito — la auditoría marcó AuditPool TWAP + PulseAMM como HIGH):

```bash
./scripts/deploy_ecosystem_base.sh            # dry-run (no gas)
./scripts/deploy_ecosystem_base.sh broadcast  # real deploy
```

**Agent Lottery** — `AIAgentLottery` (boletos en ETH nativo; admin/governance/treasury fijados a
`OWNER` en el despliegue):

```bash
./scripts/deploy_lottery_base.sh              # dry-run (simulate, NO gas)
./scripts/deploy_lottery_base.sh broadcast    # real deploy
```

Ambos leen la clave burner desde `$BURNER_KEYFILE` (por defecto `~/.aicom-base-deployer.json`) y usan `BASE_RPC` (por defecto `https://mainnet.base.org`). El script ecosystem-core transfiere la propiedad de Escrow/NFT a `OWNER` en dos pasos tras un broadcast (`OWNER` debe luego llamar a `acceptOwnership`); la lotería, en cambio, fija admin/governance/treasury en `OWNER` durante el deploy, sin transferencia posterior. Son fondos reales — mantén los importes al mínimo.

---

## 8. Topología multi-host

```
┌──────────────────────────────────────────────┐      ┌────────────────────────────────────┐
│  FACTORY FLEET — modeldev.modelmarket.dev      │      │ ORACLE HOST — oracles.modelmarket.dev│
│                                                │      │                                      │
│  Factory  aicom-app-1        :9081 API/:9080 UI│      │  Platon Shadow Oracle  127.0.0.1:8080│
│  Hub      modelmarket-hub    :9083             │ fed  │  Oracle family (17 oracles)          │
│  Mesh     aicom-mesh-api     :8090             │◄────►│                                      │
│  ARGUS    reference agent    :8787             │ announce-platon-oracles.sh (factory)      │
│  Monitor  alien-monitor      :9100             │      │  oracles.modelmarket.dev           │
│  Pulse    terminal           :5199             │      │  NO en deploy_ecosystem.sh (L4)    │
│  Lottery relayer (UNI)       :9195             │      │                                      │
│  Landing  modeldev…          nginx             │      └────────────────────────────────────┘
│  magic-ai-factory.com  /  modelmarket.dev      │
└──────────────────────────────────────────────┘
```

`deploy_ecosystem.sh` / `quickstart_ecosystem.sh` cubren el **bloque izquierdo** (pasos 1–7).

---

## 9. Qué no incluye un VPS

| Componente | Por qué | Cómo añadir |
|-----------|---------|-------------|
| **17 oráculos** | Nivel L4 | `setup-oracles-platon-on-host.sh` |
| **On-chain Base** | opcional | `deploy_ecosystem_base.sh broadcast` |
| **Metis** | no en fleet script | deploy separado |
| **DIOSCURI / HELIOS** | satélites | repos aparte |
| **Prometheus** | opcional | `deploy_observability.sh` |

---

## 10. Verificar y operar

### Smoke completo (más de 17 checks)

```bash
./scripts/verify_ecosystem_full.sh
```

Comprueba el núcleo de Factory (`/api/health`, frontend `:9080`, `/api/products`, trust-metrics, el
almacén de seguridad, el lead del funnel, el dashboard de admin, el P&L de producto), el Hub
(`.well-known`, `stats/live`, pricing de capital), el Mesh (`/v1/stats`), Pulse (`:5199`), el Alien
Monitor (salud de UNIVERSE + sondas en proceso TEST/REAL/UNIVERSE) y la lotería UNI (el `evm_lottery`
desplegado, el `/healthz` del relayer, métricas de lotería en vivo). Sobrescribe los objetivos con
`FACTORY_URL`, `HUB_URL`, `MESH_URL`, `MONITOR_URL`, `PULSE_URL`, `LOTTERY_RELAYER_URL`.

### Redespliegues parciales

| Objetivo | Comando |
|------|---------|
| Solo Factory | `./scripts/deploy.sh` |
| Solo Hub | `./scripts/deploy_hub.sh` |
| Mesh + Monitor (stack de demo) | `./scripts/deploy_demo_stack.sh` (asume Factory + Hub ya activos) |
| Solo verificar | `./scripts/verify_ecosystem_full.sh` |

### Peligro del redespliegue del Hub — lee esto

> **NO uses el Compose de la subcarpeta para redesplegar el Hub.** Usa siempre `./scripts/deploy_hub.sh`.
>
> ```bash
> cd aimarket-hub && docker compose up -d --build   # WRONG — breaks image/context; Hub can disappear
> ```
>
> `deploy_hub.sh` construye desde la **raíz del monorepo** (`modelmarket-hub:latest`, contenedor
> `modelmarket-hub`), coincide con la configuración TLS de `setup-modelmarket-ssl.sh` y reemplaza el
> contenedor de forma segura. El archivo `aimarket-hub/docker-compose.yml` se conserva solo como
> referencia para desarrollo local. Nunca detengas/elimines `modelmarket-hub` sin ejecutar de
> inmediato `deploy_hub.sh`.

---

## 11. Documentación relacionada

- [`deploy-ecosystem.md`](./deploy-ecosystem.md) — referencia de operaciones (orden manual, redespliegues parciales)
- [`production-domain.md`](./production-domain.md) — nginx + TLS de `magic-ai-factory.com`
- [`production-modelmarket-dev.md`](./production-modelmarket-dev.md) — dominio del hub, DNS, host de oráculos
- [`oracles/docs/en.md`](https://github.com/alexar76/oracles/blob/main/docs/en.md) — los diecisiete oráculos y el bucle económico
- [Documentación del SDK de AIMarket](https://github.com/alexar76/aimarket-sdks/blob/main/docs/en.md) · [Agente Python](https://github.com/alexar76/aimarket-agent/blob/main/docs/en.md) — consume el Hub

---

🇬🇧 [English](./quickstart-ecosystem-deploy.md) · 🇷🇺 [Русский](./quickstart-ecosystem-deploy.ru.md) · 🇪🇸 [Español](./quickstart-ecosystem-deploy.es.md) · 🇫🇷 [Français](./quickstart-ecosystem-deploy.fr.md) · 🇨🇳 [中文](./quickstart-ecosystem-deploy.zh.md)
