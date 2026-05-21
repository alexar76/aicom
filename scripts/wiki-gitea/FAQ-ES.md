# FAQ (español)

> **FAQ detallado:** [`docs/FAQ.es.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/FAQ.es.md)  
> **Guía ilustrada:** [`docs/USER_GUIDE.es.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/USER_GUIDE.es.md)  
> **English:** [[FAQ]] · [`docs/FAQ.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/FAQ.md)

Resumen en wiki; la versión completa (mismo nivel que `FAQ.ru.md`) está en el repositorio.

## ¿Qué es AI-Factory?

Sistema **autohospedado**: cadena de agentes LLM desde una idea hasta landing o app full-stack, con QA, seguridad y despliegue opcional en la vitrina.

## ¿Vitrina vs Admin?

| Lugar | Qué muestra |
|-------|-------------|
| Inicio `/` | Solo productos listos para el mercado |
| **Admin → Pipeline** | Todos los `prod-…`, etapas, errores, reparaciones |

**Completed** en el dashboard ≠ siempre visible en la vitrina.

## ¿Contraseña por defecto?

**No hay** en el repositorio. Primer arranque: consola o `data/secrets/bootstrap_admin.txt`.  
En el demo **magic-ai-factory.com**: `admin` / `demo123` (solo ese host).

## ¿Cuánto tarda un producto?

- **marketing_landing** — suele 20–25 minutos  
- **full_software** — ~25–45 min (brief simple) hasta **horas** si los gates reiteran  

## ¿Por qué está en reparación?

Fallo de gate (demo/TZ, navegador, security, metodólogo). Estados `BUG_FOUND` → `DEV_FIXING`. Revise **Pipeline** y **LLM Logs**.

## ¿`AIFACTORY_GATE_FAILING_MODEL`?

Modelo **más fuerte del mismo proveedor** solo en rondas de reparación tras fallo de QA. No cambia de proveedor.

## ¿`AIFACTORY_MAX_QUALITY_LOOPS`?

Límite de ciclos policy audit / remediation (por defecto **8**), luego **FAILED**.

## ¿Discovery no crea ideas?

Revise el scheduler del Director, `AIFACTORY_DISCOVERY_INTERVAL_HOURS`, `data/discovery/source_health.json`, y `POST /api/admin/discovery/run`.

## ¿Pestañas LLM / Providers vacías?

Vuelva a iniciar sesión (cookie caducada). Rol `viewer` = muchas APIs solo lectura; para cambios hace falta `operator`+.

## Documentación técnica

Guías largas de pipeline, API, seguridad: **inglés** en `docs/`. Compañeros ES/RU: guía de usuario + FAQ.

## Más

[[Pipeline]] · [[Security]] · [[Owner-Guide]] · [[Languages]] · [`docs/FAQ.es.md`](http://5.129.212.122/Superowner/aicom/src/branch/main/docs/FAQ.es.md)
