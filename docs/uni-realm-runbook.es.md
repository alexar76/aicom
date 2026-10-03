# UNI — guía de operación

> 🌐 [English](uni-realm-runbook.md) · [Русский](uni-realm-runbook.ru.md) · **Español** · [Français](uni-realm-runbook.fr.md) · [中文](uni-realm-runbook.zh.md)

Chuleta para ejecutar, trasladar y comprobar la burbuja UNI. El porqué está en
[uni-realm.md](uni-realm.md); esta página dice qué hacer y en qué orden.

## Dos cadenas, nunca una

| Cadena | Quién la ejecuta | Dirección para los contenedores | Qué vive en ella |
|---|---|---|---|
| **Cadena de la burbuja** | contenedor `anvil-uni`, volumen `anvil_uni_state` | `http://172.17.0.1:8546` | el dinero del hub: token `0x5fbd…0aa3`, escrow `0xe7f1…0512`, la cartera del hub (Anvil #1) y el comprador (Anvil #2) |
| **Cadena de demostración** | el contenedor Alien Monitor UNI (`alien-monitor`), con su propio Anvil | `http://172.17.0.1:8545` (vía `uni-rpc-bridge`) | el mundo del mapa: lotería, NFT, ACEX (PulseAMM, registro, préstamos) |

El hub UNI **liquida en la cadena de la burbuja** (`AIMARKET_RPC_BASE=…:8546`) y lee la lotería y el
NFT en la cadena de demostración (`ALIEN_EVM_RPC=…:8545`). La cadena de demostración es desechable:
el monitor la borra al superar 64 MB y vuelve a desplegar sus contratos en direcciones nuevas. El
dinero nunca vive ahí.

## Trasladar UNI a otro servidor — lista de pasos

1. Copiar el volumen `anvil_uni_state` (detener antes `anvil-uni`, para que el estado en disco esté completo).
2. Arrancar `anvil-uni` en el servidor nuevo — el `docker run` de
   [uni-realm.md](uni-realm.md#standing-it-up), publicado solo en `172.17.0.1:8546`.
3. Cortafuegos: los contenedores deben alcanzar `172.17.0.1:8546`; internet, no.
   `ufw allow proto tcp from 172.17.0.0/16 to 172.17.0.1 port 8546`
4. Comprobar que la economía está en la cadena de la burbuja: código en el token y en el escrow,
   saldos en Anvil #1 y #2. Vacío → el estado no se copió; ejecutar `scripts/deploy_uni_realm.py`
   contra **8546** (nunca 8545) y usar las direcciones que imprime.
5. Arrancar el hub desde el monorepo: `bash deploy/uni-hub.sh <imagen> <token> <escrow>`.
   Nunca desde una copia en el servidor ni fusionando `hub.env.snippet` en el hub.
6. Trasladar también lo que vende el hub — corre en el propio servidor, no en un contenedor: los seis
   satélites (copiar `/var/lib/uni-satellites` y luego `bash deploy/uni-satellites.sh`) y el proveedor
   de `uni.answer@v1` (copiar `/var/lib/uni_provider_key` y luego `bash deploy/uni-provider.sh`). El hub
   fija ambas claves: una clave nueva es un par rechazado o firmas rechazadas. Después, un rastreo
   (`POST /ai-market/v2/federation/crawl`, admin) y detener las copias viejas en el servidor anterior.
7. Apuntar el comprador del monitor a la cadena de la burbuja:
   `ALIEN_UNIVERSE_BUYER_RPC=http://172.17.0.1:8546`, `ALIEN_UNIVERSE_BUYER_TOKEN=<token>`.
8. Ejecutar `python3 deploy/uni-hub-verify.py` **en el propio servidor**. Todas las líneas deben ser `ok`.
9. En unos 15 minutos el registro del monitor muestra `hub declares its settlement wallet` y se abre
   un canal; el aviso rojo «REALM ECONOMY STALLED» no debe volver.

## `deploy/uni-hub-verify.py`

Ejecutarlo tras cada arranque o recreación del hub. Además de las reglas de publicación, comprueba
la parte del dinero contra las propias cadenas:

- el hub liquida en su propia cadena, no en la cadena de demostración del monitor;
- un solo token para depósitos y x402, y existe en la cadena de liquidación;
- una sola dirección de escrow en todas partes, y existe en la cadena de liquidación;
- se cobra en una sola cartera en todas partes (destinatario = payTo de x402 = hub del escrow);
- la lotería benéfica existe en la cadena de demostración.

`--no-chain` omite las comprobaciones de cadena (fuera del servidor), `--no-live` las públicas.

## Cuando cambia la cadena de demostración

Tras un reinicio del monitor cambian las direcciones de la lotería, el NFT y ACEX. Las nuevas están
en `data/alien-monitor/universe/hub.env.snippet`. Tomar de ahí **solo** esto:

- hub: `AIMARKET_CHARITY_LOTTERY_ADDRESS`, `LOTTERY_ADDRESS`, `HUB_LOTTERY_ADDRESS`, `AIMARKET_NFT_CONTRACT`;
- ARGUS-UNI: las líneas `ARGUS_UNI_*` de `argus/.env`, y después `docker compose up -d argus-uni`.

Nunca llevar al hub su `AIMARKET_PAYMENT_RECIPIENT`, `AIFACTORY_PAYMENT_VERIFY_STUB` ni las líneas de
RPC: describen la cadena de demostración y Anvil #0, y rompen la liquidación. El hub ignora
`AIMARKET_ADDR_UNI_*` (su red se llama `base`).

El Anvil del monitor guarda su estado cada 30 s (`ALIEN_ANVIL_STATE_INTERVAL_S`), así que un reinicio
ya no pierde los contratos desplegados desde la última salida limpia.

## Síntomas

| En el mapa / en el registro | Causa | Solución |
|---|---|---|
| `settlement chain http://172.17.0.1:8546 is unreachable` | `anvil-uni` no está en marcha o falta la regla del cortafuegos | pasos 2–3 |
| `channel/open … moved no USDC to the configured recipient` | el comprador pagó a otra cartera, o el destinatario del hub no es Anvil #1 | verificador; el comprador descarta ese depósito por sí mismo |
| `transaction not found or not yet mined` en cada ronda | comprador y hub en cadenas distintas | paso 7, verificador |
| verificador: «settlement token exists … FAIL» | el hub apunta a una cadena sin su token | paso 4 |
| verificador: «charity lottery exists … FAIL» | se reinició la cadena de demostración | «Cuando cambia la cadena de demostración» |
| `listing_not_sellable` en el registro del comprador | normal: ese anuncio no tiene dirección de pago; los canales se pagan a la cartera que declara el hub | — |
| `Invoke error for uni.answer@v1: timed out` | el proveedor no está en marcha en este servidor; la conexión se cuelga más allá del tiempo de espera del comprador | paso 6 (`deploy/uni-provider.sh`) |
| `no match for …` en cada ronda; el catálogo tiene unas pocas herramientas en vez de ~93 | los satélites no están en marcha en este servidor (nginx responde 502 en `/sat/*`) | paso 6 (`deploy/uni-satellites.sh`) y luego un rastreo |
