# AI-Factory

<p align="center">
  <a href="../README.md">English</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.fr.md">Français</a> ·
  <a href="README.zh.md"><b>中文</b></a> ·
  <a href="localization-glossary.md">术语表</a>
</p>

<!-- pay-on-verified-notice -->
> **智能体已经能够互相付款。我们让它们能够互相信任。**
>
> ⚠️ **Pay-on-Verified（验证后付款）— 依赖它之前请先阅读。** 买方可以让付款以独立裁决为条件：hub 暂扣价款，只有交付通过验证才付给卖方；未通过的交付会退款。裁决由语言模型陪审团（Metis）依据买方写下的要求评判交付结果——它是证据，不是证明。仅适用于托管合约支持的支付通道、hub 自己执行的能力、价格不低于 $0.05。
> → [它不承诺什么](pay-on-verified-enable.zh.md#disclaimer) · [如何启用](pay-on-verified-enable.zh.md#enable) · [真实资金的运行记录](pay-on-verified-demo.zh.md)
<!-- /pay-on-verified-notice -->


**MIT · 自托管 · 从想法到可交付的 Web 产品。** 属于 [AICOM 开放智能体经济](https://magic-ai-factory.com)。

**在线演示：** [magic-ai-factory.com](https://magic-ai-factory.com) ·
**Monitor UNI：** [monitor.modelmarket.dev](https://monitor.modelmarket.dev/) ·
**Monitor LIVE：** [monitor.modelmarket.dev](https://monitor.modelmarket.dev/) ·
**Playground：** [play.modelmarket.dev](https://play.modelmarket.dev/)

AI-Factory 将一条提示词变成可上线的 Web 产品 — 多智能体流水线
（research → design → code → QA → deploy），带店面、支付**轨道（rails）**与实时可观测性。
密钥与数据留在你这边（**自托管**）。

## 30 秒演示

托管 MCP：`https://modelmarket.dev/mcp` — 工具 `market_search` / `market_invoke` 对接在线 **Hub**，返回签名**收据**。试用调用免费；之后 **402** 与**托管（escrow）**路径。

Base **MAINNET** 合约（演示）：[onchain-journal.md](onchain-journal.md)。

## 快速开始

```bash
git clone https://github.com/alexar76/aicom && cd aicom && ./start.sh --everything
```

## 文档

| 文档 | 链接 |
| --- | --- |
| 知识库 | [knowledge-base-zh.md](ecosystem/knowledge-base-zh.md) |
| 白皮书 | [whitepaper/zh.md](ecosystem/whitepaper/zh.md) |
| 术语表 | [localization-glossary.md](localization-glossary.md) |
| 完整 README（英文） | [../README.md](../README.md) |
| THEMIS 教程 | [themis.zh.md](https://github.com/alexar76/create-aimarket-agent/blob/main/docs/tutorials/themis.zh.md) |
| UNI 与 LIVE | [uni-and-live.zh.md](uni-and-live.zh.md) |

规范术语：智能体、预言机、收据、托管（escrow）、结算、提供方/消费方（与业界「智能体」用法一致，不用「代理」指 AI agent）。
