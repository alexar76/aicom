# Failover de emergencia LLM — caída de DeepSeek → OpenRouter (MiniMax + Kimi K3)

Cuando **DeepSeek** falla, el pago no pasa o las claves dejan de funcionar, puede cambiar toda la ecosfera a **OpenRouter** en minutos.

## Cuándo usarlo

- Errores de pago / cuota / outage de DeepSeek en Factory, Metis, ATLAS, MOMUS, etc.
- Necesita una ruta cloud **fiable** mientras se arregla el billing de DeepSeek.
- Quiere la **fábrica en hold** para que el pipeline autónomo no empeore el incidente.

## Qué hace el script

`./scripts/failover_openrouter_minimax.sh`:

| Objetivo | Acción |
|----------|--------|
| **Factory** | `factory_on_hold: true`; proveedor `openrouter_api` por defecto |
| **Metis** | `prod.yaml`: base → MiniMax; asientos DeepSeek → OpenRouter; **`intent_parser_c` → `moonshotai/kimi-k3`** |
| **ATLAS** | overrides `ATLAS_LLM_*` en `.env` |

## Ejecución rápida

```bash
./scripts/failover_openrouter_minimax.sh --from-metis-env
```

## Restaurar DeepSeek

1. Quitar hold en Admin → Settings.
2. Restaurar copias `*.bak-*` de `prod.yaml` y `model_providers.yaml`.
3. Reiniciar contenedores.

Detalle completo (EN): [llm-failover-openrouter.md](llm-failover-openrouter.md)
