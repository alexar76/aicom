# Admisión federada — ensayo sandbox, luego índice automático

> **English:** [federation-admission.md](./federation-admission.md) · **Русский:** [federation-admission.ru.md](./federation-admission.ru.md) · **Français:** [federation-admission.fr.md](./federation-admission.fr.md) · **中文:** [federation-admission.zh.md](./federation-admission.zh.md)
>
> Código: [`federation_assay.py`](../aimarket_hub/federation_assay.py) · [`api.py`](../aimarket_hub/api.py) · [`crawler.py`](../aimarket_hub/crawler.py) · [`config.py`](../aimarket_hub/config.py)
>
> Cómo unirse: [`docs/join-the-federation.es.md`](https://github.com/alexar76/aicom/blob/main/docs/join-the-federation.es.md)

---

## Por qué existe

Un golpe (`POST /federation/announce` o `X-AIMarket-Crawler` de entrada) es una
**observación**. No debe indexar un catálogo: eso sería inyección de manifiesto. Antes, la
única salida de cuarentena era un humano en `/operator` pulsando Approve por cada hub nuevo.

El operador no va a sentarse en esa cola. La admisión tras la cuarentena es por tanto
**automática**, pero puntúa **lo que corrió en el sandbox**, no lo que el visitante escribió
en `.well-known`.

Análogo de fábrica (no se importa la fábrica al hub):

| Fábrica | Hub federado |
|---------|----------------|
| `product_automated_verify` — puntuar tests/artefactos, no el escaparate | `analyze_sandbox_output` — safety gate + schema + sin IPs privadas |
| `docs/sandbox-trust-model.md` — aislamiento suave, no hipervisor | POST HTTP acotado a *su* invoke público (no ejecutamos su código aquí) |
| `agents/surrogate_reviewer.py` — JSON approve/block | `AIMARKET_FEDERATION_JUDGE_URL` opcional — **solo veto**, evidence sin `name`/`description` |

Un LLM al que se le dan `name` / `description` estampa marketing fluido. Esa vía está cerrada.

## Pipeline

```text
golpe → pending (nada indexado)
     → comprobaciones duras (SSRF / schema / Ed25519 / same-origin)
     → POST sandbox de hasta 3 capabilities públicas gratuitas (gana el primer recibo firmado)
     → ¿nada gratis? se llama a la de pago más barata y se lee su 402 (sin pagar)
     → analizar el payload vivo
     → veto LLM opcional sobre evidence (sin folleto)
     → pass + AUTO_ADMIT=1 → trusted + crawl
     → fail / review → siguen pending (escritorio del operador)
```

Disparo: tarea de fondo tras announce sin token; fin de cada ciclo de crawl (hasta 3 pending);
admin `POST /ai-market/v2/federation/assay`.

## Veredictos

| Veredicto | Significado | Auto-admisión |
|-----------|-------------|---------------|
| `pass` | Duras + recibo firmado + análisis no false + juez no false | sí, si `AIMARKET_FEDERATION_AUTO_ADMIT=1` (default) |
| `review` | Nada ofrecido públicamente, un 402 sin instrucciones de pago, precio que no coincide con el catálogo, capability de pago servida sin cobrar, análisis fail o juez `block` | no |
| `fail` | SSRF, schema, firma mala, clave distinta | no |

Sin `AIMARKET_FEDERATION_JUDGE_KEY` / `OPENROUTER_API_KEY` el juez no se consulta y
**no hay auto-admisión**. El operador Aprueba en `/operator`. En prod el modelo es
MiniMax (`minimax/minimax-m3`) vía OpenRouter, el mismo token que el resto de la flota.

## Entorno

| Variable | Default | Efecto |
|----------|---------|--------|
| `AIMARKET_FEDERATION_ASSAY` | `1` | Interruptor maestro |
| `AIMARKET_FEDERATION_ASSAY_SANDBOX` | `1` | Probar hasta 3 capabilities públicas gratuitas |
| `AIMARKET_FEDERATION_AUTO_ADMIT` | `1` | `pass` → `trusted` + crawl. Alias: `AIMARKET_FEDERATION_ASSAY_AUTO_TRUST` |
| `AIMARKET_FEDERATION_JUDGE_URL` | vacío | POST chat compatible con OpenAI |
| `AIMARKET_FEDERATION_JUDGE_REQUIRED` | `0` | Error del juez bloquea la admisión |
| `AIMARKET_FEDERATION_ASSAY_REQUIRE` | `0` | Approve humano rechaza sin último `pass` |
| `AIMARKET_FEDERATION_ASSAY_LLM` | ignorado | No es juez de folleto |

## Escritorio del operador

`/operator` es la vía de **excepción**: hubs solo de pago, vetos, dismiss. No es la cola
estable de admisión.

## Límites de aislamiento

El hub no ejecuta el código del peer en un venv local ni gVisor. Hace POST a su invoke
público con tope de bytes (`262_144`) aplicado **durante el streaming**. Aislamiento **suave**,
como el preview de fábrica. Los guards SSRF siguen rechazando destinos privados / link-local.

El destino lo decide [`federation_transport`](../aimarket_hub/federation_transport.py), la misma
regla que usan los invokes enrutados: un peer que se declara hub (`hub_version`, o `v2` en
`protocol_versions`) se sondea en su `/ai-market/v2/invoke`, porque su `mcp_endpoint` habla MCP
JSON-RPC. Un servicio de capabilities simple conserva el endpoint que anuncia.
