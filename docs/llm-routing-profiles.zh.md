# LLM 路由配置 — 四主机集群

| 配置 | 用途 |
|------|------|
| `hybrid-metis` | 生产：全局 DeepSeek；Metis 怀疑者席位经 OpenRouter 使用 MiniMax |
| `deepseek-all` | 全部切回 DeepSeek API；取消工厂 hold |
| `openrouter-all` | 应急：OpenRouter + 工厂 hold |

```bash
./scripts/switch_llm_profile.sh hybrid-metis
./scripts/switch_llm_profile.sh deepseek-all
./scripts/switch_llm_profile.sh openrouter-all --from-metis-env
```

英文全文：[llm-routing-profiles.md](llm-routing-profiles.md)
