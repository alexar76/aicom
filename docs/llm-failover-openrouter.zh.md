# LLM 紧急故障转移 — DeepSeek 中断 → OpenRouter（MiniMax + Kimi K3）

当 **DeepSeek** 宕机、无法付款或密钥失效时，可在数分钟内将整个生态切换到 **OpenRouter**，无需逐个手改服务。

## 适用场景

- Factory、Metis、ATLAS、MOMUS 等出现 DeepSeek 付款/配额/中断错误
- 修复 DeepSeek 账单期间需要**可靠**的云路径
- 需要将**工厂置于 hold**，避免自主流水线扩大故障

## 脚本作用

`./scripts/failover_openrouter_minimax.sh`：

| 目标 | 操作 |
|------|------|
| **Factory** | `factory_on_hold: true`；默认提供商 `openrouter_api` |
| **Metis** | `prod.yaml`：base → MiniMax；DeepSeek 槽位 → OpenRouter；**`intent_parser_c` → `moonshotai/kimi-k3`** |
| **ATLAS** | `.env` 中 `ATLAS_LLM_*` 覆盖 |

## 快速执行

```bash
./scripts/failover_openrouter_minimax.sh --from-metis-env
```

从 `/opt/metis/.env` 读取 `OPENROUTER_API_KEY`，更新 Metis 与 factory 主机，并重启相关容器。

## 恢复 DeepSeek

1. 在 Admin → Settings 取消 hold
2. 恢复 `prod.yaml` 与 `model_providers.yaml` 的 `*.bak-*` 备份
3. 重启 `metis`、`aicom-app-1`、`atlas-atlas-1`、`alien-monitor`

完整说明（EN）：[llm-failover-openrouter.md](llm-failover-openrouter.md)
