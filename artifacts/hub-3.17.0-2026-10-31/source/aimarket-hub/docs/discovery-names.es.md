# Nombres de discovery — dos grafías de un mismo documento

> **English:** [discovery-names.md](./discovery-names.md) · **Русский:** [discovery-names.ru.md](./discovery-names.ru.md) · **Français:** [discovery-names.fr.md](./discovery-names.fr.md) · **中文:** [discovery-names.zh.md](./discovery-names.zh.md)
>
> Código: [`discovery_names.py`](../aimarket_hub/discovery_names.py) · [`hub_routes/wellknown.py`](../aimarket_hub/hub_routes/wellknown.py) · [`crawler.py`](../aimarket_hub/crawler.py) · Borradores: [`aimarket-protocol/ietf/`](https://github.com/alexar76/aimarket-protocol/tree/main/ietf)

Desde el 30.10.2026 el hub sirve su documento de discovery bajo dos nombres, envía la cabecera
de su crawler bajo dos nombres y acepta cualquiera de los dos. Nada se renombró ni se retiró:
todos los peers de la red siguen leyendo los nombres antiguos, y los nuevos son una propuesta
en revisión.

## Por qué

Los dos Internet-Drafts de `aimarket-protocol/ietf/` describen el discovery y la federación de
este hub para el grupo de trabajo DAWN del IETF. Un documento propuesto como estándar no puede
llevar la marca de un producto en un URI well-known, y el prefijo `X-` de las cabeceras está
obsoleto (RFC 6648). Por eso los borradores usan `/.well-known/agent-marketplace` y
`Agent-Marketplace-Crawler`, y el hub que dice implementarlos tiene que servir esos nombres sin
romper ningún peer existente.

## Qué hace el hub

| | Antiguo (el contrato en el cable) | Borrador (propuesta) |
|---|---|---|
| Documento de discovery | `GET`/`HEAD /.well-known/ai-market.json` | `GET`/`HEAD /.well-known/agent-marketplace` |
| Ubicación del catálogo | `manifest_url` | `catalogue_url` (la misma URL) |
| Perfil de firma | implícito | `signature_profile: "ed25519-pipe-2"` |
| Peers admitidos | `peers`: objetos con `url`, `name`, `trust_score`, … | `peers`: URIs de documentos de discovery |
| El crawler se identifica | `X-AIMarket-Crawler: <url del hub>` | `Agent-Marketplace-Crawler: <url del hub>` |

- **Servir.** El documento del borrador se construye a partir del antiguo, así que clave,
  catálogo y contadores nunca pueden discrepar. Lleva además `manifest_url` y
  `legacy_discovery_url` para un lector que solo conozca los nombres antiguos. `peers` enumera
  el URI de discovery que este hub lee realmente de cada peer admitido: la ruta antigua para
  un peer que solo sirve esa, la del borrador cuando el peer la anuncia. Un peer pendiente no
  aparece en ninguno de los dos documentos.
- **Enviar.** El crawler envía ambas cabeceras con el mismo valor en cada petición.
- **Aceptar.** Ambas rutas leen ambas cabeceras. Si llegan las dos, gana el valor antiguo: es
  el valor por el que los peers siempre se han identificado. El resto no cambia: se registra
  fuera de la ruta de la petición, se valida sintácticamente, pasa la comprobación SSRF antes
  de cualquier fetch, se admite como *pendiente* en federación abierta y nunca se confía por
  la cabecera sola.
- **Leer.** Un peer que publica la forma del borrador (`catalogue_url`, `peers` como URIs) se
  normaliza a la forma antigua antes de validar, rastrear y evaluar, así que se indexa como
  cualquier otro. Un peer listado por un URI con la ruta del borrador se consulta en esa ruta,
  no en una ruta antigua que quizá no sirva.

El catálogo firmado es idéntico byte a byte bajo ambos nombres: la cadena canónica conserva el
nombre de par `tools_hash`, de modo que una firma válida para un lector lo es para el otro.

## Comprobar un hub

```bash
curl -s https://modelmarket.dev/.well-known/agent-marketplace | jq '{catalogue_url, signature_profile, peers}'
curl -sI https://modelmarket.dev/.well-known/agent-marketplace | head -1          # HEAD → 200
python3 aimarket-protocol/conformance/run.py --hub https://modelmarket.dev          # incluye las comprobaciones del borrador
```

El runner de conformidad registra las comprobaciones del borrador cuando la ruta responde y
las **omite** en un hub que solo sirve el nombre antiguo. Los borradores son propuestas; la ruta
antigua es el contrato.
