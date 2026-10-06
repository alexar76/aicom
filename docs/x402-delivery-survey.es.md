# Encuesta de entrega x402 — una llamada pagada a 100 vendedores

> 🌐 [English](x402-delivery-survey.md) · [Русский](x402-delivery-survey.ru.md) · **Español** · [Français](x402-delivery-survey.fr.md) · [中文](x402-delivery-survey.zh.md)

**Más de veinte índices de confianza comprueban si los vendedores x402 responden con un precio. Nosotros comprobamos lo que recibe un comprador después de pagar.**

El 5 de octubre de 2026 elegimos al azar 100 vendedores del CDP Bazaar. A cada uno le enviamos la solicitud de ejemplo de su propio listado, la pagamos en USDC en Base y comprobamos el cargo en la cadena. Después, un jurado de cinco modelos evaluó cada respuesta. Aquí no se nombra a ningún vendedor; los motivos están en [Por qué sin nombres](#por-qué-sin-nombres).

## Resultados

| Resultado | Vendedores |
|---|---|
| Respuesta aceptada por el jurado | 74 |
| Respuesta rechazada por el jurado, comprador cobrado | 3 |
| Respuesta recibida, el jurado no alcanzó confianza en ningún sentido | 8 |
| Error tras el pago, comprador **no** cobrado | 9 |
| Error tras el pago, comprador cobrado | 1 |
| No comprado | 5 |
| **Total** | **100** |

- **Compras.** Se firmaron 95 pagos por $0.536 en total. En la cadena se ejecutaron 85, por $0.489.
- **Respuestas aceptadas.** 74 de las 85 llamadas pagadas (87%) devolvieron una respuesta auténtica del tipo que promete el listado.
- **Dinero a cambio de nada.** En 4 de las 85 llamadas pagadas (4.7%) se cobró al comprador sin una respuesta útil: $0.022 en total.
- **Fallos honestos.** Nueve vendedores fallaron tras el pago y no cobraron; varios lo dicen en el propio error («you were not charged»).
- **Tiempo de respuesta.** Las llamadas pagadas respondieron en 1.9 s de mediana, 4.3 s en el percentil 90 y 40 s como máximo.

## Qué salió mal

| Problema | Vendedores |
|---|---|
| El ejemplo del propio listado falla: el servicio lo rechaza, o lleva a un error o a un eco de la descripción del campo | 7 |
| El ejemplo del propio listado no se puede enviar: marcadores en lugar de valores, o un tipo de cuerpo que los clientes HTTP no envían | 2 |
| Fallo del proveedor de datos tras el pago (502 de la pasarela, RPC caído, modelo en frío, feed de precios reconectándose) | 4 |
| Error después del cargo | 1 |
| Resultado vacío a cambio de dinero | 1 |
| Resultado incompleto a cambio de dinero («partial», «indeterminate») | 1 |
| Un informe de error donde deberían estar los datos prometidos | 1 |
| La cabecera de liquidación dice «pagado», la cadena no muestra transferencia | 1 |
| Cobrado, pero sin cabecera de liquidación | 1 |
| El 402 mezcla campos de x402 v1 y v2, y el cliente de referencia se niega a pagar | 1 |
| El beneficiario del 402 no coincide con el del listado | 1 |
| Precio real por encima del precio listado | 1 |
| Sin respuesta a la solicitud no pagada en 20 s | 1 |

Un vendedor puede tener más de un problema.

Casi no hay nada que llamar fraude. El defecto más común es el propio listado: aproximadamente uno de cada diez vendedores anuncia una solicitud de ejemplo que no funciona. Un agente comprador que copia la llamada documentada recibe un error. Normalmente no se le cobra, pero tampoco obtiene respuesta.

## Lo que una sonda del 402 no puede ver

Todos los índices que encontramos envían una solicitud sin pagar y leen el 402. En nuestra muestra, 96 de 100 vendedores pasaron esa prueba. Varias cosas solo aparecen cuando alguien paga:

- si el ejemplo documentado funciona;
- si el vendedor cobra ante un error;
- si la liquidación que declara llegó a la cadena;
- si una respuesta 200 es una respuesta de verdad o una lista vacía.

Las cifras de esta encuesta salen de 95 llamadas pagadas, no del 402.

## El hallazgo mayor: la demanda

El Bazaar publica sus propios contadores de 30 días. De 34,768 listados, 22,559 (65%) tuvieron exactamente un monedero pagador en 30 días, casi seguro el propio vendedor pagando una vez para quedar indexado. Solo 396 (1.1%) tuvieron diez o más. En nuestra muestra, 23 de los 74 vendedores con respuesta aceptada tuvieron exactamente un pagador.

Al mercado x402 no parece faltarle confianza. Parece faltarle compradores.

## Método

- **Catálogo.** API de descubrimiento del CDP Bazaar el 2026-10-05 a las 19:47 UTC: 34,768 listados. La instantánea se conserva, sha256 `6de6966927e5cc5b83f55f7c128c48861eab4cebf1e3fb61c2c9cb0d583d876c`.
- **Listados elegibles.** x402 v2, HTTPS, una solicitud de ejemplo declarada (`extensions.bazaar.info.input`) y una oferta `exact` en USDC en la red principal de Base de $0.01 como máximo. Se excluyeron nuestros propios hosts y monederos, y los de nuestros ecosistemas hermanos. Quedan 28,382 listados en 1,466 hosts. Un host cuenta como un vendedor.
- **Muestra.** 100 hosts elegidos por sha256 de la semilla `aimarket delivery survey 2026-10-05` y el nombre del host. De cada host se eligió un listado del mismo modo. Cualquiera con la instantánea y la semilla elige los mismos vendedores.
- **Solicitud.** Exactamente el ejemplo declarado por el vendedor: método, parámetros de ruta, query y cuerpo. Las cabeceras declaradas no se enviaron; casi siempre son las claves de API del propio vendedor.
- **Ensayo en seco.** La misma solicitud sin pago, para leer el 402 y compararlo con el listado. 96 vendedores se podían pagar dentro del límite y al beneficiario listado.
- **Compra.**
  - El 402 se vuelve a leer, y el pago solo se hace si sus condiciones son exactamente las del ensayo en seco.
  - El comprador es el cliente de referencia x402 2.28, con su propio límite de gasto fijado en $0.01. Solo puede firmar un `transferWithAuthorization` EIP-3009: nunca Permit2, nunca una aprobación.
  - Toda la ejecución tuvo un presupuesto estricto de $0.55. Cada respuesta se guardó como prueba.
- **Cargo.** `authorizationState(payer, nonce)` del contrato USDC en Base para cada pago firmado. Es el registro de la cadena, no la palabra del vendedor.
- **Evaluación.**
  - El jurado es Metis, cinco modelos de cinco proveedores. Su prompt y su lector de veredictos son los mismos que liberan el depósito en garantía en [Pay-on-Verified](pay-on-verified-demo.es.md); véase también [jury-3-vs-5.es.md](jury-3-vs-5.es.md).
  - La pregunta: ¿es la respuesta una contestación auténtica y completa a esta solicitud, del tipo que promete el listado, y no un error, un resultado vacío o de relleno, una exigencia de más pago o de credenciales, ni contenido ajeno?
  - Un veredicto solo cuenta cuando la propia confianza del jurado es de al menos 0.7.
  - Revisamos a mano 12 respuestas aceptadas. Todas eran reales: un embedding de 768 números, un artículo de Wikipedia, datos de Product Hunt, una proyección inversa Web Mercator correcta.

## Límites

- **Un momento, una llamada.** Cada vendedor recibió una llamada en un día. Un vendedor caído en ese minuto cuenta como caído.
- **Solo el ejemplo del propio vendedor.** Un ejemplo trivial («analiza el user agent `example`») recibe una respuesta trivial, y esa respuesta pasa.
- **No es una verificación de hechos.** El jurado juzga si la respuesta es auténtica y del tipo prometido. Donde podía comprobar un hecho (una proyección, un artículo), lo hizo; en general no lo hace.
- **Una franja estrecha del mercado.** Vendedores de $0.01 o menos, en Base, con un ejemplo declarado. Los listados más caros o sin ejemplo no están cubiertos.
- **Nuestro interés en la respuesta.** Operamos [AIMarket](https://modelmarket.dev), un mercado donde los agentes pagan a agentes, y vendemos verificación. Por eso la semilla, la herramienta y los datos anonimizados son públicos, y por eso este informe dice lo que encontró: la mayoría de los vendedores entrega.

## Por qué sin nombres

Una llamada pagada en un día es una prueba pequeña sobre un negocio, y nuestra solicitud puede no ser el uso que el vendedor tenía en mente. En lugar de una lista pública:

- **Los datos.** La fila anonimizada de cada vendedor está en [`scripts/delivery-survey/results/2026-10-05.json`](../scripts/delivery-survey/results/2026-10-05.json). Las filas están barajadas dentro de cada resultado, los precios y el número de pagadores van en rangos, y no hay hosts ni transacciones.
- **Las pruebas privadas.** El archivo completo — host, solicitud, respuesta, transacción y veredicto — tiene el sha256 `f55c952d752319d1a862c7154f8d93ca0aa675b5cd1172b368846e5fbe2f5cf9`, así que no puede cambiar después de la publicación. A cada vendedor se le puede mostrar su propia fila.
- **Contacto con los vendedores.** Estamos escribiendo a los vendedores cuyos listados tuvieron un problema, cada uno con sus propias pruebas.

Un vendedor también puede comprobarse a sí mismo con la misma herramienta. El paso sin pago no cuesta nada:

```bash
cd scripts/delivery-survey && npm ci
node survey.mjs catalog --out bazaar.json
node survey.mjs sample --catalog bazaar.json --host your.host --cap 0.01 --seed self --out plan.json
node survey.mjs probe --plan plan.json --out probe.jsonl      # sin pago: su ejemplo y su 402
node survey.mjs buy --plan plan.json --probe probe.jsonl --out buy.jsonl --budget 0.05 \
  --payer 0xYourBuyer --key-file wallet.json                   # una llamada pagada por listado
node survey.mjs chain --buy buy.jsonl --out chain.json         # cobrado o no, según la cadena
```

`wallet.json` contiene `{"mnemonic": "…"}` de un monedero comprador desechable (`--address-index` elige la cuenta). Use un monedero aparte con unos pocos céntimos.

## Herramienta y datos

- Herramienta: [`scripts/delivery-survey/`](../scripts/delivery-survey/). Cubre la muestra, el ensayo en seco, la compra, la comprobación en la cadena y el informe, con 22 pruebas. Entre ellas hay un vendedor local que verifica la firma EIP-712 de verdad.
- Paso del jurado: [`judge_in_hub.py`](../scripts/delivery-survey/judge_in_hub.py). Se ejecuta dentro de nuestro hub, donde está la clave del verificador.
- Datos anonimizados: [`results/2026-10-05.json`](../scripts/delivery-survey/results/2026-10-05.json).
