# 让你已经在运行的 API 成为节点

[English](run-a-node.md) · [Русский](run-a-node.ru.md) · [Español](run-a-node.es.md) · [Français](run-a-node.fr.md) · [中文](run-a-node.zh.md)

你已经通过 HTTP 在卖东西——一个 x402 路由，或一个 REST 端点。想被联邦里的枢纽发现，你不需要运行一个枢纽：`aimarket node` 是一个小进程，放在你的 API 旁边，替它说协议的语言。

- 发布签名的 `/.well-known/ai-market.json`，以及你列出的路由的签名清单，每次读取都重新签名。
- 响应 `POST /ai-market/v2/invoke` 时调用**你的**路由——GET 时把输入作为查询参数，POST 时作为 JSON——并在两个方向上透传 x402 支付头：你的 402 原样到达买家，付费后的重试连同付款一起到达你的路由。x402 V1（报价在响应体中）和 V2（报价在 `PAYMENT-REQUIRED` 中）都支持。
- 为你的路由每一个 2xx 响应签发收据。

你的钱还在原来的地方：节点不托管、不验证、也不转移任何付款。你的路由照旧完成这些事。

## 1. 描述你的路由

```bash
pip install "aimarket-hub[pqc]"            # 需要 Python 3.11+，或：uvx --from "aimarket-hub[pqc]" aimarket …
aimarket node init                         # 生成 node.toml
```

```toml
name = "Acme weather"
url = "https://api.acme.example"           # 其他枢纽访问该节点的地址
upstream = "http://127.0.0.1:8000"         # 你现在运行的 API

[[capability]]
id = "weather.now@v1"
product = "acme-weather"
description = "Current weather for a city"
price_usd = 0.002                          # 必须等于你的路由 402 所要求的金额
method = "GET"
path = "/weather"
input_schema = { type = "object", required = ["city"], properties = { city = { type = "string" } } }
```

如果你有免费路由，它是通过准入最快的证据：沙箱会调用它并检查收据上的节点签名。只有付费路由的节点则凭它的付款入口获准：未付款的调用必须返回 402，报价中写明你的钱包，价格与 `price_usd` 相同。

## 2. 在你的 API 旁运行

```bash
aimarket node serve --config node.toml     # 默认监听 127.0.0.1:9090（--host、--port）
```

把公网域名的两个路径转发给它，其余保持不变。Caddy：

```
api.acme.example {
    handle /.well-known/ai-market.json { reverse_proxy 127.0.0.1:9090 }
    handle /ai-market/* { reverse_proxy 127.0.0.1:9090 }
    handle { reverse_proxy 127.0.0.1:8000 }
}
```

nginx：`location = /.well-known/ai-market.json` 和 `location /ai-market/`，都设为 `proxy_pass http://127.0.0.1:9090;`。节点的密钥（默认 `data/node_signing_key`，旁边还有 `_mldsa`）就是它的身份：请备份。

## 3. 先检查，再敲门

```bash
aimarket doctor --url https://api.acme.example   # 其他枢纽将对你运行的准入检查
aimarket node knock                               # 向 modelmarket.dev 宣布（用 --hub 指定其他枢纽）
```

响应中带有 `assay_url`，结论会出现在那里。得到 `pass` 后，开启自动准入的枢纽会索引你的能力：它们会出现在这些枢纽的搜索、MCP 端点（`https://modelmarket.dev/mcp` 上的 `market_search` / `market_invoke`）和 `/hubs` 页面中。经由枢纽来的买家会原样看到你路由的 402（包括头部），并直接向你付款；枢纽不对直接 x402 销售收取路由费（节点声明了 `payment_rails.seller_direct`，枢纽据此得知）。

## 它不做什么

- 不定价，也不抽成；为你转发直接 x402 销售的枢纽同样不抽成：买家付给你路由的钱全部归你。
- 不会让你的路由变得安全或正确，也不为答案作保：由节点签名的收据记录的是你的路由作出了应答（capability、价格、时间、延迟、成功与否），而不是应答的内容。
- 联邦中的买家流量目前还很少。实时计数器是公开的：`https://verify.modelmarket.dev/demand.json`。
