# Pay-on-Verified por un efecto físico — un agente paga a un enchufe solo cuando el medidor prueba que se encendió

> 🌐 [English](pay-on-verified-device-demo.md) · [Русский](pay-on-verified-device-demo.ru.md) · **Español** · [Français](pay-on-verified-device-demo.fr.md) · [中文](pay-on-verified-device-demo.zh.md)

Base mainnet, 2026-10-16, hub modelmarket.dev (versión `899ecbdb4`). Un agente comprador pagó **$0.05**
por encender un enchufe durante 60 segundos. El precio quedó en custodia (escrow) hasta que el verificador
de GAIA comprobó la orden firmada y las lecturas del medidor antes y después. Nadie apeló en la hora
siguiente, así que el hub cobró $0.05 en cadena y el comprador recuperó **$0.95** de su depósito de $1.00.
La primera demostración, un agente que contrata a dos desconocidos para factorizar un número, está
[aquí](pay-on-verified-demo.es.md); cómo funciona el control de dispositivos, [en la documentación de
GAIA](https://github.com/alexar76/gaia/blob/main/docs/i18n/ACTUATION.es.md).

## Quién es quién — lea esto primero

- **El vendedor es nuestro.** GAIA (`gaia.gateway`, editor `gaia`) la opera el operador de modelmarket.dev.
- **El enchufe es simulado.** `plug-sim-01` es un calefactor de 1500 W que solo existe en software, y cada
  respuesta lo indica (`"simulated": true`). Esto prueba el camino del dinero y de la verificación, no el
  hardware. El hardware real es un enchufe Tasmota con chip de energía ([ACTUATION](https://github.com/alexar76/gaia/blob/main/docs/i18n/ACTUATION.es.md)).
- **La cartera del comprador es aparte, pero la financiamos nosotros:** `0x097e3F339D0b023605e12A6B81E2d6Cb7571475a`,
  la misma que en la primera demostración. Para esta ejecución el propietario la recargó con 0.50 USDC desde
  la cartera del operador `0x1218…Ad0a`. Esto prueba el mecanismo, no la demanda de terceros.
- **El juez es el propio verificador del vendedor.** El hub envía `gaia.actuate@v1` a `gaia.verify@v1`, la
  comprobación exacta de GAIA, en lugar de a su jurado de LLM. Así GAIA es a la vez vendedor y juez. Es
  aceptable solo porque la comprobación es determinista sobre pruebas firmadas que cualquiera puede repetir,
  y porque el comprador puede apelar un aprobado ante el tribunal de apelación del hub, otro verificador.
  Véase «Lo que esto no demuestra».

## Qué hubo que cambiar antes, y por qué

La capacidad salió a la venta esa misma mañana. Cinco cosas se interponían entre ella y una llamada
pagada y verificada.

| # | Problema | Qué hicimos | Por qué |
|---|---|---|---|
| 1 | El hub tenía un solo verificador para todo: el jurado de LLM de Metis. | Rutas de verificador por capacidad, `AIMARKET_VERIFY_ROUTES` (hub `71be57610`). `gaia.actuate@v1` → `gaia.verify@v1`; todo lo demás sigue con Metis. | Un modelo de lenguaje no puede comprobar una firma Ed25519 ni la física de un medidor, y un jurado puede abstenerse y dejar sin pago un efecto honesto. Una ruta inutilizable **se niega** a verificar; nunca recurre en silencio a Metis. |
| 2 | El punto de verificación de GAIA respondía 503 a todos en producción: el compose nunca pasaba `GAIA_VERIFY_TOKEN` al contenedor. | Token creado en el host de GAIA y pasado al contenedor (`c718f810e`); el hub lo envía como Bearer desde la variable que nombra la ruta. | Un veredicto aprobado avanza la marca anti-repetición de GAIA, así que un punto de verificación abierto podría hacer fracasar todas las liquidaciones pendientes. Solo el hub puede llamarlo. |
| 3 | modelmarket.dev ejecutaba una versión antigua parcheada a mano, sin el código de rutas. | Se calculó el hash de cada archivo del contenedor en vivo y se comparó con git: no había ningún arreglo que existiera solo en el servidor. Después, una versión completa desde main con `deploy_hub_rebuild.sh`, conservando el contenedor anterior para revertir. | El código tiene que estar en lo que realmente se ejecuta, y una versión no debe perder en silencio un parche que vive solo en el servidor. |
| 4 | `gaia.actuate@v1` solo figuraba como capacidad federada, y Pay-on-Verified retiene dinero solo en capacidades que el hub ejecuta él mismo. | Un listado local: editor `gaia` (editor propio del operador), clave de firma de GAIA fijada, firmas de respuesta obligatorias. | Sin él, el bloque `verify` se omite y no se retiene nada. |
| 5 | El canario de pagos alertaba de «trabajo pagado servido gratis». | Era la prueba gratuita propia de Independent en un par al que el hub solo hace de intermediario. Ahora el canario sabe por quién vende el hub (`899ecbdb4`). | Una falsa alarma sobre dinero enseña a ignorar las verdaderas. |

Antes de gastar nada, la ruta se probó con una prueba gratuita (sandbox): el enchufe consumió 1491 W y el
veredicto fue `passed`, firmado `verifier: gaia.verify@v1` (traza `gaia_c12c4efa209ea762`). No se movió dinero.

## La ejecución pagada, paso a paso

| # | Paso | Qué pasó |
|---|---|---|
| 1 | La tarea y el límite | «Enciende plug-sim-01 durante 60 s». Límite: un depósito de $1.00 en custodia, que el contrato no deja superar al agente. |
| 2 | Encontrar al vendedor | `GET /ai-market/v2/search` devolvió `gaia.actuate@v1`, `gaia.gateway`, $0.05, editor `gaia`. El comprador toma solo el listado **local**, porque el federado nunca se verifica. |
| 3 | El trabajo, con pruebas | GAIA firmó la orden (`act_0aec0a640ed36476`), leyó el medidor antes, encendió y volvió a leer. Se esperaba ≥ 1000 W en 20 s; **se observaron 1506.2 W**. El enchufe se apagó solo a las 10:53:15 UTC. La llamada completa tardó 15.5 s. |
| 4 | El veredicto | `gaia.verify@v1`: **passed**, puntuación 1.0 con el umbral del hub en 0.7 (traza `gaia_e34da88c0a648c51`). Fue provisional hasta que cerró la ventana de apelación a las 11:52:29 UTC; nadie apeló y pasó a ser definitivo. |
| 5 | El dinero | El firmante del hub cobró **$0.05** en cadena a las 12:03 UTC. El comprador pidió el cierre, esperó la ventana de liquidación de una hora y liquidó: **$0.05 para el hub, $0.95 de vuelta**. |

Coste para el comprador: **$0.05** y unos 0.000007 ETH de gas. Saldo 1.094148 → 1.044148 USDC.
El registro de la ejecución es [`pov-demo/runs/2026-10-16T105204Z.json`](../pov-demo/runs/2026-10-16T105204Z.json).

## Transacciones (Base mainnet)

Contratos: custodia AIMarketEscrowV2 [`0xa4cb6ef7…1B2Eb`](https://basescan.org/address/0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb),
cobrada por el firmante del hub [`0xBE0bBE44…C5f1`](https://basescan.org/address/0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1),
USDC [`0x833589fC…02913`](https://basescan.org/address/0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913).
Canal de custodia `0x8c89c278…e8f3`.

| Paso | Quién | Bloque | Tx |
|---|---|---|---|
| `USDC.approve(escrow, 1.00)` | comprador | 52679290 | [`0xf765fe99…b52d`](https://basescan.org/tx/0xf765fe99e6570fb7590abb4f9a492b8544d52f96185eb8990931215e3e01b52d) |
| `openChannel` $1.00 | comprador | 52679291 | [`0x6ed3cdb4…19c8`](https://basescan.org/tx/0x6ed3cdb421b1a1619d8a695f857feb34dceac398f27cf9fabd678f9e7c1b19c8) |
| veredicto **passed** de `gaia.verify@v1`, definitivo tras la ventana de apelación | — | — | — |
| `debitChannel` $0.05 | firmante del hub | 52681416 | [`0x6973d111…fe10`](https://basescan.org/tx/0x6973d11160f4f58951f42c8ee65ba3639d2b376b02e037e5747663ea7d28fe10) |
| `requestClose` | comprador | 52681422 | [`0xbfb451bd…52cf`](https://basescan.org/tx/0xbfb451bd33db3af0db7f3258c6f0fab56ded47204e9c4f9a28540df575db52cf) |
| `settleChannel`: $0.05 para el hub, **$0.95 de vuelta** | comprador | 52683232 | [`0x1e2b0aa7…9f25`](https://basescan.org/tx/0x1e2b0aa794924a373635dc651e20afd6a1baa2be5e5f3d80724fbff1fcef9f25) |

## Qué salió mal por el camino

1. **El oráculo de confianza estaba fuera de alcance.** El enlace entre el host del hub y el de los
   oráculos estaba degradado ese día: LUMEN respondía en 4 a 35 segundos o no respondía. El hub consulta a
   LUMEN por un editor del que no tiene confianza guardada, así que las cinco primeras pruebas gratuitas se
   rechazaron con «trust oracle unavailable» y no se cobró nada. La sexta obtuvo respuesta, el hub guardó
   una confianza de 0.70 para `gaia`, y la ejecución pagada usó ese valor guardado. El problema de red en sí
   sigue abierto.
2. **Demasiado corto para ser seguro.** La prueba que pasó pedía 5 segundos y GAIA la rechazó: `plug-sim-01`
   acepta de 10 a 900 segundos, para que nada quede encendido sin límite. No se cobró nada.
3. **El primer envío del cobro falló** y la siguiente pasada, 15 minutos después, lo consiguió. La
   autorización firmada dura dos horas más que la ventana de apelación precisamente para que un reintento
   siga funcionando.
4. **La versión tenía su propia trampa.** La comprobación de versión del hub exige que el cliente de
   pipeline publicado coincida con la versión del hub. Se servía el cliente 3.15.1 con el hub en 3.15.28, así
   que la versión se habría revertido sola. Primero se reconstruyó el cliente.

## Lo que esto no demuestra

- Hardware real: el enchufe es simulado. Un enchufe Tasmota firma lo que informa su medidor: custodia del
  informe, no prueba de que el hardware no pueda mentir.
- Un juez independiente: GAIA vende y verifica. Las pruebas están firmadas con claves que tiene GAIA, así que
  ningún verificador, ni GAIA ni un LLM, detectaría pruebas falsificadas por quien tiene la clave. La
  protección del comprador es que cualquiera puede repetir la comprobación (`POST /v1/verify`, o
  `gaia.verify@v1` con el paquete), más el tribunal de apelación.
- Demanda de terceros: el vendedor y el dinero del comprador son nuestros.

## Hágalo usted mismo

```bash
python3 pov-demo/buyer.py --key-file <json de su cartera> --task actuate --duration 60 --yes
```

Necesita $1.00 USDC y unos 0.00005 ETH en Base. Con la ventana de apelación de una hora y la de liquidación
de una hora, la ejecución dura unas dos horas; vuelve todo salvo $0.05.
