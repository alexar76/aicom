# Guía de implementación de Expert Memory Market

Esta guía describe los recorridos reales de production para compradores,
editores e integradores de agentes. Descubrimiento público, entrega de pago,
contabilidad del editor y prueba son contratos separados de forma deliberada.

## Elige la vía de acceso antes de integrar

- Usa el trial de 1 día para validar UX y API sin transacción de wallet.
- Usa Expert Pass para siete días de exploración con una clave `ask_` acotada.
- Usa pago por lectura cuando cada Memory Unit entregada deba atribuirse y pagar a su editor.
- No mezcles la economía del pass con ingresos del editor: el pass financia la tienda; el capture de Meter financia el reparto.

## Inspecciona antes de comprar

Llama `GET /market/v1/listings?q=<tema>` sin clave. Cada resultado publica
resumen, `rank_score`, `rank_reasons`, Truth, Provenance, precio y editor.
`GET /market/v1/listings/<memory_id>` nunca devuelve el cuerpo pagado.

Rechaza listings sin evidencia pública suficiente para tu política. Un score
alto no ordena confiar: revisa sus motivos. Un claim rechazado queda por debajo
de uno no verificado y la popularidad no participa en el ranking.

## Empieza con el trial gratuito

Abre `/` con `trial=expert-market` o usa el asistente. El navegador crea la
identidad del actor y conserva localmente la clave privada de firma. Gateway
emite un trial de 1 día por actor y producto. Guarda la clave `ask_` en un secret
vault; nunca en URL, logs o analítica del cliente.

El trial valida encaje, pero no crea transacción, reparto ni entitlement
permanente.

## Compra un pass o una lectura entregada

Para Expert Pass abre `/billing?plan=expert.pass.7d`, crea la factura exacta,
envía canonical USDC en Base y espera la finality de KOVA. Gateway emite la clave
por siete días; el checkout permite recuperarla durante 48 horas.

Para pago por lectura crea y financia una cuenta en Attested Meter, conserva
`amk_` en servidor y llama `POST /market/v1/read` con `x-meter-key` y
`{"memory_id":"<id>"}`. Meter reserva el precio y solo hace capture cuando se
entrega el contenido; error o rechazo libera la reserva.

## Publica memoria experta y fija precio

- Crea una Memory Unit con título preciso, resumen público útil, tags y `source_refs`.
- Añade evidencia Truth y Provenance antes de cobrar cuando sea posible.
- Regístrate en `POST https://meter.attestedmemory.net/v1/publishers` con identidad firmada y dirección Base.
- Mantén privada la clave del editor y tarifa solo `expert.read:<memory_id>` propio mediante `/v1/publishers/me/prices`.
- Comprueba el listing por `GET /market/v1/listings` antes de enviar compradores.

El reparto estándar es 70% editor / 30% plataforma; Publisher Pro cambia a
85% / 15%. Sobre el mínimo, el operador emite `attested.payout/v1` firmado y
registra el hash de pago.

## Integra un agente autónomo

- Separa descubrimiento y compra; autoriza el gasto después de evaluar metadata.
- Define precio máximo, publishers permitidos, Truth states y política de fuentes.
- Guarda `ask_` y `amk_` en secretos de servidor y elimínalos de traces.
- Interpreta `401` como credencial inválida, `402` como acceso/saldo, `403` como scope y `429` como backoff.
- Conserva listing ID, rank reasons, charge ID y provenance receipt junto a la salida.
- Usa idempotency para facturas y no reintentes transferencias con otro importe.

## Despliega en un equipo

- Define una categoría inicial y la decisión que mejora.
- Siembra 10–20 listings de alta señal antes de invitar compradores.
- Acuerda resumen público mínimo y fuentes obligatorias.
- Prueba lectura correcta, memoria inexistente, saldo insuficiente, fallo upstream y revocación.
- Mide conversión discovery-to-read, refusals, capture/release, acumulación y backlog de payouts.

## Respeta límites de confianza y dinero

Memory Market clasifica y sirve memoria autorizada. Attested Meter controla
reservas, capture, contabilidad y payouts. Attested Prove permite verificar
recibos y provenance sin compartir claves. KOVA verifica settlement exacto por
un canal service-to-service autenticado y sigue disponible por federación.

Ningún componente pide seed phrase o clave privada. El USDC de suscripción va
directo al receptor y los payouts se ejecutan aparte. Consulta
[KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md) y [MARKET_USE_CASES.md](MARKET_USE_CASES.md).
