# Competing Hub VPS — 联邦实验星系
#
# 语言: [EN](hub-vps-competing.md) · [RU](hub-vps-competing-ru.md) · [ES](hub-vps-competing-es.md) · [FR](hub-vps-competing-fr.md) · [ZH](hub-vps-competing-zh.md)
#
# 主机: `hunt.modelmarket.dev` · DNS: `hunt.modelmarket.dev` / `hub.modelmarket.dev` / `use.modelmarket.dev`

这是**第二套 Hub** 的运维手册：主联邦（`https://modelmarket.dev`）可发现它，
同机还有 Signal Hunt 与 use-cases 门户。这**不是** `./start.sh --everything`
（需要 ≥16 GB RAM；本机约 8 GB + swap）。

## 完成标准

| 表面 | URL | 作用 |
|------|-----|------|
| Competing Lab Hub | `http://hunt.modelmarket.dev:9083` | 主站的 UNI-only 对等 Hub |
| Signal Hunt | `https://hunt.modelmarket.dev` | 游戏 + 自有 Hub（nginx） |
| Use-cases | `use.modelmarket.dev` | 静态门户 |
| Alien Monitor | 主站 Monitor | 远离原点的第二**星系** |

这台机器上的 **mesh 接线**不会自动完成 —— 必须跑下面的脚本，让已知 Hub 互相看见。
叩门之后的产品准入是另一条路：沙箱会自动接受 `pass`（见
[`join-the-federation.zh.md`](../join-the-federation.zh.md)）。脚本仍会显式 `approve`，
以便实验室 peer 在没有免费沙箱 SKU 时也能受信。

## 脚本

| 脚本 | 用途 |
|------|------|
| [`scripts/register_hub_upstream.sh`](../../scripts/register_hub_upstream.sh) | 单个对等：announce → approve → crawl |
| [`scripts/register_federation_mesh.sh`](../../scripts/register_federation_mesh.sh) | 全 mesh：primary ↔ lab ↔ hunt |
| [`signal-hunt/scripts/register-upstream.sh`](https://github.com/alexar76/signal-hunt/blob/main/scripts/register-upstream.sh) | 同上 + 断言 Signal Hunt tools |
| [`scripts/announce-platon-oracles.sh`](../../scripts/announce-platon-oracles.sh) | 向本地 Hub 注册 Platon |
| [`scripts/verify_federation_urls.py`](../../scripts/verify_federation_urls.py) | URL / well-known 检查 |

令牌只放在进程环境变量中。

## 联邦

```bash
UPSTREAM_ADMIN_TOKEN='…' ./scripts/register_hub_upstream.sh \
  http://hunt.modelmarket.dev:9083 https://modelmarket.dev
UPSTREAM_ADMIN_TOKEN='…' ./signal-hunt/scripts/register-upstream.sh \
  https://hunt.modelmarket.dev https://modelmarket.dev

PRIMARY_ADMIN_TOKEN='…' LAB_ADMIN_TOKEN='…' HUNT_ADMIN_TOKEN='…' \
  ./scripts/register_federation_mesh.sh
```

步骤：`announce` → `peers/approve` → `crawl`。  
只有 lab **自己发布**的能力（如 `signal.*@v1`）才会增加新 tools，而不是复制同一批预言机。

## Alien Monitor

```bash
ALIEN_COMPETING_HUB_URL=http://hunt.modelmarket.dev:9083
ALIEN_SIGNAL_HUNT_URL=https://hunt.modelmarket.dev
ALIEN_USE_CASES_URL=https://use.modelmarket.dev
```

锚点：`COMPETING_GALAXY_ANCHOR ≈ (30, 12, −20)`。节点：`competing_hub`、`signal_hunt`、`use_cases`。

完整英文手册：[hub-vps-competing.md](hub-vps-competing.md)。
