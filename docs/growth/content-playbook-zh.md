# Content playbook — landing、README 与 docs

> 🌐 语言： [English](./content-playbook.md) · [Русский](./content-playbook-ru.md) · [Español](./content-playbook-es.md) · [Français](./content-playbook-fr.md) · **中文**

面向所有接触 AICOM 生态系统仓库的智能体与人类的 playbook。**面向公众的文案仅用英语。** 俄语应放在明确的 RU 配套文件里（例如 DIOSCURI 上的 `README-ru.md`）— 不要混进主 README 或 landing。

**另见：** [THEOXENIA content plan](https://github.com/alexar76/dioscuri/blob/main/docs/content-plan.md) · [seeding playbook](./seeding-playbook.md) · [knowledge base](../ecosystem/knowledge-base.md)

---

## 1. 规范链接（各处统一一套）

每个仓库都必须使用相同的 URL。DIOSCURI 从 `dioscuri.config.json` → `links` 读取它们；审核会删除非规范的 Discord/Telegram 邀请。

| 是什么 | 生产 URL | 用途 |
|--------|---------|------|
| Telegram bot (Castor) | https://t.me/next_agent_market_bot | Q&A — 向孪生提问 |
| Telegram channel (Castor) | https://t.me/just_for_agents | 新闻、发布、摘要 |
| Discord (Pollux) | https://discord.gg/aimarket | 讨论、求助、show-and-tell |
| 生态系统 | https://magic-ai-factory.com | 主站 |
| 镜像 / dev | https://modeldev.modelmarket.dev | 演示、staging |
| Observatory | https://magic-ai-factory.com/monitor/ | 整套系统的实时状态 |
| GitHub org | https://github.com/alexar76 | 代码 |
| DIOSCURI | https://github.com/alexar76/dioscuri | 孪生、setup |
| THEOROS canon | https://alexar76.github.io/theoros/ | Agent Sovereignty Canon · Discord 上的 `#the-canon` |
| THEOROS repo | https://github.com/alexar76/theoros | CANON.md、章节、花岗岩风格 landing |

**规则：** 不要自造 Discord/Telegram 邀请。如果需要第二个频道，先达成一致并把它加入 DIOSCURI 的 `links`。

---

## 2. 两扇门 — 两类受众

不要使用单一泛化的「join community」CTA。要有两条不同的路径：

| 受众 | CTA | Copy (EN) |
|------|-----|-----------|
| 观察者 | Telegram | “Release news and digests — Castor on Telegram” → https://t.me/just_for_agents |
| 开发者 | Discord | “Discuss, ask, show what you built — Pollux on Discord” → https://discord.gg/aimarket |

每个 README 与 landing 都包含**两个**链接。顺序取决于仓库类型：

| 仓库类型 | 领头的 community 链接 |
|----------|----------------------|
| SDK / client / widget | **Discord 优先**（开发者） |
| Demo / monitor / landing | **Telegram 优先**（展示） |

---

## 3. Landing — 必需区块

最小骨架（见 [DIOSCURI `landing/index.html`](https://github.com/alexar76/dioscuri/blob/main/landing/index.html)）：

### Hero

- **Eyebrow：** Community · AICOM · MIT（或项目角色）
- **H1：** 产品名 — 不要 crypto hype
- **Subtitle：** 一句话 — 它做什么，而不是你有多牛
- **3 个 CTA：** Demo · GitHub · Community（Telegram + Discord）

### 这是什么（2–3 段）

问题 → 解决方案 → 在生态系统中的位置（Factory / Oracles / AIMarket / ARGUS）。一个指向 [Alien Monitor](https://magic-ai-factory.com/monitor/) 的链接作为存活证明。

### Features（3–6 张卡片）

事实，而非营销迷雾：端口、协议、今天真正能用的东西。有 live demo 时给出链接。

### Community block（必需）

> Questions? The DIOSCURI twins answer from synced GitHub docs.
>
> • Telegram (Castor) — fast news: https://t.me/just_for_agents
> • Discord (Pollux) — deep threads: https://discord.gg/aimarket

### Footer

Repository · Setup/Docs · Alien Monitor · AICOM ecosystem ·（可选）俄语 README

### Meta / SEO

- `description` — ≤160 字符，具体事实
- `og:title`、`og:description` — 相同事实、相同语气
- 公开页面上 `lang="en"`

---

## 4. README — 必需章节

### Top (after badges)

```markdown
Part of the [AICOM open agent economy](https://magic-ai-factory.com).
**Live demo:** <url> · **Community:** [Telegram](https://t.me/just_for_agents) · [Discord](https://discord.gg/aimarket)
```

### What it does

3–5 条要点。每条都是可验证的事实（「syncs READMEs every 60 min」），而不是「revolutionary AI」。

### Quick start

copy-paste 命令。如果有 demo URL，把它单独放在 install 之后紧接的一行。

### Demo URLs（对 MNEMOSYNE 至关重要）

DIOSCURI 会解析 README 并把 demo 链接拉进指南与截图。格式：

```markdown
## Demo
- **Live:** https://modeldev.modelmarket.dev/your-demo/
- **Docs:** https://github.com/alexar76/your-repo/blob/main/docs/setup.md
```

如果没有 demo，就写 **No public demo yet** — 不要省略该章节。

### Related repos

3 到 8 个生态系统相邻仓库的表格并带链接。帮助孪生回答「它旁边有什么？」。

### Community（结尾处）

与 landing 上相同的区块。可选补充：

> Release announcements are syndicated by [KERYX](https://github.com/alexar76/dioscuri#keryx-syndication-post-only) (post-only, no spam automation).

---

## 5. Docs (`docs/`) — 规则

| 类型 | 文件 | 内容 |
|------|------|------|
| Setup | `docs/setup.md` | env 变量、端口、首次运行 |
| Usage | `docs/usage.md` | 怎么用 — 而不是怎么营销 |
| Architecture | `docs/architecture.md` | 图表、模块边界 |
| Security | `docs/security.md` | 威胁以及代码实际做了什么 |

在每个 `setup.md` 中：

- 在 **Support / Community** 章节放 community 链接
- 若服务在 Alien Monitor 上出现，则放其链接
- 示例中不含密钥（`REPLACE_ME`，而非真实 token）

**Cross-links：** org 内部用相对路径；从外部用完整 URL。

---

## 6. 语气与风格（THEOXENIA charter）

与 [`docs/content-plan.md`](https://github.com/alexar76/dioscuri/blob/main/docs/content-plan.md) 对齐：

- 公开帖子、landing、Discord 指南中 **English only**
- Dry, technical, myth-flavored — **每帖一个 Olympus touch**，不多于此
- Twins tease each other, never users
- **No hype：** 不用 revolutionary、game-changer、to the moon、price talk、airdrops
- **No emoji walls** — emoji 作为标记（🔨 digest、⚒ release），而非装饰
- **Silence beats filler** — 空档的一周 → 不发 digest，而不是编造一个

被禁的 corporate 短语 — 见 [`dioscuri/src/personas/index.ts`](https://github.com/alexar76/dioscuri/blob/main/src/personas/index.ts) 中的 `styleCharter()`。如果孪生会引用你的文本，就不要使用这些短语。

---

## 7. 什么能帮到 MNEMOSYNE（以及孪生）

README 与 docs 是 bot 的饲料。写作时要让 retrieval 返回有用的答案：

- 清晰的 **H1** = 项目名
- 第一段 = 一句话：「X is Y that does Z」
- **Demo** 章节带一个可用的 URL（不是 localhost）
- **Related** 章节 — 生态系统邻居
- Release notes：第一句以句号结束（KERYX 用它发 Mastodon/Bluesky）
- README 里不要开 prompt-injection 玩笑（「ignore previous instructions」）— AEGIS 会丢掉该 chunk

---

## 8. KERYX / releases — release notes

当你给一个 release 打 tag 时，KERYX 会自动发布：

```
⚒ your-repo v1.2.3 shipped — Short plain title here
https://github.com/alexar76/your-repo/releases/tag/v1.2.3
Community: discord.gg/aimarket | t.me/just_for_agents
```

给作者：

- release notes 第一行 — plain English title，≤120 字符，尽量以句号结尾
- 开头不要 markdown 墙（`##`、`**`、要点）— Mastodon 反垃圾会抓到 junk
- Mastodon：在使用 API 之前手动养号；细节见 [`docs/use-cases.md`](https://github.com/alexar76/dioscuri/blob/main/docs/use-cases.md) §9

---

## 9. 红线 — 不要写

- 自造的 `discord.gg/…` 或 `t.me/…` 邀请（审核 = delete）
- 「Join for airdrop / whitelist / pump」
- 付费流量、join4join、auto-bump DISBOARD
- README、docs 或 landing 里的密钥
- 没有 demo 链接的「AI does everything」
- 每次部署都重复的 setup 帖子（幂等是 DIOSCURI 的活儿，不是你 README 的）

---

## 10. 合并前检查清单

- [ ] Hero：它做什么 + demo + GitHub + community（TG + Discord）
- [ ] README 里的 Demo URL（可用，不是 502）
- [ ] Related repos — 3+ 个邻居
- [ ] 公开文本为英语
- [ ] 规范的 community 链接（不是自造邀请）
- [ ] Release notes：第一行简洁且短
- [ ] docs 里没有密钥、没有 hype、没有 injection 玩笑
- [ ] 若项目在 Alien Monitor 上，则带其链接

---

## 11. Copy-paste — README community block

```markdown
## Community

The [DIOSCURI](https://github.com/alexar76/dioscuri) twins answer questions from synced GitHub docs.

| Channel | Twin | Best for |
|---------|------|----------|
| [Telegram](https://t.me/just_for_agents) | Castor | Releases, digests, quick news |
| [Discord](https://discord.gg/aimarket) | Pollux | Help, ideas, show-and-tell |

**Ecosystem map:** [Alien Monitor](https://magic-ai-factory.com/monitor/) · [AICOM](https://magic-ai-factory.com)
```

---

## 12. Copy-paste — landing CTA row

```html
<a href="https://t.me/just_for_agents">Telegram · Castor</a>
<a href="https://discord.gg/aimarket">Discord · Pollux</a>
<a href="https://github.com/alexar76/YOUR_REPO">GitHub</a>
<a href="YOUR_DEMO_URL">Live demo</a>
```

---

## 13. Copy-paste — 「Ask the twins」按钮

landing 与 hero rows 上的主 CTA — 链接到 live 频道，而不是 `#` 锚点或 setup docs：

```html
<a href="https://t.me/next_agent_market_bot">Ask Castor · Telegram</a>
<a href="https://discord.gg/aimarket">Ask Pollux · Discord</a>
```

在 **demo / monitor / landing** 仓库上，Telegram 优先。在 **SDK / client / widget** 仓库上，Discord 优先。

给自托管孪生的运营方的可选二级链接：`Deploy your twins` → `docs/setup.md`。

---

## 14. YouTube 广播（HELIOS）

视频上传**不再是**手动的 `upload_youtube.py` — 请使用 [HELIOS](https://github.com/alexar76/helios/blob/main/README.md)：

| 步骤 | 命令 |
|------|------|
| 批量 backfill | `helios backfill-enqueue -n 10`，然后 `helios worker` |
| Approve | 在 Studio 中审阅私有视频 → `helios approve JOB_ID` |
| 新发布的 short | `helios enqueue --template release-short --repo REPO --tag TAG` |
| 编辑侦察 | 在 `helios worker`（cron）上自动 — 或 `helios calliope run-editorial` |

### Growth cadence（频道 @My-AI-Factory）

| 阶段 | 上传 | 公开节奏 | 组合 |
|------|------|----------|------|
| **现在 Backfill** | 每天最多 9 个私有 | 按批 approve | PromoMaterials E10+ 积压 |
| **稳定期** | 每次侦察运行 1 个 CALLIOPE 脚本 | **每周 2–4 个公开** | 常青讲解 + 仓库深度剖析 |
| **Releases** | 按 tag 的 DIOSCURI `release-short` | 附加 | 生态系统打 tag 时发布新闻 |
| **Human gate** | 始终先私有 | 从不自动公开 | Studio + `helios approve` |

编辑配置（`helios.config.yaml` → `calliope`）：

- `scout_interval_days: 3` — 每周约 2 次侦察运行，创意记录到 `data/editorial/scout_log.jsonl`
- `weekly_enqueue_quota: 3` — 质量重于数量
- `backfill_pause_threshold: 8` — 不与积压上传争抢

**Charter：** private-first，backfill 只用模板 VO，新内容用基于 MNEMOSYNE 的脚本，不做任何互动自动化。Monitor 节点显示缓存的 YouTube 统计。

---

## Summary

Landing 与 README 不是广告 — 它们是**入口地图**：demo → 代码 → 两个 community 频道 → Monitor 上的生态系统。一个声音、一套链接、来自仓库的事实。只要你留给孪生和 KERYX 一个像样的 README，其余的它们会自己搞定。
