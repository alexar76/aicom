# Basculement d'urgence LLM — panne DeepSeek → OpenRouter (MiniMax + Kimi K3)

Quand **DeepSeek** est en panne, le paiement échoue ou les clés ne fonctionnent plus, basculez toute l'écosphère sur **OpenRouter** en quelques minutes.

## Quand l'utiliser

- Erreurs de facturation / quota / outage DeepSeek sur Factory, Metis, ATLAS, MOMUS, etc.
- Besoin d'une voie cloud **fiable** pendant la résolution du billing DeepSeek.
- Mettre l'**usine en pause** (soft hold) pour éviter que le pipeline autonome aggrave l'incident.

## Ce que fait le script

`./scripts/failover_openrouter_minimax.sh` :

| Cible | Action |
|-------|--------|
| **Factory** | `factory_on_hold: true` ; fournisseur par défaut `openrouter_api` |
| **Metis** | `prod.yaml` : base → MiniMax ; sièges DeepSeek → OpenRouter ; **`intent_parser_c` → `moonshotai/kimi-k3`** |
| **ATLAS** | overrides `ATLAS_LLM_*` dans `.env` |

## Lancement rapide

```bash
./scripts/failover_openrouter_minimax.sh --from-metis-env
```

## Revenir à DeepSeek

1. Reprendre l'usine dans Admin → Settings.
2. Restaurer les sauvegardes `*.bak-*`.
3. Redémarrer les conteneurs.

Détails (EN) : [llm-failover-openrouter.md](llm-failover-openrouter.md)
