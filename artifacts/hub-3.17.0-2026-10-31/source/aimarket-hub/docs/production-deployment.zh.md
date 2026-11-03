# 独立 AIMarket Hub 的生产部署

[English](production-deployment.md) · [Русский](production-deployment.ru.md) · [Español](production-deployment.es.md) · [Français](production-deployment.fr.md) · [中文](production-deployment.zh.md)

> 本文术语遵循规范的[本地化词汇表](https://github.com/alexar76/aicom/blob/main/docs/localization-glossary.md)。产品名称、协议标识符、URL、CLI 命令和环境变量一律不翻译。

本运行手册面向独立运营者：部署一个无需人工绕过信任检查、能够通过联邦准入的公共枢纽 (Hub)。内容涵盖单台 Ubuntu 主机、nginx、TLS、可选 Alien Monitor、付费且已签名的 capability，以及可选的 SKOPOS 节点智能体注册。

## 1. 目标架构与信任边界

```text
互联网
  └─ nginx :80/:443
       ├─ /hub/      → 127.0.0.1:9083 上的 AIMarket Hub
       ├─ /monitor/  → 127.0.0.1:9100 上的 Alien Monitor（可选）
       └─ provider   → 127.0.0.1:<port> 上的 capability 后端，不公开
```

每个服务使用独立的非特权 Unix 账户。只有 nginx 和 SSH 对公网监听。SQLite 数据库和 Ed25519 密钥必须放在 Git checkout 之外。枢纽 (Hub) 的公共 origin 是安全边界：discovery、已签名清单和公布的 `invoke` 必须使用同一 origin。

使用 `hub.example.com` 之类的独立主机名最简单。`https://example.com/hub` 这样的子路径也可以，但必须配置 §7 中的全部代理规则。遗漏一项通常会造成 API 正常而 UI assets、WebSocket 或联邦 URL 失效。

## 2. 前置条件

- Ubuntu 24.04 LTS 或受支持的其他 systemd Linux。
- 公共 IPv4/IPv6，DNS `A`/`AAAA` 记录已指向主机。
- 由您控制且未过期的域名；全球 DNS 解析生效前不要申请 TLS。
- 使用 Ed25519 密钥的 SSH 访问。第二个纯密钥会话成功前，不要关闭第一个会话。
- Hub + Monitor 至少需要 2 CPU、2 GB RAM 和 10 GB 可用磁盘。
- 允许访问 Git、ACME、联邦 crawl 和 SKOPOS 注册的出站 HTTPS。

```bash
sudo apt update
sudo apt install -y git nginx python3 python3-venv python3-pip \
  certbot python3-certbot-nginx sqlite3 ufw fail2ban unattended-upgrades
```

## 3. 固定源代码版本

不要直接部署会移动的分支。记录并审核 commit SHA，然后精确 checkout 该版本：

```bash
sudo install -d -m 0755 /opt/aimarket/releases
sudo git clone https://github.com/alexar76/aimarket-hub.git \
  /opt/aimarket/releases/aimarket-hub-<sha>
sudo git -C /opt/aimarket/releases/aimarket-hub-<sha> checkout --detach <sha>
git -C /opt/aimarket/releases/aimarket-hub-<sha> rev-parse HEAD
python3 -m venv /opt/aimarket/venvs/hub
/opt/aimarket/venvs/hub/bin/pip install --upgrade pip
/opt/aimarket/venvs/hub/bin/pip install "/opt/aimarket/releases/aimarket-hub-<sha>[pqc]"
```

`[pqc]` 扩展会安装 ML-DSA-65 签名器和验证器。缺少它时，枢纽 (Hub) 对任何混合签名都以失败关闭方式处理，因而无法与采用混合签名的枢纽联邦——而所有 AIMarket 枢纽都采用混合签名。

使用 `alexar76/alien-monitor` 与 `alexar76/skopos` 时重复上述步骤。把所有 SHA 写入部署记录。如需生产 hardening patch，应在 checkout 外保存补丁和原始源码；`git status --short` 只能显示有意改动。上线前在 CI 或构建主机上对该精确版本运行仓库测试。

## 4. 用户、目录与权限

```bash
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin aimarket-hub
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin aimarket-provider
sudo useradd --system --home /nonexistent --shell /usr/sbin/nologin alien-monitor
sudo install -d -o aimarket-hub -g aimarket-hub -m 0750 /var/lib/aimarket/hub
sudo install -d -o aimarket-provider -g aimarket-provider -m 0750 /var/lib/aimarket/provider
sudo install -d -o root -g root -m 0700 /etc/aimarket
sudo install -d -o root -g root -m 0700 /var/backups/aimarket
```

- 枢纽 (Hub) 签名密钥（`hub_signing_key`，启用后量子签名时还有其旁边的 `hub_signing_key_mldsa`）：`0600`，所有者 `aimarket-hub`。
- 提供方签名密钥：`0600`，所有者 `aimarket-provider`。
- 环境文件：`0600`，所有者 root。
- SQLite 目录：仅所属服务可写。
- 含密钥的备份：放在 `0700` 目录内，权限 `0600`。

绝不能把私钥、admin token、enrollment ticket 或数据库密码放进 Git、进程参数、shell 历史或公开支持日志。

## 5. 枢纽 (Hub) 配置

创建 `/etc/aimarket/hub.env`：

```dotenv
AIMARKET_HUB_NAME=Example Independent Hub
AIMARKET_HUB_URL=https://example.com/hub
AIMARKET_BIND_HOST=127.0.0.1
AIMARKET_DB_PATH=/var/lib/aimarket/hub/hub.db
AIMARKET_SIGNING_KEY_PATH=/var/lib/aimarket/hub/hub_signing_key
# 混合签名（Ed25519 + ML-DSA-65）；需要 [pqc] 扩展（第 3 节）。ML-DSA 密钥写在经典密钥旁边，
# 文件名为 <AIMARKET_SIGNING_KEY_PATH>_mldsa；对等方第一次看到它时就会将其固定。
AIMARKET_PQC=1
AIFACTORY_PROD=1
# 只信任本机 nginx 转发的客户端地址；绝不能使用 *。
AIMARKET_TRUSTED_PROXIES=127.0.0.1,::1
# 同一个解析后的地址也决定 ecosystem.json（与数据库同目录）中所列服务器的 SELF 归类：
# 见 docs/traffic-classes.zh.md。
# 同一源上由其他服务提供的付费路由（/x402/ 下的 x402 边车）会并入 /openapi.json，
# x402 索引器（x402scan、AgentCash）在那里查找它们。仅限与 AIMARKET_HUB_URL 同源；
# 不会覆盖 hub 自身的路由。每 10 分钟刷新一次。
# AIMARKET_OPENAPI_MERGE_URLS=https://hub.example.com/x402/openapi.json
# 独立运营者不应依赖另一运营者的 oracle。
AIMARKET_ORACLE_FAMILY_URL=off
AIMARKET_AUTO_CRAWL=1
AIMARKET_CRAWL_INTERVAL_S=3600
AIMARKET_CRAWL_REFRESH_MAX=64
AIMARKET_SEED_LIST=https://modelmarket.dev/.well-known/ai-market.json
AIMARKET_SEED_PUBKEYS=https://modelmarket.dev/.well-known/ai-market.json=<seed-ed25519-public-key>
AIMARKET_FEDERATION_ASSAY=1
AIMARKET_FEDERATION_ASSAY_SANDBOX=1
AIMARKET_FEDERATION_AUTO_ADMIT=1
AIMARKET_CREDITS_ENABLED=1
AIMARKET_CREDITS_OPEN_SIGNUP=1
AIMARKET_CREDITS_FREE_GRANT_USD=0

# 用 USDC 出售额度（docs/credits-topup.zh.md，见下文 5.1 节）。默认关闭。
AIMARKET_TOPUP_ENABLED=1
# 只接收充值、不接收任何其他款项的钱包（只需地址，枢纽永远不需要其私钥）。这样枢纽会自己监视它
# 并为每笔到账入账；不设置时，充值进入 AIMARKET_X402_PAY_TO，每笔都需要有人出示。
AIMARKET_TOPUP_PAY_TO=<专用充值钱包>
AIMARKET_TOPUP_MIN_CONFIRMATIONS=2
# 读取付款的节点（逗号分隔）；不设置时使用 Base 公共节点。
# AIMARKET_SETTLE_RPC_URL=https://mainnet.base.org,https://base-rpc.publicnode.com
# 到账监视器——只要设置了 AIMARKET_TOPUP_PAY_TO 就开启；以下为默认值。
# AIMARKET_DEPOSIT_WATCH=1
# AIMARKET_DEPOSIT_WATCH_INTERVAL_S=60
# AIMARKET_DEPOSIT_WATCH_CHUNK_BLOCKS=500
# AIMARKET_DEPOSIT_WATCH_LOOKBACK_BLOCKS=1800
AIMARKET_ADMIN_TOKEN=<secret>
AIMARKET_PUBLISHER_TOKENS=<publisher-id>:<secret>
AIMARKET_ECOSYSTEM_LABELS=publisher-id=Display Name
AIMARKET_CORS_ORIGINS=https://example.com
```

重要规则：

1. `AIMARKET_HUB_URL` 是外部可访问 URL；使用子路径时必须包含 `/hub`。生产环境绝不能写 `localhost`。
2. 枢纽 (Hub) 第一次启动时创建 Ed25519 密钥。应立即备份。替换密钥会改变联邦身份，在固定该密钥的对等方看来类似密钥劫持。启用 `AIMARKET_PQC=1` 时，它还会创建 ML-DSA-65 密钥 `<密钥路径>_mldsa`：两者都要备份，并放在同一个卷上。
3. seed key 虽是公钥，但固定它属于信任决策。应通过已验证 TLS，从已签名 well-known 获取并记录比对结果。
4. 未设置 admin token 时，运营者路由必须 fail-closed（默认拒绝）。
5. 使用 SQLite 时，应停止枢纽 (Hub) 或调用 SQLite backup API。多进程或高写入场景应优先使用 PostgreSQL。
6. 为每个提供方分配独立的 subject-scoped publisher token，绝不能把枢纽 (Hub) 的 admin token 复用为提供方 credential。多个模块属于同一 Hub 时，设置 `AIMARKET_ECOSYSTEM_LABELS=publisher-id=Display Name,...`；已签名的 `ecosystem.nodes` 扩展会表达归属关系，而不会把这些模块伪装成独立的联邦对等方。
7. 每个周期都应在明确上限内刷新已信任的 active peers，即使当前 seed graph 已不再链接它们。按 roster 规模设置 `AIMARKET_CRAWL_REFRESH_MAX`；否则，一个包含 30 个 capability 的有效 peer 可能无限期保留旧的一项 capability 清单。

### 5.1 用 USDC 出售额度：专用钱包

设置 `AIMARKET_TOPUP_ENABLED=1` 后，任何代理都可以自己在 Base 上用 USDC 购买额度
（[credits-topup.zh.md](credits-topup.zh.md)）。给这个入口一个专用钱包，就没有人需要盯着链上或手动入账：

1. **创建一个只接收充值、不接收其他款项的钱包。** 枢纽只需要它的地址，永远不需要私钥：枢纽不会从中
   支出任何款项。私钥存放在运营者存放金库私钥的地方。
2. **设置上面的变量**（`AIMARKET_CREDITS_ENABLED=1`、`AIMARKET_TOPUP_ENABLED=1`、
   `AIMARKET_TOPUP_PAY_TO=<地址>`）。在 systemd 下写入 env 文件或 drop-in
   （`Environment=AIMARKET_TOPUP_PAY_TO=0x…`）；在 Docker Compose 下，容器只能看到 compose 文件转发的
   变量，因此要在枢纽的 `environment:` 中加入 `AIMARKET_TOPUP_PAY_TO: ${TOPUP_PAY_TO:-}`，并在 `.env`
   中加入 `TOPUP_PAY_TO=0x…`。
3. **备份数据库并重启枢纽。** 迁移 `050_deposit_watch` 会新增 `payer_wallets`、`deposit_watch_cursor`
   和 `hub_deposits`。
4. **检查**：`pay_to` 是新钱包，`deposit_watch.enabled` 为 `true`（关闭时，`reason` 会说明缺少什么）。
   为每家将用普通转账付款的公司关联一次钱包。查看来自未知方的到账：

```bash
curl -s "$AIMARKET_HUB_URL/.well-known/ai-market.json" | jq '.payment_rails.credits.topup | {pay_to, deposit_watch}'
curl -s "$AIMARKET_HUB_URL/ai-market/v2/accounts/$ACCOUNT_ID/payer-wallets" -H "Authorization: Bearer $AIMARKET_ADMIN_TOKEN" \
     -H 'Content-Type: application/json' -d '{"address": "0x…"}'
curl -s "$AIMARKET_HUB_URL/ai-market/v2/admin/deposits" -H "Authorization: Bearer $AIMARKET_ADMIN_TOKEN"
```

5. **设置告警**：把枢纽加入生态告警器的 `AICOM_ALERT_DEPOSIT_HUBS`（只检查其 `AICOM_ALERT_SCOPE` 范围内的枢纽）（`deposit_watch_on:<hub>`——枢纽
   应当监视却没有监视；`deposits_unattributed:<hub>`——有款项来自无人关联的钱包）。

首次扫描在枢纽启动一个间隔之后开始，从链头之后 `AIMARKET_DEPOSIT_WATCH_LOOKBACK_BLOCKS`（1800，Base 上
约一小时）个区块处起读，因此开启前不久的转账仍会被找到；更早的转账按其 `tx_hash` 手动入账。新钱包会
有新的游标，旧钱包不再被读取。

切勿把 `AIMARKET_TOPUP_PAY_TO` 指向任何接收其他款项的钱包：每笔转入都会被当作充值。枢纽会拒绝自己的
x402 钱包和收款钱包（`AIMARKET_X402_PAY_TO`、`AIMARKET_PAYMENT_RECIPIENT`；见 well-known 中的 `reason`）；
但它无法知道其他钱包还会收到什么，也无法知道是否有另一个枢纽在用同一个钱包。

## 6. systemd 服务

创建 `/etc/systemd/system/aimarket-hub.service`：

```ini
[Unit]
Description=Independent AIMarket Hub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=aimarket-hub
Group=aimarket-hub
WorkingDirectory=/opt/aimarket/releases/aimarket-hub-<sha>
EnvironmentFile=/etc/aimarket/hub.env
ExecStart=/opt/aimarket/venvs/hub/bin/python -m aimarket_hub serve
Restart=on-failure
RestartSec=5s
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=yes
RestrictNamespaces=yes
LockPersonality=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
ReadWritePaths=/var/lib/aimarket/hub
UMask=0027
MemoryMax=1G
TasksMax=256

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now aimarket-hub
sudo systemctl status aimarket-hub --no-pager
```

若所选版本支持 bind-host，应把应用绑定到 loopback。即使应用监听 `0.0.0.0:9083`，UFW 仍必须阻止该端口，nginx 仍应是唯一公网入口。

## 7. nginx、子路径与 TLS

以下是子路径所需的核心配置；请按发行版调整证书与 rate limit：

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name example.com;
    location ^~ /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 301 https://$host$request_uri; }
}
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name example.com;
    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_tickets off;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options nosniff always;
    add_header Referrer-Policy strict-origin-when-cross-origin always;
    client_max_body_size 1m;

    location = /hub { return 301 /hub/; }
    location ^~ /hub/ {
        proxy_pass http://127.0.0.1:9083/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }
    location ~ ^/(ai-market|api|mcp|developers|examples|widget|plugins|operator|studio)(/|$) {
        proxy_pass http://127.0.0.1:9083;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto https;
    }
    location = /hub-ui-i18n.json { proxy_pass http://127.0.0.1:9083/hub-ui-i18n.json; }
    location = /cap-descriptions-i18n.json { proxy_pass http://127.0.0.1:9083/cap-descriptions-i18n.json; }
}
```

Alien Monitor frontend 应使用 `VITE_BASE_PATH=/monitor/` 构建；`/monitor/` 代理到 loopback HTTP 端口，`/monitor/ws` 单独设置 WebSocket `Upgrade`/`Connection` 头和较长 read timeout。为 `/` 构建的版本可能返回 HTTP 200，却在子路径下丢失 JavaScript 和 CSS。

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d example.com
sudo certbot renew --dry-run
systemctl is-enabled certbot.timer
```

在所有覆盖的子域 HTTPS 均正确前，不要启用 HSTS。

如果域名根路径承载独立门户，应把它作为另一个非特权 loopback 服务运行，并只作为 nginx 的最终 fallback。门户 API 前缀（例如 `/api/v1/`）必须排在 Hub 的宽泛 root-relative compatibility 规则之前；否则页面能够渲染，而 API 会静默转发到 Hub。显式保留 `/hub/`、`/monitor/` 与提供方路径；当门户是预期入口时，不要把 `/` 重定向到 `/hub/`。

## 8. 发布不可绕过支付门的真实 capability

首次创建本地 smoke capability 时，先停止枢纽 (Hub)，再以其服务账户运行内置的幂等 quickstart。它会创建无需模型或外部提供方的可执行 static pack；作为产品发布前，应换成您自己的 backend：

```bash
sudo systemctl stop aimarket-hub
sudo -u aimarket-hub env \
  AIMARKET_DB_PATH=/var/lib/aimarket/hub/hub.db \
  AIMARKET_HUB_URL=https://example.com/hub \
  AIMARKET_CREDITS_ENABLED=1 \
  /opt/aimarket/venvs/hub/bin/python -m aimarket_hub quickstart \
  --price 0.01 --grant 0
sudo systemctl start aimarket-hub
```

生成的 buyer key 是只显示一次的秘密。grant 为零时没有余额；请存入 password manager 或将其撤销。接入真实提供方时，请参阅[自行运营本枢纽 (Hub)](operator-quickstart.md)，只注册您控制的 backend，并妥善保存其签名密钥。

生产 capability 有两个表面：完成工作并签名结果的内部提供方后端，以及校验安全、支付、路由和收据的公共枢纽 (Hub) gateway。

已签名清单必须公布枢纽 (Hub) gateway，例如 `https://example.com/hub/ai-market/v2/invoke`，绝不能公布原始 `/provider/invoke` URL。把提供方路由限制在 loopback、双向认证连接或主机自身地址。若版本在清单中暴露提供方 URL，必须先升级或应用经审核的 backport。

对于仅付费 capability，未授权请求（包括携带 `X-AIMarket-Sandbox-Visitor` 的请求）必须返回 `402`，给出可用支付通道，并准确引用已签名目录中的价格。也可以提供真正免费的 capability：实际执行工作并返回已签名收据。只有宣传页面而无真实证据不合格。

最低一致性检查：

- `/hub/.well-known/ai-market.json` 通过随附 schema；
- `manifest_url` 公共可达且 same-origin；
- well-known 与清单签名可由公布的 Ed25519 密钥验证；
- `generated_at` 新鲜；
- 五字段 canonical 覆盖 capability 数、timestamp、protocol version、`tools_hash` 和 `by_hub_hash`；
- 每个数值 schema 字段都是数字而非 `null`；
- `invoke_url` same-origin 且进入枢纽 (Hub) gateway；
- `402` 价格等于 `price_per_call_usd`；
- 成功的提供方响应带有可验证签名。

## 9. 联邦准入

本地检查全部通过后，通过公共协议 announce：

```bash
curl -fsS -X POST https://modelmarket.dev/ai-market/v2/federation/announce \
  -H 'Content-Type: application/json' \
  --data '{
    "hub_url":"https://example.com/hub",
    "hub_name":"Example Independent Hub",
    "well_known_url":"https://example.com/hub/.well-known/ai-market.json"
  }'
curl -fsS 'https://modelmarket.dev/ai-market/v2/federation/assay?url=https%3A%2F%2Fexample.com%2Fhub'
```

```text
announce 或入站 crawl → pending/quarantine → sandbox assay → pass → trusted/indexed
```

不要通过 operator panel、admin endpoint 或手工修改 peer table 绕过信任。已知的 pending 对等方可能要等接收方下一次 crawl；每小时一次很正常。若为 `review` 或 `fail`，修复线上证据并等待文档规定的重试。保留指出具体失败检查的 dossier。

准入后，要按名称和 `capability_id` 检查 peer roster、联邦搜索结果与 Alien Monitor，不能只看 HTTP 200。

## 10. 主机安全

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw limit 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status verbose
```

启用 Fail2ban 的 `sshd`、`nginx-http-auth`、`nginx-botsearch` jails 和 unattended security upgrades。应定期检查 bans 与升级日志；仅安装不等于监控。

SSH hardening 顺序非常关键：

1. 安装运营者公钥。
2. 使用目标密钥和 `BatchMode=yes` 打开第二个会话。
3. 检查 `sshd -T`；cloud-init drop-in 可能覆盖看似更晚的文件。
4. 设置 `PasswordAuthentication no`、`KbdInteractiveAuthentication no`、`PermitRootLogin prohibit-password`，或完全禁用 root 并使用 sudo。
5. reload SSH，保留第一个会话，再测试第三个纯密钥登录。

独立测试成功前，绝不能关闭唯一可用会话。

## 11. 备份与恢复

至少备份：Hub SQLite 及独立 channel/provenance 数据库；枢纽 (Hub) 和提供方的私钥（Ed25519 密钥，以及在 `AIMARKET_PQC=1` 时与之配套的 ML-DSA 密钥 `<密钥路径>_mldsa`）；root 所有的环境文件及 systemd drop-ins；nginx 配置；已固定 SHA 与有意应用的补丁。

使用 `sqlite3 /path/hub.db '.backup /staging/hub.db'`，或停止服务再复制。创建仅 root 可读的压缩归档，保留多个版本，并把加密副本移出主机。未实际恢复过的备份未经验证。

恢复流程：停止枢纽 (Hub) 和提供方；以原 ownership/mode 恢复数据库与密钥；恢复配置并执行 `systemctl daemon-reload` 和 `nginx -t`；启动服务并确认两把签名公钥都未改变（`/.well-known/ai-market.json` 中的 `signature.public_key` 和 `signature.pq_public_key`）；重新检查 schema、签名、`402`、搜索及联邦。

## 12. Alien Monitor 与 SKOPOS

Alien Monitor 应以独立非特权服务运行在 LIVE 模式，指向本地 Hub URL，并分别代理 HTTP API 与 WebSocket。reboot 后确认 tick 继续增长。财务指标为空可能只是尚无流量；tick 停滞或 health endpoint 失败则是故障。

把每个独立 Hub 视为单独的星系。按稳定身份与规范化 URL 去重，规定 Hub 中心之间的最小距离，并把 `ecosystem.nodes` 围绕所属 Hub 分组。应先把每个 Hub 的 child budget 留给已签名的 `ecosystem.nodes`，再绘制联邦 peer 链接；大量 roster 不得隐藏 Hub 自己的提供方。AI 助手应先从当前 live snapshot 解析名称（包括本地化或音译查询），再退回静态帮助；这样即使没有外部 LLM key，新部署模块仍可被发现。

SKOPOS 使用受限的 push-only 节点智能体。注册必须使用官方一次性 ticket：

1. 在 SKOPOS control plane 为准确的服务器记录签发 ticket。
2. 在节点上以 root 运行生成的 installer。
3. 从隐藏 stdin 输入 ticket，绝不能放入 argv、URL、shell 历史或聊天。
4. 确认 ticket 已被消耗、credential file 仅 root/智能体可读且 timers 上报成功。

节点不能自行签发 ticket：它只能由 SKOPOS control plane 创建。如果没有 ticket，应让已准备的 installer 保持停止状态，并明确标记 enrollment 为 pending；不要猜测 ticket，也不要从其他节点复制。

不要手工在 SKOPOS 数据库创建 credential，也不要授予节点智能体 Docker 组或不受限 sudo。

## 13. 最终验收清单

```bash
systemctl is-active aimarket-hub nginx fail2ban ufw unattended-upgrades
systemctl --failed
curl -fsS https://example.com/hub/.well-known/ai-market.json
curl -fsS https://example.com/hub/ai-market/v2/manifest
curl -sS -o /tmp/invoke.json -w '%{http_code}\n' \
  -H 'Content-Type: application/json' \
  --data '{"product_id":"example","capability_id":"example.echo@v1","input":{}}' \
  https://example.com/hub/ai-market/v2/invoke
ufw status verbose
sshd -T | egrep '^(permitrootlogin|passwordauthentication|kbdinteractiveauthentication) '
```

最后 reboot 主机，并从外部网络重做检查。所有服务必须自动恢复；公网只开放 SSH/HTTP/HTTPS；TLS renewal dry-run 成功；签名仍可验证且密钥不变；无法绕过提供方支付门；Hub 仍可在联邦搜索；Alien Monitor 自动重连且 LIVE tick 增长；有最新备份及明确恢复步骤。

## 14. 升级与回滚

1. 新建不可变 release 目录和 virtualenv；不要在活动 release 中执行 `git pull`。
2. 阅读迁移说明，特别是 SQLite channel/provenance 路径变更。
3. 备份数据库与签名密钥。
4. 对候选版本运行测试及本地 federation assay。
5. 只切换 systemd 的 `WorkingDirectory`/`ExecStart` 目标，重启并执行验收。
6. 必要时回滚代码，但没有匹配备份时，不要跨不兼容数据库迁移回滚。

签名身份（Ed25519 密钥，以及启用后量子签名时配套的 `_mldsa` 密钥）和支付 ledger 是持久状态，不是 release artifact。丢失或静默替换任何一项都不是常规重新部署。

## 15. 把 hub 迁移到另一台主机

容器及其数据卷是容易的部分。让迁移出问题的是在主机上与 hub **并列**运行的东西：它们都不在镜像里，绿色的 `/health` 对此一无所知，而旧主机还会继续为一个已经不在那里的 hub 运行它的副本。2026-10-01，modelmarket.dev 的 hub 迁移了主机，而托管合约签名者的隧道和结算清扫留在了旧主机上：两天里没有一笔托管扣款上链，也没有任何告警，因为旧的清扫一直在发布"ok，无需提交"。

**随容器一起迁移**

| 内容 | 位置 | 在新主机上 |
|---|---|---|
| hub 数据（`hub.db`、通道账本、托管授权存储、deposit claims） | 数据卷 | 从 hub 停止时做的最新备份复制（§11） |
| 签名身份 | 数据卷 / 密钥路径：`hub_signing_key` 与 `hub_signing_key_mldsa` | 两把密钥都保持原样，绝不换新（§14）：固定过后量子密钥的对等方会拒绝新密钥，直到各自重新固定 |
| 托管签名者隧道 | `escrow-signer-tunnel.service`（到签名者主机的 SSH `-L`） | 在新主机上生成新的 SSH 密钥；在签名者主机上以 `restrict,port-forwarding,permitopen="127.0.0.1:9500",command="/bin/false"` 添加它；通过与旧主机 `known_hosts` 比对指纹来固定签名者的主机密钥；监听 `127.0.0.1:9500` **以及** hub 容器所在 Docker 网络的网关；防火墙：只允许该网络子网访问网关的 9500 端口 |
| 结算清扫 | `aicom-settlement-sweep.{service,timer}` + `/usr/local/lib/aicom-settlement/escrow_settlement_sweep.py` | 安装，把 `--publish` 指向新主机提供 `verify.<域名>` 的目录，运行一次 |
| 支付金丝雀 | `aicom-payment-canary.{service,timer}`（`scripts/payment_canary.py`） | 安装，发布到同一个 `verify.<域名>` 目录；`status.json` 过期时告警器会报警 |
| 审计者（THEMIS） | 加入 hub 的网络命名空间 | 在 hub 之后用 `--network container:<hub>` 重建（否则会成为孤儿） |
| 验证后付款的验证者密钥 | `/root/.metis-verify-key`（0600）→ `AIMARKET_VERIFY_METIS_*` | 服务器之间直接复制，绝不经过终端 |
| 自有提供者 | systemd 单元（`weather-witness`、`pov-demo`） | 安装，然后重新检查它们的 nginx location |
| nginx location、TLS、续期钩子 | `/etc/nginx`、`/etc/letsencrypt` | 重新检查每个代理到主机端口的 `location` |

**前三行由一个脚本完成并检查：** 在新主机上运行 `scripts/hub_host_companions.sh --install`（hub 通过外部签名者签名时设置 `AICOM_SIGNER_SSH_HOST`），用 `--verify` 检查（单元未运行、hub 容器无法访问签名者或两份报告不新鲜时都会失败），在旧主机上运行 `--disable`。`scripts/deploy_hub_rebuild.sh` 在每次部署结束时运行 `--verify`，缺少任何一项时以退出码 3 结束。

**然后关掉旧主机上的服务**——列表中的每个单元都要显式关闭（`systemctl disable --now`）。留在那里的清扫会读取一个已经没人写入的存储，并永远报告成功。

**在宣布迁移完成之前，证明资金路径可用**

```bash
# hub 容器通过隧道访问签名者（打印签名者地址）
docker exec <hub> python -c "import httpx;print(httpx.get('http://<网关>:9500/health').text[:120])"
# 清扫在这里运行过：checked_at 是几分钟前，errors 为空
curl -s https://verify.<域名>/settlement.json | jq '{checked_at, ok, errors}'
# 旧主机上已没有任何服务在运行
ssh <旧主机> 'systemctl is-active escrow-signer-tunnel aicom-settlement-sweep.timer'   # inactive, inactive
# 验证后付款仍然接通：enabled、你的验证者、已声明 escrow_hub
curl -s https://<域名>/.well-known/ai-market.json | jq '.pay_on_verified.enabled, .contracts.entries'
```

UNI 气泡有它自己的清单（私有链、防火墙、买方设置）：
[docs/uni-realm-runbook.zh.md](https://github.com/alexar76/aicom/blob/main/docs/uni-realm-runbook.zh.md)。
