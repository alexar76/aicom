# Prueba gratuita y actualización

Personal ofrece 7 días gratis, Team 14 días y Expert Market 1 día. Cada actor
verificado puede activar la prueba una vez por producto.

El navegador crea una prueba de actor Ed25519. Gateway emite una clave
`ask_...` sin pago. La clave caduca automáticamente y usa las mismas reglas de
introspección, rotación y revocación que una clave pagada.

Al actualizar, Gateway crea una factura exacta de USDC canónico en Base. KOVA
verifica la transacción y la nueva clave pagada se emite automáticamente tras
las confirmaciones requeridas.
