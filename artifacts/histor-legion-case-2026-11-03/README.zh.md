# 在同一个 MCP 服务器上比对 HISTOR 与 LEGION-tlog

[English](README.en.md) · [Русский](README.md) · [Español](README.es.md) · [Français](README.fr.md) · [简体中文](README.zh.md)

两个独立的透明日志能否在相近时间相互印证同一个 MCP 服务器公布的工具定义？我们选择 LEGION-tlog，因为它公开观测时间和每个工具的 SHA-256 指纹。这样就能找到一致的工具集，并定位同一服务器 `com.aiapplyd/aiapplyd` 在后续观测中的差异。

| HISTOR 观测时间（UTC） | 与 LEGION 的比对结果 |
|---|---|
| 2026 年 10 月 19 日 21:37:07 | 对 `name`、`description` 和 `inputSchema` 计算的 23 个指纹全部与 LEGION 在 22:01:05 的观测一致。 |
| 10 月 24 日 18:19:21 | 23 个工具名称的前缀从 `aiapplyd_` 变为 `getmattered_`，后缀保持一致。归档的 LEGION 响应仍显示 10 月 19 日的记录。 |
| 10 月 31 日 12:45:49 | HISTOR 记录了 40 个工具，名称与归档的 LEGION 记录没有交集。11 月 2 日的快照包含这个工具集。后一次读取时间来自快照元数据。 |

## 离线验证

在仓库根目录使用 Node.js 22 运行。

```sh
node artifacts/histor-legion-case-2026-11-03/replay.mjs
```

将输出与 [result.json](result.json) 比对。脚本验证 LEGION 的 Ed25519 签名，并检查叶子 29030 在包含 50 578 个叶子的签名树头（STH）下的包含证明。随后验证 HISTOR 包含 1 564 894 个叶子的 STH，以及叶子 762851、988911 和 1324412 对应的 MTL/1 标签签名和包含证明。脚本还会重新计算每个工具集的 SHA-256 摘要，与签名标签中的摘要核对，再逐个比对工具指纹。

证据范围限于这些观测和对应的默克尔树树头。服务器安全性、归档的 LEGION 响应未记录后续变更的原因、树头之间的一致性以及比特币锚定均不在本次验证范围内。

[数据来源](README.md) · [HISTOR 日志文档](../../histor/docs/log.zh.md) · [LEGION 规范](https://legion-api.com/tlog/docs/)
