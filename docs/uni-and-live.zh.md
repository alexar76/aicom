# UNI 与 LIVE — 两个领域

> **English:** [uni-and-live.md](./uni-and-live.md) · **Русский:** [uni-and-live.ru.md](./uni-and-live.ru.md) · **Español:** [uni-and-live.es.md](./uni-and-live.es.md) · **Français:** [uni-and-live.fr.md](./uni-and-live.fr.md) · **中文**

两个进程、两个 Hub、两份目录。混在一起，就会把气泡里的美元当成营收。

本页只讲 **UNI 对 LIVE**。TEST 是同一监视器进程上的第三层覆盖，不是第三套经济。链上开关：
[crypto-switch.zh.md](./crypto-switch.zh.md)。UNI 封印：[uni-realm.md](./uni-realm.md)。

## 一览

| | **LIVE** | **UNI** |
|---|---|---|
| Hub | [modelmarket.dev](https://modelmarket.dev) | [uni.modelmarket.dev](https://uni.modelmarket.dev) |
| Alien Monitor | [`monitor.modelmarket.dev`](https://monitor.modelmarket.dev/) · `:9101` · `ALIEN_MODE=real` | [monitor-uni.modelmarket.dev](https://monitor-uni.modelmarket.dev/) · `:9100` · `ALIEN_MODE=universe` |
| 资金 | 加密**开启**时走 Base | 私有 Anvil，chain id `31337` — 模拟 |
| 目录 | 实况联邦（Platon、ATLAS、GAIA、预言机……） | 下方六个气泡实验室 |
| 这六个实验室 | **不是** LIVE 联邦对等方 | KHRONOS · STOICHEION · HORIZON · PSEPHOS · KYMA · DIKTYON |
| 部署 Hub | `./scripts/deploy_hub.sh` | `bash deploy/uni-hub.sh …` |
| 部署能力 | 实况卫星主机 | `bash deploy/uni-satellites.sh` |
| 部署监视器 | `ALIEN_MODE=real ./scripts/deploy_alien_monitor.sh --live` | `./scripts/deploy_alien_monitor.sh`（universe） |

宇宙地图上的 LIVE 徽章不是真金白银。按钮在地图之间**跳转**，不会给同一个进程重新上色。

## LIVE

你部署的是真实经济。

- **Hub** 在 `https://modelmarket.dev` 应答。本地能力为零；目录来自实况卫星的联邦。
- **监视器**是第二个容器（`alien-monitor-live`）。卡片 CTA 和统计轮询指向该 Hub。LIVE
  按钮留在原地。UNI 按钮转到 `/monitor/`。
- **球体：** 实况卫星与外来者。六个 UNI 实验室**不是**目录对等方。
- **加密**是另一把开关。加密**关闭**的 LIVE 仍与实况 Hub 通信；不会点亮链上节点。见
  [crypto-switch.zh.md](./crypto-switch.zh.md)。

## UNI

你部署的是密封的平行经济。从内部看 API 与 LIVE 相同。名字就是封印：独立子域，绝不是实况主机下的路径。

- **Hub** 在 `https://uni.modelmarket.dev` 应答（nginx 后的 loopback `:9183`）。
- **监视器**是默认的宇宙进程。CTA 与统计轮询走 `ALIEN_UNI_HUB_URL` /
  `https://uni.modelmarket.dev` — **不是**实况 Hub。UNI 按钮留在原地。LIVE 按钮转到
  `/monitor-live/`。
- **目录对等方**是六个仅气泡实验室：一个进程（`uni/satellite.py`）× 六份目录，由
  `deploy/uni-satellites.sh` 拉起。路径挂在 UNI Hub 自己的名字下，以便爬虫的 SSRF 守卫放行。
  `/var/lib/uni-satellites` 中的密钥必须保留：Hub 在首次接触时钉死对等方公钥。

| 卫星 | 产品 | caps | 出售 |
|---|---|---|---|
| KHRONOS Time Series | `khronos` | 20 | 统计、平滑、分解、预测 |
| STOICHEION Data Hygiene | `stoicheion` | 17 | 模式、差分、画像、文本、单位 |
| HORIZON Geo & Telemetry | `horizon` | 17 | 大地测量、空间查询、传感器变换 |
| PSEPHOS Draws & Ballots | `psephos` | 13 | 带承诺的抽签、离散概率、选票 |
| KYMA Signal Lab | `kyma` | 12 | 频谱、滤波、波形 |
| DIKTYON Graph Metrics | `diktyon` | 12 | 中心性、连通性、排序 |

每项能力都是输入的纯函数，用标准库计算。只有资金是模拟的。细节：[uni/README.md](../uni/README.md)。

**观察甲板。** Platon、ATLAS 及其他实况卫星仍可能出现在 UNI 地图上，作为**实况**服务的状态叠加。
它们不是 UNI 目录对等方。目录对等方是这六个实验室。

## 不要混用

| 泄漏 | 后果 |
|---|---|
| UNI 监视器轮询实况 Hub | 两张地图显示同一批 invoke / 美元 |
| UNI 卡片 CTA 指向 `modelmarket.dev` | 气泡内的运营者拿到一扇出门 |
| UNI Hub 使用 LIVE seed 列表 | 气泡公布真实卫星地址，并可路由真钱 |
| 在 UNI 进程上涂成 `mode=real` | 屏幕上的数字仍是气泡的 |

Hub 封印（`aimarket_hub/realm.py`）拒绝 UNI 内的实况 seed 和 LIVE 内的私有 seed。监视器
（`session_tick_mode`）拒绝在本进程上跳动另一领域的数字。

## 相关

- [uni-realm.md](./uni-realm.md) — 链封印、Anvil、气泡为何跑生产模式
- [crypto-switch.zh.md](./crypto-switch.zh.md) — 链上经济开关（不是 UNI）
- [alien-monitor-factory-catalog.zh.md](./alien-monitor-factory-catalog.zh.md) — 两张地图上的 Factory 星团
- [quickstart-ecosystem-deploy.zh.md](./quickstart-ecosystem-deploy.zh.md) — 实况舰队
