# UNI — 运维手册

> 🌐 [English](uni-realm-runbook.md) · [Русский](uni-realm-runbook.ru.md) · [Español](uni-realm-runbook.es.md) · [Français](uni-realm-runbook.fr.md) · **中文**

运行、迁移和检查 UNI 气泡的速查表。为什么这样设计见 [uni-realm.md](uni-realm.md)；本页只说做什么、按什么顺序做。

## 两条链，绝不合为一条

| 链 | 由谁运行 | 容器看到的地址 | 链上内容 |
|---|---|---|---|
| **气泡链** | 容器 `anvil-uni`，卷 `anvil_uni_state` | `http://172.17.0.1:8546` | hub 的资金：代币 `0x5fbd…0aa3`、托管合约 `0xe7f1…0512`、hub 钱包（Anvil #1）和买家（Anvil #2） |
| **演示链** | Alien Monitor UNI 容器（`alien-monitor`）自带的 Anvil | `http://172.17.0.1:8545`（经 `uni-rpc-bridge`） | 地图世界：彩票、NFT、ACEX（PulseAMM、注册表、借贷） |

UNI hub **在气泡链上结算**（`AIMARKET_RPC_BASE=…:8546`），在演示链上读取彩票和 NFT（`ALIEN_EVM_RPC=…:8545`）。演示链是一次性的：状态超过 64 MB 时监视器会清空它，并把自己的合约重新部署到新地址。资金从不放在那里。

## 把 UNI 迁到另一台服务器 — 步骤清单

1. 复制 `anvil_uni_state` 卷（先停止 `anvil-uni`，保证磁盘上的状态完整）。
2. 在新服务器上启动 `anvil-uni` — 使用 [uni-realm.md](uni-realm.md#standing-it-up) 中的 `docker run`，只发布在 `172.17.0.1:8546`。
3. 防火墙：容器必须能访问 `172.17.0.1:8546`，互联网不能。
   `ufw allow proto tcp from 172.17.0.0/16 to 172.17.0.1 port 8546`
4. 确认经济在气泡链上：代币和托管合约有代码，Anvil #1 和 #2 有余额。为空 → 状态没有复制过来；对 **8546**（绝不是 8545）运行 `scripts/deploy_uni_realm.py`，并使用它打印的地址。
5. 从 monorepo 启动 hub：`bash deploy/uni-hub.sh <镜像> <代币> <托管合约>`。绝不使用服务器上的副本，也绝不把 `hub.env.snippet` 合并进 hub。
6. 把 hub 出售的东西也一起迁移——它们运行在服务器本机上，而不在容器里：六个卫星服务（复制 `/var/lib/uni-satellites`，然后运行 `bash deploy/uni-satellites.sh`）和 `uni.answer@v1` 的提供者（复制 `/var/lib/uni_provider_key`，然后运行 `bash deploy/uni-provider.sh`）。hub 固定了这两类密钥：换了新密钥，就是被拒绝的对等节点或被拒绝的签名。然后执行一次抓取（`POST /ai-market/v2/federation/crawl`，需管理员令牌），并停掉旧服务器上的旧副本。
7. 让监视器的买家使用气泡链：`ALIEN_UNIVERSE_BUYER_RPC=http://172.17.0.1:8546`、`ALIEN_UNIVERSE_BUYER_TOKEN=<代币>`。
8. **在服务器本机上**运行 `python3 deploy/uni-hub-verify.py`。每一行都必须是 `ok`。
9. 大约 15 分钟内，监视器日志会出现 `hub declares its settlement wallet` 并打开一个通道；红色的 “REALM ECONOMY STALLED” 横幅不应再出现。

## `deploy/uni-hub-verify.py`

每次启动或重建 hub 后都要运行。除发布规则外，它还直接对照链本身检查资金部分：

- hub 在自己的链上结算，而不是监视器的演示链；
- 存款和 x402 使用同一个代币，且该代币存在于结算链上；
- 各处使用同一个托管合约地址，且它存在于结算链上；
- 各处收款到同一个钱包（收款人 = x402 payTo = 托管合约中的 hub）；
- 慈善彩票存在于演示链上。

`--no-chain` 跳过链上检查（不在服务器上时），`--no-live` 跳过公网检查。

## 演示链变化时

监视器重置后，彩票、NFT 和 ACEX 的地址会变。新地址在 `data/alien-monitor/universe/hub.env.snippet` 中。**只**从中取以下内容：

- hub：`AIMARKET_CHARITY_LOTTERY_ADDRESS`、`LOTTERY_ADDRESS`、`HUB_LOTTERY_ADDRESS`、`AIMARKET_NFT_CONTRACT`；
- ARGUS-UNI：`argus/.env` 中的 `ARGUS_UNI_*` 各行，然后执行 `docker compose up -d argus-uni`。

绝不要把其中的 `AIMARKET_PAYMENT_RECIPIENT`、`AIFACTORY_PAYMENT_VERIFY_STUB` 或 RPC 行带进 hub：它们描述的是演示链和 Anvil #0，会破坏结算。hub 会忽略 `AIMARKET_ADDR_UNI_*`（它的网络名为 `base`）。

监视器的 Anvil 每 30 秒写一次状态（`ALIEN_ANVIL_STATE_INTERVAL_S`），因此重启不再丢失上次正常退出后部署的合约。

## 症状

| 地图上 / 日志中 | 原因 | 处理 |
|---|---|---|
| `settlement chain http://172.17.0.1:8546 is unreachable` | `anvil-uni` 未运行，或缺少防火墙规则 | 第 2–3 步 |
| `channel/open … moved no USDC to the configured recipient` | 买家付给了别的钱包，或 hub 的收款人不是 Anvil #1 | 校验脚本；买家会自行丢弃这笔存款 |
| 每一轮都是 `transaction not found or not yet mined` | 买家和 hub 在不同的链上 | 第 7 步，校验脚本 |
| 校验：“settlement token exists … FAIL” | hub 指向一条没有其代币的链 | 第 4 步 |
| 校验：“charity lottery exists … FAIL” | 演示链被重置 | “演示链变化时” |
| 买家日志中的 `listing_not_sellable` | 正常：该商品没有收款地址；通道付款到 hub 声明的钱包 | — |
| `Invoke error for uni.answer@v1: timed out` | 提供者没有在本服务器上运行；连接挂起的时间超过了买家的超时 | 第 6 步（`deploy/uni-provider.sh`） |
| 每一轮都是 `no match for …`；目录里只有几个工具，而不是约 93 个 | 卫星服务没有在本服务器上运行（nginx 对 `/sat/*` 返回 502） | 第 6 步（`deploy/uni-satellites.sh`），然后抓取一次 |
