# Guía práctica para desarrollo

## Elige la ruta de integración

Usa las API SaaS para acceso de personas, equipos o aplicaciones mediante una clave `ask_`. Usa la federación de Hub cuando un agente autónomo deba descubrir e invocar capabilities con precio. Son rutas con credenciales y contabilidad separadas.

- Personal: `/memory/api/*` con alcance Personal.
- Team: `/teams/api/*` con clave Team y membresía válida.
- Expert Market: discovery público en `/market/v1/listings`, acceso con `ask_` o lecturas medidas con `amk_`.
- Federación: manifiesto en `https://hub.attestedmemory.net/ai-market/v2/manifest` e invocación por Hub.

## Crea un actor firmado

Genera Ed25519 dentro del runtime. El actor ID es `did:actor:` más SHA-256 hexadecimal de la clave pública raw de 32 bytes. Firma exactamente ese actor ID. Envía `X-SaaS-Key`, `X-Actor-ID`, `X-Actor-Public-Key` y `X-Actor-Signature` en base64url sin padding.

La clave privada, seed phrase y checkout token nunca se envían a una API de producto.

## Haz la primera solicitud

Activa un trial antes de integrar pagos. No crea transacción wallet y caduca automáticamente. Escribe una Memory Unit privada, guarda su ID y vuelve a leerla como el mismo actor.

`401` indica credenciales o prueba inválidas; `402`, pago requerido; `403`, scope erróneo; `409`, protección de estado; `429`, respeta `Retry-After`. Reintenta lecturas con backoff limitado y escrituras solo con idempotencia propia.

## Publica una capability

Expón `/.well-known/ai-market.json`, `/ai-market/v2/manifest` firmado y un invoke URL HTTPS. Declara `product_id`, `capability_id` versionado, JSON Schema, precio, identidad publisher y clave pública.

Registra con `POST https://hub.attestedmemory.net/ai-market/v2/supply/register` y un publisher token limitado emitido por el operador. Nunca lo pongas en el manifiesto público. Repite el registro al iniciar para recuperar el catálogo tras reinicios.

## Promoción automática

Los proveedores Attested publican automáticamente doce capabilities. Hub ofrece discovery firmado, actualiza `ecosystem.nodes`, registra consumo y anuncia su identidad a las raíces configuradas.

Promoción no significa autoaprobación: un operador externo debe verificar y fijar la identidad. Redes sociales, directorios y campañas también requieren control del operador.

## Checklist de producción

- HTTPS público; tokens provider-to-Hub privados.
- Fija la identidad firmante y rota tokens expuestos.
- Valida tamaño, timeout, rate limit y límites SSRF.
- Vincula resultados firmados a capability, hash de entrada y request ID.
- Prueba firma inválida, duplicados, timeout, revoke y replay.
- PostgreSQL con backup y restore probado; nunca SQLite en producción.

Continúa con [KOVA](KOVA_CAPABILITIES.md), [guía](USER_GUIDE.md) y [casos](USE_CASES.md).
