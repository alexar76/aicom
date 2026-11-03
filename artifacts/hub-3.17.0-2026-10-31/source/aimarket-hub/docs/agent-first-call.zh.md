# 智能体首次调用：发现 → 调用 → 验证

[English](agent-first-call.md) · [Русский](agent-first-call.ru.md) · [Español](agent-first-call.es.md) · [Français](agent-first-call.fr.md) · [中文](agent-first-call.zh.md)

选择现有客户端即可。MCP 和 A2A 使用同一交易市场和调用控制，无需同时接入两种协议。

## MCP 客户端

在支持 Streamable-HTTP 的 MCP 客户端中添加 `https://modelmarket.dev/mcp`。通过 `tools/list` 查看当前参数结构，然后给智能体以下任务：

> 使用 `market_search` 查找 GAIA Open-Meteo 天气服务。显示所选报价的价格和输入结构。为 `device_id` `om-wx-01` 调用 `market_invoke`，从该报价复制 `product_id`、`capability_id` 和 `source_hub`。使用免费试用；如果要求付款，则停止。显示结果和收据。分别报告执行是否成功、收据是否通过验证；存在签名字段并不等于验证成功。

务必保留 `source_hub`：调用联邦报价时需要指定其来源。试用耗尽后，托管服务可能返回 `429 trial_quota_exhausted`。参见 [MCP 详情](https://github.com/alexar76/aicom/blob/main/docs/hosted-mcp-endpoint.md)。下面的 A2A 示例会在客户端明确验证签名。

## A2A 智能体

共用的 [Python 示例](../examples/first-agent-call.py) 获取 Agent Card，搜索 `gaia.weather.read@v1`，保留来源枢纽，并将单次调用价格限制为 $0.01。请使用 Python 3.11+，从 `aimarket-hub` 目录运行：

```bash
python -m pip install 'aimarket-agent>=2.4.0'
```

```bash
python examples/first-agent-call.py
python examples/first-agent-call.py --invoke
```

第一条命令仅执行搜索，第二条命令执行一次调用。未设置 `AIMARKET_KEY` 时，会使用尚未耗尽的免费试用。如需体验预付额度付款，请在调用前将 `AIMARKET_KEY` 设为已充值账户的 API 密钥；本次调用最多可能扣除 $0.01。不要把密钥写入脚本或提交记录。可通过 `AIMARKET_HUB_URL` 选择其他枢纽。

示例向 GAIA Open-Meteo 报价传入 `device_id` `om-wx-01`。若目录发生变化，请查看搜索结果中的输入结构。没有匹配报价时，示例会停止，不执行调用。

## 继续 x402 Task

退出码为 `2` 时，请查看 Task 中的支付条件。使用钱包支付该账单一次，等待结算，然后使用下方相同的 Task ID 和交易哈希。示例只提交已经完成的转账，不签署、发送或替换交易。账户所属的 Task 需要相同的 `AIMARKET_KEY`。读取已完成的 Task 不会再次付款或调用。

x402 后续处理的修复位于此 `aicom` 工作副本中。在 SDK 发布修复之前，请从 `aimarket-hub` 目录安装本地客户端：

```bash
python -m pip install -e ../aimarket-agent
```

```bash
python examples/first-agent-call.py --task-id a2at_... --payment-tx 0x...
python examples/first-agent-call.py --task-id a2at_...
```

## 解读结果

- 使用 `--invoke` 后退出码为 `0`：Task 状态为 `TASK_STATE_COMPLETED`，且 `receipt_verified` 为 true。SDK 已使用签名方的密钥验证收据；对于联邦报价，使用提供方的密钥。验证通过后才显示结果。
- 退出码 `1`：天气报价不可用。
- 退出码 `2`：Task 尚未完成。`TASK_STATE_INPUT_REQUIRED` 可能要求付款，`TASK_STATE_AUTH_REQUIRED` 可能要求提供凭据。请查看输出状态和[支付指南](a2a.md#invoke)。
- 退出码 `3`：执行已完成，但收据验证失败或未返回收据。不要将结果视为已验证。
- 退出码 `4`：收据有效，但缺少天气结果。仅执行成功和签名验证通过，仍不足以证明本示例成功。

不带 `--invoke` 时，退出码 `0` 仅表示发现成功。网络或协议错误也会使示例停止。示例不会自动充值、转账、继续付款或重试。Task 未完成并不证明没有扣款；重试前应查看状态。有意重试时，请按照 [A2A 指南](a2a.md)复用同一 `message_id`。

有效收据确认签名记录的真实性，并不能独立证明天气数据正确。试用限制和报价可用性由枢纽决定，本示例不作保证。
