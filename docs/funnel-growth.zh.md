# 漏斗增长层 (Funnel growth)

> **English:** [funnel-growth.md](./funnel-growth.md) · **Русский:** [funnel-growth.ru.md](./funnel-growth.ru.md) · **Español:** [funnel-growth.es.md](./funnel-growth.es.md) · **Français:** [funnel-growth.fr.md](./funnel-growth.fr.md) · **中文**

公开的潜在客户（lead）捕获、流水线自动启动、状态跟踪、分析，以及交付后分发。实现位于 `web/backend/services/funnel_*` 和 `web/backend/api/marketing.py`。

---

## 概览

| 界面 | 路径 / API | 用途 |
|------|-----------|------|
| 潜在客户表单 | `/lead` | 公开简报 → 可选的自动流水线 |
| 状态页 | `/status/{token}` | 轮询产品状态（15 秒） |
| 信任指标 | 首页 `TrustMetricsStrip` | 实时 shipped / in-pipeline / leads |
| 管理小组件 | Dashboard → Funnel 卡片 | `GET /api/admin/funnel/dashboard` |
| Waitlist embed | `GET /api/marketing/waitlist.js` | 生成的落地页上的表单 |

当流水线进入 **COMPLETED** 时，`orchestrator/task_executor_agent.py` 调用 `funnel_distribute`（hub 自动上架 + 博客）和 `notify_lead_product_completed`（email）。

---

## 公开 API

### `POST /api/marketing/lead`

```json
{
  "email": "owner@example.com",
  "idea": "Marketing landing for AI scheduling assistant with waitlist",
  "name": "",
  "company": "",
  "source": "lead_page",
  "referral": null
}
```

响应包含 `status_token`、`status_url`、`product_id`、`pipeline_started`。

### `GET /api/marketing/lead/status/{token}`

公开（无需鉴权）。返回脱敏的 email、`product_state`、`storefront_url`、`sandbox_ready`。

### `POST /api/marketing/waitlist`

用于生成的落地页。请求体：`{ "product_id", "email", "name?", "meta?" }`。

### 在生成的落地页中嵌入

```html
<script src="/api/marketing/waitlist.js" data-product-id="prod-xxx"></script>
<form data-aifactory-waitlist>
  <input type="email" name="email" required />
  <button type="submit">Join waitlist</button>
</form>
```

或通过 **Admin → Settings → published site head HTML** 注入该脚本。

---

## 环境变量

| 变量 | 默认值 | 作用 |
|------|--------|------|
| `AIFACTORY_LEAD_AUTO_PIPELINE` | `1` | 提交 lead 时将 `marketing_landing` 产品加入队列 |
| `AIFACTORY_FUNNEL_AUTO_HUB_LIST` | `1` | COMPLETED 时在 hub 上架产品 |
| `AIFACTORY_FUNNEL_NOTIFY_DISABLE` | 未设置 | 为 `1` 时跳过完成通知 email |
| `AIFACTORY_FUNNEL_DIR` | `data/funnel/` | leads 与 waitlist 的持久化 |
| `OUTREACH_SMTP_*` / `AIFACTORY_FUNNEL_SMTP_*` | — | 完成通知 email（复用 outreach SMTP） |

Docker `data-init` 与 `entrypoint.sh` 创建 `data/funnel/` 和 `data/logs/marketing/`，属主为 UID `10001`。

---

## 持久化

| 文件 | 内容 |
|------|------|
| `data/funnel/leads.json` | lead 记录、状态 token、产品关联 |
| `data/funnel/waitlist.jsonl` | 仅追加（append-only）的 waitlist 注册 |
| `data/logs/marketing/events.jsonl` | 分析事件（也用于漏斗指标） |

---

## 管理后台 (Admin)

- **`GET /api/admin/funnel/dashboard?window_hours=168`** — 漏斗阶段、7 天内 leads、已付订单、最近 leads。
- 需要管理员 RBAC（`Depends(require_admin_with_rbac)`）。

---

## 测试

`tests/test_funnel_growth.py` — lead 自动流水线、公开状态、分析阶段。

---

## 不在范围内（未来）

- 落地页 CTA 的 Stripe 一次性结账
- 弃购挽回
- Hero 区域的 email 捕获（hero 仍使用 `/api/public/generate-landing`）

另见：[marketing.md](./marketing.md)（storefront 分析）、[pipeline-operations.md](./pipeline-operations.md)。
