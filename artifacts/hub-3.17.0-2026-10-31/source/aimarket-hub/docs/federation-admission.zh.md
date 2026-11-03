# 联邦准入 — 沙箱检测，然后自动编入索引

> **English:** [federation-admission.md](./federation-admission.md) · **Русский:** [federation-admission.ru.md](./federation-admission.ru.md) · **Español:** [federation-admission.es.md](./federation-admission.es.md) · **Français:** [federation-admission.fr.md](./federation-admission.fr.md)
>
> 代码：[`federation_assay.py`](../aimarket_hub/federation_assay.py) · [`api.py`](../aimarket_hub/api.py) · [`crawler.py`](../aimarket_hub/crawler.py) · [`config.py`](../aimarket_hub/config.py)
>
> 加入路径：[`docs/join-the-federation.zh.md`](https://github.com/alexar76/aicom/blob/main/docs/join-the-federation.zh.md)

---

## 为何存在

叩门（`POST /federation/announce` 或入站 `X-AIMarket-Crawler`）是一次 **观察**。
它绝不能把目录编入索引：那会变成清单注入。此前，离开隔离区的唯一出口是人在 `/operator`
上为每个新枢纽点击 Approve。

运营人员不会一直守着这条队列。因此隔离之后的准入是 **自动的**，但打分对象是
**沙箱里实际跑出来的结果**，而不是叩门者写在 `.well-known` 里的文案。

工厂对照（不要把工厂代码 import 进枢纽）：

| 工厂 | 联邦枢纽 |
|---------|----------------|
| `product_automated_verify` — 给运行中的测试/产物打分，而不是橱窗文案 | `analyze_sandbox_output` — safety gate + schema + 禁止私网 IP |
| `docs/sandbox-trust-model.md` — 软隔离，不是虚拟机监控器 | 对 *对方* 公开 invoke URL 做有界 HTTP POST（不在本地执行其代码） |
| `agents/surrogate_reviewer.py` — JSON approve/block | 可选 `AIMARKET_FEDERATION_JUDGE_URL` — **仅否决**，evidence 不含 `name`/`description` |

把 `name` / `description` 交给 LLM 会给流畅营销盖章。这条路已关闭。

## 流水线

```text
叩门 → pending（不编入索引）
    → 硬检查（SSRF / schema / Ed25519 / same-origin）
    → 对至多 3 项公开免费 capability 做 sandbox POST（第一份签名回执胜出）
    → 没有免费的？敲最便宜的付费能力，读它的 402（不付款）
    → 分析实时 payload
    → 可选 LLM 对 evidence 否决（无宣传字段）
    → pass + AUTO_ADMIT=1 → trusted + crawl
    → fail / review → 仍为 pending（运营台）
```

触发：无 token 的 announce 成功后的后台任务；每个 crawl 周期结束（最多 3 个 pending）；
管理员 `POST /ai-market/v2/federation/assay`。

## 裁决

| 裁决 | 含义 | 自动准入 |
|---------|---------|------------|
| `pass` | 硬检查 + 已签名收据 + 分析非 false + 裁判非 false | 是，若 `AIMARKET_FEDERATION_AUTO_ADMIT=1`（默认） |
| `review` | 没有任何公开供应、402 未给出支付说明、402 报价与目录不符、付费能力未收款即返回、分析失败或裁判 `block` | 否 |
| `fail` | SSRF、schema、签名错误、密钥不一致 | 否 |

没有 `AIMARKET_FEDERATION_JUDGE_KEY` / `OPENROUTER_API_KEY` 时不调用裁判，**也不会自动准入**。运营在 `/operator` 上 Approve。生产默认 MiniMax（`minimax/minimax-m3`）经 OpenRouter，与舰队其余服务同一把 token。

## 环境变量

| Variable | Default | 作用 |
|----------|---------|--------|
| `AIMARKET_FEDERATION_ASSAY` | `1` | 总开关 |
| `AIMARKET_FEDERATION_ASSAY_SANDBOX` | `1` | 探测至多 3 项公开免费 capability |
| `AIMARKET_FEDERATION_AUTO_ADMIT` | `1` | `pass` → `trusted` + crawl。别名：`AIMARKET_FEDERATION_ASSAY_AUTO_TRUST` |
| `AIMARKET_FEDERATION_JUDGE_URL` | 空 | OpenAI 兼容的 chat POST |
| `AIMARKET_FEDERATION_JUDGE_REQUIRED` | `0` | 裁判出错则阻止准入 |
| `AIMARKET_FEDERATION_ASSAY_REQUIRE` | `0` | 人工 Approve 在没有最近一次 `pass` 时拒绝 |
| `AIMARKET_FEDERATION_ASSAY_LLM` | 忽略 | 不是宣传文案裁判 |

## 运营台

`/operator` 是 **例外** 路径：纯付费枢纽、否决、驳回。它不是稳态准入队列。

## 隔离边界

枢纽不在本地 venv 或 gVisor 中运行 peer 的代码。它对对方的公开 invoke 做 POST，字节上限
`262_144`，并在 **流式读取过程中** 生效。这是与工厂 preview 同类的 **软** 隔离，不是多租户
虚拟机监控器。SSRF 防护仍拒绝私网 / link-local 目标。

探测哪个地址由 [`federation_transport`](../aimarket_hub/federation_transport.py) 决定，与路由
invoke 同一条规则：自称枢纽的 peer（`hub_version`，或 `protocol_versions` 含 `v2`）在其
`/ai-market/v2/invoke` 上被探测，因为它公布的 `mcp_endpoint` 讲的是 MCP JSON-RPC。纯能力服务
保留自己公布的端点。
