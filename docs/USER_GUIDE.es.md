# Guía de usuario AI-Factory (detallada)

> **Para quién:** operadores de la fábrica, dueños de la instancia, soporte — vitrina, admin, pipeline.  
> **Idiomas:** [English](./USER_GUIDE.md) · [Русский](./USER_GUIDE.ru.md) · **Español** · [Français](./USER_GUIDE.fr.md) · [中文](./USER_GUIDE.zh.md) · **FAQ:** [FAQ.md](./FAQ.md) · [FAQ.ru.md](./FAQ.ru.md) · [FAQ.es.md](./FAQ.es.md) · [FAQ.fr.md](./FAQ.fr.md) · [FAQ.zh.md](./FAQ.zh.md)

> **Las capturas** están en [`docs/assets/screenshots/`](./assets/screenshots/). Si faltan `.png` en el clon — levante el stack y ejecute:
>
> ```bash
> cd web/frontend
> DOCS_SCREENSHOT_BASE_URL=http://127.0.0.1:9080 ADMIN_PASSWORD='su-contraseña' npm run capture-docs-screenshots
> ```

---

## Contenido

1. [Qué es este producto](#1-qué-es-este-producto)
2. [Chuleta: dónde mirar según la situación](#2-chuleta-dónde-mirar-según-la-situación)
3. [Primeros 15 minutos](#3-primeros-15-minutos)
4. [Vitrina pública (sin login)](#4-vitrina-pública-sin-login)
5. [Sitio de documentación `/docs`](#5-sitio-de-documentación-docs)
6. [Entrada a admin y seguridad](#6-entrada-a-admin-y-seguridad)
7. [Navegación por admin](#7-navegación-por-admin)
8. [Dashboard — instantánea de salud](#8-dashboard--instantánea-de-salud)
9. [Live Monitor — métricas en vivo](#9-live-monitor--métricas-en-vivo)
10. [New product — asistente y plantillas](#10-new-product--asistente-y-plantillas)
11. [Pipeline Monitor — pantalla de verdad](#11-pipeline-monitor--pantalla-de-verdad)
12. [Workshop — comparación y canvas](#12-workshop--comparación-y-canvas)
13. [Discovery — ideas antes del pipeline](#13-discovery--ideas-antes-del-pipeline)
14. [LLM Providers y LLM Logs](#14-llm-providers-y-llm-logs)
15. [Settings — toda la fábrica](#15-settings--toda-la-fábrica)
16. [Escenarios paso a paso](#16-escenarios-paso-a-paso)
17. [Errores en la UI — qué pulsar](#17-errores-en-la-ui--qué-pulsar)
18. [Índice de capturas](#18-índice-de-capturas)
19. [Documentos relacionados](#19-documentos-relacionados)

---

## 1. Qué es este producto

**AI-Factory** recibe una **idea breve en lenguaje natural** y la ejecuta por un **pipeline fijo de agentes** (analista → PM → arquitecto → desarrollador → QA → seguridad → DevOps → marketing → ventas → evolución).

| Superficie | URL | Rol |
|-------------|-----|------|
| Vitrina | `/` | Compradores, demo, marketing |
| Ficha de producto | `/product/{id}` | Estado público de un `prod-…` |
| Admin | `/admin` | Operador de la fábrica |
| Documentación en app | `/docs` | Mismo contenido que en el repositorio |

**Cinco términos imprescindibles:**

| Término | Significado |
|--------|----------|
| **Product** | Una fila del pipeline, id `prod-xxxxxxxx` |
| **State** | Etapa del pipeline (`IDEA_RECEIVED`, `COMPLETED`, `FAILED` …) — **no** es lo mismo que «visible en vitrina» |
| **Delivery profile** | `full_software` (producto completo), `marketing_landing` (solo landing), `infer` (auto) |
| **Sandbox** | Vista previa del código generado: `/api/sandbox/…` |
| **Storefront visible** | Pasó los gates de vitrina — aparte de `COMPLETED` |

---

## 2. Chuleta: dónde mirar según la situación

| Situación | Ir primero a | Qué mirar | Captura |
|----------|----------------|--------------|----------|
| «Nada carga en el navegador» | URL, `docker compose ps`, `/api/health` | Contenedor `app` healthy | — |
| «No puedo entrar a admin» | `/admin/login`, [security.md](./security.md) | `bootstrap_admin.txt`, no `admin123` | ![Login](./assets/screenshots/admin-login.png) |
| «Creé un producto — ¿dónde está?» | **Pipeline** | Buscar `prod-…`, orden *shipped first* | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| «Pipeline tarda Connecting / try N of 8» | **Pipeline** (espere hasta 5 min por intento) | Barra *Connection phase* = **reintentos HTTP**, no % catálogo; luego *N / total* | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| «Producto atascado en una etapa» | **Pipeline** → clic en ficha de agente | Tarea `running` / `failed`, `last_error` | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| «Agente falló con error LLM» | **LLM Providers** → **LLM Logs** | Claves, límites, timeout del modelo | ![Providers](./assets/screenshots/admin-providers.png) |
| «COMPLETED pero no en vitrina» | **Pipeline** → tarjeta → storefront gates | `storefront_gate_reasons`, quality, código en disco | ![Pipeline](./assets/screenshots/admin-pipeline.png) |
| «Necesito landing urgente» | **New product** → *Marketing landing page only* | `marketing_landing`, más rápido que full stack | ![New product](./assets/screenshots/admin-new-product.png) |
| «Comparar dos especificaciones» | **Workshop** → Material diff | Dos `prod-…` | ![Workshop](./assets/screenshots/admin-workshop.png) |
| «Ideas automáticas» | **Discovery** | Cola ranked ideas, auto-enqueue en Settings | ![Discovery](./assets/screenshots/admin-discovery.png) |
| «Primer arranque / URL / claves» | **Setup wizard** | Configuración paso a paso | ![Setup](./assets/screenshots/admin-setup.png) |
| «Salud general en 10 s» | **Dashboard** | KPI, tareas pending/running | ![Dashboard](./assets/screenshots/admin-dashboard.png) |
| «Cifras y escalaciones en vivo» | **Live Monitor** | SSE, Director, demo replay | ![Live Monitor](./assets/screenshots/admin-live-monitor.png) |
| «Comprador pregunta por producto» | **Support** / Lumen público (no pipeline) | Aparte de AI Agents | — |
| «Sesión caducada» | De nuevo **/admin/login** | 401 → JWT caducado | ![Login](./assets/screenshots/admin-login.png) |
| «Sin permisos en Settings» | [admin-panel-rbac.md](./admin-panel-rbac.md) | Rol `viewer` / `operator` | — |

---

## 3. Primeros 15 minutos

1. Abra la vitrina `/` — qué ve el invitado.
2. Abra `/docs` — documentación integrada con las mismas imágenes.
3. Entre en **`/admin/login`** (usuario `admin`, contraseña del primer arranque — [security.md](./security.md)).
4. Lea la tarjeta azul **Get oriented in three moves**, luego **Dismiss**.
5. **New product** → plantilla Quick-start o su texto → **Idea → Options → Review** → **Start building**.
6. **Pipeline** → busque `prod-…` → despliegue la tarjeta → siga la franja de etapas.

---

## 4. Vitrina pública (sin login)

**Caso A — invitado prueba generar un landing**

1. Home `/` — formulario de idea (si está en su skin).
2. Tras enviar — id del producto y enlace `/product/{id}`.
3. El operador ve el mismo id en **Pipeline**.

![Vitrina](./assets/screenshots/public-home.png)

**Caso B — comprador explora el catálogo**

- Rejilla en `/` o categoría `/explore/...`.
- En vitrina solo productos que pasaron **marketplace gates** (ver FAQ).
- Dos bloques en home: **Marketing landing pages** (`marketing_landing`) y **Full products** (otros perfiles).
- **Caché del catálogo:** primero pinta desde `localStorage` (`aicom_storefront_catalog_v1_all` o `_<categoría>`), luego actualización API (*Showing cached catalog — updating…*). **No** es la caché de Pipeline Monitor (`aicom_pipeline_catalog_v2_*`).

---

## 5. Sitio de documentación `/docs`

La ruta **`/docs`** en Next.js es un hub para las partes interesadas sin git: inicio rápido, capturas de admin, enlaces.

![Documentación](./assets/screenshots/public-docs.png)

---

## 6. Entrada a admin y seguridad

1. URL: **`/admin/login`**, usuario **`admin`**.
2. **No hay `admin123` por defecto.** Primer arranque:
   - interactivo: `docker compose run -it app` — pide contraseña en consola;
   - headless: archivo **`data/secrets/bootstrap_admin.txt`** (leer una vez y borrar/cambiar).
3. Producción: solo **HTTPS**, cambiar contraseña el primer día.
4. JWT en `localStorage` — no deje sesión en PC ajeno.

![Login admin](./assets/screenshots/admin-login.png)

---

## 7. Navegación por admin

Menú izquierdo — una SPA `/admin`, pestañas vía `?tab=…`.

![Barra lateral](./assets/screenshots/admin-sidebar.png)

| Pestaña (EN) | Para el operador |
|--------------|------------------|
| **Dashboard** | Instantánea KPI al abrir |
| **Setup wizard** | URL pública y LLM iniciales |
| **Live Monitor** | Flujo de métricas, Director, video demo |
| **Pipeline** | Todos los `prod-…`, etapas, vitrina, errores |
| **New product** | Encolar trabajo nuevo |
| **Workshop** | Diff spec/arch, canvas, patrones |
| **LLM Providers** | Claves y enrutamiento de modelos |
| **LLM Logs** | Depurar fallos de llamadas LLM |
| **Discovery** | Señales externas → ideas |
| **Settings** | Piloto automático, CORS, demo replay, Railway … |
| **Corporate Chat / Brainstorming** | Debates, no pipeline | ![Chat](./assets/screenshots/admin-corporate-chat.png) · ![Brainstorming](./assets/screenshots/admin-brainstorming.png) |

Referencia completa por pestaña: [admin-guide.md](./admin-guide.md).

---

## 8. Dashboard — instantánea de salud

**Cuándo mirar:** por la mañana, tras despliegue, cuando «algo raro» pero aún no sabe qué producto.

| Bloque | Qué mirar |
|------|----------------|
| Total / Active / Completed / Failed | Escala de la cola |
| Pending / Running tasks | Atasco en el worker |
| CPU / Memory / Disk | Recursos del host |
| Revenue | Si hay comercio activo |

**Importante:** **Completed** en Dashboard ≠ número de tarjetas en vitrina pública.

![Dashboard](./assets/screenshots/admin-dashboard.png)

---

## 9. Live Monitor — métricas en vivo

**Cuándo mirar:** durante demo, con Director autónomo, cuando necesita eventos sin recargar.

![Live Monitor](./assets/screenshots/admin-live-monitor.png)

- Indicador **Connected** (SSE).
- **Demo replay** — video del recorrido del pipeline (en Settings).
- Escalaciones y feed de agentes.

Detalle: [pipeline-operations.md](./pipeline-operations.md) (sección Live Monitor demo replay).

### Setup wizard (primera visita)

![Setup wizard](./assets/screenshots/admin-setup.png)

Pestaña **Setup wizard** — URL pública, clave LLM, comprobaciones antes del modo autónomo. Ver también la tarjeta azul de onboarding en Dashboard.

---

## 10. New product — asistente y plantillas

**Ruta:** `/admin?tab=new-product`

![Asistente nuevo producto](./assets/screenshots/admin-new-product.png)

### Caso: SaaS con dashboard (full_software)

| Paso | Acción |
|-----|----------|
| Idea | «SaaS for remote team standups with auth and API» |
| Options | **Full product**, idioma de copy **Auto** o **Spanish** |
| Review | **Start building** → anote `prod-…` |

### Caso: solo landing (rápido)

| Paso | Acción |
|-----|----------|
| Options | **Marketing landing page only** |
| Review | Menos etapas y `COMPLETED` más rápido |

### Caso: guardar preset para el equipo

- **Save current to cloud** — plantilla en servidor (visible desde otro navegador tras login).
- Plantillas locales — solo en ese navegador.

### Caso: AI prefill

- Marque el **checkbox de consentimiento** — sin él no se llama al LLM.
- Si falla — panel rojo **Actionable failure** con **Retry** y enlaces a Providers.

---

## 11. Pipeline Monitor — pantalla de verdad

**Ruta:** `/admin?tab=pipeline`

![Pipeline Monitor](./assets/screenshots/admin-pipeline.png)

### Carga del catálogo (pregunta frecuente)

1. **Primera visita / otra ordenación / limpiar localStorage** — fase *Fetching first catalog page…* y *Server request N / M*.
2. Son **peticiones HTTP repetidas** (hasta 8) si el API está ocupado o el proxy cortó — **no** «el navegador no ve el servidor».
3. **Timeout de un intento** — hasta **5 minutos**; entre intentos — backoff.
4. Tras las primeras filas: encabezado **Updating from server… X / total** y barra verde — **% real de filas cargadas**.
5. **Caché:** tras carga exitosa, instantánea en **localStorage** (`aicom_pipeline_catalog_v2_*`) — la siguiente visita pinta al instante y actualiza en segundo plano.

### Elementos de la tarjeta de producto

| Elemento | Para qué |
|---------|--------|
| Franja de etapas (Anl, Pm, Dev, Qa …) | Estado por agente; **clic** — modal de tarea |
| **Spec** | Especificación PM |
| **Dev handoff** | Handoff al desarrollador |
| Badges state / category | Filtros y búsqueda |
| Storefront / follow-up | Etiquetas manuales y gates de vitrina |

### Filtros

- **Sort: shipped first** — primero `COMPLETED` / `DEPLOYED`, útil para vitrina.
- **Search** — id, nombre, descripción, follow-up.
- **State / Storefront / fechas** — acotar lista.

### Caso: producto en `FAILED`

1. Abrir tarjeta → etapas rojas.
2. **Show Tasks** o clic en ficha → `error` en la tarea.
3. **LLM Logs** si el error es del modelo.
4. Si hace falta **human rework** (admin-guide).

---

## 12. Workshop — comparación y canvas

![Workshop](./assets/screenshots/admin-workshop.png)

| Herramienta | Caso de uso |
|------------|-------------------|
| Board | Encontrar `prod-…` recientes por state |
| Material diff | Comparar spec o architecture de dos corridas |
| Iteration canvas | Guardar grafo de iteraciones (Iteration Hub API) |
| Pattern library | Plantillas JSON reutilizables |

---

## 13. Discovery — ideas antes del pipeline

![Discovery](./assets/screenshots/admin-discovery.png)

**Cuándo mirar:** modo autónomo, búsqueda de nichos, rellenar cola de ideas.

- Ranked ideas, digest, salud de fuentes.
- Auto-enqueue — solo si está explícito en **Settings** / env (`AIFACTORY_DISCOVERY_AUTO_ENQUEUE`).

---

## 14. LLM Providers y LLM Logs

![Providers](./assets/screenshots/admin-providers.png)

![LLM Logs](./assets/screenshots/admin-llm-logs.png)

| Síntoma | Acción |
|---------|----------|
| Todos los agentes fallan con auth | Revisar clave en Providers |
| Solo un agente | Routing rules, model id |
| Timeout / rate limit | Logs + subir timeout en yaml del proveedor |
| Tras cambiar clave | Guardar, **Retry** tarea o esperar rework |

---

## 15. Settings — toda la fábrica

![Settings](./assets/screenshots/admin-settings.png)

Bloques típicos (según versión):

- **Autonomous pipeline** / Director
- **Demo replay** para Live Monitor
- **Auto-publish** (Vercel / Netlify / Cloudflare)
- **Railway** para `full_software`
- CORS, tema, notificaciones

Lista completa de env: [configuration.md](./configuration.md).

---

## 16. Escenarios paso a paso

### Escenario 1: «Primer producto desde cero»

1. Providers — al menos una clave (DeepSeek, etc.).
2. New product → idea → full_software → Start.
3. Pipeline → buscar id → esperar etapas verdes.
4. Con `COMPLETED` — comprobar URL sandbox en tarjeta / vitrina.
5. Si no está en vitrina — ver `storefront_gate_reasons` en la tarjeta.

### Escenario 2: «Catálogo Pipeline vacío 2 minutos»

1. Comprobar `/api/health` en :9081.
2. No recargar la página decenas de veces — espere el intento o **Retry catalog**.
3. DevTools → Network → `pipeline/products?light=1` — código 200 y tamaño de respuesta.
4. Si 502 de nginx — subir `proxy_read_timeout` del reverse proxy.

### Escenario 3: «Quitar de vitrina sin borrar»

1. Pipeline → producto → storefront controls / follow-up **not pursuing** (admin-guide).
2. Comprobar vitrina pública en incógnito.

### Escenario 4: «Demo a inversor en 5 minutos»

1. Antes: producto en `COMPLETED`, sandbox abre.
2. Live Monitor → **demo replay** (video).
3. Dashboard → cifras.
4. Pipeline → una tarjeta «bonita» con franja verde.

### Escenario 5: «Endurecieron reglas de vitrina — productos antiguos desaparecieron»

1. Es **policy audit** — el worker puede pasar a repair.
2. Pipeline — productos en `BUG_FOUND` / rework.
3. [pipeline-operations.md](./pipeline-operations.md) — `AIFACTORY_POLICY_AUDIT_*`.

---

## 17. Errores en la UI — qué pulsar

| Mensaje / síntoma | Botones en UI | También |
|---------------------|-------------|----------|
| Could not reach the server | Retry, Settings | `docker compose ps`, proxy |
| 401 / Sign in again | Login | Sesión caducada |
| 403 | — | RBAC, [admin-panel-rbac.md](./admin-panel-rbac.md) |
| LLM / provider | Open LLM Providers, LLM Logs | Claves |
| Catalog partial load | Retry catalog | Red, ver FAQ «try 4 of 8» |
| AI prefill consent | Checkbox consentimiento | New product |

---

## 18. Índice de capturas

| Archivo | Contenido |
|---------|-----------|
| `public-home.png` | Vitrina `/` |
| `public-docs.png` | `/docs` |
| `admin-login.png` | Login |
| `admin-dashboard.png` | Dashboard |
| `admin-sidebar.png` | Barra lateral completa |
| `admin-setup.png` | Setup wizard |
| `admin-live-monitor.png` | Live Monitor |
| `admin-pipeline.png` | Pipeline Monitor |
| `admin-new-product.png` | Asistente New product |
| `admin-workshop.png` | Workshop |
| `admin-providers.png` | LLM Providers |
| `admin-llm-logs.png` | LLM Logs |
| `admin-discovery.png` | Discovery |
| `admin-settings.png` | Settings |
| `admin-corporate-chat.png` | Corporate Chat |
| `admin-brainstorming.png` | Brainstorming |

Regenerar: `cd web/frontend && npm run capture-docs-screenshots` — detalles en [assets/screenshots/README.md](./assets/screenshots/README.md).

---

## 19. Documentos relacionados

| Documento | Cuándo leer |
|----------|----------------|
| [FAQ.es.md](./FAQ.es.md) | Preguntas frecuentes |
| [owner-guide.md](./owner-guide.md) | Dueño de la instancia en producción |
| [admin-guide.md](./admin-guide.md) | Cada pestaña, API |
| [security.md](./security.md) | Contraseñas, CSRF, sandbox |
| [pipeline-operations.md](./pipeline-operations.md) | Worker, discovery, E2E |
| [configuration.md](./configuration.md) | Variables de entorno |

---

*Versión: AI-Factory v2.1 — caché de catálogo Pipeline, modo light, timeout HTTP ampliado. Regenerar capturas tras cambios grandes de UI.*
