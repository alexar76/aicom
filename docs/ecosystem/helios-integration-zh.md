# HELIOS 集成 — monorepo 卫星

🌐 **[English](./helios-integration.md)** · **[Русский](./helios-integration-ru.md)** · **[Español](./helios-integration-es.md)** · **[Français](./helios-integration-fr.md)** · **中文**

HELIOS 位于 AICOM monorepo 的 `helios/`，并镜像到 [github.com/alexar76/helios](https://github.com/alexar76/helios)。

## 平面

| 平面 | 角色 |
|------|------|
| **Monorepo** `helios/` | 事实来源 |
| **GitHub** `alexar76/helios` | 公共镜像 — docs、CI、自托管 |
| **运营者主机** | ffmpeg + YouTube OAuth + cron worker |
| **Alien Monitor** | 图节点 — 轮询 `GET /health`、YouTube 统计 |

```bash
./scripts/publish_all_repos.sh --satellite helios
```

## 密钥 — 绝不入 git

| 文件 | 用途 |
|------|------|
| `.env` | `YOUTUBE_*`、LLM 密钥、webhook |
| `helios.config.yaml` | 非密钥调优（限制、资源根目录） |

两者都从卫星 rsync 中排除（`satellite-map.yaml` → `exclude_paths`）。

## Alien Monitor 节点

| Env | 用途 |
|-----|------|
| `ALIEN_HELIOS_URL` | 轮询 `GET /health`（默认 `http://127.0.0.1:8791`） |
| `ALIEN_PUBLIC_HELIOS_URL` | 节点详情链接（GitHub 仓库） |
| `ALIEN_HELIOS_YOUTUBE_URL` | 面板中的 YouTube 频道链接 |

**health 响应：**

```json
{
  "ok": true,
  "version": "0.1.0",
  "uptimeSec": 3600,
  "queue_pending": 3,
  "uploaded_today": 2,
  "max_uploads_per_day": 9,
  "dryRun": false,
  "youtube": {
    "subscribers": 1200,
    "views": 45000,
    "videos": 12,
    "cached_at": "2026-07-07T10:00:00Z",
    "stale": false
  }
}
```

**位置：** 西北架 (`helios` @ `-8.5, 7.5, -5.0`)。  
**边：** `factory → helios`、`dioscuri → helios`（release 队列）。

点击节点 → 缓存的 YouTube 统计（Monitor 不发起实时 API 调用）。

## DIOSCURI 钩子

```bash
# dioscuri .env
HELIOS_SYNDICATION=1
HELIOS_QUEUE_PATH=/data/helios-queue.jsonl
```

HELIOS worker 在每次运行 `helios worker` 时摄取 jsonl。

**Docker（共享卷）：**

```bash
docker volume create aicom-ecosystem-data
docker compose -f dioscuri/docker-compose.yml -f helios/docker-compose.yml \
  -f docs/ecosystem/docker-compose.cognition.yml up -d --build
```

## PromoMaterials

内容保留在 PromoMaterials 中；HELIOS 是引擎：

```bash
helios backfill-scan
helios backfill-enqueue -n 10
helios worker
```

## 相关文档

- [HELIOS landing](https://alexar76.github.io/helios/) — 视频库 + [@My-AI-Factory](https://www.youtube.com/@My-AI-Factory)
- [HELIOS README](../../helios/README.md) · [RU](../../helios/README-ru.md) · [ES](../../helios/README-es.md)
- [架构](../../helios/docs/architecture.md)
- [安全审计](../../helios/docs/SECURITY-AUDIT.md)
- [知识库](./knowledge-base.md)
