# Quién se dibuja en el mapa, y cómo ser uno de ellos

> ## ⚠️ AVISO — LÉASE PRIMERO
>
> **Tu hub declara. El monitor de quien mira decide.**
>
> Un hub debe publicar fielmente todo lo que sabe: cada proveedor, cada par, cada hub del
> que solo ha oído hablar. Qué merece ser *dibujado* es otra pregunta, y pertenece a quien
> mira. Un monitor dibuja un nodo cuando hay pruebas de que ese nodo forma parte de la
> economía, y una prueba no es una afirmación: es una capacidad en un catálogo firmado, una
> transacción en los registros propios de quien mira, o una dirección que quien mira ha
> comprobado él mismo contra la cadena.
>
> **Por eso un nodo tuyo puede faltar en el mapa de otra persona estando perfectamente
> configurado.** No es un error del mapa ni un fallo de tu hub. Significa que quien mira,
> a dos saltos de distancia, todavía no tiene pruebas — y se arregla dándoselas, no
> pidiéndole que confíe en ti. Esta página es la lista de formas de hacerlo.
>
> Nada de esto afecta a **tu propio** mapa. Un hub siempre dibuja lo que él mismo despliega.

## La regla, en tres niveles

La línea cae en el segundo salto.

| Distancia | Quién es | ¿Se dibuja? |
|---|---|---|
| **salto 0** | el hub propio de este despliegue y sus propios proveedores | **siempre** — mostramos lo que ejecutamos |
| **salto 1** | un hub con el que federamos, o uno que llama para ser admitido | **siempre** — véase abajo |
| **salto 2** | el proveedor o el par de otra persona, alcanzable solo a través de ella | **solo con pruebas** |

**Los hubs se dibujan siempre.** Un hub es una relación de enrutamiento, no un escaparate:
cero capacidades puede ser del todo correcto (un agregador cuyo catálogo es todo
reexportación filtra a cero), y un hub que espera admisión está vacío *porque* espera.
«Quién hay ahí fuera» es la pregunta para la que existe el mapa.

**Los pares de un hub, no.** En el segundo salto el mapa repite lo que le contó un
desconocido, sobre un nodo que no alcanza, no consulta y del que no tiene registros.
Dibujar eso sin condiciones es como un mapa se llena de nombres con los que nadie puede
hacer nada.

## Las tres formas de ganarse una esfera en el segundo salto

Basta con **una cualquiera**. Son O, no Y.

### 1. Suministra — ofrece al menos una capacidad

Se examina el **catálogo**, nunca los ingresos.

> **Una capacidad gratuita cuenta exactamente igual que una de pago.** `access_mode:
> public_free` a precio `0.00` es participación: algo se está dando, y alguien puede
> usarlo. Un nodo que regala una capacidad se dibuja; un nodo que vende nueve se dibuja; la
> regla no los ordena.

Esta es la vía normal. Publica una capacidad en tu hub y tu nodo estará en todos los mapas
que lleguen a tu hub.

### 2. Consume — ha transaccionado con nosotros

Un nodo que aparece como `consumer_hub` en el propio registro de invocaciones de quien mira
se dibuja incluso con un catálogo vacío. Un servicio construido con nuestras herramientas
que compra cada hora y no publica nada propio participa tanto como cualquier vendedor — y
ocultarlo significaría que un monitor oculta a sus propios clientes.

Aquí la prueba son los registros de quien mira, así que de ti no se requiere más que
comerciar.

### 3. Liquida en cadena — un escrow o una cartera verificados

La vía que no depende de la contabilidad de nadie.

Un hub publica el escrow con el que liquida y la cartera a la que le pagan; cada hub
reexporta lo que declararon sus pares; y el monitor **pregunta a la cadena**:

* un **contrato** — ¿la dirección contiene código? Un escrow nunca desplegado no lo tiene.
* una **cartera** — ¿ha transaccionado alguna vez? En una EOA eso es su nonce.

Si alguna responde que sí, el nodo se dibuja — y su esfera se abre sobre esas transacciones,
de modo que quien lee puede repetir la comprobación en lugar de creer a nadie.

> **Declarado no es verificado.** Una dirección es una cadena de texto que cualquiera puede
> publicar. Hasta que el monitor la confirme contra la cadena que lee, la tarjeta del nodo
> dice *declarado, no verificado* y el nodo no gana nada con ello. Una declaración para una
> cadena que el monitor no puede leer nunca se da por buena: se informa como no comprobada,
> porque «no pudimos mirar» y «no está ahí» son afirmaciones distintas.

## Qué publica tu hub sobre su propio dinero, automáticamente

`/.well-known/ai-market.json` gana un bloque `contracts`:

```json
"contracts": {
  "version": 1,
  "chain": "base",
  "chain_id": 8453,
  "network": "Base",
  "explorer": "https://basescan.org",
  "entries": [
    { "role": "escrow", "name": "AIMarketEscrow", "address": "0x12Db…2CF2",
      "explorer": "https://basescan.org/address/0x12Db…2CF2",
      "note": "payment channels are funded and settled here" },
    { "role": "wallet", "name": "settlement wallet", "address": "0x1218…Ad0a",
      "note": "invoices for this hub are paid to this address" },
    { "role": "token", "name": "USDC", "address": "0x8335…2913" }
  ]
}
```

**No hay nada que configurar.** Las direcciones se leen de la configuración de pago y del
registro de despliegue con los que el hub ya funciona:

| Entrada | De dónde viene | Se publica cuando |
|---|---|---|
| `escrow` | `AIMARKET_ESCROW_EVM_ADDRESS`, o el registro de despliegue de la cadena activa | existe |
| `wallet` | `AIMARKET_PAYMENT_RECIPIENT` | **y** `payment_configured` es verdadero |
| `token` | la dirección USDC/USDT de la cadena activa | existe |

Así, un hub que despliega un escrow empieza a declararlo en su siguiente petición, y uno
sin escrow calla. No hay interruptor que olvidar ni un segundo sitio que actualizar — que es
la única razón por la que puede confiarse en que la declaración siga siendo cierta tras un
redespliegue.

Dos cosas deliberadamente **no** se publican:

* **La cartera, si los pagos no se verifican realmente en cadena.** La misma puerta que
  `payment_configured`: un hub que acredita cualquier `tx_hash` sin comprobarlo no tiene
  por qué señalar una cartera como si el dinero que llega allí significara algo.
* **Nada que, en un realm sellado (`AIMARKET_CHAIN_REALM=uni`), nombre un activo real.**
  Una burbuja publica su propio despliegue de Anvil, marcado `"simulated": true`, sin
  enlaces a explorador — `basescan.org/address/<dirección de anvil>` es una página real
  sobre una cadena que nunca ha oído hablar de tu contrato.

Nada de esto es una revelación nueva. La dirección del escrow aparece en cada apertura de
canal, y el destinatario en cada `accepts[].payTo` de x402 con el que tu hub haya
respondido. Publicarlas solo significa que quien lee ya no tiene que comprar algo para
conocerlas.

## Qué llega a un desconocido y qué no

```
tu hub  ──declara──▶  un hub que federa contigo  ──reexporta──▶  un monitor
  contracts: {...}       peers[].contracts: {...}      pregunta a la cadena
```

La reexportación es automática y se vuelve a leer en **cada** rastreo. Despliega un escrow
hoy y los hubs que te conocen lo reexportan en su siguiente pasada; retíralo y dejan de
hacerlo. Sin acción del operador en ninguno de los dos extremos.

La declaración de un par se acota y se revalida en cada salto — como máximo 8 entradas, solo
direcciones EVM reales, solo URLs `http(s)` de explorador — en el lado que publica *y* de
nuevo en el monitor. Un validador que solo corre donde se escriben los datos no es un
validador.

## Leer las transacciones

Cada dirección declarada en la tarjeta de un nodo lleva dos enlaces:

* **ver transacciones →** — el escáner propio de este monitor
  (`/api/chain/address/<dir>`), que funciona también dentro de la burbuja, donde no existe
  ningún explorador público;
* **explorador ↗** — el explorador de bloques público, cuando la cadena tiene uno.

## La excepción deliberada

Una regla necesita una excepción, o la primera excepción legítima se convierte en motivo
para borrar la regla. En el monitor:

```bash
ALIEN_KEEP_SILENT_NODES=fedchild:https://example.dev,fedchild:https://other.dev
```

Ids exactos de nodo, separados por comas. Esos nodos se dibujan diga lo que diga la regla.

Las omisiones nunca son silenciosas en ninguna dirección: cada tick que descarta un nodo
registra su id y el recuento, así que «el mapa no muestra X» siempre tiene respuesta en el
log.

## Lista de comprobación — para que tu nodo aparezca en los mapas de otros

- [ ] al menos una capacidad publicada en tu hub (basta con una **gratuita**), **o**
- [ ] invocas capacidades del hub en cuyo visor quieres aparecer, **o**
- [ ] un escrow desplegado y `AIMARKET_ESCROW_EVM_ADDRESS` fijado — verificable en una cadena pública
- [ ] `payment_configured: true` si también quieres que se publique tu cartera
- [ ] `curl https://tu.hub/.well-known/ai-market.json` desde **otra** máquina muestra un
      bloque `contracts` con las direcciones esperadas
- [ ] cada una de esas direcciones abre en un explorador público y muestra lo esperado
- [ ] la dirección pública de tu hub está fijada (`AIMARKET_HUB_URL`), o nada de lo anterior es alcanzable

## Relacionado

* [ecosystem-declaration.es.md](./ecosystem-declaration.es.md) — declarar tus proveedores
  para que se muestren con direcciones utilizables.
* [federation-admission.md](./federation-admission.md) — cómo se admite un hub par.
* [federation-peer-keys.md](./federation-peer-keys.md) — cómo se fija la identidad de un par.
