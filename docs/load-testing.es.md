# Pruebas de carga: resultados del 2026-10-23, antes y después

**Idiomas:** [English](load-testing.md) · [Русский](load-testing.ru.md) · Español · [Français](load-testing.fr.md) · [中文](load-testing.zh.md)

Qué hace la flota pública bajo carga, qué hace el camino del dinero con concurrencia, qué era lento
y por qué, y qué cambió. Todas las cifras se midieron el 2026-10-23; los comandos para repetirlas
están al final.

## Qué se ejecutó

| Prueba | Herramienta | Objetivo | Carga |
|---|---|---|---|
| Smoke público | Locust 2.46.5, `scripts/load/run_load_smoke.sh` | flota en vivo (solo lectura) | 8 usuarios, 90 s |
| Constant público | igual | flota en vivo (solo lectura) | 20 usuarios, 10 min |
| Camino del dinero | `aimarket-hub/scripts/load_money_path.py` | hub local, SQLite y PostgreSQL | 2.300 peticiones, 64 a la vez |
| Soak de la fábrica (KI-3) | `scripts/load_test_factory.sh` | backend local de la fábrica, 4 workers de uvicorn | 10 hilos, 15 min |

La mezcla pública solo lee: salud de la fábrica, catálogo y franja de confianza, escaparate,
búsqueda, estadísticas y discovery del hub, mesh, ARGUS, monitor y pulse. Nunca abre una llamada de
pago; el camino del dinero se prueba en un hub local.

## Flota pública, 20 usuarios durante 10 minutos

| | Antes | Después |
|---|---|---|
| Peticiones | 7.538 | 7.626 |
| Fallos | **0 (0,00%)** | **0 (0,00%)** |
| Mediana, todas las peticiones | 170 ms | 180 ms |
| p95, todas las peticiones | 530 ms | 610 ms |

| Petición | Antes: mediana / p95 | Después: mediana / p95 | Cambio |
|---|---|---|---|
| Fábrica `GET /api/products` (escaparate) | 7,3 s / 12 s | **0,22 s / 2,0 s** | mediana 33× más rápida |
| Fábrica `GET /api/marketing/trust-metrics` | 4,7 s / 7,8 s | **0,18 s / 0,75 s** | mediana 26× más rápida |
| Fábrica `GET /api/health` | 0,18 s / 3,8 s | **0,17 s / 0,43 s** | p95 9× menor |
| Escaparate `/` | 0,35 s / 0,38 s | 0,36 s / 0,60 s | — |
| Búsqueda del hub | 0,34 s / 0,56 s | 0,33 s / 0,65 s | — |
| Estadísticas del hub | 0,17 s / 0,36 s | 0,18 s / 0,45 s | — |
| Hub well-known | 0,33 s / 0,49 s | 0,34 s / 0,67 s | — |
| Precios de capital del hub | 0,19 s / 0,39 s | 0,19 s / 0,46 s | — |
| Mesh, ARGUS, Pulse | 0,16–0,17 s / ≤ 0,18 s | 0,17 s / 0,24–0,40 s | — |
| Monitor `/api/health` | 0,16 s / 4,3 s | 0,17 s / 1,8 s | **desplegada el 2026-10-23** (abajo) |
| Estado del Monitor | 0,17 s / 3,0 s | 0,19 s / 2,4 s, máx. 62 s | **desplegada el 2026-10-23** (abajo) |

«Antes» se midió justo después de publicar las correcciones de la auditoría; «después», tras las
optimizaciones de abajo. En las filas con «—» no cambió nada; la diferencia es la red del portátil
entre las dos ejecuciones.

### El smoke de 8 usuarios

| | Antes | Después |
|---|---|---|
| Peticiones / fallos | 477 / 0 | 477 / 0 |
| Respuesta media | 306 ms | 253 ms |
| Escaparate de la fábrica, mediana | 5,1 s | 0,19 s |
| Franja de confianza, mediana | 4,6 s | 0,18 s |
| Petición más lenta | 5,1 s | 2,4 s (monitor) |

### El servidor durante la ejecución de 20 usuarios

| | Antes | Después |
|---|---|---|
| CPU del worker del pipeline (cola vacía) | ~89% de un núcleo | **16%** |
| CPU de la API de la fábrica | 85–196% | — |
| CPU / memoria del hub | 0–55% / 0,1 GB | — |
| Load average (factory-vps) | 2,1–3,6 | — |
| Reinicios, bloqueos del limitador, trazas de la fábrica | 0 / 0 / 0 | 0 / 0 / 0 |

### Monitor, antes y después de desplegarlo

Desplegado en monitor.modelmarket.dev a las 09:21 UTC (imagen `alien-monitor:overlaythread-20261023-alien-monitor-live`:
la imagen en marcha más el nuevo `main.py`). La misma sonda antes y después: 20 clientes, cada uno con un
`GET /api/health` por segundo durante 90 segundos, desde el mismo portátil. La mediana es sobre todo una conexión TLS
nueva por petición.

| | Antes | Después |
|---|---|---|
| Peticiones / fallos | 960 / 0 | 1.060 / 0 |
| Mediana | 685 ms | 666 ms |
| p95 | 1.844 ms | **1.147 ms** |
| p99 | 4.185 ms | **1.272 ms** |
| La más lenta | 4.330 ms | **1.369 ms** |

## Camino del dinero en un hub local

Llamadas de pago desde muchas cuentas, cada llamada de pago repetida tres veces a la vez con un
mismo `Idempotency-Key`, y altas compitiendo por un presupuesto de bonos de $0,25; después, una
auditoría del libro.

| Base de datos | Peticiones | Simultáneas | Rendimiento | p95 | Libro tras la ejecución |
|---|---|---|---|---|---|
| SQLite | 2.300 | 64 | 80 pet/s | 2,3 s | todos los invariantes se cumplen; 100 grupos con clave cobrados una vez cada uno; los bonos se detienen en $0,25 |
| PostgreSQL 18 | 2.299 | 64 | 41 pet/s | 4,3 s | lo mismo; una conexión cortada que, según la auditoría, no se cobró |

Los invariantes: lo retenido de una cuenta es la suma de sus retenciones activas (y es cero al
terminar), no se crea ni se pierde dinero, y cada grupo con clave se cobra exactamente una vez.

## Backend de la fábrica con 4 workers (KI-3)

| | Antes de la corrección | Después de la corrección |
|---|---|---|
| Peticiones en 15 min | 25.577 | 33.710 |
| `/api/health` rechazado por el propio limitador de la app | **13.779 de 17.907** | **0 de 23.542** |
| Fallos (sin respuesta o 5xx) | 0 | 0 |
| Reinicios de workers | 0 | 0 |
| Memoria de los 4 workers | — | 480 → 435 MB, estable |

El supervisor mata el backend tras cinco comprobaciones de salud fallidas seguidas. El limitador
contaba esa comprobación y la rechazaba bajo carga: un backend ocupado moría por estar ocupado.

## Qué era lento y qué cambió

| Dónde | Causa, medida | Cambio |
|---|---|---|
| Worker del pipeline | 92% de su CPU en `yaml.safe_load`: la configuración se volvía a leer para cada producto en cada ciclo (py-spy, proceso en vivo) | el análisis se reutiliza mientras ningún archivo de configuración cambie (mtime, tamaño, inode) |
| Escaparate `/api/products` | 57 evaluaciones de demo para 19 productos, cada una recorriendo el árbol del producto con `node_modules`: 5,1 s de 5,4 s | el recorrido poda los árboles de terceros; una evaluación por producto y petición; el escaparate construido se reutiliza 30 s y se reconstruye en cuanto el pipeline escribe |
| Franja de confianza | 4 s cargando las 3.510 tareas que la fábrica ha ejecutado, para contar estados de productos | lectura solo de productos (0,4 ms); caché de un minuto; fuera del event loop |
| `/api/health` de la fábrica | event loop bloqueado detrás de la franja de confianza | el trabajo pasó a un hilo |
| Supervisor KI-3 | el limitador por dirección contaba y rechazaba la comprobación | comprobación sin medir; 403/429 cuenta como vivo |
| Monitor | 17 sondeos de satélites con clientes HTTP bloqueantes en el event loop | un hilo de trabajo; **desplegado el 2026-10-23** |
| Registros del hub | 311 trazas al día de los libros de ACEX, apagados por configuración | un aviso por libro; las mismas respuestas 503 |
| Director | una respuesta vacía del modelo tiraba un ciclo de descubrimiento entero | un enriquecimiento que falla queda vacío |

## Repetirlo

```bash
LOAD_TARGET=public LOAD_MODE=smoke ./scripts/load/run_load_smoke.sh
LOAD_TARGET=public LOAD_MODE=constant ./scripts/load/run_load_smoke.sh
python aimarket-hub/scripts/load_money_path.py --invokes 2000 --concurrency 64
python aimarket-hub/scripts/load_money_path.py --invokes 2000 --concurrency 64 --database-url postgresql:///scratch_db
./scripts/load_test_factory.sh --base-url http://127.0.0.1:9081 --duration 900 --concurrency 10
```

La ejecución con PostgreSQL borra el esquema de la base que recibe. Método, modos y criterios:
[`scripts/load/METHODOLOGY.md`](../scripts/load/METHODOLOGY.md). Ejecuciones anteriores:
[`scripts/load/RESULTS-2026-09-14.md`](../scripts/load/RESULTS-2026-09-14.md).
