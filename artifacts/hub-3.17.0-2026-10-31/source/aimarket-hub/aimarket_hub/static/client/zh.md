# 一次客户端调用完成钱包付款流水线

[English](https://modelmarket.dev/clients/pipeline-guide/en) · [Русский](https://modelmarket.dev/clients/pipeline-guide/ru) · [Español](https://modelmarket.dev/clients/pipeline-guide/es) · [Français](https://modelmarket.dev/clients/pipeline-guide/fr) · [中文](https://modelmarket.dev/clients/pipeline-guide/zh)

`await run_pipeline(...)` 将准备、本地签名、根任务执行与自动等待合并为一次客户端操作。正常路径只需**两次主要 Hub 请求**：准备图，再调用根任务。区块链 RPC 请求另计。HTTP 202、网络故障或服务器临时错误可能需要继续请求同一订单；两次 HTTP 交互并不保证任务已经完成。

## 独立卖家与恢复：3.10.1

付费图现在可以使用声明 **`SELLER-OP/1`** 的可信 peer，无需 `SELLS_FOR`、转售账户或该 peer 的信用 API 密钥。买家直接用钱包中的真实资金支付卖家账单。每个节点保留 `source_hub`；现有 `run_pipeline(...)`、HTTP 和 MCP 自动选择适配器。免费链仍然无需付款来源。

准备阶段验证 peer 的签名清单，并向同一 peer 获取签名报价。peer 必须处于 active 状态、受信任且已固定公钥；若固定了 PQ 公钥，也必须验证 PQ 签名。适配器校验 SKU、买家、目录价格、已声明的收款地址、链、代币、金额分配及有效期，不跟随报价中的任意 URL。不兼容的 peer 在签名和付款前以 `settlement_route_unsupported` 拒绝。准备可能留下未使用的卖家账单，但不执行工作或转账。

卖家持久化 `operation_id`，并发放仅限该操作的 `operation_token`。签名报价包含条款、账单 nonce/有效期和输入 schema。token 保存在买家 Hub 的私有运行状态中，不出现在公开账单中。输入可以依赖前序步骤；首次 invoke 固定具体输入、买家和交易哈希。修改后返回 HTTP 409。账单 secret 留在卖家端；买家 Hub 不生成竞争账单，也不转发信用凭据或 SUB/1 grant。钱包私钥始终留在客户端。

卖家路由为 `POST /ai-market/v2/operations/prepare`、`POST /ai-market/v2/operations/{operation_id}/invoke`、`GET /ai-market/v2/operations/{operation_id}`。invoke 和 status 需要 `X-Operation-Token`；缺失或错误返回 404。prepare 接受 `product_id`、`capability_id`、`wallet`、`max_price_usd`；invoke 接受 `input`、`wallet`、`tx_hash`，免费操作省略哈希。未完成 invoke 返回 202；成功或失败的终态返回 200，必须检查 `status` 和 `success`。status 返回签名状态，不执行工作或转账。普通链客户端仍使用原有的两个主要 Hub 请求。

买家 Hub 广播原始签名交易并确认付款后，先读取远程操作，再决定是否 invoke。卖家也验证付款，在调用提供方之前持久化执行占用，并缓存签名结果。状态签名绑定操作、报价摘要、输入摘要、钱包和交易哈希。HTTP 响应丢失时读取同一操作恢复；已保存的结果可跨卖家重启保留。根账单包含 `payment_rail: independent_seller`、签名报价与状态/收据。本地 SUB/1 子节点将结果连接到根树，使用 `own` 资金标记，不跨 Hub 转移信用 allowance。

买家 worker 每 30 秒续租。连续 180 秒未续租后，若在途 `SELLER-OP/1` 子步骤及 job 已持久化，可通过同一根 invoke 恢复。服务器原子转移执行权，并拒绝旧 worker 写入。只读 status 声明 `resume_same_run`，SDK 保留原签名付款包。此机制不会任意解锁旧式提供方；其他不确定状态仍需要操作员核对。

保证是**最多向提供方派发一次，并持久保存结果**，不是对任意提供方保证严格一次执行。最终提供方收到稳定的 `Idempotency-Key` 和 `X-AIMarket-Operation-Id`；它必须实现持久幂等，才能消除自身执行与响应之间的空档。若卖家在该边界崩溃或无法确认结果，返回 `reconciliation_required`，不再次派发。卖家占用超过 180 秒会报告异常，但不会自动解锁。`recovery.action: contact_operator` 表示核对同一操作，`replacement_payment_allowed` 始终为 false。目前只封装卖家的本地 listing，禁止递归 `pipeline.run@v1`；任意 x402 endpoint 不会自动支持该协议。

部署 Hub **3.10.1** 及数据库迁移 **44**（卖家操作）、**45**（worker 租约）。无需重新部署支付智能合约。独立 peer 也必须更新才能发布此卖家协议。付费图仍限制单链/单代币；现成付费客户端仍支持 Base USDC，并需要原生 gas。gas 代付、多网络、跨机器 nonce 协调和自动退款不包含在此版本中。

测试覆盖独立公钥与数据库、不可变请求、篡改报价、并发调用、响应丢失、旧 worker 隔离、动态输入、免费链，以及通过真实 Hub 支付代码在本地 Anvil 上结算。两个 Anvil 场景使用一次性代币和开发钱包，包括响应丢失；这证明集成有效，不代表所有外部卖家均已升级。生产检查单独记录。这些测试无需新增主网扣款。

## 1. 准备执行图

调用 `POST /studio/prepare-pipeline`，传入 `nodes`、可选的 `wallet` 和 `max_budget_usd`。它合并了原来的 `/studio/preflight` 与 `/studio/paid-runs/{run_id}/prepare-pipeline`。响应包含 `ready`、`blockers`、步骤标识及付款条件、`total_units`、`run_id`、`access_token`、`graph_digest`、`wallet`、`expires_at`，以及带发票 nonce 和 EIP-712 授权的 `offers`。准备阶段不创建根 job，也不付款。免费图不需要钱包，`offers` 为空；付费图没有钱包则被拒绝。旧接口仍然可用。清单中的 `pipeline_execution.prepare_graph` 公布新接口地址。

Hub 请求中的 `max_budget_usd` 仅限制服务费用。SDK 的 `max_total_usd` 还会检查下文所述的网络费用预留。

```json
{
  "nodes": [
    {"id": "weather", "product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1", "source_hub": "https://iot.modelmarket.dev", "input": {"city": "Berlin"}},
    {"id": "air", "product_id": "gaia.gateway", "capability_id": "gaia.air.read@v1", "source_hub": "https://iot.modelmarket.dev", "input": {"city": "Berlin"}, "depends_on": ["weather"]}
  ],
  "wallet": "<buyer-address>",
  "max_budget_usd": 1
}
```

## 2. 本地签名并执行

客户端核对响应与请求图、钱包是否一致，并检查报价、授权、余额、链、待处理 nonce 与 gas 估算。它在本地签署 EIP-3009 授权和 EIP-1559 交易，分配连续 nonce，在发送前保存完整付款包。Hub 收到签名交易，永远不接收私钥。客户端提交一个 `pipeline.run@v1` 根订单，执行器只在某步骤可以执行时广播相应付款。成功响应包含最终结果、签名账单、根回执和 SUB/1 树。检查 `status` 与 `success`：供应商失败也是终态，外部付款不会自动退款。

```json
{
  "product_id": "hephaestus",
  "capability_id": "pipeline.run@v1",
  "source_hub": "local",
  "input": {
    "run_id": "<prepared-run-id>",
    "access_token": "<scoped-run-token>",
    "transactions": {"weather": "0x<signed-transaction>", "air": "0x<signed-transaction>"}
  }
}
```

## Python 与命令行

安装已发布的 wheel 及 `client` 扩展（命令见下文）。客户端使用 **Base（8453）或以太坊（1）上的原生 USDC** 付款（见下文的其他支付配置），已在 macOS/Linux 上测试。其他链或代币一律拒绝，除非你自己的 `accepted_assets` 策略列出了它。免费图无需签名器、RPC 或汇率上限。签名器是提供 `address`、`sign_message` 与 `sign_transaction` 的本地对象。

```python
import json, os
from eth_account import Account
from aimarket_hub.pipeline_client import run_pipeline

result = await run_pipeline(
    json.load(open("blueprint.json")),
    hub="https://modelmarket.dev",
    signer=Account.from_key(os.environ["PIPELINE_WALLET_KEY"]),
    rpc_url="https://mainnet.base.org",
    max_total_usd="1",
    state_path="order.private.json",
    wait=True,
)
print(result["status"], result["final_result"], result["bill_of_materials"])
```

```bash
python examples/pipeline-run/run.py blueprint.json \
  --hub https://modelmarket.dev --rpc https://mainnet.base.org \
  --max-total-usd 1 \
  --execute --prompt-key --state order.private.json
```

`--prompt-key` 在本地无回显读取私钥；也可安全地通过环境变量 `PIPELINE_WALLET_KEY` 提供。免费图与签名后的恢复无需私钥。新的 CLI 订单必须带 `--execute`。原有 `client.py --budget` 示例继续保留仅计算服务费的语义。3.10.1 需要部署 Hub 并执行数据库迁移 44–45，无需重新部署支付智能合约。

## 预算、状态与恢复

`max_total_usd` 包含服务费及保守的 gas 预留。签名前以及每次提交或重试根调用前，客户端通过两个不同主机名的 RPC 读取固定地址的 Base Chainlink ETH/USD 合约。第二个端点默认为 `https://base-rpc.publicnode.com`；若主端点是 PublicNode，则使用 `https://mainnet.base.org`。可通过 `price_rpc_url` / `--price-rpc` 指定另一个可信提供商。两次读取都必须通过检查：Base 链 ID、8 位小数、已完成且为正的价格轮次、报价不超过 1500 秒、区块不超过 120 秒，以及排序器恢复运行已超过一小时。合约调用使用所观察区块的编号。价格差超过 2% 时停止提交。预算按较高价格 **加 25%** 计算。旧的可选 `native_usd_ceiling` 现在只能提高估值，不能降低预言机估值，也不能替代不可用的预言机。ETH 升至 $20,000 时，gas 至少按 $25,000 计算，即使旧恢复文件写着 6000。

每笔付款预留 300,000 gas，按观测 gas 价格的两倍计价，并加上 Base GasPriceOracle 对 2048 字节给出的 L1 上界的 100 倍；每单另加 $0.05。超过已保存预算时暂停提交，保留同一订单和签名。报价缺失、过期或不一致同样阻止新提交，不回退到固定价格。免费图和本地已保存的最终结果不需要预言机。已提交订单中断后，先只读查询状态，再决定是否重新估价。恢复文件记录两个报价、轮次、时间及采用的估值。不能因为重试被暂停就用新订单替代结果未知的旧订单。

检查发生在客户端提交前，不会在 Hub 执行长图期间持续运行。RPC 仍是信任依赖；不同主机名并不能证明基础设施独立。提交后美元汇率和 L1 费用仍可能变化，EIP-1559 签名不能固定这些值。这是保守的预算保护，不是保证绝对美元限额的链上托管。

[Chainlink ETH/USD — Base](https://data.chain.link/feeds/base/base/eth-usd) · [L2 sequencer](https://docs.chain.link/data-feeds/l2-sequencer-feeds).

恢复文件以 0600 权限原子替换并 fsync，独立文件锁防止同时使用同一路径。文件包含订单专用凭据及可执行的签名交易，必须保密，但不包含钱包私钥。付款包保存之后，恢复无需签名器，也不会选择新 nonce 或替代付款。如果中断发生在签名前，仍需要原签名器。准备响应丢失可能留下未使用的报价；此时尚无付款或根 job。不要同时从同一钱包发送其他交易。

默认自动等待。HTTP 202、传输异常、HTTP 429 与服务器错误会在有限等待时间内重试相同 payload。超时或需要人工核对时，`PipelinePending` 保留状态文件路径。服务器任务仍被占用时返回状态供后续检查，不擅自解锁。`wait=False` 返回待处理结果，由调用方恢复。已完成的本地状态直接返回缓存结果，无需联网。失败子任务不会自动重新购买或执行。恢复时不再传入图或新的预算/RPC 参数；已保存的图与策略保持不变。

```python
result = await run_pipeline(resume=True, state_path="order.private.json")
```

```bash
python examples/pipeline-run/run.py --resume --state order.private.json
```

[Codex：一次客户端操作，两个付费分包任务](https://modelmarket.dev/clients/pipeline-guide/zh) — 2026-09-30.

## 外部代理接入：3.9.0 更新

无需克隆仓库即可安装带版本号的 wheel。已签名清单通过 `pipeline_execution.client.distribution` 公布 URL 与 SHA-256。安装包由 Hub 提供；这不表示 PyPI 已经发布此版本。

```bash
pip install "aimarket-hub[client] @ https://modelmarket.dev/clients/aimarket_hub-3.14.0-py3-none-any.whl"
aimarket-pipeline --help
```

`aimarket-pipeline` 接受与 `examples/pipeline-run/run.py` 相同的参数。`client` extra 包含支付签名和 ML-DSA 验证。需要 Python 3.11+。已测试 Linux/macOS；Windows 文件锁已实现，但本次未测试。任何语言均可通过 HTTP/MCP 接入并在本地签名。

MCP 新增 `pipeline_prepare`、`pipeline_invoke`、`pipeline_status`。准备接收图、服务预算和可选钱包地址；执行接收 `run_id`、`access_token` 及本地签名包；状态只接收 ID 与令牌。免费图无需签名器或资金来源。远程 MCP 服务不能替它不控制的钱包签名：付费时接入本地签名器或使用 Python 客户端。不要将私钥作为工具参数发送。工具保留完整签名和付款报价，不做截断。

SDK 验证准备响应、账单及最终根收据的签名，校验图/订单/钱包绑定和结果/账单哈希，包括本地缓存。首次 HTTPS 准备时固定 Hub 的签名公钥。若要独立建立信任，可传入 `trusted_hub_key` 和 `trusted_hub_pq_key`（CLI：`--trusted-hub-key`、`--trusted-hub-pq-key`）。固定 PQ 公钥后，删除 PQ 签名会被拒绝。这里验证的是 Hub 的签名执行报告，并非独立认证每台设备身份。

带 `X-Studio-Run-Token` 的 `GET /studio/paid-runs/{run_id}/pipeline` 只读取结果，不支付也不调用子节点。响应丢失或恢复时，SDK 先读取此状态，再按需检查 RPC/gas。因此 RPC 中断或费用上涨时仍可获取已完成结果。忙碌的工作仅以只读方式轮询。429/5xx 重试增加间隔，并在剩余等待时间内遵守数值型 `Retry-After`。`PipelineHTTPError` 保留 `status_code`、`detail` 和 `state_path`，便于自动处理。

持久化钱包预留可防止同一主机的不同状态文件签署重叠 nonce。文件位于 `~/.aimarket/wallets`，可用 `AIMARKET_WALLET_STATE_DIR` 指定共享目录。参与客户端必须使用同一目录。成功后释放；失败后须等所有 nonce 已消耗，或授权过期且无待确认交易。请保留原恢复文件。跨主机或不同钱包程序需使用共享签名器/nonce 协调器或独立钱包；本地文件不能协调任意外部签名器。

预检返回稳定的 `blockers[].code`：`settlement_route_unsupported`、`route_unavailable`、`mixed_assets_unsupported`、`service_budget_exceeded`。外部付费路由支持 Hub 作为销售主体、已配置的转售和实现 SELLER-OP/1 的独立 peer。清单明确公布此边界。付费图使用单一链/代币，Python 客户端接受 Base USDC。列入目录不等于支持其支付方式。

若提供方已执行但响应丢失，不会自动再次购买。`recovery.action` 返回 `wait`、`resume_same_run` 或 `contact_operator`，禁止替代付款。核对需要提供方收据或其他执行证据。未发送的子节点不付款；已确认的外部支付不自动退款。系统明确报告这种不确定性，不会静默重复执行。


2026-09-30 补充生产验证：独立部署的卖方 Hub `https://independentai.network/hub` 在 Base 上以 0.002 USDC 完成 `kova.network.status@v1`。客户端故意丢失首次响应，随后恢复同一操作，没有再次付款。两个 Hub 由同一运营方管理；该测试证明部署与收款地址分离，不代表商业所有权独立。

[Base transaction](https://basescan.org/tx/0x0d3f6ab3c20ea6c719a7bf8127583d6e3a14ddd48220e961834772cb852e8919) · Evidence: `independent-seller-mainnet-2026-09-30.json` · Oracle RPC evidence — SDK 3.10.2: `native-price-oracle-2026-09-30.json`.


2026-09-30 生产环境预付费提供商测试：`weather.witness@v1` 已发布真实收款地址并启用固定价格模式。提供商的独立账户从零开始，没有赠款或抵押额度，通过 EIP-3009 实际充值 0.02 USDC；买方随后支付 0.002 USDC 购买根 SKU。提供商从这笔真实预付余额中分别支付 0.001 购买 GAIA 天气和空气数据，剩余 0.018。这是实际充值后的内部预付记账，不是另两笔链上子转账，也不是信用额度。提供商每日上限为 0.02，不自动充值。柏林结果为 agreement=true、14.5°C、湿度 64%、PM2.5 9.9 µg/m³、US AQI 33，采样时间为 2026-09-30T07:01:32Z。运行 `paid_580f85c4a2f4deba7a83bc26140fc558` 对应 job `job_db9c841f8a360f04c891a68b`，保留两个子收据摘要。RPC 在本地签名后返回 HTTP 429，阻止提交；恢复已保存签名包后完成同一订单。充值和购买均使用实时预言机预算检查。保守累计测试费用为 $0.047149423922618862625，低于 $1 上限；已计入全部充值，不重复计算预付余额中的子扣款。

Evidence: `witness-prepaid-mainnet-2026-09-30.json` · [Deposit](https://basescan.org/tx/0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e) · [Root payment](https://basescan.org/tx/0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272).


SDK 3.10.3 在 HTTP 429/5xx 或传输错误时，对同一 RPC 请求最多尝试三次，每次等待最多五秒。尝试耗尽后停止提交并保留原订单，不回退到固定汇率，也不创建新付款。

## 软件包发布状态 — 检查日期 2026-09-30

PyPI 已发布 `aimarket-hub==3.10.3` 的 wheel 和源码归档；包内 131 个文件与生产构建一致。3.11.0 新增 Gas 代付，需要单独发布，不能覆盖已发布的 3.10.3。独立软件包 `aimarket-agent==2.5.0` 的发布仍需确认。发布软件包和部署 Hub 是不同操作。供应商恢复、退款及更多网络/代币支持仍是后续阶段。

## Gas 代付 — SDK 3.11.0

SDK 默认使用 `gas_mode="auto"`。Hub 签名的准备结果会说明能否为整个图代付 Gas。可用时，买方只在本地签署金额、收款人均已确定的 USDC EIP-3009 授权；运营方的独立钱包签署链上交易并支付 Gas。买方不需要 ETH、交易签名方法或 RPC 配置。`gas_mode="required"` 在准备阶段拒绝无法代付的收费图；`gas_mode="buyer"` 保留买方支付 Gas 的流程。为保持兼容，HTTP 与 MCP 准备接口仍默认 `buyer`。CLI 使用 `--gas-mode required`。

准备结果包含 `gas_sponsorship`；根调用接收 `authorizations: {step_id: signature}`，替代 `transactions`，两者不能同时提交。报价固定支付模式、买方、收款人、金额、授权 nonce 与有效期；重试不得更换签名包。Hub 不接收买方私钥。签名账单记录代付模式以及每笔付款的 Gas 支付方；买方 Gas 费用为零。免费图仍不需要签名者或代付钱包，即使设置 `required`。

首版支持 Base 8453 上直接支付 USDC，也支持兼容的独立卖方。当前 MarketSplitter 将付款人绑定到 `msg.sender`，因此明确不支持分佣交易代付。直接支付无需重新部署合约。`auto` 可以回退到买方付 Gas；`required` 不会回退。代付余额不足、每日额度耗尽、预言机不可用或 nonce 被占用时，同一订单进入等待状态，不创建替代付款。

每次新付款前，Hub 检查实时 ETH/USD 预言机、保守 Gas 估算、余额及单笔和每日上限。只有解析并验证步骤输入后，才在共享数据库内原子地预留 nonce 并保存已签名交易字节。每个代付钱包同时只能有一笔未确认交易。多个工作进程共享 nonce 和预算账本，重试广播完全相同的字节。保存交易后发生崩溃，即使报价已过期也可恢复，因为付款可能已经发生。缓存的完成结果无需 RPC。不同数据库不得共用同一个 Gas 钱包。

运营配置：`AIMARKET_PIPELINE_RELAY_ENABLED=1`、`AIMARKET_PIPELINE_RELAY_KEY_FILE`（私密文件，非符号链接）、`AIMARKET_PIPELINE_RELAY_RPC`、可选 `AIMARKET_PIPELINE_RELAY_PRICE_RPC`、`AIMARKET_PIPELINE_RELAY_DAILY_WEI`（默认 20000000000000）和 `AIMARKET_PIPELINE_RELAY_MAX_GAS_USD`（默认 0.10）。充值专用 Gas 钱包，绝不把买方私钥安装到服务器。每日预算按保守 ETH 费用上界预留，挖矿后不释放差额。USD 估算是留有余量的检查，不是不可变的链上美元上限。停用新代付后，已保存交易仍可恢复。

已验证：不同数据库连接的并发工作进程、预算预留回滚、无效签名、不可变恢复、免费图，以及买方 ETH 为零的真实 Anvil EIP-3009 转账。这些测试本身不代表已经生产部署，也不代表完成了供应商恢复、退款或多网络支持。

2026-09-30 生产验证：先执行免费的 LOGOS 步骤，再调用 `https://independentai.network/hub` 的 `kova.network.status@v1`；签名者只能签署消息，SDK 未配置 RPC。买方服务费为 **0.002 USDC**，Gas 为 **0**；ETH 余额与交易 nonce 均未变化。人为丢弃第一次 invoke 响应后，恢复的是同一订单。KOVA 返回 `pass`、100 分、Base 区块 51983924。代付方支付了 516607663289 wei。已将其全部 0.00002 ETH 充值计入预算，因此不重复计算代付 Gas。包括此前测试在内，保守累计支出为 **$0.1163241752052936711504319125 / $1**。以下证据不含访问令牌或私钥。

`run_id: paid_38c0a7c6c2fe992186116a2822205d3d` · `job_id: job_dc0b37b785a7f358bfb30b23`

[Base transaction](https://basescan.org/tx/0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857) · Evidence: `gas-sponsorship-mainnet-2026-09-30.json`

## 供应商结果恢复 — SDK/Hub 3.12.0

`PROVIDER-OP/1` 处理供应商已经完成工作、但卖方 Hub 未收到响应的情况。兼容供应商在执行前记录操作 ID 以及产品、capability、输入的摘要，并在返回前持久化结果与签名。重复相同操作返回已保存结果；更改输入会被拒绝。并发请求不会重复执行。KOVA 在现有 SQLite 数据库中保存该日志。

卖方明确启用兼容产品：`AIMARKET_PROVIDER_OPERATION_PRODUCTS=kova-network`。新的签名 `SELLER-OP/1` 报价声明 `provider_recovery: PROVIDER-OP/1`；原始供应商 URL 和公钥固定在私密操作状态中。响应丢失或执行声明过期后，卖方读取 `GET <invoke_url>/operations/<operation_id>`，验证签名、操作 ID、产品、capability、精确输入摘要及独立的结果签名。恢复付费工作还要求已保存原付款验证。最终卖方响应不可更改，即使旧工作进程随后返回。恢复不会向供应商发出第二次 POST，也不创建新付款。

KOVA 的 invoke 与 status 接口均要求私密服务间令牌：`AIMARKET_CAPABILITY_TOKEN` 和 `KOVA_CAPABILITY_TOKEN` 必须一致；`AIMARKET_INVOKE_HOST_GATEWAY` 只允许运营方供应商的主机。公有证据不包含密钥或令牌。买方仍通过 Hub 的支付和授权检查。

这是需要供应商配合的恢复机制，并非对任意外部副作用承诺“恰好一次”。如果供应商在产生外部效果后、保存结果前崩溃，结果仍属未知，不自动重做。供应商必须将业务事务绑定到操作 ID，或先核实效果再记录结果。旧供应商仍需要人工核对；KOVA 的不确定记录阻止重复写入。

已付款发票可在过期后恢复，但已验证的区块时间必须严格早于有效期。过期后付款仍被拒绝，nonce 仍只能使用一次。逗号分隔的显式 RPC 现在正确形成独占列表。公开账单移除了内部 job grant 字段。测试覆盖重启、并发、修改输入、身份验证、篡改签名、双 Hub 无重复付款恢复、未知副作用以及发票有效期边界。

2026-09-30 生产验证：LOGOS → KOVA 花费 0.002 USDC，买方 Gas 为零。重启 KOVA 后，通过 GET 从持久日志恢复签名结果。响应丢失在卖方操作的隔离副本中模拟，没有修改生产账本，也没有新供应商调用或付款。恢复结果保留原 Base 区块 51984647。无令牌访问 status 返回 401，带授权查询不存在的操作返回 404。保守累计支出为 $0.1183241752052936711504319125 / $1。退款以及更多网络/代币仍是后续阶段。

`run_id: paid_7f29b95f0ebf51092a52883053172f93` · `job_id: job_4ca838ba5866031111ed1778`

[Base transaction](https://basescan.org/tx/0x633c83fcdf9dc2a086a218597068503df4165a230141f69e64fa0209d130e758) · Evidence: `provider-recovery-mainnet-2026-09-30.json`


## 卖家批准的退款 — SDK/Hub 3.13.0

`SELLER-REFUND/1` 可退回已确认的 Base USDC 直接付款。买家为已结束流水线中的步骤申请退款报价，原卖家在本地签署 EIP-3009 授权，赞助者支付网络 gas。双方均不向 Hub 提交私钥，也不需要持有 ETH 才能走此路径。准备报价不会转账，也不强制卖家同意退款。

HTTP 使用原 `X-Studio-Run-Token`：`POST /studio/paid-runs/{run_id}/refunds/{step_id}/prepare` 创建或读取签名报价；`POST /studio/paid-runs/{run_id}/refunds/{step_id}` 接收 `{"authorization":"0x…"}` 并推进同一退款；该路径的 `GET` 只读状态。HTTP 202 表示等待中。MCP 提供 `pipeline_refund_prepare`、`pipeline_refund`、`pipeline_refund_status`，参数为相同的 run ID、受限访问令牌和 step ID。只提交卖家签名，绝不提交钱包私钥。

SDK `refund_pipeline(state_path=..., step_id=...)` 仅返回报价，不转账。只把其中的 `offer` 对象交给卖家，不要分享买家的私有恢复文件。卖家通过 `aimarket_hub.refund_client` 调用 `sign_refund_offer(offer, seller_signer=..., buyer_wallet=..., original_tx_hash=..., max_usdc=..., trusted_hub_key=..., trusted_hub_pq_key=...)`。该方法在本地核验获批收款人、原付款、金额上限、代币、网络及 Hub 签名。买家用 `refund_pipeline(..., authorization=signature)` 提交返回的签名。再次使用同一私有文件会恢复同一退款；`RefundPending` 保留其身份。是否应退款由卖家应用在签名前决定。

Hub 仅允许原卖家向原买家退回已核验付款的完整准确金额。流水线必须为 completed 或 failed；供应商执行结果未知时必须先对账。已提交签名不可更改。交易字节在广播前持久化，并使用赞助者共享数据库中的 nonce 和预算协调器。回复丢失或重启后复用同一交易。授权过期后，只有 Hub 尚未签署交易时才能续期，退款 ID 和授权 nonce 保持不变，防止新旧授权执行两次转账。

原签名账单和结果保持不变。独立签名的 `pipeline.refund/1` 贷项凭证关联原付款与退款交易哈希、金额、代币、网络、双方和 gas 付款人。查询状态不转账。首版支持每笔无拆分手续费的 Base USDC 直接付款进行一次全额退款，并要求赞助者可用。尚不支持部分退款、MarketSplitter 费用退还、强制扣款或任意代币。卖家可能拒绝或余额不足；赞助者额度不足时同一退款保持等待。已经消耗的 gas 不退还。免费流水线仍无需支付来源。

测试涵盖错误签名者、金额篡改、并发状态保护、授权过期、已保存交易不可变、回复丢失、SDK/MCP，以及买卖双方无 ETH 时在 Anvil 完成购买和退款。完成后的主网验证将另行记录。


主网验证，2026-09-30：运营方临时静态 SKU 以 0.001 USDC 交付结果，其独立卖家钱包随后批准全额退回。这是实际结算与退款机制测试，不代表独立商业卖家。买卖双方 USDC 余额均恢复初始值，买家的 ETH 和 nonce 未变，两笔交易的 gas 均由赞助者支付。故意丢弃退款回复后恢复了同一贷项凭证；重启 Hub 后，原结果与退款的完整 JSON 值仍完全相同。临时商品已删除。保守累计支出为 $0.1193241752052936711504319125，低于 $1 限额，包含赞助者的全部充值和退款前的购买总额。没有部署新合约。

`run_id: paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc` · `refund_id: refund_95331477f4fb1e81b122b51b63857f0e`

[Purchase / Покупка / Compra / Achat / 购买](https://basescan.org/tx/0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58) · [Refund / Возврат / Reembolso / Remboursement / 退款](https://basescan.org/tx/0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf) · Evidence: `refund-mainnet-2026-09-30.json`


## 更多支付配置与多台客户端 — SDK/Hub 3.14.0

SDK 现在接受 **Base 8453 和 Ethereum 1** 上的原生 USDC，固定合约地址、6 位小数以及 EIP-712 `USD Coin` / `2`。一个付费图仍只使用一条链和一种资产；混合图应拆分为不同订单。Hub 必须提供对应路径：SDK 支持某网络并不会跨链搬运余额，也不会改变卖家报价币种。免费图不变。gas 赞助和卖家批准退款目前仍限于 Base USDC 直接付款；Ethereum 的 gas 由买家支付。`gas_mode="required"` 会在签名前拒绝无赞助者的付费路径。

`accepted_assets=[...]` 替换默认白名单。每项明确指定 `chain_id`、`token_contract`、`decimals`、`eip712_name`、`eip712_version`、`usd_pegged: true` 和 `authorization: "EIP-3009"`。这是买家对已审查美元代币的政策，不证明任意 ERC-20 都具备这些属性；Hub 无权扩充。金额采用十进制计算。非美元资产、仅支持 approve 的普通 ERC-20、其他链及原子跨链图会被拒绝，不会暗中兑换。CLI：`--accepted-assets approved-assets.json`。恢复文件固定此政策，resume 不可更改。

本地 Ethereum 卖家配置 `AIMARKET_X402_CHAIN=ethereum`。广播和核验使用已签名 chain ID；`AIMARKET_SETTLE_RPC_1`、`AIMARKET_SETTLE_RPC_8453` 分别指定节点。全局 `AIMARKET_SETTLE_RPC_URL` 仍是排他的后备列表，不能用仅 Base 的节点服务 Ethereum。核验 receipt 或广播之前，RPC 必须报告账单指定网络。自定义 Hub 资产还需正确配置地址、符号、小数位、`AIMARKET_X402_EIP712_NAME` 和 `AIMARKET_X402_EIP712_VERSION`，并与买家白名单一致。不可将非美元代币按美元计价。

Ethereum 通过两个不同 RPC 主机读取最新 ETH/USD，采用 25% 价格余量、gas 上限及 $0.05 储备，不计入 Base L1 附加费。固定 Chainlink feed 为 `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419`，8 位小数，heartbeat 3600 秒，最大允许年龄 3900 秒。Base 保留 sequencer 检查及单独 L1 储备。错误网络、过旧区块或价格、超过 2% 的差异均停止付款。手动价格只能提高上限。

多台机器上的代理应安装 `postgres` extra，在创建订单前设置同一个**买家自有** `AIMARKET_WALLET_DATABASE_URL`。使用直连或 session pooling；PgBouncer transaction pooling 无法保留会话 advisory locks。协调器跨连接串行化每个 `(chain_id, wallet)`，在提交前保存私有恢复状态、Hub 受限令牌和确切签名交易字节，绝不保存钱包私钥。数据库只应开放给合作的买家代理。DSN 不写入订单，也不发给 Hub。

将私有恢复文件安全复制到下一台机器，并调用 `run_pipeline(resume=True, state_path=...)`。签名前的旧副本会从 PostgreSQL 获取已保存交易；已完成订单会在任何新签名前读取结果。其他订单不能抢占未完成保留。终态失败后，只有所有签名 nonce 已消耗，或授权过期且不存在 pending 交易，才能释放。数据库故障会阻止新提交，已完成的本地结果仍可读取。所有客户端必须使用相同数据库和 schema，不要混用独立协调器或其他钱包软件。默认仍为本地文件；gas 获赞助的买家无需 PostgreSQL。

测试使用真实临时 PostgreSQL，覆盖独立连接、客户端崩溃、旧副本和保存失败。chain ID 1 的本地 EVM 通过 SDK 执行了真实 EIP-3009 购买；oracle 因本地无 Chainlink 而单独测试。Ethereum 主网仅做只读检查：两个价格观测一致，USDC 的 name/version/decimals 与配置匹配。不声称完成 Ethereum 主网购买，没有新增支出。

[Circle 合约表](https://developers.circle.com/stablecoins/usdc-contract-addresses) · [Ethereum ETH/USD](https://data.chain.link/feeds/ethereum/mainnet/eth-usd) · 只读验证: `ethereum-profile-2026-09-30.json`

版本交付：Hub 与可下载 wheel 为 3.14.0。2026-09-30 检查 PyPI 仍为 `aimarket-hub==3.10.3` 和 `aimarket-agent==2.4.0`。待发布产物是 `aimarket-hub==3.14.0` 以及独立供应商 SDK `aimarket-agent==2.5.0`。当前环境没有发布凭据，上传 PyPI 仍需运营方完成。下方固定 Hub wheel 已可安装。无需重新部署已有合约。

```bash
pip install "aimarket-hub[client,postgres] @ https://modelmarket.dev/clients/aimarket_hub-3.14.0-py3-none-any.whl"
# Optional: buyer-owned PostgreSQL, same database/schema on every client host.
export AIMARKET_WALLET_DATABASE_URL='postgresql://<buyer-user>:<password>@<buyer-db>/<database>'
aimarket-pipeline --resume --state pipeline-run.private.json
```

---

# Codex：一次客户端操作，两个付费分包任务

[English](https://modelmarket.dev/clients/pipeline-guide/en) · [Русский](https://modelmarket.dev/clients/pipeline-guide/ru) · [Español](https://modelmarket.dev/clients/pipeline-guide/es) · [Français](https://modelmarket.dev/clients/pipeline-guide/fr) · [中文](https://modelmarket.dev/clients/pipeline-guide/zh)

**2026 年 9 月 30 日**，Codex 使用新的 `await run_pipeline(...)`、同一个运营方提供的钱包及 **$1 总预算**，再次完成 GAIA 分包测试。Hub 运行 `modelmarket-hub:prod-20260930-onecall`。两个子任务均成功，客户端自动等待确认。服务费为 **0.002 USDC**，包含 gas 的实测总费用为 **≈ $0.00468270**。

## 流程与实际请求

客户端调用 `POST /studio/prepare-pipeline` 提交图和钱包，核对图、付款条件、余额及费用预留，在本地签名并私密保存付款包，然后调用 `pipeline.run@v1`。Hub 没有收到管理员凭据或私钥。购买通过 Codex 终端中的 Python 使用公共 REST API 完成，不是 MCP。调用方只等待一次 SDK 操作，无需手动运行 resume。

| 顺序 | Hub 请求 | HTTP | 状态 |
|---|---|---:|---|
| 1 | `POST /studio/prepare-pipeline` | 200 | `ready` |
| 2 | `POST /ai-market/v2/invoke` | 202 | `active` |
| 3 | `POST /ai-market/v2/invoke` | 202 | `active` |
| 4 | `POST /ai-market/v2/invoke` | 200 | `completed` |

付费测试实际发送了**四次 Hub 请求**，并非严格两次。区块链 RPC 与汇率请求另计。第一次准备响应同时给出报价与授权。每次 202 都继续同一个 run，使用完全相同的签名包。全程只有一个根 job 和两个成功子调用。完成后，`run_pipeline(resume=True, ...)` 返回相同的本地缓存结果，**额外 Hub 请求为零**。测试与证据核验共用时 11.872 秒；这是观测结果，不是延迟保证。

## 图与结果

图依次购买 `gaia.gateway` 的 `gaia.weather.read@v1` 和 `gaia.air.read@v1`，保留 `source_hub: https://iot.modelmarket.dev`，输入为 `city: Berlin`。`air` 等待 `weather` 完成，但没有接收天气数值。最终结果来自 **GAIA-AQ1（Open-Meteo AQ 中继）** 设备 `om-aq-01` 的签名读数，时间为 **2026-09-30 04:24:34 UTC**。证据记录天气步骤成功，但没有包含其中间读数。这是中继数据，并非柏林部署了独立物理传感器的证明。

| 指标 | 数值 |
|---|---:|
| PM2.5 | 8.8 µg/m³ |
| PM10 | 11.1 µg/m³ |
| US AQI | 33 |
| European AQI | 24 |

## 预算与结算

付款方为 `0x6E94c380d908531f9822035d6cc4c8D2B0186C9c`，USDC 收款方为 `0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a`。使用 Base 主网上现有的 USDC，chain ID 为 8453。买方选择 ETH/USD 上限 6000；最后记录的保守费用估算为 $0.1195256567368，低于 $1。实际美元成本按测试期间 Coinbase 报价 **$2673.555/ETH** 折算。行情与估算都不是链上强制执行的绝对美元上限。

| 费用 | 金额 |
|---|---:|
| 服务 / USDC | 0.002 USDC |
| 网络费用 (L2 + L1) | 0.000001003418744789 ETH |
| 网络费用 / USD | ≈ $0.00268270 |
| 总计 / USD | ≈ $0.00468270 |

## 附加测试与验证

两步免费 LOGOS 图通过同一 SDK 成功执行，无需钱包、RPC 或汇率上限，只发送两次 Hub 请求。总预算 $0.003 的付费图通过服务报价检查，但因手续费预留不足被客户端拒绝：只有一次准备请求，没有根调用或付款。**84 项本地测试**与 **4 项 Anvil 付款测试**通过，覆盖响应丢失、相同请求重试、签名后无签名器恢复、gas 预算拒绝、错误链或授权、文件锁，以及子任务失败终态。

CLI 也在生产环境完成了免费图，随后在不提供钱包私钥的情况下恢复执行，返回完全相同的已保存结果。

两笔链上交易均成功。USDC 金额与网络费用同买方余额变化一致。根回执和账单签名使用测试前记录的 Hub 公钥验证，并核对账单/结果哈希和两个子回执引用。空气读数签名按所附公钥验证，没有独立固定设备身份公钥。公共证据包含签名结果与链上回执，不含私钥、执行访问令牌或原始签名付款交易。

这仍是运营方授权的集成测试：GAIA 与 Hub 属于同一运营生态，Hub 是负责收款的卖方。它证明真实付款与分包执行，不证明独立客户需求。SUB/1 关联任务，资金来源为 `buyer_wallet`，子任务为 `funded_by: own`，未使用信用 allowance。没有重新部署智能合约。免费 SDK 测试不代表单独配置的旧 `/studio/run` 路由也已验证通过。

## 证据与复现

- JSON: `codex-one-call-2026-09-30.json` · Blueprint: `codex-one-call-2026-09-30-blueprint.json`
- [API / SDK](https://modelmarket.dev/clients/pipeline-guide/zh)
- `run_id`: `paid_ce7dfb28ec21c0ffbc6f65884929aeec`
- `job_id`: `job_dd54651f9104c5c5ac31cc4e`
- `weather`: [0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e](https://basescan.org/tx/0x5ecc8cf51aec0618e730d130ce9d61003cbdccc0b1814d5a39d6c67228c2543e)
- `air`: [0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1](https://basescan.org/tx/0x5ef82ffce3e6d7a5a4866cf492ae2db5b44df238b85ad361ab4641de61304fa1)

---

外部代理接入更新（3.9.0）的后续验证：175 项针对性测试与 4 项本地 Anvil 支付测试通过。干净安装的客户端通过 SDK 用两次 Hub 请求完成免费图；MCP prepare/invoke/status 完成另一个免费图。原付费订单仅通过两次 GET（清单与根状态）恢复，无需钱包私钥或 RPC。Hub 收据由 SDK 自身验证。本轮未新增 mainnet 支付。wheel 由 Hub 分发，其 SHA-256 位于已签名清单中；尚未发布到 PyPI。

JSON: `agent-rails-2026-09-30.json`

## 后续：独立卖家协议，3.10.1

Codex 添加了 SELLER-OP/1，并部署 Hub 及迁移 44–45。链操作指南详细说明协议和边界。**223 项针对性测试及 6 个本地 Anvil 场景通过**，其中两个场景使用一次性代币，在独立 Hub 间结算，一个模拟卖家响应丢失。每个独立卖家场景中，买家仅支付一次，恰好 4,000 个代币最小单位；卖家创建并核销账单。这是本地链集成测试，不是新的主网购买。

生产验证包括签名清单、wheel、五种语言指南、免费 MCP 链、使用两个主要请求的免费 SDK 链，以及仅通过 GET 恢复原付费订单。测试钱包没有新增主网付款。本地 weather.witness listing 没有兼容的直接收款路径：准备现在于执行和付款前返回 409/settlement_route_unsupported，而不是 500；该 SKU 原有基于信用的 SUB/1 协议不变。本次未升级或购买独立的生产 peer；该路径在两个受控 Hub 和 Anvil 上验证。

脱敏验证证据: `seller-operations-2026-09-30.json`。不公开私钥、操作 token 或签名付款包。

### codex-one-call-2026-09-30-blueprint.json

```json
{
  "nodes": [
    {
      "id": "weather",
      "product_id": "gaia.gateway",
      "capability_id": "gaia.weather.read@v1",
      "source_hub": "https://iot.modelmarket.dev",
      "input": {
        "city": "Berlin"
      }
    },
    {
      "id": "air",
      "product_id": "gaia.gateway",
      "capability_id": "gaia.air.read@v1",
      "source_hub": "https://iot.modelmarket.dev",
      "depends_on": [
        "weather"
      ],
      "input": {
        "city": "Berlin"
      }
    }
  ]
}
```

### agent-rails-2026-09-30.json

```json
{
  "version": "3.9.0",
  "wheel_sha256": "b5a3ccc3ec10be2a2c4ae01dd052d60216e1834751550ba206f63b2446ae4014",
  "guides": [
    "en",
    "ru",
    "es",
    "fr",
    "zh"
  ],
  "mcp_free_run_id": "paid_838b4c9fceefadc04daee59599a8ff2e",
  "mcp_free_job_id": "job_f3dbbfcd48b38769c2bc5959",
  "sdk_free_run_id": "paid_c997741497bb4fad3c0a6c8183cddea1",
  "sdk_free_requests": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "existing_paid_run_id": "paid_ce7dfb28ec21c0ffbc6f65884929aeec",
  "existing_paid_job_id": "job_dd54651f9104c5c5ac31cc4e",
  "paid_recovery_requests": [
    {
      "method": "GET",
      "path": "/.well-known/ai-market.json"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_ce7dfb28ec21c0ffbc6f65884929aeec/pipeline"
    }
  ],
  "new_mainnet_payments": 0,
  "hub_receipts_verified": true
}
```

### seller-operations-2026-09-30.json

```json
{
  "version": "3.10.1",
  "wheel_sha256": "32dd7e248a05f9c4052d7d3dd71470e6b3d183d73a786c7795f1e7f4b87c8d94",
  "protocol": "SELLER-OP/1",
  "guides": [
    "en",
    "ru",
    "es",
    "fr",
    "zh"
  ],
  "older_wheel_preserved": true,
  "mcp_free_run_id": "paid_20e4b10e6eafcb80199cce1b34a759e2",
  "mcp_free_job_id": "job_78bb0fc253938109f00762c1",
  "sdk_free_run_id": "paid_0d1a123a53176be3c66490aef8e35b46",
  "sdk_free_requests": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "existing_paid_run_id": "paid_ce7dfb28ec21c0ffbc6f65884929aeec",
  "existing_paid_job_id": "job_dd54651f9104c5c5ac31cc4e",
  "paid_recovery_requests": [
    {
      "method": "GET",
      "path": "/.well-known/ai-market.json"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_ce7dfb28ec21c0ffbc6f65884929aeec/pipeline"
    }
  ],
  "new_mainnet_payments": 0,
  "hub_receipts_verified": true,
  "local_tests": {
    "focused": 223,
    "anvil": 6,
    "independent_seller_anvil": 2,
    "mainnet_independent_seller_test": false
  },
  "seller_quote_smoke": {
    "sku": "weather.witness@v1",
    "status": "preflight_refused",
    "reason": "listing has no supported seller payout or token",
    "http_status": 409,
    "invoke_sent": false,
    "payment_sent": false,
    "invalid_token_rejected": true,
    "recursive_pipeline_rejected": true
  },
  "production_migrations": [
    44,
    45
  ]
}
```

### independent-seller-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "buyer_hub": "https://modelmarket.dev",
  "seller_hub": "https://independentai.network/hub",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "run_id": "paid_356c3e6931dc6a7f4b3bd2640881e04b",
  "job_id": "job_b9aebbd2aa412d310b14c91e",
  "operation_id": "op_c6d88ad6d742603073eaa6eab5326d38",
  "source_hub": "https://independentai.network/hub",
  "payment_rail": "independent_seller",
  "pay_to": "0xB73d8Bc93B791510C4733C5C5Ac2015a3c2930Ec",
  "tx_hash": "0x0d3f6ab3c20ea6c719a7bf8127583d6e3a14ddd48220e961834772cb852e8919",
  "success": true,
  "status": "completed",
  "final_result": {
    "block_number": 51980340,
    "chain": "base",
    "chain_id": 8453,
    "findings": [],
    "score": 100,
    "summary": "Base mainnet is reachable through KOVA.",
    "verdict": "pass"
  },
  "service_usdc": ".002",
  "gas_wei": "603167313432",
  "usd_policy_ceiling": 6000,
  "prior_cost_at_ceiling_usd": "0.016197102150400000",
  "new_cost_at_ceiling_usd": "0.005619003880592000",
  "cumulative_cost_at_ceiling_usd": "0.021816106030992000",
  "approved_total_usd": "1",
  "new_order_limit_usd": ".15",
  "controlled_client_response_loss": true,
  "signed_result_verified": true,
  "http_requests": [
    {
      "method": "GET",
      "host": "modelmarket.dev",
      "path": "/studio/paid-runs/paid_356c3e6931dc6a7f4b3bd2640881e04b/pipeline",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "mainnet.base.org",
      "path": "/",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "mainnet.base.org",
      "path": "/",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "modelmarket.dev",
      "path": "/ai-market/v2/invoke",
      "http_status": 200
    },
    {
      "method": "GET",
      "host": "modelmarket.dev",
      "path": "/studio/paid-runs/paid_356c3e6931dc6a7f4b3bd2640881e04b/pipeline",
      "http_status": 200
    },
    {
      "method": "POST",
      "host": "mainnet.base.org",
      "path": "/",
      "http_status": 200
    }
  ],
  "operator_note": "Separate production hub, keys, database and seller wallet; both deployments administered by the same user. Not evidence of an independently owned customer."
}
```

### native-price-oracle-2026-09-30.json

```json
{
  "source": "chainlink_base_eth_usd",
  "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
  "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
  "observations": [
    {
      "price_usd": "2658.74990071",
      "round_id": "55340232221128660926",
      "updated_at": 1790750527,
      "block_number": 51980758,
      "block_timestamp": 1790750863,
      "sequencer_up_since": 1782491507
    },
    {
      "price_usd": "2658.74990071",
      "round_id": "55340232221128660926",
      "updated_at": 1790750527,
      "block_number": 51980758,
      "block_timestamp": 1790750863,
      "sequencer_up_since": 1782491507
    }
  ],
  "margin_percent": 25,
  "max_age_s": 1500,
  "manual_floor_usd": null,
  "native_usd_ceiling": "3323.4373758875",
  "checked_at": 1790750864.630485,
  "rpc_providers": [
    "mainnet.base.org",
    "base-rpc.publicnode.com"
  ],
  "new_mainnet_payments": 0,
  "private_key_used": false,
  "client_version": "3.10.2"
}
```

### witness-prepaid-mainnet-2026-09-30.json

```json
{
  "topup": {
    "tx_hash": "0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e",
    "amount_usdc": ".02",
    "fee_wei": "500743844349",
    "budget_check": {
      "service_usdc": "0.02",
      "native_fee_bound_wei": "4832812118600",
      "native_usd_ceiling": "3328.5750",
      "native_price": {
        "source": "chainlink_base_eth_usd",
        "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
        "observations": [
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981039,
            "block_timestamp": 1790751425,
            "sequencer_up_since": 1782491507
          },
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981039,
            "block_timestamp": 1790751425,
            "sequencer_up_since": 1782491507
          }
        ],
        "margin_percent": 25,
        "max_age_s": 1500,
        "manual_floor_usd": null,
        "native_usd_ceiling": "3328.5750",
        "checked_at": 1790751427.5852952
      },
      "l1_upper_bound_wei": "12328121186",
      "l1_multiplier": 100,
      "extra_reserve_usd": "0.05",
      "conservative_total_usd": "0.08608637759766899500",
      "checked_at": 1790751427.585309
    },
    "redeem_status": 200,
    "redeem_result": {
      "success": true,
      "status": "credited",
      "nonce": "0x9078baf0077009ef3f0c29a7baea1458ec130c16600df38260e1e71153e763a1",
      "tx_hash": "0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e",
      "credited_usd": 0.02,
      "chain": "base",
      "paid_usd": 0.02,
      "idempotent_replay": false,
      "protocol_version": "v2"
    }
  },
  "purchase": {
    "result": {
      "trace_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
      "status": "completed",
      "busy": false,
      "bill_of_materials": {
        "trace_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
        "graph_digest": "020dc99f6c776c7eb40a87190b5385800a6d2fe3c534a059972436c81657c282",
        "funding": "buyer_wallet",
        "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
        "status": "completed",
        "budget_usd": 0.002,
        "total_usd": 0.002,
        "remaining_budget_usd": 0.0,
        "payment_unresolved": [],
        "steps": [
          {
            "id": "witness",
            "product_id": "weather-witness",
            "capability_id": "weather.witness@v1",
            "source_hub": "local",
            "status": "succeeded",
            "quoted_usd": 0.002,
            "payment_rail": "seller_direct",
            "terms": {
              "amount_units": "2000",
              "amount_usd": 0.002,
              "chain": "base",
              "chain_id": 8453,
              "decimals": 6,
              "eip712_name": "USD Coin",
              "eip712_version": "2",
              "fee_to": "",
              "fee_units": "0",
              "min_confirmations": 1,
              "offer_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
              "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
              "seller_units": "2000",
              "token": "USDC",
              "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
            },
            "success": true,
            "status_code": 200,
            "receipt": {
              "capability_id": "weather.witness@v1",
              "latency_ms": 1738,
              "list_price_usd": 0.002,
              "nonce": "rcpt_1b670e8c9d8a414658a165fb2aefdf59",
              "price_usd": 0.002,
              "product_id": "weather-witness",
              "signature": {
                "algorithm": "ed25519",
                "pq_algorithm": "ml-dsa-65",
                "pq_public_key": "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",
                "pq_value": "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",
                "value": "EgDG7QkWIX4Qe8U+Wvf23dIQVfP7rEfFTZlmdJZ0dPlb3Nb9syBthPIV42BTadQFH8sglyp9S9/ZHBUK5pPjAw=="
              },
              "success": true,
              "timestamp": "2026-09-30T07:01:33Z"
            },
            "job": {
              "depth": 1,
              "funded_by": "own",
              "job_id": "job_db9c841f8a360f04c891a68b",
              "node": "node_228186546b7fac0f4d89706a",
              "parent": "node_ba3a877444eda0486258c30b"
            },
            "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
            "payment": {
              "amount_usd": 0.002,
              "authorizer": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
              "block_number": 51981171,
              "chain": "base",
              "confirmations": 2,
              "fee_units": "0",
              "nonce": "0x7fe9ed564701050ec2e2633ba60421946eecef2205292c4f8d667e741ac709d0",
              "paid_units": "2000",
              "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
              "token": "USDC",
              "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
              "verified_at": 1790751691.358382
            },
            "started_at": 1790751691.358526,
            "finished_at": 1790751693.5381346,
            "price_usd": 0.002
          }
        ],
        "created_at": 1790751593.7525403,
        "completed_at": 1790751693.53815,
        "job_id": "job_db9c841f8a360f04c891a68b",
        "signature": {
          "algorithm": "ed25519",
          "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
          "value": "wvBu5M7Yfz0zCMg0jg0c/Eyxa5Vdpx8MVPuoyQaDv6WMcVR6l/MWjQgXHfjRhFmmtM78awfMUxX8G24jma6kDQ==",
          "pq_algorithm": "ml-dsa-65",
          "pq_public_key": "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",
          "pq_value": "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"
        }
      },
      "next_step": null,
      "final_result": {
        "agreement": {
          "agree": true,
          "location_km": 0.0,
          "max_km": 75.0,
          "max_time_apart_s": 7200,
          "reasons": [],
          "time_apart_s": 0
        },
        "air": {
          "attestation": {
            "algorithm": "ed25519",
            "canonical": "device|model|seq|ts|values_sha256",
            "public_key": "k3t0cjTwaxBD9R9DFmx4KbpsPLXX3VEYT4MRLDQeZfI=",
            "value": "Bgmfdy3F5Fmr2zr/dwmeft73N3liNMetH9K8lcyNqE3c01XATspP4BoXZrXmozeM/uUY3al3gohjjVLHxwu6DA=="
          },
          "capability_id": "gaia.air.read@v1",
          "reading": {
            "device_id": "om-aq-01",
            "firmware": "1.0.0",
            "model": "GAIA-AQ1 (Open-Meteo AQ relay)",
            "seq": 184,
            "site": "live-air-eu",
            "ts": "2026-09-30T07:01:32Z",
            "units": {
              "co2_ppm": "ppm",
              "european_aqi": "EAQI",
              "pm10_ugm3": "ug/m3",
              "pm2_5_ugm3": "ug/m3",
              "us_aqi": "US AQI"
            },
            "values": {
              "european_aqi": 22.0,
              "pm10_ugm3": 12.8,
              "pm2_5_ugm3": 9.9,
              "us_aqi": 33.0
            }
          },
          "resolved": {
            "device_id": "om-aq-01",
            "latitude": 52.52,
            "longitude": 13.41,
            "matched_place": "Berlin",
            "requested": "Berlin"
          }
        },
        "children": [
          {
            "capability_id": "gaia.weather.read@v1",
            "funded_by": "own",
            "node": "node_766d429147ff1048f8f0fc11",
            "price_usd": 0.001,
            "receipt_digest": "sha256-7f1Bc8Jub3ekfgB7oc6jcc8cO6AYICd/+CbnJXKd1FY="
          },
          {
            "capability_id": "gaia.air.read@v1",
            "funded_by": "own",
            "node": "node_db5caa18e04cca2e44466d23",
            "price_usd": 0.001,
            "receipt_digest": "sha256-QmdjTl8w0vq4v2UCkSXnvyzGZwD6Sc7Cu1AqRX0o7aY="
          }
        ],
        "funding": "fixed-price",
        "job": {
          "depth": 1,
          "job_id": "job_db9c841f8a360f04c891a68b",
          "node": "node_228186546b7fac0f4d89706a"
        },
        "place": {
          "city": "Berlin"
        },
        "weather": {
          "attestation": {
            "algorithm": "ed25519",
            "canonical": "device|model|seq|ts|values_sha256",
            "public_key": "bdtWcNGNNk2Q6mcblT1OqAdtkncOohceH/G2dlxLDk0=",
            "value": "O7no3SiO0xrS1LohHXoUKncNOim7OKS3zTyJytpi5wEitc+4KSQbfDOArgbkOJ9wybv5j+7QBX+iF2BgbTNWBA=="
          },
          "capability_id": "gaia.weather.read@v1",
          "reading": {
            "device_id": "om-wx-01",
            "firmware": "1.0.0",
            "model": "GAIA-WS1 (Open-Meteo relay)",
            "seq": 231,
            "site": "live-weather-eu",
            "ts": "2026-09-30T07:01:32Z",
            "units": {
              "humidity_pct": "percent",
              "pressure_hpa": "hPa",
              "temperature_c": "cel",
              "wind_mps": "m/s"
            },
            "values": {
              "humidity_pct": 64.0,
              "pressure_hpa": 1020.3,
              "temperature_c": 14.5,
              "wind_mps": 2.82
            }
          },
          "resolved": {
            "device_id": "om-wx-01",
            "distance_km": 0.0,
            "matched_place": "Berlin",
            "relay_latitude": 52.52,
            "relay_longitude": 13.41,
            "requested": "Berlin"
          }
        },
        "witness": "weather-witness/1"
      },
      "detail": "",
      "success": true,
      "price_usd": 0,
      "product_id": "hephaestus",
      "capability_id": "pipeline.run@v1",
      "result": {
        "status": "completed",
        "final_result": {
          "agreement": {
            "agree": true,
            "location_km": 0.0,
            "max_km": 75.0,
            "max_time_apart_s": 7200,
            "reasons": [],
            "time_apart_s": 0
          },
          "air": {
            "attestation": {
              "algorithm": "ed25519",
              "canonical": "device|model|seq|ts|values_sha256",
              "public_key": "k3t0cjTwaxBD9R9DFmx4KbpsPLXX3VEYT4MRLDQeZfI=",
              "value": "Bgmfdy3F5Fmr2zr/dwmeft73N3liNMetH9K8lcyNqE3c01XATspP4BoXZrXmozeM/uUY3al3gohjjVLHxwu6DA=="
            },
            "capability_id": "gaia.air.read@v1",
            "reading": {
              "device_id": "om-aq-01",
              "firmware": "1.0.0",
              "model": "GAIA-AQ1 (Open-Meteo AQ relay)",
              "seq": 184,
              "site": "live-air-eu",
              "ts": "2026-09-30T07:01:32Z",
              "units": {
                "co2_ppm": "ppm",
                "european_aqi": "EAQI",
                "pm10_ugm3": "ug/m3",
                "pm2_5_ugm3": "ug/m3",
                "us_aqi": "US AQI"
              },
              "values": {
                "european_aqi": 22.0,
                "pm10_ugm3": 12.8,
                "pm2_5_ugm3": 9.9,
                "us_aqi": 33.0
              }
            },
            "resolved": {
              "device_id": "om-aq-01",
              "latitude": 52.52,
              "longitude": 13.41,
              "matched_place": "Berlin",
              "requested": "Berlin"
            }
          },
          "children": [
            {
              "capability_id": "gaia.weather.read@v1",
              "funded_by": "own",
              "node": "node_766d429147ff1048f8f0fc11",
              "price_usd": 0.001,
              "receipt_digest": "sha256-7f1Bc8Jub3ekfgB7oc6jcc8cO6AYICd/+CbnJXKd1FY="
            },
            {
              "capability_id": "gaia.air.read@v1",
              "funded_by": "own",
              "node": "node_db5caa18e04cca2e44466d23",
              "price_usd": 0.001,
              "receipt_digest": "sha256-QmdjTl8w0vq4v2UCkSXnvyzGZwD6Sc7Cu1AqRX0o7aY="
            }
          ],
          "funding": "fixed-price",
          "job": {
            "depth": 1,
            "job_id": "job_db9c841f8a360f04c891a68b",
            "node": "node_228186546b7fac0f4d89706a"
          },
          "place": {
            "city": "Berlin"
          },
          "weather": {
            "attestation": {
              "algorithm": "ed25519",
              "canonical": "device|model|seq|ts|values_sha256",
              "public_key": "bdtWcNGNNk2Q6mcblT1OqAdtkncOohceH/G2dlxLDk0=",
              "value": "O7no3SiO0xrS1LohHXoUKncNOim7OKS3zTyJytpi5wEitc+4KSQbfDOArgbkOJ9wybv5j+7QBX+iF2BgbTNWBA=="
            },
            "capability_id": "gaia.weather.read@v1",
            "reading": {
              "device_id": "om-wx-01",
              "firmware": "1.0.0",
              "model": "GAIA-WS1 (Open-Meteo relay)",
              "seq": 231,
              "site": "live-weather-eu",
              "ts": "2026-09-30T07:01:32Z",
              "units": {
                "humidity_pct": "percent",
                "pressure_hpa": "hPa",
                "temperature_c": "cel",
                "wind_mps": "m/s"
              },
              "values": {
                "humidity_pct": 64.0,
                "pressure_hpa": 1020.3,
                "temperature_c": 14.5,
                "wind_mps": 2.82
              }
            },
            "resolved": {
              "device_id": "om-wx-01",
              "distance_km": 0.0,
              "matched_place": "Berlin",
              "relay_latitude": 52.52,
              "relay_longitude": 13.41,
              "requested": "Berlin"
            }
          },
          "witness": "weather-witness/1"
        },
        "bill_of_materials": {
          "trace_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
          "graph_digest": "020dc99f6c776c7eb40a87190b5385800a6d2fe3c534a059972436c81657c282",
          "funding": "buyer_wallet",
          "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
          "status": "completed",
          "budget_usd": 0.002,
          "total_usd": 0.002,
          "remaining_budget_usd": 0.0,
          "payment_unresolved": [],
          "steps": [
            {
              "id": "witness",
              "product_id": "weather-witness",
              "capability_id": "weather.witness@v1",
              "source_hub": "local",
              "status": "succeeded",
              "quoted_usd": 0.002,
              "payment_rail": "seller_direct",
              "terms": {
                "amount_units": "2000",
                "amount_usd": 0.002,
                "chain": "base",
                "chain_id": 8453,
                "decimals": 6,
                "eip712_name": "USD Coin",
                "eip712_version": "2",
                "fee_to": "",
                "fee_units": "0",
                "min_confirmations": 1,
                "offer_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
                "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
                "seller_units": "2000",
                "token": "USDC",
                "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
              },
              "success": true,
              "status_code": 200,
              "receipt": {
                "capability_id": "weather.witness@v1",
                "latency_ms": 1738,
                "list_price_usd": 0.002,
                "nonce": "rcpt_1b670e8c9d8a414658a165fb2aefdf59",
                "price_usd": 0.002,
                "product_id": "weather-witness",
                "signature": {
                  "algorithm": "ed25519",
                  "pq_algorithm": "ml-dsa-65",
                  "pq_public_key": "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",
                  "pq_value": "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",
                  "value": "EgDG7QkWIX4Qe8U+Wvf23dIQVfP7rEfFTZlmdJZ0dPlb3Nb9syBthPIV42BTadQFH8sglyp9S9/ZHBUK5pPjAw=="
                },
                "success": true,
                "timestamp": "2026-09-30T07:01:33Z"
              },
              "job": {
                "depth": 1,
                "funded_by": "own",
                "job_id": "job_db9c841f8a360f04c891a68b",
                "node": "node_228186546b7fac0f4d89706a",
                "parent": "node_ba3a877444eda0486258c30b"
              },
              "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
              "payment": {
                "amount_usd": 0.002,
                "authorizer": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
                "block_number": 51981171,
                "chain": "base",
                "confirmations": 2,
                "fee_units": "0",
                "nonce": "0x7fe9ed564701050ec2e2633ba60421946eecef2205292c4f8d667e741ac709d0",
                "paid_units": "2000",
                "pay_to": "0x1218ff36C5d2e3B6A565CdB1A8B1AcCFc606Ad0a",
                "token": "USDC",
                "tx_hash": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272",
                "verified_at": 1790751691.358382
              },
              "started_at": 1790751691.358526,
              "finished_at": 1790751693.5381346,
              "price_usd": 0.002
            }
          ],
          "created_at": 1790751593.7525403,
          "completed_at": 1790751693.53815,
          "job_id": "job_db9c841f8a360f04c891a68b",
          "signature": {
            "algorithm": "ed25519",
            "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
            "value": "wvBu5M7Yfz0zCMg0jg0c/Eyxa5Vdpx8MVPuoyQaDv6WMcVR6l/MWjQgXHfjRhFmmtM78awfMUxX8G24jma6kDQ==",
            "pq_algorithm": "ml-dsa-65",
            "pq_public_key": "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",
            "pq_value": "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"
          }
        }
      },
      "subcontracting": {
        "job_id": "job_db9c841f8a360f04c891a68b",
        "funding": "buyer_wallet",
        "nodes": [
          {
            "node": "node_ba3a877444eda0486258c30b",
            "parent": "",
            "depth": 0,
            "product_id": "hephaestus",
            "capability_id": "pipeline.run@v1",
            "price_usd": 0.0,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-yKlROh9qyPfcrewL0EbuIbu7PLEh4omMZDqPYz4aNbA=",
            "receipt_id": "urn:aimarket:pipeline:paid_580f85c4a2f4deba7a83bc26140fc558"
          },
          {
            "node": "node_228186546b7fac0f4d89706a",
            "parent": "node_ba3a877444eda0486258c30b",
            "depth": 1,
            "product_id": "weather-witness",
            "capability_id": "weather.witness@v1",
            "price_usd": 0.002,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-ENZqx9XQlAqVW9EIAueoRDiU3CQ/zWmWYUfYcNBVMbY=",
            "receipt_id": "urn:uuid:7120b86c-5142-4b45-9b01-a5c5ecaa795e"
          },
          {
            "node": "node_db5caa18e04cca2e44466d23",
            "parent": "node_228186546b7fac0f4d89706a",
            "depth": 2,
            "product_id": "gaia.gateway",
            "capability_id": "gaia.air.read@v1",
            "price_usd": 0.001,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-QmdjTl8w0vq4v2UCkSXnvyzGZwD6Sc7Cu1AqRX0o7aY=",
            "receipt_id": "urn:uuid:645e7e42-42fa-4e42-91d6-b84cb2344b67"
          },
          {
            "node": "node_766d429147ff1048f8f0fc11",
            "parent": "node_228186546b7fac0f4d89706a",
            "depth": 2,
            "product_id": "gaia.gateway",
            "capability_id": "gaia.weather.read@v1",
            "price_usd": 0.001,
            "funded_by": "own",
            "status": "captured",
            "receipt_digest": "sha256-7f1Bc8Jub3ekfgB7oc6jcc8cO6AYICd/+CbnJXKd1FY=",
            "receipt_id": "urn:uuid:c18abe0c-33aa-4ea7-9a25-97c7f167293f"
          }
        ],
        "budget_usd": 0.002,
        "spent_usd": 0.002,
        "unspent_budget_usd": 0.0
      },
      "protocol_version": "v2",
      "receipt": {
        "kind": "pipeline.run/1",
        "run_id": "paid_580f85c4a2f4deba7a83bc26140fc558",
        "job_id": "job_db9c841f8a360f04c891a68b",
        "product_id": "hephaestus",
        "capability_id": "pipeline.run@v1",
        "graph_digest": "020dc99f6c776c7eb40a87190b5385800a6d2fe3c534a059972436c81657c282",
        "success": true,
        "parents": [
          {
            "id": "urn:uuid:7120b86c-5142-4b45-9b01-a5c5ecaa795e",
            "digestSRI": "sha256-ENZqx9XQlAqVW9EIAueoRDiU3CQ/zWmWYUfYcNBVMbY="
          }
        ],
        "result_digest": "04b959e9264be0c3203b005819cd8ded9e468532e94647122fba0004aa26571a",
        "bill_digest": "7bb9257690299bad9d875484b5f4741c0a39a6a781bab36b647e5d333744fd4e",
        "signature": {
          "algorithm": "ed25519",
          "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
          "value": "rSfbsQKIdwcJccPjytyKVqcvOZ4Lk1pcQWDm5RnuWIyGA/Y3cCmqNs1I/6kGVQQmRwtj6USCIo+LXip0UgMMCQ==",
          "pq_algorithm": "ml-dsa-65",
          "pq_public_key": "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",
          "pq_value": "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"
        }
      }
    },
    "tx_hashes": {
      "witness": "0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272"
    },
    "fee_wei": "500681057186",
    "budget_check": {
      "service_usdc": "0.002",
      "native_fee_bound_wei": "4774506722000",
      "native_usd_ceiling": "3328.5750",
      "native_price": {
        "source": "chainlink_base_eth_usd",
        "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
        "observations": [
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981171,
            "block_timestamp": 1790751689,
            "sequencer_up_since": 1782491507
          },
          {
            "price_usd": "2662.86",
            "round_id": "55340232221128660927",
            "updated_at": 1790751309,
            "block_number": 51981171,
            "block_timestamp": 1790751689,
            "sequencer_up_since": 1782491507
          }
        ],
        "margin_percent": 25,
        "max_age_s": 1500,
        "manual_floor_usd": null,
        "native_usd_ceiling": "3328.5750",
        "checked_at": 1790751690.875712
      },
      "l1_upper_bound_wei": "11745067220",
      "l1_multiplier": 100,
      "extra_reserve_usd": "0.05",
      "conservative_total_usd": "0.0678923037121811500",
      "checked_at": 1790751690.875724
    }
  },
  "account_starting_grant_usd": 0,
  "conservative_cumulative_usd": "0.047149423922618862625",
  "cumulative_limit_usd": "1",
  "accounting_note": "Earlier runs retain their historical 6000 USD/ETH ceiling; new gas is valued at the saved oracle price plus 25%. Entire 0.02 USDC deposit is counted; later prepaid child debits are not counted twice.",
  "provider_account_after": {
    "balance_usd": 0.018,
    "spent_usd": 0.002,
    "granted_usd": 0,
    "topped_up_usd": 0.02,
    "collateral_usd": 0
  }
}
```

### gas-sponsorship-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.11.0",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "sponsor": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
  "run_id": "paid_38c0a7c6c2fe992186116a2822205d3d",
  "job_id": "job_dc0b37b785a7f358bfb30b23",
  "tx_hash": "0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857",
  "service_usdc": ".002",
  "sponsor_fee_wei": "516607663289",
  "buyer_gas_wei": "0",
  "buyer_nonce_unchanged": true,
  "buyer_native_balance_unchanged": true,
  "message_only_signer": true,
  "sdk_rpc_configured": false,
  "controlled_reply_loss": true,
  "cumulative_conservative_usd": "0.1163241752052936711504319125",
  "sponsor_funding_already_counted_in_full": true,
  "budget_limit_usd": "1",
  "calls": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_38c0a7c6c2fe992186116a2822205d3d/pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "funding": {
    "sponsor": "0x663E0C31925EAd877fD9414C2e1862fa50b2650b",
    "payer": "0x6E94c380d908531f9822035d6cc4c8D2B0186C9c",
    "tx_hash": "0x73cff1e1da3242a2f3c77e1f7389fc5ed23f7625634975d7dbef2086bcfcfc78",
    "funding_wei": "20000000000000",
    "funding_fee_wei": "133597605703",
    "budget_check": {
      "service_usdc": "0",
      "native_fee_bound_wei": "6235958489800",
      "native_usd_ceiling": "3336.4504743875",
      "native_price": {
        "source": "chainlink_base_eth_usd",
        "feed": "0x71041dddad3595F9CEd3DcCFBe3D1F4b0a16Bb70",
        "sequencer_feed": "0xBCF85224fc0756B9Fa45aA7892530B47e10b6433",
        "observations": [
          {
            "price_usd": "2669.16037951",
            "round_id": "55340232221128660934",
            "updated_at": 1790756921,
            "block_number": 51983794,
            "block_timestamp": 1790756935,
            "sequencer_up_since": 1782491507
          },
          {
            "price_usd": "2669.16037951",
            "round_id": "55340232221128660934",
            "updated_at": 1790756921,
            "block_number": 51983794,
            "block_timestamp": 1790756935,
            "sequencer_up_since": 1782491507
          }
        ],
        "margin_percent": 25,
        "max_age_s": 1500,
        "manual_floor_usd": null,
        "native_usd_ceiling": "3336.4504743875",
        "checked_at": 1790756935.732915
      },
      "l1_upper_bound_wei": "26359584898",
      "l1_multiplier": 100,
      "extra_reserve_usd": "0.05",
      "conservative_total_usd": "0.07080596666155396807999750",
      "checked_at": 1790756935.7329228
    },
    "prior_total_usd": "0.047149423922618862625",
    "cumulative_conservative_usd": "0.1143241752052936711504319125",
    "budget_limit_usd": "1",
    "funding_counted_in_full": true
  },
  "local_validation": {
    "focused_regression_passed": 178,
    "mcp_after_static_card_sync_passed": 81,
    "oracle_and_relay_passed": 37,
    "anvil_zero_eth_buyer_passed": 1
  },
  "final_result": {
    "block_number": 51983924,
    "chain": "base",
    "chain_id": 8453,
    "findings": [],
    "score": 100,
    "summary": "Base mainnet is reachable through KOVA.",
    "verdict": "pass"
  },
  "signed_result_verified": true,
  "steps": [
    {
      "id": "summary",
      "product_id": "prod-logos",
      "capability_id": "logos.federation.summary@v1",
      "source_hub": "https://logos.modelmarket.dev",
      "status": "succeeded",
      "price_usd": 0.0
    },
    {
      "id": "network",
      "product_id": "kova-network",
      "capability_id": "kova.network.status@v1",
      "source_hub": "https://independentai.network/hub",
      "status": "succeeded",
      "price_usd": 0.002,
      "tx_hash": "0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857"
    }
  ]
}
```

### provider-recovery-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.12.0",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "sponsor": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
  "run_id": "paid_7f29b95f0ebf51092a52883053172f93",
  "job_id": "job_4ca838ba5866031111ed1778",
  "tx_hash": "0x633c83fcdf9dc2a086a218597068503df4165a230141f69e64fa0209d130e758",
  "service_usdc": ".002",
  "sponsor_fee_wei": "516795861906",
  "buyer_gas_wei": "0",
  "buyer_nonce_unchanged": true,
  "buyer_native_balance_unchanged": true,
  "message_only_signer": true,
  "sdk_rpc_configured": false,
  "controlled_reply_loss": true,
  "cumulative_conservative_usd": "0.1183241752052936711504319125",
  "sponsor_funding_already_counted_in_full": true,
  "budget_limit_usd": "1",
  "calls": [
    {
      "method": "POST",
      "path": "/studio/prepare-pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    },
    {
      "method": "GET",
      "path": "/studio/paid-runs/paid_7f29b95f0ebf51092a52883053172f93/pipeline"
    },
    {
      "method": "POST",
      "path": "/ai-market/v2/invoke"
    }
  ],
  "final_result": {
    "block_number": 51984647,
    "chain": "base",
    "chain_id": 8453,
    "findings": [],
    "score": 100,
    "summary": "Base mainnet is reachable through KOVA.",
    "verdict": "pass"
  },
  "signed_result_verified": true,
  "recovery_proof": {
    "operation_id": "op_1b8b1cdfe08a509dc0bd6115b2a657d5",
    "isolated_copy_recovered": true,
    "production_ledgers_modified": false,
    "new_payments": 0,
    "new_provider_invokes": 0,
    "status_reads": [
      {
        "method": "GET",
        "operation_id": "op_1b8b1cdfe08a509dc0bd6115b2a657d5"
      }
    ],
    "provider_result": {
      "capability_id": "kova.network.status@v1",
      "input_sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a",
      "operation_id": "op_1b8b1cdfe08a509dc0bd6115b2a657d5",
      "product_id": "kova-network",
      "protocol": "PROVIDER-OP/1",
      "result": {
        "block_number": 51984647,
        "chain": "base",
        "chain_id": 8453,
        "findings": [],
        "score": 100,
        "summary": "Base mainnet is reachable through KOVA.",
        "verdict": "pass"
      },
      "result_signature": "SDpaLWz7Xvwpa4jVM515EFOVv3rtqUUH8skEbfXBShKDEQ8vuvgy6rraGxFNXJr9eOZevFArDr7Z3Hxk36BECQ==",
      "signature": "4i9lfCn+KRuVi2NUW49E2DsnziK2nbFivGD+Ciex8VwFkBVZUFDXVedYIvgCSoU2H4ZaVhf7Rp7WLflOsl1lCA==",
      "status": "completed"
    }
  },
  "scope": "Live provider journal after restart; lost seller response simulated in an isolated database copy. Production ledgers were not altered.",
  "provider_gateway_authenticated": true,
  "local_validation": {
    "recovery_payment_and_peer_tests": 76,
    "recovery_and_pipeline_tests": 36,
    "kova_operations_and_api_tests": 22,
    "kova_bound_signature_followup_tests": 9
  }
}
```

### refund-mainnet-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.13.0",
  "wallet": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
  "seller": "0xd41bdb11ae589b7b11c1daca1f7b6ae408f0bb20",
  "operator_owned_fixture": true,
  "run_id": "paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc",
  "job_id": "job_da32d04e2b39e575684e9d50",
  "refund_id": "refund_95331477f4fb1e81b122b51b63857f0e",
  "service_usdc": ".001",
  "refunded_usdc": ".001",
  "buyer_gas_wei": "0",
  "transactions": [
    {
      "tx_hash": "0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58",
      "gas_payer": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
      "fee_wei": "620782210434"
    },
    {
      "tx_hash": "0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf",
      "gas_payer": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
      "fee_wei": "487781767367"
    }
  ],
  "buyer_nonce_unchanged": true,
  "buyer_native_balance_unchanged": true,
  "buyer_usdc_balance_restored": true,
  "seller_usdc_balance_restored": true,
  "controlled_refund_reply_loss": true,
  "original_bill_unchanged": true,
  "same_refund_retry": true,
  "credit_note": {
    "amount_units": "1000",
    "amount_usdc": "0.001",
    "buyer_gas_fee_units": "0",
    "chain_id": 8453,
    "from": "0xd41bdb11ae589b7b11c1daca1f7b6ae408f0bb20",
    "gas_payer": "0x663e0c31925ead877fd9414c2e1862fa50b2650b",
    "kind": "pipeline.refund/1",
    "original_tx_hash": "0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58",
    "refund_id": "refund_95331477f4fb1e81b122b51b63857f0e",
    "refund_tx_hash": "0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf",
    "run_id": "paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc",
    "signature": {
      "algorithm": "ed25519",
      "pq_algorithm": "ml-dsa-65",
      "pq_public_key": "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",
      "pq_value": "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",
      "public_key": "lUgnD6FKzGU0gMaTVjtKzUbtIKd/aRqI3Kzn12vQio0=",
      "value": "uCRKNXnCxZpCl+4d2SitFnEX6PjvYdqq3trKwowCGjPDm7QPKT2SzWzSJJgJ81FI9fekrgy9ti+HIuhSxGcrDA=="
    },
    "step_id": "proof",
    "to": "0x6e94c380d908531f9822035d6cc4c8d2b0186c9c",
    "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
  },
  "final_result": {
    "operator_owned_fixture": true,
    "refund_test": "2026-09-30",
    "result": "delivered"
  },
  "cumulative_conservative_usd": "0.1193241752052936711504319125",
  "gross_purchase_counted_despite_refund": true,
  "sponsor_funding_already_counted_in_full": true,
  "budget_limit_usd": "1",
  "same_refund_after_hub_restart": true,
  "original_result_after_hub_restart": true,
  "temporary_listing_removed": true
}
```

### ethereum-profile-2026-09-30.json

```json
{
  "date": "2026-09-30",
  "version": "3.14.0",
  "chain_id": 1,
  "token_contract": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
  "token_metadata": {
    "name": "USD Coin",
    "version": "2",
    "decimals": 6
  },
  "native_price": {
    "source": "chainlink_ethereum_eth_usd",
    "feed": "0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419",
    "sequencer_feed": null,
    "observations": [
      {
        "price_usd": "2683.51528449",
        "round_id": "129127208515966895503",
        "updated_at": 1790760323,
        "block_number": 26089454,
        "block_timestamp": 1790761163,
        "sequencer_up_since": null
      },
      {
        "price_usd": "2683.51528449",
        "round_id": "129127208515966895503",
        "updated_at": 1790760323,
        "block_number": 26089454,
        "block_timestamp": 1790761163,
        "sequencer_up_since": null
      }
    ],
    "margin_percent": 25,
    "max_age_s": 3900,
    "manual_floor_usd": null,
    "native_usd_ceiling": "3354.3941056125",
    "checked_at": 1790761170.358094
  },
  "read_only": true,
  "new_mainnet_transactions": 0,
  "sources": [
    "https://developers.circle.com/stablecoins/usdc-contract-addresses",
    "https://data.chain.link/feeds/ethereum/mainnet/eth-usd",
    "https://reference-data-directory.vercel.app/feeds-mainnet.json"
  ]
}
```
