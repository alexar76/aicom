# Capabilities de KOVA en Attested

## Qué es KOVA

KOVA es un servicio independiente para Base y USDC; no está instalado dentro de
Attested Hub. Publica seis productos en el Hub para que los agentes los descubran,
valoren e invoquen mediante la federación.

## Cómo invoca un agente

El agente llama al Hub con `POST /ai-market/v2/invoke`, no a la URL privada de
KOVA. El Hub aplica acceso y liquidación, registra el invoke y enruta la solicitud.

Las capabilities son `kova.network.status@v1`, `kova.asset.balance@v1`,
`kova.usdc.invoice.create@v1`, `kova.usdc.invoice.status@v1`,
`kova.usdc.invoice.cancel@v1` y `kova.usdc.webhook.register@v1`.

## Por qué el checkout usa otra ruta

La suscripción de Attested llama a la API de facturas de KOVA mediante una conexión
service-to-service autenticada. No compra una capability pagada para verificar su
propio pago. Así se evita la facturación recursiva y una orden emite un entitlement.

## Quién paga KOVA

Una suscripción Attested envía el USDC del comprador directamente a
`SAAS_PAYMENT_RECIPIENT`. Esta transferencia no aplica reparto ni porcentaje
automático para KOVA. Gateway usa una `KOVA_API_KEY` dedicada; si procede de un plan
KOVA Pro o Business de pago, el operador la compra o renueva por separado. Las
invocaciones federadas de capabilities forman un tercer flujo medido: su precio por
llamada y la routing fee del Hub se registran como consumo y nunca se descuentan del
pago de la suscripción Attested.

## Qué se puede observar

El Hub registra precio, estado y recibo de cada invoke federado. El Operator ledger
protegido muestra órdenes, claves trial/paid y peticiones de Attested. El Settlement
desk de KOVA muestra sus órdenes, prefijos y uso; nunca devuelve claves completas.

## Límite de seguridad

La ruta privada exige `X-AIMarket-Internal-Token`, coteja la identidad de ruta y
body y limita más las escrituras. `X-Provider-Signature` firma con Ed25519
`product_id`, `capability_id`, hash del input y resultado para impedir su reutilización.

## Configuración segura

Use un `KOVA_CAPABILITY_TOKEN` aleatorio de 32+ caracteres igual al
`AIMARKET_CAPABILITY_TOKEN` del Hub. Configure `KOVA_HUB_URL` y `KOVA_INVOKE_BASE`;
mantenga la URL del proveedor en la red privada.
