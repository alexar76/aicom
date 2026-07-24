# DIOSCURI — 生态系统集成

**DIOSCURI**（社区双子智能体）如何与 GitHub、Gitea 和 Alien Monitor 一起融入 AICOM 技术栈。

**着陆页：** [alexar76.github.io/dioscuri](https://alexar76.github.io/dioscuri/) · **语言：** **[EN](./dioscuri-integration.md)** · **[RU](./dioscuri-integration-ru.md)** · **[ES](./dioscuri-integration-es.md)** · **[FR](./dioscuri-integration-fr.md)** · **ZH**

## 平面

| 平面 | 角色 |
|------|------|
| **Monorepo** `dioscuri/` | 事实来源 |
| **GitHub** `alexar76/dioscuri` | 公共镜像 — docs、CI、自托管参考 |
| **Gitea#2** `alexar76/dioscuri` | 私有运维镜像（rsync） |
| **VPS** | Docker compose — Castor (Telegram) + Pollux (Discord) |
| **Alien Monitor** | 图节点 — 轮询 `GET /health`，显示 KB + 适配器状态 |

发布 GitHub 镜像（无密钥）：

```bash
./scripts/publish_all_repos.sh --satellite dioscuri
```

同步 Gitea（运营者）：

```bash
./scripts/mirror_to_gitea.sh dioscuri
```

## 在 oracle 主机上部署 (oracles.modelmarket.dev)

DIOSCURI 运行在 **oracle VPS** 上，而非工厂机群（`modeldev.modelmarket.dev`）。Factory Monitor 仅轮询 `http://oracles.modelmarket.dev:8790/health`。

**一条命令**（mirror → Gitea#2 → ssh → git pull → compose）：

```bash
./scripts/deploy_dioscuri_oracle.sh
RUN_CANON_SLOT=1 ./scripts/deploy_dioscuri_oracle.sh   # + 第一个 THEOROS 列
```

需要免密码的 `ssh root@oracles.modelmarket.dev`（或 `ssh oracle` — 见 `~/.ssh/config`）。**git push** 的认证使用 `data/secrets/git-credentials`（与 `mirror_to_gitea.sh` 相同），而非 SSH。

mirror 之后在 oracle 上的手动等效操作：

```bash
ssh root@oracles.modelmarket.dev
cd /root/dioscuri && git pull --ff-only && docker compose up -d --build
DIOSCURI_RUN_SLOT=canon DIOSCURI_RUN_SLOT_EXIT=1 docker compose run --rm dioscuri
```

`./scripts/deploy_cognition.sh` 用于运行它的主机上的**本地** cognition 栈 — 不是远程 oracle 的封装。

## 密钥 — 绝不入 git

| 文件 | 用途 |
|------|------|
| `.env` | 机器人令牌、LLM 密钥、联合发布密钥 |
| `dioscuri.config.json` | 非密钥调优（链接、主题、审核旋钮） |

两者都从卫星 rsync 中**排除**（`satellite-map.yaml` → `exclude_paths`），并在 push 前由 `scripts/verify_mirror_secrets.sh` 拦截。

仅复制模板：

```bash
cp dioscuri/.env.example dioscuri/.env
cp dioscuri/dioscuri.config.example.json dioscuri/dioscuri.config.json
```

在本地填写令牌 — **绝不提交**。

## 社区链接（Telegram + Discord）

**生产环境（规范 — 用于 README 和 landing）：**

| 键 | URL |
|-----|-----|
| Telegram 机器人（Castor — Q&A） | https://t.me/next_agent_market_bot |
| Telegram 频道（Castor — 新闻） | https://t.me/just_for_agents |
| Discord (Pollux) | https://discord.gg/aimarket |

自托管者在 `dioscuri.config.json` 中设置邀请链接：

```json
"links": {
  "discordInvite": "https://discord.gg/YOUR_INVITE",
  "telegramChannel": "https://t.me/YOUR_CHANNEL",
  "telegramBot": "https://t.me/YOUR_BOT",
  "siteUrl": "https://magic-ai-factory.com",
  "githubOrg": "https://github.com/alexar76"
}
```

Alien Monitor 从 env 读取公共链接（可选，用于图面板）：

```bash
ALIEN_DIOSCURI_TELEGRAM_BOT_URL=https://t.me/next_agent_market_bot
ALIEN_DIOSCURI_TELEGRAM_CHANNEL_URL=https://t.me/just_for_agents
ALIEN_DIOSCURI_DISCORD_URL=https://discord.gg/YOUR_INVITE
ALIEN_DIOSCURI_URL=http://dioscuri:8790          # 轮询目标（compose 网络）
```

## THEOROS（canon 列）

**THEOROS** 是同一 DIOSCURI 进程中的第三个 persona — 而非独立的机器人。它每周向 Discord `#the-canon` 发布 **Agent Sovereignty Canon**（周日约 16 UTC，content kind `canon`）。

| 资源 | URL |
|------|-----|
| 语料库 + landing | [alexar76/theoros](https://github.com/alexar76/theoros) · [alexar76.github.io/theoros](https://alexar76.github.io/theoros/) |
| 辩论 | DIOSCURI Discord 上的 `#canon-debate` |
| 配置 | `dioscuri.config.json` 中的 `links.theorosUrl`；将 `"theoros"` 添加到 `githubRepos` 以用于 MNEMOSYNE 的 grounding |
| 手动运行 | `DIOSCURI_RUN_SLOT=canon DIOSCURI_RUN_SLOT_EXIT=1` |

Castor/Pollux 宣布各章节；它们**不会**假冒 Theoros。完整指南：**[dioscuri/docs/theoros.md](../../dioscuri/docs/theoros.md)**（架构、voice charter、配置、清单）。

## Alien Monitor 节点

**DIOSCURI** 节点出现在 client shelf 的西北侧。它轮询：

```
GET {ALIEN_DIOSCURI_URL}/health
```

使用的响应字段：`adapters.telegram`、`adapters.discord`、`kb.chunks`、`kb.repos`、`uptimeSec`、`social.*`（缓存的 Discord/Telegram/X 指标）。

灰色 = 不可达；金色脉冲 = 至少一个双子处于活动状态或 KB 已初始化。

### 社交统计（缓存）

当配置了平台 API 令牌时，`GET /health` 会包含 `social`：

| 字段 | 来源 |
|------|------|
| `discord_members` | Discord Bot API `approximate_member_count` |
| `telegram_members` | Telegram `getChatMemberCount` |
| `twitter_followers` | X API v2 `public_metrics` |

缓存 TTL：`DIOSCURI_SOCIAL_CACHE_SEC`（默认 300s）。Alien Monitor 在点击节点时立即从缓存显示指标 — 图不会发起实时 API 调用。

可选 env：`TWITTER_BEARER_TOKEN`、`TWITTER_USER_ID`、`TELEGRAM_CHANNEL_ID`。

## HELIOS 联合发布（可选）

当 `HELIOS_SYNDICATION=1` 时，DIOSCURI 在每次新的 GitHub release 上向 `HELIOS_QUEUE_PATH` 追加 `release-short` 任务（fail-soft）。见 [helios-integration.md](./helios-integration.md)。

## MNEMOSYNE ↔ GitHub

双子从**公共 GitHub 仓库**（`githubOwner: alexar76`）同步 README 和 release。DIOSCURI 无需在 KB 列表中拥有自己的仓库即可回答生态系统问题 — 但发布 `alexar76/dioscuri` 可让双子记录自身。

## 合著者与协作者

卫星 push 会压缩为**单个由人类署名的提交**（`sanitize_git_commit_meta.py` 会剥离 `Co-Authored-By` 和 AI 工具 trailer）。push 之后，`prune_github_collaborators.py` 会从仓库中移除 bot/cursor/copilot 协作者。

## 相关

- [DIOSCURI README (EN)](../../dioscuri/README.md) · [RU](../../dioscuri/README-ru.md) · [ES](../../dioscuri/README-es.md)
- [Setup](../../dioscuri/docs/setup.md)
- [生态系统知识库](./knowledge-base.md)
- [Gitea 发布](../gitea-publishing.md)（内部）
