# Perfiles de enrutamiento LLM — flota de 4 servidores

| Perfil | Uso |
|--------|-----|
| `hybrid-metis` | Producción: DeepSeek + MiniMax OpenRouter en asientos escépticos de Metis |
| `deepseek-all` | Todo DeepSeek API; reanudar fábrica |
| `openrouter-all` | Emergencia: OpenRouter + hold de fábrica |

```bash
./scripts/switch_llm_profile.sh hybrid-metis
./scripts/switch_llm_profile.sh deepseek-all
./scripts/switch_llm_profile.sh openrouter-all --from-metis-env
```

EN: [llm-routing-profiles.md](llm-routing-profiles.md)
