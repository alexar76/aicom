# 支付测试与交易

**EN** [English](payment-tests-and-transactions.md) · **RU** [Русский](payment-tests-and-transactions.ru.md) · **ES** [Español](payment-tests-and-transactions.es.md) · **FR** [Français](payment-tests-and-transactions.fr.md) · **ZH** [中文](payment-tests-and-transactions.zh.md)

记录日期：**2026-10-23**。本指南说明结账付款、交易认领、内部 UNI 账本、故障恢复测试，以及这些结果能够证明的范围。

## 1. 证据与范围

下表保留初次验证结果；最新结果紧接其后。

| 检查 | 已记录结果 | 真实执行与模拟的边界 |
| --- | --- | --- |
| 支付恢复测试集 | **50 passed，无跳过**：25 个 SQLite 用例 + 25 个 PostgreSQL 用例 | 存储、签名、并发及子进程退出均真实执行；交易为合成数据，区块链/供应商响应为模拟 |
| Factory 主测试集 | **5 828 passed**，60 个跳过 | 主测试选择；其中的支付测试不能再次加到总数中 |
| PostgreSQL 补充运行 | PostgreSQL **18.3** 临时集群，结束后已停止 | 独立本地数据库，没有使用生产数据库 |

证据：[支付 JUnit 报告](../artifacts/quality-audit-2026-10-23/payments-sqlite-postgres.xml)、
[验证清单](../artifacts/quality-audit-2026-10-23/verification.json)、
[完整质量报告](quality-audit-2026-10-23.md)。
本地测试通过**不代表完成了新的真实资金转账**。另一次有日期的
[部署记录](../artifacts/payment-production-deploy-2026-10-23/deployment-summary.json)
同样注明：没有用真实资金完成成功的端到端付款或链上退款。
历史真实链上交易见[链上日志](onchain-journal.md)和[付费调用案例](case-study-paid-invoke.md)；
它们是带日期的证据，不是当前可用性检查。

PostgreSQL 参数化针对 UNI 账本。Factory commerce 和 KOVA/SaaS 存储仍使用各自的 SQLite 数据库；这不代表验证了 PostgreSQL 结账订单后端。

### 后续审计：故障处理与关键场景

最新验证：本地完整套件 **6 139 passed、84 个子测试、24 个有意关闭的 live 探针**；其中 **450 个支付/UNI 检查无财务测试跳过**。另一次生产运行 **32 个测试通过：24 个 live 检查和 8 个契约测试，零跳过**。**13 个关键财务函数**的行/分支覆盖均达到强制的 100%。总覆盖：**60.8% 行 / 50.0% 分支**。依赖审计仍未报告漏洞。

最终边界测试在两种存储夹具上增加七个场景：空哈希或错误网络哈希、等待真实异步锁时报价已被消费、旧报价缺少金额、固定交易重试、持久化报价含不支持的网络，以及订单插入冲突。真实提交的竞争订单返回 **409**，不会新增许可证或泄露其密钥。参见[付款确认边界](../tests/test_payment_confirmation_boundaries.py)及[最新证据](quality-audit-2026-10-23.md#braces-resolution)。完成函数没有静态分支；异常清理已测试。这些百分比仅针对指定关键函数，并不涵盖所有支付集成或生产故障模式。

新增 HTTP 测试覆盖订单提交前/后故障、待处理存储写入失败、报价密钥丢失/截断，以及 RPC 和历史记录不可用。
**503** 保留使用同一交易恢复的路径；提交结果未知时，交易认领仍被保留。
只有 `confirmed` 标记而没有已提交订单，不能认定成功。应从备份恢复原报价密钥，不应生成替代密钥。
旧历史为空、类型错误或 UNI 历史不可读取时，结算被拒绝。损坏的待付款文件会保留至恢复；RPC 凭据不会写入公开错误或 checkout 日志。
Solana 余额必须有限且非负，并验证 SPL 原始数量与小数位数。
真实 Ed25519 测试拒绝格式错误的签名、小阶公钥，以及属于其他客户、站点或交易的证明。
退款测试拒绝未知、不符合条件、已广播或金额无效的提现，并确认不会增加余额。

参见[后续验证结果及限制](quality-audit-2026-10-23.md#follow-up)。

### 生产验证与原来的 34 个跳过项

本轮已执行**原来全部 34 个跳过场景**。五个文件系统场景使用临时区分大小写卷；三个 Compose 场景使用合成变量解析真实配置，不读取部署密钥文件；两个 CSS 检查覆盖当前导入与本地字体样式表；KOVA 徽章改为记录**实际通过的 59 个测试**。配置解析错误现在导致失败，不再变成跳过。

原有 23 个 live 场景在生产环境执行，并新增一个未付款 invoke 检查。SKOPOS 公共 health 不得泄露内部指标；使用操作员密钥读取 fleet status，未付款请求必须返回 **402**。SSH 运行器仅在内存中保留密钥，隧道绑定 loopback 并在完成后关闭。不创建付款通道、不转账、不发放许可证、不调用 LLM。本地完整套件仍默认关闭 24 个 live 探针；相同场景已在单独生产运行中通过。测试选择存在重叠，不应直接相加。

新增 **88 个结算场景**，覆盖 SQLite 和 PostgreSQL：签名失败、真实数据库触发器失败、收据插入后的八次子进程硬退出、并发重试、用尽的预留及旧历史缺失。余额、账本、提现/预留和签名收据现共同提交；任一失败全部回滚。重试返回已存储收据；完整幂等键即使前 128 个字符相同也保持独立。收据 JSON 类型错误或钱包金额未知时拒绝操作。旧收据或预留记录缺失时拒绝操作，等待核对。新增七个 100% 目标为 `UniWalletService` 的 `charge`、`withdraw_to_chain`、`hold`、`spend_hold`、`release_hold`、`_credit`，以及 `issue_receipt`。

**UNI 修复仅在本地，本次审计未部署。** 生产探针验证当前运行版本，并不证明新修复已经上线。参见[逐项跳过证据](quality-audit-2026-10-23.md#skip-resolution)。

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-live-contracts \
  "$PYTHON" scripts/run_ecosystem_live_tests.py --ssh-host factory-vps \
  --skopos-ssh-host skopos-vps
```

## 2. 一笔结账交易的完整过程

1. 已登录客户调用 `POST /api/payment/create`。服务器从目录读取价格，忽略客户端给出的金额，
   生成**有效期一小时的报价**，绑定客户、产品、站点、链、代币和收款人。Factory 结账接受 **USDT/USDC**，
   不把 ETH/SOL 数量直接当成 USD 金额。
2. 客户在报价指定的网络上发送指定代币。`payment_id` 是内部报价 ID，`tx_hash` 是区块链交易 ID。
   只有哈希或成功的 HTTP 响应，都不能证明已付款。
3. `GET /api/payment/proof/{payment_id}?tx_hash=...` 返回待签名消息。
   `POST /api/payment/confirm/{payment_id}` 接收 `tx_hash` 和 `payer_signature`。
   签名把转账绑定到该客户的订单和站点。EVM 支持 EIP-191，以及合约钱包的 EIP-1271 验证。
4. 验证交易回执、网络、代币、收款人、转账金额与确认数。Factory 的金额容差为 **0.1%**；
   `AIFACTORY_PAYMENT_MIN_CONFIRMATIONS` 默认 **2**，最低 1。通过 `GET /api/payment/chains`
   查看实际配置；其他服务使用各自的规则。
5. 持久化交易认领登记防止同一转账在 checkout、pilot、通道注资、付费 invoke 和 UNI 充值之间重复消费。
   改变 EVM 哈希大小写或去掉 `0x` 无法绕过保护；Solana 签名保留大小写。
   成功结账创建**一个订单和一个许可证**。

| 结果 / 状态 | 含义与后续操作 |
| --- | --- |
| `pending` | 报价已存在，结算尚未完成 |
| `pending_confirmation` | 同一笔交易正在等待确认；使用同一哈希重试 |
| `confirmed` | 订单/许可证已创建或恢复；保存确认响应和 `order_id` |
| `claim_review` 元数据 | 缺少有效付款人证明，或付款时间过晚/无法证明；保留记录供操作员审核 |
| 重启后遗留的 `confirming` | 恢复为可重试状态，避免永久阻塞已经付款的客户 |

已完成报价会从待处理存储中移除，因此随后查询状态可能返回 **404**。这不证明付款丢失，应查询客户订单。
重试会找回已经提交到数据库的订单。目录价格变化或登录密钥轮换不会改写封存报价。
报价过期后，仍可按原价格恢复有效期内完成的转账；过晚付款或时间未知需要审核。
将 `checkout_quote.key` 与报价一同备份；不要把密钥内容写入日志或文档。

## 3. 购买、余额和退款分别处理

- Checkout 购买许可证，**不会额外增加可消费 UNI 余额**。钱包注资使用独立入口
  `/api/uni/topup/confirm`，同样受交易只能使用一次的保护。
- Hub 银行卡充值验证 Stripe webhook 签名并获取已保存的 checkout 会话；事件内容不能选择客户或入账金额。
  重复或并发通知只能入账一次；未付款会话不入账，测试模式资金不能计入 live hub。
  测试还覆盖 webhook 丢失后的恢复、手续费/税费、退款、争议及付款完成前到达的撤销事件。
- UNI 账本中的 `balance_uni` 是**未预留**余额，`hold_uni` 是已预留金额。
  从 1 000 中预留 600 后，可用余额为 400，不会再次扣除预留款而变成零。
  `hold_charge` 消费预留款，普通 `charge` 消费可用余额。账本快照必须与钱包状态一致。
- 失败提现使用持久化 `refund_due`；余额、退款账本记录和最终状态在同一事务中提交。
  重试、重启或并发 worker 都只能退款一次。提现成功前，手续费不确认为收入；历史手续费在退款时冲回。
- 已广播或结果未知的链上交易**不能自动退款**：必须先核对，否则链上付款和内部退款可能同时发生。
  当前部署记录指出，真实 UNI 链上提现适配器尚未实现；进入队列不等于已经广播交易。
- KOVA 拒绝早于发票创建时间的转账。SaaS 将发票/付款绑定到一个 API 密钥。
  eSIM 在调用供应商之前持久化采购意图；结果不明确的超时进入 `procurement_pending`，
  再次采购前必须按供应商交易 ID 核对结果。

## 4. 回归测试矩阵

| 不变量 | 主要测试来源 |
| --- | --- |
| 服务器价格、收款人、稳定币、回执、金额和确认数 | [价格控制](../tests/test_payment_price_control.py)、[安全](../tests/test_payment_security.py)、[审计回归](../tests/test_payment_audit_regressions.py) |
| 跨入口交易只使用一次；付款人/站点绑定；操作员审核 | [单次使用测试](../tests/test_payment_transfer_single_use.py) |
| 等待确认、重试及客户订单可见性 | [待确认 API](../tests/test_payment_confirm_pending_api.py) |
| KOVA → SaaS；封存报价；许可证提交前/后真正执行 `os._exit(9)`；UNI 预留、退款和手续费 | [SQLite/PostgreSQL 恢复](../tests/test_payment_chain_recovery.py) |
| eSIM 供应商结果不明确、重启和防止重复采购 | [商店恢复](https://github.com/alexar76/esim-operator-kit/blob/main/store/test/procurement-recovery.test.js)、[rails 结算](https://github.com/alexar76/esim-operator-kit/blob/main/rails/test/settlement.test.js) |
| Hub 银行卡商户凭据隔离、webhook 签名、单次入账及撤销 | [密钥范围集成](../tests/test_hub_card_secret_scope.py)、[Hub 银行卡测试](https://github.com/alexar76/aimarket-hub/blob/main/tests/test_card_topup.py) |
| HTTP/存储/RPC 故障恢复、损坏历史及报价字段 | [故障集成测试](../tests/test_payment_failure_recovery.py) |
| 真实 Ed25519、无效编码、合约检查失败；退款资格与回滚 | [密码学证明](../tests/test_payment_claim_crypto.py)、[退款保护](../tests/test_payment_refund_guards.py) |
| 报价密钥备份、损坏及并发 worker 原子发布 | [持久密钥测试](../tests/test_payment_quote_key.py) |

## 5. 本地运行

从仓库根目录执行，测试环境需安装 Python 3.12、根目录 requirements，以及本地 `aimarket-hub` 源码。
已验证的默认环境为 `.venv-quality`；可用 `AIFACTORY_TEST_PYTHON` 指定其他已准备好的环境。
准备步骤见[质量报告](quality-audit-2026-10-23.md#reproduction)。
测试夹具隔离存储并模拟外部付款；不要把测试 stub 开关复制到生产环境。

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-payment-tests \
  "$PYTHON" -m pytest -q -ra --timeout=60 \
  tests/test_payment_chain_recovery.py \
  tests/test_payment_failure_recovery.py \
  tests/test_payment_confirmation_boundaries.py \
  tests/test_uni_settlement_atomicity.py tests/test_uni_settlement_boundaries.py \
  tests/test_payment_claim_crypto.py \
  tests/test_payment_quote_key.py \
  tests/test_payment_refund_guards.py \
  tests/test_payment_security.py \
  tests/test_payment_price_control.py \
  tests/test_payment_transfer_single_use.py \
  tests/test_payment_confirm_pending_api.py \
  tests/test_payment_audit_regressions.py
```

未设置 `PAYMENT_FIX_TEST_PG_URL` 时，PostgreSQL 用例会被**跳过**，不算通过。
原有 50 个用例与新增故障场景需要一次性的本地 PostgreSQL 集群。测试夹具会创建和删除 schema：
**绝不能连接生产数据库**。以下代码要求 PostgreSQL 工具位于 `PATH`，本地端口 55487 空闲；
子 shell 会在测试失败时也停止集群。

```bash
(
  set -eu
  PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
  payment_pg_dir=$(mktemp -d /tmp/aicom-payment-pg.XXXXXX)
  initdb -D "$payment_pg_dir/db" -U aicom_test \
    --auth-local=trust --auth-host=trust --no-locale --encoding=UTF8
  pg_ctl -D "$payment_pg_dir/db" -l "$payment_pg_dir/server.log" \
    -o "-h 127.0.0.1 -p 55487 -k $payment_pg_dir" -w start
  trap 'pg_ctl -D "$payment_pg_dir/db" -m fast -w stop' EXIT
  PAYMENT_FIX_TEST_PG_URL=postgresql://aicom_test@127.0.0.1:55487/postgres \
    USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-payment-tests \
    "$PYTHON" -m pytest -q -ra --timeout=60 tests/test_payment_chain_recovery.py \
      tests/test_payment_failure_recovery.py tests/test_payment_claim_crypto.py \
      tests/test_payment_refund_guards.py tests/test_payment_quote_key.py \
      tests/test_payment_confirmation_boundaries.py \
      tests/test_uni_settlement_atomicity.py tests/test_uni_settlement_boundaries.py
)
```

还应单独运行 Hub 和 eSIM 场景。Node.js 用例需要 Node 20+，并按各包的 lockfile 安装依赖。Stripe 和供应商响应均为模拟；这些测试不会扣银行卡费用或购买 eSIM。

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
hub_test_python=$("$PYTHON" -c 'import sys; print(sys.executable)')
USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-payment-tests \
  "$PYTHON" -m pytest -q --timeout=60 tests/test_hub_card_secret_scope.py
(
  cd aimarket-hub
  "$hub_test_python" -m pytest -q tests/test_card_topup.py
)
node --test esim-kit/store/test/procurement-recovery.test.js
node --test esim-kit/rails/test/settlement.test.js
```

非零退出码、超时、测试收集失败或跳过，都不能证明相应用例通过。这些命令不会广播区块链交易。

Factory 运行器要求 **coverage gate 所列 13 个函数的已测行和分支均为 100%**。CI 现提供隔离 PostgreSQL；450 个财务场景也已在 PostgreSQL 16 通过。本地完整检查需要 `PAYMENT_FIX_TEST_PG_URL` 指向临时测试集群。报告缺失、格式错误或无分支数据均判为失败。项目总覆盖单独报告。

```bash
PYTHON="${AIFACTORY_TEST_PYTHON:-.venv-quality/bin/python}"
PAYMENT_FIX_TEST_PG_URL="${PAYMENT_FIX_TEST_PG_URL:?use a disposable PostgreSQL test cluster}" \
  USE_SQLITE=true AIFACTORY_DATA_ROOT=/tmp/aicom-quality \
  AIFACTORY_PYTEST_HARD_CAP_SEC=1800 \
  "$PYTHON" scripts/run_factory_pytest_ci.py --timeout-method=signal
```

## 6. 核对真实交易

保留网络/chain ID、规范化哈希、代币合约或 mint、收款人、原始代币数量及小数位、交易回执/区块/确认数、
区块时间、`payment_id`、`order_id`、认领入口和账本/收据 ID。与原始报价和已认证客户核对；
公开证据中不能包含私钥、访问令牌或许可证内容。HTTP **400/422** 表示输入无效或尚未验证；
**401/403** 表示认证、归属或付款证明问题；**409** 表示重复使用/人工审核冲突；
**503** 表示验证或存储已关闭/不可用。必须阅读具体错误；任何错误本身都不能成为要求客户再付款一次的理由。

获授权管理员可查看 `/api/payment/admin/claims`，并通过
`/api/payment/admin/claims/{payment_id}/approve` 审批；报价、链上验证和单次使用检查仍然执行。
回滚软件不会撤销链上转账。退款或创建新付款前应先核对。
配置参考：[启用付款](payment-enable-runbook.md)、[链网络](chain-networks.md)、
[UNI 与 LIVE](uni-and-live.zh.md)、[Hub 银行卡充值](https://github.com/alexar76/aimarket-hub/blob/main/docs/card-topup.md)。
