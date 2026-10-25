# 负载测试：2026-10-23 的结果，优化前后对比

**语言：** [English](load-testing.md) · [Русский](load-testing.ru.md) · [Español](load-testing.es.md) · [Français](load-testing.fr.md) · 中文

公开服务集群在负载下的表现、资金路径在并发下的表现、哪里慢以及为什么慢、改了什么。所有数字均于
2026-10-23 测得；复现命令见文末。

## 运行了什么

| 测试 | 工具 | 目标 | 负载 |
|---|---|---|---|
| 公开冒烟 | Locust 2.46.5，`scripts/load/run_load_smoke.sh` | 线上集群（只读） | 8 个用户，90 秒 |
| 公开恒定负载 | 同上 | 线上集群（只读） | 20 个用户，10 分钟 |
| 资金路径 | `aimarket-hub/scripts/load_money_path.py` | 本地 hub，SQLite 和 PostgreSQL | 2,300 个请求，64 个并发 |
| 工厂长时压测（KI-3） | `scripts/load_test_factory.sh` | 本地工厂后端，4 个 uvicorn worker | 10 个线程，15 分钟 |

公开测试只读取：工厂健康检查、目录和信任条、店面、hub 的搜索、统计和发现、mesh、ARGUS、monitor
和 pulse。它从不发起付费调用；资金路径在本地 hub 上测试。

## 公开集群，20 个用户，10 分钟

| | 优化前 | 优化后 |
|---|---|---|
| 请求数 | 7,538 | 7,626 |
| 失败 | **0（0.00%）** | **0（0.00%）** |
| 全部请求中位数 | 170 ms | 180 ms |
| 全部请求 p95 | 530 ms | 610 ms |

| 请求 | 优化前：中位数 / p95 | 优化后：中位数 / p95 | 变化 |
|---|---|---|---|
| 工厂 `GET /api/products`（店面） | 7.3 s / 12 s | **0.22 s / 2.0 s** | 中位数快 33 倍 |
| 工厂 `GET /api/marketing/trust-metrics` | 4.7 s / 7.8 s | **0.18 s / 0.75 s** | 中位数快 26 倍 |
| 工厂 `GET /api/health` | 0.18 s / 3.8 s | **0.17 s / 0.43 s** | p95 降低 9 倍 |
| 店面 `/` | 0.35 s / 0.38 s | 0.36 s / 0.60 s | — |
| hub 搜索 | 0.34 s / 0.56 s | 0.33 s / 0.65 s | — |
| hub 统计 | 0.17 s / 0.36 s | 0.18 s / 0.45 s | — |
| hub well-known | 0.33 s / 0.49 s | 0.34 s / 0.67 s | — |
| hub 资本定价 | 0.19 s / 0.39 s | 0.19 s / 0.46 s | — |
| Mesh、ARGUS、Pulse | 0.16–0.17 s / ≤ 0.18 s | 0.17 s / 0.24–0.40 s | — |
| Monitor `/api/health` | 0.16 s / 4.3 s | 0.17 s / 1.8 s | **已于 2026-10-23 部署**（见下文） |
| Monitor 状态 | 0.17 s / 3.0 s | 0.19 s / 2.4 s，最大 62 s | **已于 2026-10-23 部署**（见下文） |

“优化前”在审计修复上线后立即测量，“优化后”在下面的优化之后测量。标为“—”的行没有改动；差异来自两次
运行之间笔记本电脑的网络。

### 8 个用户的冒烟测试

| | 优化前 | 优化后 |
|---|---|---|
| 请求 / 失败 | 477 / 0 | 477 / 0 |
| 平均响应 | 306 ms | 253 ms |
| 工厂店面，中位数 | 5.1 s | 0.19 s |
| 工厂信任条，中位数 | 4.6 s | 0.18 s |
| 最慢请求 | 5.1 s | 2.4 s（monitor） |

### 20 个用户运行期间的服务器

| | 优化前 | 优化后 |
|---|---|---|
| 流水线 worker CPU（队列空闲） | 约一个核心的 89% | **16%** |
| 工厂 API CPU | 85–196% | — |
| hub CPU / 内存 | 0–55% / 0.1 GB | — |
| 平均负载（factory-vps） | 2.1–3.6 | — |
| 重启、限流拦截、工厂异常堆栈 | 0 / 0 / 0 | 0 / 0 / 0 |

### Monitor 部署前后

于 09:21 UTC 部署到 monitor.modelmarket.dev（镜像 `alien-monitor:overlaythread-20261023-alien-monitor-live`：运行中的
镜像加上新的 `main.py`）。部署前后使用同一探测：20 个客户端，每个大约每秒一次 `GET /api/health`，持续 90 秒，从同一台
笔记本发出。中位数主要是每个请求新建的 TLS 连接。

| | 部署前 | 部署后 |
|---|---|---|
| 请求 / 失败 | 960 / 0 | 1,060 / 0 |
| 中位数 | 685 ms | 666 ms |
| p95 | 1,844 ms | **1,147 ms** |
| p99 | 4,185 ms | **1,272 ms** |
| 最慢 | 4,330 ms | **1,369 ms** |

## 本地 hub 上的资金路径

许多账户发起付费调用，每个付费调用在同一个 `Idempotency-Key` 下同时重试三次，注册请求争抢 $0.25 的
赠送额度预算；之后审计账本。

| 数据库 | 请求数 | 并发 | 吞吐量 | p95 | 运行后的账本 |
|---|---|---|---|---|---|
| SQLite | 2,300 | 64 | 80 次/秒 | 2.3 s | 所有不变量成立；100 个带键的组每组只扣费一次；赠送额度止于 $0.25 |
| PostgreSQL 18 | 2,299 | 64 | 41 次/秒 | 4.3 s | 同上；一个连接中断，审计显示未扣费 |

不变量：账户的冻结金额等于其所有冻结中预留之和（运行结束后为零），资金不会凭空产生或丢失，每个带键
的组恰好扣费一次。

## 4 个 worker 的工厂后端（KI-3）

| | 修复前 | 修复后 |
|---|---|---|
| 15 分钟内的请求 | 25,577 | 33,710 |
| 被应用自身限流器拒绝的 `/api/health` | **17,907 次中 13,779 次** | **23,542 次中 0 次** |
| 失败（无响应或 5xx） | 0 | 0 |
| worker 重启 | 0 | 0 |
| 4 个 worker 的内存 | — | 480 → 435 MB，稳定 |

监管进程在连续五次健康检查失败后会杀掉后端。限流器原先把这项检查计入并在负载下拒绝它：一个繁忙的
后端因为繁忙而被杀掉。

## 哪里慢，改了什么

| 位置 | 原因（实测） | 改动 |
|---|---|---|
| 流水线 worker | 92% 的 CPU 花在 `yaml.safe_load`：每个周期为每个产品重新解析配置（py-spy，线上进程） | 只要配置文件（mtime、大小、inode）不变就复用解析结果 |
| 店面 `/api/products` | 19 个产品做了 57 次演示评估，每次都遍历产品目录树，包括 `node_modules`：5.4 秒中占 5.1 秒 | 遍历剪掉第三方目录；每个请求每个产品只评估一次；构建好的店面复用 30 秒，流水线一写入就重建 |
| 信任条 | 为了统计产品状态，花 4 秒加载工厂执行过的全部 3,510 个任务 | 只读取产品（0.4 ms）；缓存一分钟；在事件循环之外构建 |
| 工厂 `/api/health` | 事件循环被信任条阻塞 | 工作移到线程中 |
| KI-3 监管进程 | 健康检查被按地址限流器计入并拒绝 | 健康检查不计入；403/429 视为存活 |
| Monitor | 事件循环中用阻塞 HTTP 客户端轮询 17 个卫星服务 | 放到一个工作线程；**已于 2026-10-23 部署** |
| hub 日志 | 按配置关闭的 ACEX 账本每天产生 311 条异常堆栈 | 每个账本一条警告；返回同样的 503 |
| Director | 模型一次空回答就丢掉整个发现周期 | 失败的补充信息留空 |

## 复现

```bash
LOAD_TARGET=public LOAD_MODE=smoke ./scripts/load/run_load_smoke.sh
LOAD_TARGET=public LOAD_MODE=constant ./scripts/load/run_load_smoke.sh
python aimarket-hub/scripts/load_money_path.py --invokes 2000 --concurrency 64
python aimarket-hub/scripts/load_money_path.py --invokes 2000 --concurrency 64 --database-url postgresql:///scratch_db
./scripts/load_test_factory.sh --base-url http://127.0.0.1:9081 --duration 900 --concurrency 10
```

PostgreSQL 运行会清空所给数据库的 schema。方法、模式和通过标准：
[`scripts/load/METHODOLOGY.md`](../scripts/load/METHODOLOGY.md)。以往的运行：
[`scripts/load/RESULTS-2026-09-14.md`](../scripts/load/RESULTS-2026-09-14.md)。
