# Haga nodo la API que ya tiene en marcha

[English](run-a-node.md) · [Русский](run-a-node.ru.md) · [Español](run-a-node.es.md) · [Français](run-a-node.fr.md) · [中文](run-a-node.zh.md)

Ya vende algo por HTTP: una ruta x402, un endpoint REST. Para que los hubs de la federación lo
encuentren no necesita ejecutar un hub: `aimarket node` es un proceso pequeño que se coloca junto
a su API y habla el protocolo por ella.

- Publica un `/.well-known/ai-market.json` firmado y un manifiesto firmado de las rutas que
  nombre, firmados de nuevo en cada lectura.
- Responde a `POST /ai-market/v2/invoke` llamando a **su** ruta —GET con la entrada como
  parámetros de consulta, o POST con ella como JSON— y deja pasar las cabeceras de pago x402 en
  ambos sentidos: su 402 llega al comprador tal cual, y el reintento pagado llega a su ruta con
  su pago. Funcionan x402 V1 (oferta en el cuerpo) y V2 (oferta en `PAYMENT-REQUIRED`).
- Firma un recibo por cada respuesta 2xx de su ruta.

Su dinero sigue donde está: el nodo no custodia, verifica ni mueve pagos. Su ruta lo sigue
haciendo exactamente como hoy.

## 1. Describa sus rutas

```bash
pip install "aimarket-hub[pqc]"            # Python 3.11+, o: uvx --from "aimarket-hub[pqc]" aimarket …
aimarket node init                         # escribe node.toml
```

```toml
name = "Acme weather"
url = "https://api.acme.example"           # donde otros hubs alcanzan el nodo
upstream = "http://127.0.0.1:8000"         # su API, tal como funciona ahora

[[capability]]
id = "weather.now@v1"
product = "acme-weather"
description = "Current weather for a city"
price_usd = 0.002                          # debe ser lo que pide el 402 de su ruta
method = "GET"
path = "/weather"
input_schema = { type = "object", required = ["city"], properties = { city = { type = "string" } } }
```

Una ruta gratuita, si la tiene, es la prueba más rápida para la admisión: el sandbox la llama y
comprueba la firma del nodo en el recibo. Un nodo solo de pago se admite por su puerta: una
llamada sin pago debe responder 402 con una oferta que nombre su cartera y el mismo precio que
`price_usd`.

## 2. Ejecútelo junto a su API

```bash
aimarket node serve --config node.toml     # → 127.0.0.1:9090 por defecto (--host, --port)
```

Envíele dos rutas de su dominio público y deje el resto como está. Caddy:

```
api.acme.example {
    handle /.well-known/ai-market.json { reverse_proxy 127.0.0.1:9090 }
    handle /ai-market/* { reverse_proxy 127.0.0.1:9090 }
    handle { reverse_proxy 127.0.0.1:8000 }
}
```

nginx: `location = /.well-known/ai-market.json` y `location /ai-market/`, ambos con
`proxy_pass http://127.0.0.1:9090;`. La clave del nodo (`data/node_signing_key` por defecto, y
`_mldsa` al lado) es su identidad: haga copia de seguridad.

## 3. Compruebe y llame

```bash
aimarket doctor --url https://api.acme.example   # la comprobación de admisión que harán otros hubs
aimarket node knock                               # anuncio en modelmarket.dev (--hub para otro)
```

La respuesta incluye `assay_url`, donde aparece el veredicto. Con un `pass`, los hubs con
admisión automática indexan sus capabilities: aparecen en su búsqueda, en su endpoint MCP
(`market_search` / `market_invoke` en `https://modelmarket.dev/mcp`) y en su página `/hubs`. Un
comprador que llega a través de un hub encuentra el 402 de su ruta tal cual —cabecera incluida— y le
paga directamente; los hubs no cobran tarifa de enrutamiento en una venta x402 directa (el nodo
declara `payment_rails.seller_direct`, y así lo saben).

## Lo que no hace

- No fija precios ni se queda una parte, y tampoco los hubs que le enrutan una venta x402 directa:
  lo que un comprador paga a su ruta es todo suyo.
- No hace su ruta segura ni correcta, ni responde por la respuesta: el recibo, firmado por el nodo,
  registra que su ruta respondió (capability, precio, hora, latencia, éxito), no qué respondió.
- El tráfico de compradores en la federación todavía es pequeño. Los contadores en vivo son
  públicos: `https://verify.modelmarket.dev/demand.json`.
