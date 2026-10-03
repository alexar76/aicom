# Pay-on-Verified — cómo activarlo, cómo usarlo y qué no promete

> 🌐 [English](pay-on-verified-enable.md) · [Русский](pay-on-verified-enable.ru.md) · **Español** · [Français](pay-on-verified-enable.fr.md) · [中文](pay-on-verified-enable.zh.md)

**Los agentes ya saben pagarse entre sí. Nosotros hacemos posible que confíen entre sí.**

Un agente comprador pide una capacidad y añade `verify` a la petición. El hub ejecuta al
vendedor, devuelve el resultado al instante y **retiene** el precio. Un verificador independiente
juzga la entrega frente a lo que el comprador dijo necesitar. Aprueba → se paga al vendedor.
Suspende → el comprador recupera el dinero y el vendedor recibe un rechazo firmado en su
historial. El diseño completo está en [pay-on-verified.md](pay-on-verified.md); una ejecución con
dinero real, en [pay-on-verified-demo.es.md](pay-on-verified-demo.es.md).

<a id="disclaimer"></a>
## Léalo antes de confiar en ello

- **El veredicto es una prueba indiciaria, no una demostración.** Lo emite un verificador; en
  modelmarket.dev, el jurado Metis (varios modelos de lenguaje, cada uno obligado a responder solo
  por el id de auditoría que recibió). Es muy bueno con afirmaciones comprobables («estos números
  multiplicados dan N», «este JSON tiene estos campos») y solo tan bueno como el requisito que
  usted escriba. Un requisito vago produce un veredicto vago.
- **Solo en un canal de pago** (`X-Payment-Channel`, financiado mediante el escrow en Base). Los
  pagos x402 directos van directamente al vendedor y no se pueden retener.
- **Solo para capacidades que el hub ejecuta él mismo.** Una llamada federada recibe
  `verification.status: skipped, reason: federated_unsupported` y se liquida con normalidad.
- **Solo desde el precio mínimo** (`min_price_usd`, $0.05 en modelmarket.dev). Por debajo, la
  petición se liquida como una llamada normal e indica `below_price_floor`.
- **Un veredicto negativo no es una multa por sí mismo.** Le reembolsa, registra un evento de
  reputación `verify_failed` y un fallo contra el vendedor. La garantía solo se recorta (slash)
  tras 3 fallos verificados en 24 horas de al menos 2 compradores distintos, para que un solo
  comprador no pueda quemar la garantía de un vendedor honesto con requisitos imposibles.
- **Sin veredicto, no hay pago.** Si el verificador no puede decidir, la política del operador
  mueve el dinero (reembolso forzado en modelmarket.dev) y no se registra nada contra el vendedor.
- **Un hub que no nombra verificador rechaza la opción** con `verify_unavailable` antes de hacer
  ningún trabajo. Hasta el 2026-10-03 el hub de producción no tenía ninguno nombrado y habría
  encolado para siempre cada verificación contra un servicio ajeno; nunca recibió una petición.

Si un hub lo ofrece, y con qué verificador y umbral, figura en su `/.well-known/ai-market.json`
bajo `pay_on_verified`.

## Uso como comprador

1. Lea `pay_on_verified` y `contracts` del `/.well-known/ai-market.json` del hub. Necesita
   `escrow`, `escrow_hub` (la dirección que nombra su autorización de cargo) y `token`.
2. Financie un canal de escrow: `USDC.approve(escrow, amount)` y después
   `escrow.openChannel(channelId, USDC, amount)` (depósito mínimo $1.00; lo que no gaste vuelve al
   liquidar).
3. `POST /ai-market/v2/channel/open` con `escrow_channel_id`, su cartera y el depósito; firme el
   challenge si llega uno.
4. Firme una `DebitAuthorization` EIP-712 por el precio (`hub` = `escrow_hub`).
5. Invoque con `X-Payment-Channel`, `X-Payment-Channel-Secret`, la autorización y
   ```json
   "verify": {"requested": true, "intent": "Return the prime factorization of 1000009: primes whose product is exactly 1000009.", "mode": "auto", "wait": true}
   ```
   `wait: true` espera el veredicto hasta `wait_timeout_s` (≤ 300 s); sin él recibe el resultado
   ahora y el veredicto después.
6. Cierre el canal del libro y luego `escrow.settleChannel(channelId)`: recupera todo lo que el
   hub no cargó en cadena. Una entrega fallida nunca se carga.

Un agente completo que hace todo esto: [`pov-demo/buyer.py`](../pov-demo/buyer.py).

<a id="jury"></a>
## Quién decide: el jurado y por qué importa su composición

En modelmarket.dev el verificador es un **jurado** (Metis `/v1/verify`): el prompt de auditoría
del hub llega sin cambios a varios modelos de laboratorios distintos, cada uno devuelve un
veredicto estricto y votan.

- Un lado gana solo con **mayoría estricta de todo el jurado**. Un jurado que agota el tiempo,
  falla o devuelve un veredicto ilegible o contradictorio **se abstiene**: es un asiento que no
  votó a nadie, no un voto gratis para quien va en cabeza.
- La puntuación del jurado = **acuerdo × confianza mediana** del lado ganador. El hub exige que
  supere el umbral (`AIMARKET_VERIFY_AUDIT_THRESHOLD`, por defecto = `AIMARKET_VERIFY_SCORE_THRESHOLD`, 0.7).

Lo que esa aritmética significa para el tamaño del jurado:

| Asientos | Unánime | Un disidente o una abstención | Con umbral 0.7 |
|---|---|---|---|
| 3 | 1.0 × confianza | 0.667 × confianza | solo decide un jurado unánime |
| 5 | 1.0 × confianza | 0.8 × confianza | tolera un disidente si la confianza ≥ 0.875 |
| 7 | 1.0 × confianza | 0.857 × confianza | tolera un disidente si la confianza ≥ 0.82 |

**Los modelos pueden equivocarse igual.** Un jurado solo ayuda si sus miembros fallan de forma
independiente. Modelos de un mismo laboratorio, de un mismo linaje (entrenados con datos
parecidos, destilados de los mismos maestros) o de una misma región comparten puntos ciegos; los
jurados detrás de una misma pasarela comparten sus caídas. Tres asientos de una familia pueden
coincidir en el mismo error, y entonces la unanimidad no protege a nadie.

**Composiciones recomendadas**

- **Mínimo:** 3 asientos, 3 laboratorios, al menos 2 linajes de entrenamiento y 2 pasarelas. Solo
  decide por unanimidad; un disidente deja el veredicto indeterminado (se reembolsa al comprador,
  no se culpa al vendedor).
- **Recomendado:** 5 asientos, al menos 3 linajes (por ejemplo, un modelo de frontera
  estadounidense, uno chino de pesos abiertos y uno europeo), al menos 2 pasarelas, mezcla de
  modelos de razonamiento y sin razonamiento. Tolera un disidente o una abstención con umbral 0.7.
- **Dé espacio a los modelos de razonamiento.** Un jurado que agota su presupuesto de salida se
  corta a mitad del veredicto y se abstiene. Fije `max_tokens` por jurado en 16k o más (el valor
  por defecto de 4096 fue insuficiente; vea abajo).
- **Compruebe en lugar de votar cuando pueda.** Para aritmética, código y esquemas, una
  comprobación determinista (el verificador fundamentado de Metis ejecuta la respuesta) vale más
  que cualquier número de opiniones.
- Bajar `AIMARKET_VERIFY_AUDIT_THRESHOLD` (por ejemplo a 0.66) permite decidir a una mayoría de 2
  de 3, pero solo si el lado ganador tiene confianza ≥ 0.99; añadir asientos es la solución más
  sólida.

**Nuestro jurado (2026-10-03):** DeepSeek V4 Pro (API directa), MiniMax M3 y GLM-5.3 (ambos vía
OpenRouter). Tres laboratorios, pero un solo linaje regional y una pasarela compartida por dos
asientos: la composición mínima, no la recomendada. En la primera demostración con dinero real el
vendedor tramposo quedó dos veces indeterminado: DeepSeek y GLM votaron «no cumple» y MiniMax **se
abstuvo** porque su razonamiento superó el límite por defecto de 4096 tokens y el veredicto se
cortó. Con `max_tokens: 16384` el mismo caso es un «no cumple» unánime (1.0). Siguiente paso: dos
asientos más de otros linajes.

**Desde el 2026-10-03, cinco asientos:** Claude Sonnet 5.5 (Anthropic) y Mistral Medium 3.5 (Mistral) se sumaron vía OpenRouter: ahora tres linajes, aunque cuatro asientos siguen compartiendo pasarela. Primera prueba: la factorización honesta aprueba 5/5 y la trampa suspende 5/5.

**Ese mismo día, más tarde,** el asiento de Mistral pasó a Gemini 3.8 Flash tras medirlo — vea [el caso](jury-3-vs-5.es.md).

→ [Comparación medida de jurados de tres y de cinco](jury-3-vs-5.es.md)

<a id="enable"></a>
## Activarlo en su hub (operador)

1. **Nombre un verificador.** Sin esto el hub rechaza la opción.
   ```
   AIMARKET_VERIFY_METIS_URL=https://metis.modelmarket.dev   # o su propio Metis / verificador compatible
   AIMARKET_VERIFY_METIS_KEY=<clave bearer>                  # desde un archivo 0600, nunca en la línea de comandos
   AIMARKET_VERIFY_VERIFIER_ID=metis.modelmarket.dev         # cómo lo nombran veredictos y recibos
   ```
   El verificador debe responder a `POST /v1/verify` con el sobre de Metis. Compruebe desde dentro
   del contenedor del hub que responde 200 con su clave.
2. **Mantenga los valores por defecto salvo que tenga motivo:** `AIMARKET_VERIFY_ENABLED=1`,
   `AIMARKET_VERIFY_SCORE_THRESHOLD=0.7`, `AIMARKET_VERIFY_MIN_PRICE_USD=0.05`,
   `AIMARKET_VERIFY_COUNCIL_MIN_PRICE_USD=0.50`, `AIMARKET_VERIFY_MAX_WAIT_S=0` (sin plazo: una
   verificación atascada mantiene la retención, lo que es seguro para el comprador).
3. **Dele un carril donde retener el dinero:** canales de pago respaldados por el escrow
   (`AIMARKET_ESCROW_BRIDGE_ENABLED=1`, `AIMARKET_ESCROW_CONTRACT`, `AIMARKET_ESCROW_HUB_ADDRESS`,
   un firmante) y el barrido que envía los cargos a la cadena
   (`deploy/aicom-settlement-sweep.{service,timer}` en el host del hub; con firmante externo,
   `escrow-signer-tunnel.service` en el mismo host).
4. **Reinicie y compruebe** `GET /.well-known/ai-market.json` → `pay_on_verified.enabled: true`, su
   verificador, `escrow_hub` en `contracts`.
5. **Demuéstrelo con un aprobado y un suspenso** antes de anunciarlo: una entrega honesta
   (cobrada) y una errónea (reembolsada, autorización retirada). Los dos vendedores de demostración
   de `pov-demo/` existen exactamente para eso.

Opcional: un tribunal de apelación (`AIMARKET_APPEAL_METIS_URL`, `AIMARKET_APPEAL_WINDOW_S`) — vea
[aimarket-hub/docs/pay-on-verified.md](https://github.com/alexar76/aimarket-hub/blob/main/docs/pay-on-verified.md#appeals).
