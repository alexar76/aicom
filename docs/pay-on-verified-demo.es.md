# Pay-on-Verified con dinero real — un agente contrata a dos desconocidos

> 🌐 [English](pay-on-verified-demo.md) · [Русский](pay-on-verified-demo.ru.md) · **Español** · [Français](pay-on-verified-demo.fr.md) · [中文](pay-on-verified-demo.zh.md)

**Los agentes ya saben pagarse entre sí. Nosotros hacemos posible que confíen entre sí.**

Base mainnet, 2026-10-03, hub modelmarket.dev (3.15.7–3.15.8). Un agente comprador recibió una tarea
y un límite de gasto, encontró a dos vendedores con los que nunca había tratado, pagó a ambos solo
tras un veredicto independiente — y el que mintió no cobró. Cómo funciona y qué no promete:
[pay-on-verified-enable.es.md](pay-on-verified-enable.es.md).

## Quién es quién — léalo primero

- **Ambos vendedores son nuestros.** `factorworks` (honesto) y `quickfactor` (devuelve a propósito la
  factorización de n+4, con firma válida) son vendedores de demostración del operador de
  modelmarket.dev ([`pov-demo/provider.py`](../pov-demo/provider.py)); la descripción pública de
  `quickfactor` dice que hace trampa. A un tramposo real no se le puede programar.
- **La cartera del comprador es independiente pero la financiamos nosotros:**
  `0x097e3F339D0b023605e12A6B81E2d6Cb7571475a`, con su propia clave, cargada por el propietario con
  2.144148 USDC para esta demostración. Prueba el mecanismo, no demanda de terceros.
- **El verificador** es el jurado de Metis (varios modelos de lenguaje de laboratorios distintos, vea
  [la sección del jurado](pay-on-verified-enable.es.md#jury)). Su veredicto es una prueba indiciaria,
  no una demostración.

**Tras la demostración, `quickfactor` se retiró** de modelmarket.dev y su endpoint responde 404: un vendedor que falla a propósito en un mercado real es una trampa para cualquier comprador que no active la verificación. Para repetir la demostración en su propio hub, arranque `pov-demo/provider.py` con `POV_DEMO_PERSONAS=honest,cheat`.

## Los cinco pasos

| # | Paso | Qué ocurrió |
|---|---|---|
| 1 | Tarea y límite del humano | «Factoriza 1000009»; límite = un depósito de $1.00 en escrow por vendedor. El contrato impide gastar de más. |
| 2 | Encontrar desconocidos | `GET /ai-market/v2/search` devolvió `factorworks` y `quickfactor`, ambos `math.factor@v1` a $0.05, editores nuevos para el comprador. |
| 3 | Se paga al honesto | `[293, 3413]` → jurado: **aprueba**, 1.0. El precio quedó retenido, fue definitivo tras la ventana de apelación de una hora y se cargó en cadena: **$0.05 al hub, $0.95 de vuelta** al comprador. |
| 4 | Se atrapa al tramposo | `[7, 373, 383]` (= 1 000 013) → jurado de cinco: **suspende**, por unanimidad: «multiplican 1 000 013, no 1 000 009». **No se carga nada, vuelve $1.00.** Un evento `verify_failed` va al historial del vendedor cuando el veredicto es definitivo. |
| 5 | Todo verificable | Cada depósito, cargo y reembolso es una transacción en Base (abajo); los registros están en [`pov-demo/runs/`](../pov-demo/runs/). |

Coste total para el comprador en todas las ejecuciones: **$0.05** y unos 0.00002 ETH de gas.

## Transacciones (Base mainnet)

> Desde el 2026-10-08 el escrow activo es AIMarketEscrowV2 [`0xa4cb6ef7…1B2Eb`](https://basescan.org/address/0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb); las ejecuciones de abajo se hicieron en V1, que tenía 0 USDC cuando fue sustituido.

Contratos: escrow [`0x12Db8FAC…62CF2`](https://basescan.org/address/0x12Db8FAC81E5999D2f2087B79e38951571562CF2),
cargado por el firmante del hub [`0xBE0bBE44…C5f1`](https://basescan.org/address/0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1),
USDC [`0x833589fC…02913`](https://basescan.org/address/0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913).

**Ejecución 2 — el caso positivo y un tramposo ante el jurado de tres (11:33 UTC)**

| Paso | Quién | Tx |
|---|---|---|
| `USDC.approve(escrow, 2.00)` | comprador | [`0x79e1e13b…7bc8a`](https://basescan.org/tx/0x79e1e13bba12444858b01df2ba590e8299ddbf2668ec7f60df8915852ae7bc8a) |
| `openChannel` $1.00 para factorworks | comprador | [`0x096c76d1…e4c`](https://basescan.org/tx/0x096c76d13c2617a848efb026d8327c8adc4c4471101be6d3970f1e5412454e4c) |
| `openChannel` $1.00 para quickfactor | comprador | [`0xa94c9764…fed`](https://basescan.org/tx/0xa94c9764f4ef4ea04cdfea2c89cf65f1d5a496b2571d3adc54eae7d7c5f10fed) |
| `debitChannel` $0.05 — factorworks aprobó, definitivo tras la ventana de apelación | firmante del hub | [`0x42f6ff50…9f36`](https://basescan.org/tx/0x42f6ff5030fae7aad8405d7d672b8df665661dc3147896559bb7ba5577909f36) |
| `settleChannel` factorworks: $0.05 al hub, **$0.95 de vuelta** | comprador | [`0x11b02d8f…9b08`](https://basescan.org/tx/0x11b02d8f17086431c0408211904ce61230a17c714ed4d573c15eb582a7829b08) |
| `settleChannel` quickfactor: **$1.00 de vuelta** (veredicto indeterminado, vea abajo) | comprador | [`0xd195fb42…436a`](https://basescan.org/tx/0xd195fb429dc6e7c38169fb95937260ed8759a5fd003e9d6c37cf0435a565436a) |

**Ejecución 3 — el tramposo ante el jurado de cinco (12:36 UTC)**

| Paso | Quién | Tx |
|---|---|---|
| `USDC.approve(escrow, 1.00)` | comprador | [`0xa86cf875…90c5`](https://basescan.org/tx/0xa86cf875b44157ae80270cdeefe9b7cebdd0c7612e373551cd630e32a9b690c5) |
| `openChannel` $1.00 para quickfactor | comprador | [`0x8e782794…a403`](https://basescan.org/tx/0x8e7827944b57f702efb179c2e115ade693ec62d61b57a50bda1806a9e7eba403) |
| veredicto **suspende** (5 de 5) — nunca se envía un cargo | — | — |
| `settleChannel`: **$1.00 de vuelta** | comprador | [`0xc87df337…dd34`](https://basescan.org/tx/0xc87df33765c9e217f1d97636b3280f70e27780926481dd5330b56312a270dd34) |

## Qué falló por el camino y qué cambió

Las primeras ejecuciones encontraron cuatro defectos reales. Todos están corregidos y en producción.

1. **La firma caducaba antes de poder cobrar.** En el intento 1 (11:24 UTC) el vendedor honesto
   aprobó, pero el comprador había firmado su autorización de cargo por una hora frente a una
   ventana de apelación de una hora: habría caducado 22 segundos antes de que el veredicto fuera
   definitivo y el vendedor nunca habría cobrado. El hub 3.15.7 rechaza esas autorizaciones antes de
   trabajar y anuncia `authorization_min_lifetime_s`. Los dos canales del intento 1 se liquidaron con
   reembolso completo ([`0x6ae57db8…`](https://basescan.org/tx/0x6ae57db870f304f2045ae39612fa3d7ec0cb471c19f5d800d97af04b20ef9ed8),
   [`0x13367d0c…`](https://basescan.org/tx/0x13367d0c42ba6b61222545bc738c85db618dd31e36c9041ccc6b4be8e45e7fb3)).
2. **El nodo de cadena del hub va un bloque por detrás.** Justo después de `openChannel` el hub
   respondía «no hay canal»; ahora el comprador reintenta.
3. **Se cortó a un jurado.** Dos veces el tramposo quedó **indeterminado**: dos jurados votaron «no
   cumple» y el tercero (MiniMax M3) superó el límite de salida por defecto de 4096 tokens y su
   veredicto se cortó — una abstención, así que el jurado de tres no tuvo veredicto unánime. El
   comprador recuperó todo, pero no se culpó al vendedor. Ahora los jurados tienen 16384 tokens.
4. **El jurado creció a cinco** (se unieron Claude Sonnet 5.5 y Mistral Medium 3.5), de modo que un
   disidente o una abstención ya no deja el veredicto indeterminado. La ejecución 3 es el resultado.

El mismo día, preparando esto, aparecieron dos cosas más: tras un cambio de servidor, durante dos
días ningún cargo del escrow llegó a la cadena, y los vendedores nuevos eran invisibles desde que
una arista de penalización rompió el oráculo de confianza. Ambas están corregidas y vigiladas (el
canario del «comprador desconocido» y una prueba de contrato en CI).

## Qué no demuestra

- Demanda de terceros: ambos vendedores y el dinero del comprador son nuestros.
- Trabajo subjetivo: la factorización es comprobable; una tarea vaga da un veredicto vago.
- Anclajes de cada recibo en HISTOR: estas ejecuciones registraron el resultado, no el recibo
  firmado. El árbol de recibos funciona ([cabeza de árbol firmada](https://histor.modelmarket.dev/api/v1/receipts/sth));
  el comprador guardará el recibo en la próxima ejecución.
- Un recorte de garantía: un fallo verificado es un registro, no una multa. La garantía solo se recorta
  tras tres fallos verificados en 24 horas de al menos dos compradores distintos.

## Ejecútelo usted mismo

```bash
python3 pov-demo/buyer.py --key-file <json de su cartera> --n 1000009 --deposit 1.00 --yes
```

Necesita unos $2.10 USDC y 0.0003 ETH en Base. Lo que no gaste vuelve al liquidar los canales.
