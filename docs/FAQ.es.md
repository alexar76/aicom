# FAQ — AI-Factory (detallado)

> Guía ilustrada: [USER_GUIDE.es.md](./USER_GUIDE.es.md) · English: [FAQ.md](./FAQ.md) · Русский: [FAQ.ru.md](./FAQ.ru.md)

---

## Preguntas generales

### ¿Qué es AI-Factory en una frase?

Un sistema que, a partir de una idea en texto, ejecuta una **cadena de agentes IA** (investigación → especificación → código → QA → …) y guarda artefactos en disco, con panel de administración y vitrina pública opcional.

### ¿En qué se diferencia la vitrina de la admin?

| | Vitrina `/` | Admin `/admin` |
|---|------------|------------------|
| Acceso | Normalmente sin login | JWT, usuario `admin` |
| Objetivo | Mostrar productos listos, captación | Gestionar el pipeline |
| Fuente de verdad | Catálogo filtrado por API | **Pipeline** — lista completa `prod-…` |

### ¿Dónde están los datos «reales» del producto?

**Admin → Pipeline** — catálogo completo con tareas y errores. Dashboard — solo una instantánea al cargar. Live Monitor — flujo de métricas.

### ¿Hace falta clonar git para el operador?

No. Basta la URL del despliegue y la contraseña de admin. La documentación también está en `/docs`.

---

## Instalación y acceso

### ¿Cuál es la contraseña por defecto de admin?

**No hay contraseña fija.** Con `data/` vacío, el entrypoint pide contraseña en consola o la escribe en `data/secrets/bootstrap_admin.txt`. Detalle: [security.md](./security.md).

### ¿Demo público (magic-ai-factory.com)?

**Sin contraseña:** usuario `admin`, botón **Enter admin demo**. `AIFACTORY_DEMO_READONLY=1` bloquea operaciones destructivas en admin. Ver [security.md § Public demo](./security.md#public-demo-mode-aifactory_demo_readonly1).

### No puedo iniciar sesión — ¿qué revisar?

1. Usuario **`admin`** (si no creó otros).
2. Archivo bootstrap / contraseña del primer `up`.
3. Reloj del servidor (JWT).
4. HTTPS vs HTTP y cookie `Secure`.
5. No confundir puertos: UI suele ser **9080**, API **9081** con Compose por defecto.

### ¿Qué son los roles viewer / operator / admin / super_admin?

Ver [admin-panel-rbac.md](./admin-panel-rbac.md). **Operator** puede ejecutar el pipeline, pero no siempre cambiar Settings ni proveedores.

---

## New product y cola

### ¿Cuánto tarda un ciclo completo?

De **minutos** a **horas** — según `full_software`, carga del LLM, QA con Playwright y ciclos de reparación. El landing suele ser más rápido.

### Producto en HUMAN_REVIEW_PENDING, sin tareas

Para **`full_software`** tras DevOps hay **gate humano**: **Approve** o **Reject** en la tarjeta Pipeline (`HumanReviewGatePanel`). Los landings (`marketing_landing`) no pasan este paso. Ver [admin-guide.md](./admin-guide.md#post-devops-human-review) (EN).

### ¿Diferencia entre full_software y marketing_landing?

| | full_software | marketing_landing |
|---|---------------|-------------------|
| Resultado | API, BD, muchas páginas | Sitio estático/simple |
| Etapas | Cadena completa | Ruta acortada |
| Despliegue | Railway / compose | Vercel/Netlify estático |

### ¿Dónde está el id del producto tras crearlo?

Pantalla de éxito del asistente, **Pipeline** (buscar por nombre), URL `/product/{id}` si ya está publicado.

### ¿Se puede cancelar un producto en cola?

Depende del state y la política del worker. Ver admin-guide y API. A menudo es más simple dejar `FAILED` / not pursuing que borrar físicamente.

---

## Pipeline Monitor

### ¿Por qué dice «try 4 of 8» / «Server request 4 / 8»?

Es el **cuarto intento HTTP** a `/api/admin/pipeline/products`. Los anteriores fallaron, expiraron o 502. El cliente **reintenta** con backoff (`pipelineCatalogFetch.ts`). No significa que «el navegador no llega al API».

### ¿Cuánto esperar un intento?

Hasta **5 minutos** (`clientTimeoutMs` 300 000 ms) por intento. Entre intentos — pausa hasta ~8 s en la primera página.

### ¿Por qué la barra de progreso «no avanza»?

- En **Connection phase** la barra muestra el **número de intento HTTP**, no el % del catálogo.
- Tras aparecer filas, mire el encabezado: **X / total** y la barra verde — **progreso real** de filas cargadas.

### ¿Dónde está la caché del catálogo?

**Pipeline Monitor:** **localStorage** — `aicom_pipeline_catalog_v2_{sort}` y peek de 2 filas. Primera visita / otra ordenación / limpiar caché — arranque «frío» con reintentos.

**Vitrina pública (`/`):** `aicom_storefront_catalog_v1_{category}` — primero caché, luego `GET /api/products` en segundo plano. Ver [marketing.md](./marketing.md).

### ¿Por qué «All Categories (0)» y luego aparecen números?

Las categorías se cuentan sobre **filas ya cargadas**; mientras el catálogo carga, los contadores pueden estar incompletos (sufijo `+` en opciones).

### Producto COMPLETED pero no en vitrina — ¿por qué?

Causas típicas en `storefront_gate_reasons`:

- sin código en disco;
- no pasó **marketplace quality**;
- oculto manualmente (**hidden from storefront**);
- state aún no de la familia shipped.

Ver tarjeta en **Pipeline** y [pipeline-operations.md](./pipeline-operations.md).

### ¿Cómo encontrar un producto «colgado»?

1. Pipeline → filtro state **running** / etapas naranjas.
2. Clic en etapa → tarea `running` mucho tiempo sin `ended_at`.
3. Live Monitor / LLM Logs.
4. Logs del worker: `data/logs/`.

### ¿Qué significa «Updating from server… 2 / 10»?

Cargadas 2 filas del catálogo de 10 en el servidor; el resto llegará en segundo plano por bloques de 12.

---

## LLM y proveedores

### Agentes en silencio / todo FAILED con LLM

1. **LLM Providers** — claves, enabled, model id.
2. **LLM Logs** — últimos errores.
3. `data/config/model_providers.yaml` en el volume (no en git).
4. Límites rate limit del proveedor.

### ¿Hace falta internet desde el contenedor?

Sí, para APIs en la nube. Ollama en el host — overlay `docker-compose.host-gateway.yml`.

### ¿Qué es modelo heavy / light?

Enrutamiento en Providers: tareas pesadas (arquitecto) vs ligeras. Ver admin-guide.

---

## Vitrina y compradores

### ¿Por qué en la home hay menos productos que Completed en Dashboard?

La vitrina aplica **filtros extra** (calidad, código, ocultación). Dashboard cuenta todos los `COMPLETED` del pipeline.

### Support / Lumen — ¿es un agente del pipeline?

**No.** Es ayuda para compradores del marketplace, aparte del roster **AI Agents**.

---

## Discovery y Director

### ¿Ideas que aparecen solas — es normal?

Si están **autonomous pipeline** y **discovery auto-enqueue**. Si no, ideas solo manual o vía API Discovery.

### ¿Cómo desactivar el auto-encolado de ideas?

`AIFACTORY_DISCOVERY_AUTO_ENQUEUE=0`, `general.auto_pipeline: false` en Settings — ver [configuration.md](./configuration.md).

---

## Sandbox y vista previa

### Sandbox no abre en iframe

1. `AIFACTORY_SANDBOX_PREVIEW_API`, compose preview.
2. Socket Docker en el contenedor app.
3. CSP / mixed content — HTTPS.
4. Logs sandbox en API.

### ¿Sandbox vs auto-publish?

**Sandbox** — vista previa en la fábrica. **Auto-publish** — subida estática a Vercel/Netlify tras DevOps.

---

## Datos y copias de seguridad

### ¿Dónde están los productos?

Bind mount **`./data`** (o `~/aicom-data`) — `data/code/`, `data/specs/`, `data/state/pipeline.db`, configs.

### Perdimos datos tras docker run

Error frecuente: **named volume** en lugar de bind mount. Ver README — migración desde named volume.

### ¿Borrar todos los productos demo?

`./scripts/run_factory_demo_reset.sh` o `wipe_pipeline_products.py` — con cuidado, irreversible.

---

## Rendimiento y CI

### API del catálogo lento

Tras optimizaciones, el modo light debería responder en **segundos** con `limit` pequeño. Si vuelven los minutos — tamaño de `pipeline.db`, timeout del proxy, no usar `light=0` sin necesidad.

### GitHub Actions falla en tests

Ver `.github/workflows/ci.yml` — pytest + Playwright. Local: `pytest -q` en venv.

---

## Seguridad

### ¿Mostrar git remote en stream?

**No**, si la URL lleva token. Ver README — Screen recordings & Git remotes.

### ¿Dónde se guarda el JWT?

`localStorage` del navegador + cookie httpOnly (security.md). No en PCs públicas.

---

## Documentación y capturas

### ¿Cómo actualizar capturas de la guía?

```bash
cd web/frontend
DOCS_SCREENSHOT_BASE_URL=http://127.0.0.1:9080 ADMIN_PASSWORD='…' npm run capture-docs-screenshots
```

Lista: [assets/screenshots/README.md](./assets/screenshots/README.md).

### Imágenes rotas en markdown tras git clone

PNG no commiteados o aún no generados — ejecute el script con el stack en marcha.

---

## Dónde escalar

| Nivel | Documento |
|-------|-----------|
| Operador UI | [USER_GUIDE.es.md](./USER_GUIDE.es.md), este FAQ |
| Dueño del instancia | [owner-guide.md](./owner-guide.md) |
| DevOps / env | [configuration.md](./configuration.md), [production-domain.md](./production-domain.md) |
| Integración API | [api-integration-guide.md](./api-integration-guide.md) |
| Vulnerabilidades | [SECURITY.md](../SECURITY.md) |

---

*Amplíe este FAQ cuando surjan preguntas repetidas en soporte.*
