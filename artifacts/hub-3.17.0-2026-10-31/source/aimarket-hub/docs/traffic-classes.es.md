# Quién cuenta como nosotros: tráfico SELF y EXT

[English](traffic-classes.md) · [Русский](traffic-classes.ru.md) · [Español](traffic-classes.es.md) · [Français](traffic-classes.fr.md) · [中文](traffic-classes.zh.md)

Cada llamada que registra el hub es **SELF** o **EXT**. La clase aparece en:
- `/ai-market/v2/stats/live`, en el campo `traffic_class` de cada evento;
- la página de inicio: la etiqueta `ext` / `self`, los filtros y el ticker;
- los contadores acumulados `external_invocations` y `operator_self_invocations`.

EXT es la cifra que usted cita como demanda. No debe contener su propio tráfico, y tampoco debe perder a ningún cliente real.

## La regla

- **SELF** es el propio hub y los componentes ligados a él que pertenecen a **su propio ecosistema**: los servicios que usted ejecuta para este hub, como sus desks, monitores, canarios y proveedores propios.
- **EXT** es todo lo demás:
  - compradores y agentes;
  - otros ecosistemas;
  - cualquiera que despliegue este código abierto por su cuenta;
  - **servicios externos conectados por un canal de pago**, aunque funcionen en su infraestructura. Un juego que compra capacidades para sus jugadores es un cliente, no parte del ecosistema.

Sin configuración, el hub solo se conoce a sí mismo. Son SELF las pruebas de humo de administración, `local` y la URL propia del hub; todo lo demás es EXT. El resto de su ecosistema se declara en un único archivo, `ecosystem.json`.

## Qué decide la clase

| Evidencia | A qué se aplica | Cuándo se decide | Efecto |
|---|---|---|---|
| El propio hub: prueba de humo con Bearer de administración, `local`, la URL del hub | cualquier llamada | al leer | siempre SELF |
| Una llamada **reenviada**. Otro hub enrutó aquí a un comprador: envía `X-AIMarket-Routing-Hub` / `X-AIMarket-Buyer` o un visitante de prueba `hub-fed-…`. También una seller operation comprada en otro hub | cualquier llamada | al escribir | nunca SELF en este hub |
| `external.networks`, `external.wallets` | cualquier llamada | al escribir | EXT, coincida lo que coincida |
| `external.accounts` | llamadas cobradas a una cuenta de crédito | al leer | EXT, coincida lo que coincida |
| `self.accounts` | llamadas cobradas a una cuenta de crédito: `X-API-Key`, un mandato, un cupo de trabajo | al leer | SELF |
| `self.wallets` | llamadas x402: el monedero que pagó, verificado en cadena (un id de canal de pago llega en una cabecera y no avala nada) | al escribir | SELF |
| `self.networks` | solo llamadas **sin pagador ni visitante de prueba**: la pasarela MCP del hub y llamadas sin identidad | al escribir | SELF |

Las filas se comprueban en ese orden y gana la primera coincidencia. Por eso `external` siempre vence a `self`, y una llamada reenviada nunca es SELF. Una excepción: un pagador x402 verificado en cadena es evidencia venga de donde venga, así que `self.wallets` / `external.wallets` se aplican también dentro de un reenvío. Una petición de un par que no está en `AIMARKET_TRUSTED_PROXIES` pero trae `X-Forwarded-For`, `Forwarded` o `X-Real-IP` es un relay que se anuncia, y cuenta como reenviada.

**«Al leer»** significa que editar el archivo reclasifica el historial. Si quita una cuenta de `self.accounts`, sus llamadas pasadas pasan a EXT en la siguiente carga de la página.

**«Al escribir»** significa que la evidencia (la dirección de quien llama, el monedero que paga) no se guarda. El hub la juzga una sola vez, al escribir la fila, y conserva solo el veredicto. Un servidor o monedero añadido hoy solo clasifica las llamadas hechas a partir de ahora. La fila sí recuerda QUÉ entrada la avaló, así que quitar una entrada errónea del archivo devuelve esas filas a EXT.

## Por qué una dirección nunca avala una llamada de pago

La propia fontanería del hub convierte a sus servidores en el llamador directo de mucho tráfico ajeno:

- un hub par que enruta la compra de un desconocido llega desde **la dirección de ese hub**;
- un paso de Studio de pago comprado en otro hub llega desde el **hub comprador**;
- una llamada hija de subcontratación, pagada con el cupo de un desconocido, la hace **el host de su proveedor**;
- un ejecutor de la fábrica ejecuta el pipeline gratuito de un visitante web **desde el host de la fábrica**.

Si una dirección pudiera volver SELF estas llamadas, la demanda real desaparecería de EXT. Así que una llamada de pago se juzga por **quién pagó** (la cuenta o el monedero), nunca por su origen. La regla de dirección solo cubre llamadas sin pagador ni visitante de prueba: un visitante de prueba que llega desde un servidor casi siempre es un relay.

Una llamada reenviada la clasifica el hub que la enrutó, el único que vio al comprador real. Así el feed de cada hub sigue siendo honesto. Si suma varios hubs, descarte las filas con `traffic_basis: "forwarded"` para que una compra no cuente dos veces.

## El archivo

**Dónde:**
1. `AIMARKET_ECOSYSTEM_FILE`, si está definida;
2. si no, `ecosystem.json` junto a la base de datos del hub (`AIMARKET_DB_PATH`). En la imagen Docker es `/app/data/ecosystem.json`, en el volumen de datos;
3. si no, `./data/ecosystem.json`.

Manténgalo en el servidor. Enumera sus servidores y cuentas, así que nunca debe ir a un repositorio público. El repositorio incluye [`examples/ecosystem.example.json`](../examples/ecosystem.example.json) con direcciones de rangos de documentación.

**Formato.** JSON. Cada entrada es una cadena o un objeto `{"value": "...", "note": "por qué está aquí"}`. El hub ignora `note`: es para quien edite el archivo después.

```json
{
  "version": 1,
  "self": {
    "accounts": [{"value": "acct_0123456789abcdef", "note": "desk de demo"}],
    "networks": [{"value": "198.51.100.7", "note": "host de desks y monitorización"}, "2001:db8:7::7"],
    "wallets":  [{"value": "0x1111111111111111111111111111111111111111", "note": "comprador de prueba"}]
  },
  "external": {
    "accounts": [{"value": "acct_aaaaaaaaaaaaaaaa", "note": "un juego que alojamos: un cliente"}],
    "networks": ["203.0.113.80"],
    "wallets":  []
  }
}
```

**Validación:**

- **Un error estructural rechaza el archivo entero:** una clave desconocida, un tipo erróneo o una `version` distinta de `1`. Si no, un `"netwroks"` mal escrito descartaría una lista sin avisar.
- **Un valor suelto erróneo** se omite y se informa, y el resto se aplica.
- **El hub rechaza las redes** que, vistas desde dentro del hub, nunca pueden ser uno de sus servidores:
  - loopback, `0.0.0.0/8` y `::`;
  - RFC 1918 y CGNAT `100.64.0.0/10`;
  - link-local, IPv6 unique-local y multicast;
  - prefijos de traducción IPv4 (NAT64 `64:ff9b::/96`, 6to4 `2002::/16`);
  - todo lo que sea más amplio que un IPv4 `/24` o un IPv6 `/56`: incluya sus servidores, no el bloque de su proveedor;
  - cualquier red que contenga una dirección de `AIMARKET_TRUSTED_PROXIES`.

  Son justamente las direcciones desde las que llegan la pasarela MCP, los puentes internos, las pasarelas de docker y los proxies, todos con llamadas ajenas.
- El IPv6 con IPv4 mapeado (`::ffff:198.51.100.7`) se trata como esa IPv4.
- Una entrada que esté en ambas listas cuenta como externa.

**Los cambios se aplican sin reiniciar.** El hub detecta el archivo modificado en la siguiente llamada. Si una edición lo deja inválido, **sigue en vigor la última versión buena**: `status` pasa a `invalid` y el error va al log. Una errata no debe pasar su propio tráfico a EXT. Borrar el archivo devuelve la regla por defecto.

**Compruebe antes de guardar:**

```bash
python -m aimarket_hub.ecosystem check /path/to/ecosystem.json
# salida 0 ok, 2 algunas entradas rechazadas, 1 archivo rechazado o inexistente
```

**En un hub con Docker**, ponga el archivo en el volumen de datos, hágalo legible para el usuario del hub (uid 10001) y compruébelo con el entorno del propio hub:

```bash
docker cp ecosystem.json modelmarket-hub:/app/data/ecosystem.json
docker exec -u 0 modelmarket-hub chown 10001:10001 /app/data/ecosystem.json
docker exec modelmarket-hub python -m aimarket_hub.ecosystem check
curl -s https://your-hub.example/ai-market/v2/stats/live | jq '.summary.traffic_policy'   # status ok, un loaded_at nuevo
```

No monte el archivo por separado (bind mount de un solo archivo): un editor que guarda renombrando deja al contenedor con la copia antigua. Inclúyalo en las copias de seguridad del volumen de datos. La última versión buena sobrevive a una edición inválida solo hasta el siguiente reinicio. Como editar cuentas reclasifica el historial, `external_invocations` no es monótono: un panel que calcule diferencias verá saltos cuando cambie el registro.

`AIMARKET_OPERATOR_ACCOUNTS` (ids de cuenta separados por comas) sigue funcionando y se suma a `self.accounts`; si además hay archivo, el hub registra un aviso: mantenga la lista en un solo sitio.

## Qué se publica

- **Cada evento** lleva `traffic_class` (`operator_self` o `external`) y `traffic_basis`, el porqué: `operator`, `account`, `address`, `wallet`, `forwarded`, `override` (una entrada de `external`) o `null` (una llamada externa sin más).
- **Propósito.** Un evento puede llevar `purpose`: una etiqueta corta que el llamante envió en el invoke (`"purpose": "feed"`) para decir para qué hizo la llamada. Es la etiqueta del propio llamante y el hub no la verifica. Solo se conserva `[a-z][a-z0-9-]{0,23}`; lo demás se descarta y la llamada no se rechaza. Vacío significa que el llamante no envió ninguna.
- **En el resumen**, `summary.traffic_policy` publica:
  - cuántas entradas tiene cada lista;
  - de dónde viene la regla (`default`, `env`, `file`, `file+env`);
  - si el archivo cargó (`absent`, `ok`, `partial`, `invalid`) y cuándo.
- **Nunca se publican:** direcciones, ids de cuenta, monederos ni la ruta del archivo. El veredicto guardado, la columna `caller_class`, no sale del hub.

```bash
curl -s https://your-hub.example/ai-market/v2/stats/live | jq '.summary.traffic_policy'
curl -s https://your-hub.example/ai-market/v2/stats/live | jq '[.events[] | {capability_id, purpose, traffic_class, traffic_basis}]'
```

## Antes de declarar algo como suyo

- **Un servidor** solo se incluye si sus propios procesos llaman a este hub como parte de su ecosistema. Nunca incluya un host que retransmita peticiones ajenas: otro hub, una pasarela, un ejecutor de la fábrica, una plataforma de tenants o sandbox donde corre código de terceros, un `aimarket-mcp` autoalojado. Deje fuera ese servidor o póngalo en `external.networks`.
- **IPv6.** De un servidor de doble pila, incluya la IPv4 y la IPv6.
- **No la dirección del propio hub.** No incluya la dirección pública del host donde corre el hub si ese host también ejecuta algo que retransmite peticiones ajenas: las llamadas del hub a su propia URL pública pasarían a SELF.
- **Proxy de confianza.** `AIMARKET_TRUSTED_PROXIES` debe nombrar su proxy inverso real (véase [despliegue en producción](production-deployment.es.md)). Si no, todo llamador parece el proxy y la regla de dirección no coincide con nada. La dirección solo es tan fiable como esa lista: cualquier proceso que llegue al hub *desde* una dirección de proxy de confianza (por ejemplo, un proceso del host a través de una pasarela de docker) puede nombrar cualquier dirección de cliente. Limite la lista al proxy inverso y no use `self.networks` en un hub al que pueda llegar así código no fiable.
- **Una cuenta:** incluya las cuentas de las que gastan sus propios componentes. Nunca una cuenta que emitió *para* un cliente: en un hub con el registro cerrado, todas las cuentas las emite el operador, también las de los clientes. Las llamadas pagadas con un mandato o un cupo de trabajo llevan la cuenta que las FINANCIA, así que nunca entregue a un proveedor externo un mandato o cupo de una cuenta declarada. Tampoco incluya la cuenta que otro hub usa en este hub: por su clave pasan compras de otros.
- **Un monedero:** incluya los que pagan sus pruebas y el tráfico del ecosistema. Nunca un monedero de hub, de relay o de canal par que paga en nombre de otros.

## Historial

Las filas registradas antes de 3.15.0 no tienen veredicto guardado y se clasifican solo por su etiqueta. Editar una cuenta las reclasifica como a todo lo demás. Las reglas de dirección y de monedero solo se aplican a llamadas registradas después de añadir la entrada.
