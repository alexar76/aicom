# Profils de routage LLM — flotte de 4 serveurs

| Profil | Usage |
|--------|-------|
| `hybrid-metis` | Prod : DeepSeek partout + MiniMax OpenRouter sur les sièges sceptiques Metis |
| `deepseek-all` | Tout sur l'API DeepSeek ; reprendre l'usine |
| `openrouter-all` | Urgence : OpenRouter + pause usine |

```bash
./scripts/switch_llm_profile.sh hybrid-metis
./scripts/switch_llm_profile.sh deepseek-all
./scripts/switch_llm_profile.sh openrouter-all --from-metis-env
```

EN : [llm-routing-profiles.md](llm-routing-profiles.md)
