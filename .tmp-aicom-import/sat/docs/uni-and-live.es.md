# UNI y LIVE — dos reinos

> **English:** [uni-and-live.md](./uni-and-live.md) · **Русский:** [uni-and-live.ru.md](./uni-and-live.ru.md) · **Español** · **Français:** [uni-and-live.fr.md](./uni-and-live.fr.md) · **中文:** [uni-and-live.zh.md](./uni-and-live.zh.md)

Dos procesos, dos hubs, dos catálogos. Mezclarlos es leer dólares de burbuja como ingresos.

Esta página es **UNI frente a LIVE**. TEST es una tercera capa sobre el mismo proceso del
monitor, no una tercera economía. Interruptor on-chain: [crypto-switch.es.md](./crypto-switch.es.md).
Sello UNI: [uni-realm.md](./uni-realm.md).

## De un vistazo

| | **LIVE** | **UNI** |
|---|---|---|
| Hub | [modelmarket.dev](https://modelmarket.dev) | [uni.modelmarket.dev](https://uni.modelmarket.dev) |
| Alien Monitor | [`monitor.modelmarket.dev`](https://monitor.modelmarket.dev/) · `:9101` · `ALIEN_MODE=real` | [monitor-uni.modelmarket.dev](https://monitor-uni.modelmarket.dev/) · `:9100` · `ALIEN_MODE=universe` |
| Dinero | Base, cuando el cripto está **ON** | Anvil privado, chain id `31337` — simulado |
| Catálogo | federación en vivo (Platon, ATLAS, GAIA, oráculos, …) | seis laboratorios de burbuja abajo |
| Esos seis laboratorios | **no** son pares de la federación LIVE | KHRONOS · STOICHEION · HORIZON · PSEPHOS · KYMA · DIKTYON |
| Desplegar hub | `./scripts/deploy_hub.sh` | `bash deploy/uni-hub.sh …` |
| Desplegar capacidades | satélites en vivo | `bash deploy/uni-satellites.sh` |
| Desplegar monitor | `ALIEN_MODE=real ./scripts/deploy_alien_monitor.sh --live` | `./scripts/deploy_alien_monitor.sh` (universe) |

Un distintivo LIVE en el mapa del universo no es dinero real. Los botones **navegan** entre
mapas; no repintan un solo proceso.

## LIVE

Qué despliegas: la economía real.

- El **hub** responde en `https://modelmarket.dev`. Cero capacidades locales; el catálogo
  está federado desde satélites en vivo.
- El **monitor** es un segundo contenedor (`alien-monitor-live`). El CTA de la tarjeta y
  el sondeo de estadísticas van a ese hub. El botón LIVE se queda. El botón UNI va a
  `/monitor/`.
- **Esferas:** satélites en vivo y extraños. Nunca los seis laboratorios UNI como pares
  de catálogo.
- El **cripto** es un interruptor aparte. LIVE con cripto **OFF** sigue hablando con el
  hub en vivo; no enciende los nodos de cadena. Ver [crypto-switch.es.md](./crypto-switch.es.md).

## UNI

Qué despliegas: una economía paralela sellada. Desde dentro las APIs se ven como LIVE. El
nombre es el sello: un subdominio aparte, nunca una ruta bajo el host en vivo.

- El **hub** responde en `https://uni.modelmarket.dev` (loopback `:9183` detrás de nginx).
- El **monitor** es el proceso universo por defecto. CTA y sondeo:
  `ALIEN_UNI_HUB_URL` / `https://uni.modelmarket.dev` — **no** el hub en vivo. El botón
  UNI se queda. El botón LIVE va a `/monitor-live/`.
- Los **pares de catálogo** son seis laboratorios solo de burbuja: un proceso
  (`uni/satellite.py`) × seis catálogos, levantados por `deploy/uni-satellites.sh`. Rutas
  bajo el nombre del hub UNI para que el guardia SSRF del crawler las acepte. Las claves
  en `/var/lib/uni-satellites` deben sobrevivir: el hub fija la clave del par en el primer
  contacto.

| satélite | producto | caps | vende |
|---|---|---|---|
| KHRONOS Time Series | `khronos` | 20 | estadística, suavizado, descomposición, pronóstico |
| STOICHEION Data Hygiene | `stoicheion` | 17 | esquemas, diffs, perfiles, texto, unidades |
| HORIZON Geo & Telemetry | `horizon` | 17 | geodesia, consultas espaciales, telemetría |
| PSEPHOS Draws & Ballots | `psephos` | 13 | sorteos con commitment, probabilidad discreta, papeletas |
| KYMA Signal Lab | `kyma` | 12 | espectros, filtros, ondas |
| DIKTYON Graph Metrics | `diktyon` | 12 | centralidad, conectividad, orden |

Cada capacidad es una función pura de su entrada, calculada con la biblioteca estándar.
Solo el dinero está simulado. Detalle: [uni/README.md](../uni/README.md).

**Cubierta de observación.** Platon, ATLAS y los demás satélites en vivo pueden aparecer
en el mapa UNI como superposición de estado de servicios **en vivo**. No son pares del
catálogo UNI. Los pares del catálogo son los seis laboratorios.

## No mezclar

| Fuga | Qué ocurre |
|---|---|
| El monitor UNI sondea el hub en vivo | ambos mapas muestran los mismos invokes / dólares |
| El CTA de la tarjeta UNI es `modelmarket.dev` | un operador dentro de la burbuja recibe una puerta de salida |
| Lista seed LIVE en el hub UNI | la burbuja publica direcciones reales y puede encaminar dinero real |
| Pintar `mode=real` en el proceso UNI | los números en pantalla siguen siendo de la burbuja |

El sello del hub (`aimarket_hub/realm.py`) rechaza un seed en vivo dentro de UNI y un seed
privado dentro de LIVE. El monitor (`session_tick_mode`) se niega a tic-tac los números
del otro reino en este proceso.

## Relacionado

- [uni-realm.md](./uni-realm.md) — sello de cadena, Anvil, por qué la burbuja corre en producción
- [crypto-switch.es.md](./crypto-switch.es.md) — economía on-chain on/off (no es UNI)
- [alien-monitor-factory-catalog.es.md](./alien-monitor-factory-catalog.es.md) — clústeres Factory en ambos mapas
- [quickstart-ecosystem-deploy.es.md](./quickstart-ecosystem-deploy.es.md) — flota en vivo
