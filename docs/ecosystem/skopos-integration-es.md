# SKOPOS — integración del ecosistema

**SKOPOS** ([`skopos/`](../../skopos/)) es el **satélite de observabilidad de flota** de AICOM: analítica nginx y Apache vía SSH, Security Center, historial de escaneos y un analista IA. Autoalojado (self-hosted); se recomienda PostgreSQL para producción.

> 🌐 Idiomas: [English](./skopos-integration.md) · [Русский](./skopos-integration-ru.md) · **Español** · [Français](./skopos-integration-fr.md) · [中文](./skopos-integration-zh.md)

---

## Superficies en vivo

| Superficie | URL | Rol |
|------------|-----|-----|
| **Panel** | [skopos.modelmarket.dev](https://skopos.modelmarket.dev) | UI de Streamlit (protegida con contraseña en producción) |
| **Estado público** | `GET /healthz` | JSON no secreto para Alien Monitor y sondas |
| **Alien Monitor** | [magic-ai-factory.com/monitor/](https://magic-ai-factory.com/monitor/) | Nodo del grafo 3D — haz clic en la esfera **SKOPOS** |

---

## Nodo Alien Monitor

| Env | Propósito |
|-----|-----------|
| `ALIEN_SKOPOS_URL` | Sondear `GET /healthz` (por defecto `https://skopos.modelmarket.dev`) |
| `ALIEN_PUBLIC_SKOPOS_URL` | Enlace del panel — URL del panel |
| `ALIEN_SKOPOS_GITHUB_URL` | Enlace de GitHub en el panel (por defecto `https://github.com/alexar76/skopos`) |

**Respuesta de health (no secreta):**

```json
{
  "ok": true,
  "service": "skopos",
  "version": "0.1.0",
  "database": "postgresql",
  "log_parsers": ["nginx", "apache"],
  "servers_monitored": 1,
  "requests_total": 4035,
  "security_score": 87
}
```

**Posición en el grafo:** repisa oeste cerca de Metis (`skopos` @ `-11.5, -3.5, 1.5`).  
**Aristas:** `factory → skopos` (telemetría de tráfico), `skopos → metis` (flota de hosts), `skopos → hub` (postura del ecosistema).

Haz clic en la esfera → **Open SKOPOS dashboard**, GitHub, docs, guía de integración. Las métricas muestran servidores monitorizados, total de solicitudes analizadas y security score — sin secretos.

---

## Despliegue en el nodo Metis

Stack de prueba de producción: [`metis/deploy/skopos-test/`](../../metis/deploy/skopos-test/).

```bash
cd metis/deploy/skopos-test
./remote-sync.sh
```

El vhost de Nginx `skopos.modelmarket.dev` está en [`metis/deploy/nginx.conf`](../../metis/deploy/nginx.conf) — proxy `:8501` (UI) y `:8502` (`/healthz`).

TLS (una vez que el DNS apunte al host Metis):

```bash
docker run --rm -v /opt/metis/deploy/letsencrypt:/etc/letsencrypt \
  -v /var/www/certbot:/var/www/certbot certbot/certbot certonly --webroot \
  -w /var/www/certbot -d skopos.modelmarket.dev --agree-tos -m you@example.com
docker restart metis-nginx
```

---

## Rutas del monorepo

| Ruta | Rol |
|------|-----|
| `skopos/` | Código fuente de la aplicación |
| `metis/deploy/skopos-test/` | Docker Compose + `servers.yaml` para el host Metis |
| `alien-monitor/backend/skopos_*.py` | Nodo del grafo + sondeo en vivo |
| `docs/ecosystem/skopos-integration.md` | Este archivo |

Repositorio del satélite: [alexar76/skopos](https://github.com/alexar76/skopos) — publica vía `./scripts/publish_all_repos.sh --satellite skopos`.

**Landing:** [skopos.modelmarket.dev](https://skopos.modelmarket.dev) (live) · [alexar76.github.io/skopos](https://alexar76.github.io/skopos/) (GitHub Pages, EN/RU/ES). Fuente: `skopos/docs/landing/index.html`. Workflow: `skopos/.github/workflows/pages.yml`.

---

## Independencia

SKOPOS no requiere Factory, Hub ni Metis en tiempo de ejecución. Alien Monitor se degrada con elegancia cuando `/healthz` es inalcanzable (el nodo muestra `offline`).

---

## Economía AIMarket (lado de la oferta opcional)

SKOPOS puede **vender inteligencia de flota** a otros agentes IA vía el [AIMarket Protocol v2](../../aimarket-protocol/spec.md) — el mismo patrón que Metis `/aimarket/invoke`.

**Desactivado por defecto.** Actívalo solo cuando quieras SKOPOS en la economía federada de agentes:

```bash
SKOPOS_AIMARKET_ENABLED=1
SKOPOS_AIMARKET_PUBLIC_URL=https://skopos.modelmarket.dev
# Optional: protect invoke with API key
SKOPOS_AIMARKET_API_KEY=your-secret
# Optional: auto-register capabilities on Hub at startup
SKOPOS_HUB_URL=https://modelmarket.dev
SKOPOS_AIMARKET_AUTO_REGISTER=1
SKOPOS_AIMARKET_PUBLISH_TOKEN=...
```

| Endpoint | Rol |
|----------|-----|
| `GET /.well-known/ai-market.json` | Descubrimiento |
| `GET /ai-market/v2/manifest` | Catálogo de capacidades |
| `POST /aimarket/invoke` | Contrato de invocación del hub `{input, product_id, capability_id}` → `{result}` |

### Capacidades facturables

| ID | Qué vende | ~USD/llamada |
|----|-----------|-----------|
| `skopos.fleet.status@v1` | Heartbeat + security score | $0.01 |
| `skopos.security.posture@v1` | Puntuación de flota, alertas, observaciones | $0.08 |
| `skopos.traffic.summary@v1` | Agregados de tráfico de 24 h | $0.05 |
| `skopos.briefing@v1` | Briefing de flota legible por humanos (reglas / LLM) | $0.15 |

ARGUS, Factory o Alien Monitor pueden **comprar** contexto de postura sin acceso SSH a tu flota.

### Modo consumidor (opcional)

Configura `SKOPOS_HUB_URL` para que SKOPOS pueda **descubrir** capacidades del hub (búsqueda gratuita). Las invocaciones de pago de SKOPOS a los oráculos requieren una integración de billetera (futuro); el modo autónomo ignora la ausencia del hub.

Nginx en Metis debe proxiar el puerto **8502** para `/healthz`, `/.well-known/*`, `/ai-market/*` y `/aimarket/invoke` (ver `metis/deploy/nginx.conf`).
