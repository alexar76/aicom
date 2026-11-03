# 一次客户端调用完成钱包付款流水线

[English](one-call-pipelines.md) · [Русский](one-call-pipelines.ru.md) · [Español](one-call-pipelines.es.md) · [Français](one-call-pipelines.fr.md) · [中文](one-call-pipelines.zh.md)

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

[Codex：一次客户端操作，两个付费分包任务](case-study-codex-one-call.zh.md) — 2026-09-30.

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

[Base transaction](https://basescan.org/tx/0x0d3f6ab3c20ea6c719a7bf8127583d6e3a14ddd48220e961834772cb852e8919) · [Evidence](evidence/independent-seller-mainnet-2026-09-30.json) · [Oracle RPC evidence — SDK 3.10.2](evidence/native-price-oracle-2026-09-30.json).


2026-09-30 生产环境预付费提供商测试：`weather.witness@v1` 已发布真实收款地址并启用固定价格模式。提供商的独立账户从零开始，没有赠款或抵押额度，通过 EIP-3009 实际充值 0.02 USDC；买方随后支付 0.002 USDC 购买根 SKU。提供商从这笔真实预付余额中分别支付 0.001 购买 GAIA 天气和空气数据，剩余 0.018。这是实际充值后的内部预付记账，不是另两笔链上子转账，也不是信用额度。提供商每日上限为 0.02，不自动充值。柏林结果为 agreement=true、14.5°C、湿度 64%、PM2.5 9.9 µg/m³、US AQI 33，采样时间为 2026-09-30T07:01:32Z。运行 `paid_580f85c4a2f4deba7a83bc26140fc558` 对应 job `job_db9c841f8a360f04c891a68b`，保留两个子收据摘要。RPC 在本地签名后返回 HTTP 429，阻止提交；恢复已保存签名包后完成同一订单。充值和购买均使用实时预言机预算检查。保守累计测试费用为 $0.047149423922618862625，低于 $1 上限；已计入全部充值，不重复计算预付余额中的子扣款。

[Evidence](evidence/witness-prepaid-mainnet-2026-09-30.json) · [Deposit](https://basescan.org/tx/0x072a83955ef9c6c7211beb22f6929ca12a82a55c6d84e6709d26aa0a85795b8e) · [Root payment](https://basescan.org/tx/0xeba985a89e95ed7f637ca832c6bba3ed109cf731982272f749970c622590b272).


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

[Base transaction](https://basescan.org/tx/0x8e4d3edbec6ab97e4c9bc7a6931b17582f9a29485b9e0b363d37d4fb2b08f857) · [Evidence](evidence/gas-sponsorship-mainnet-2026-09-30.json)

## 供应商结果恢复 — SDK/Hub 3.12.0

`PROVIDER-OP/1` 处理供应商已经完成工作、但卖方 Hub 未收到响应的情况。兼容供应商在执行前记录操作 ID 以及产品、capability、输入的摘要，并在返回前持久化结果与签名。重复相同操作返回已保存结果；更改输入会被拒绝。并发请求不会重复执行。KOVA 在现有 SQLite 数据库中保存该日志。

卖方明确启用兼容产品：`AIMARKET_PROVIDER_OPERATION_PRODUCTS=kova-network`。新的签名 `SELLER-OP/1` 报价声明 `provider_recovery: PROVIDER-OP/1`；原始供应商 URL 和公钥固定在私密操作状态中。响应丢失或执行声明过期后，卖方读取 `GET <invoke_url>/operations/<operation_id>`，验证签名、操作 ID、产品、capability、精确输入摘要及独立的结果签名。恢复付费工作还要求已保存原付款验证。最终卖方响应不可更改，即使旧工作进程随后返回。恢复不会向供应商发出第二次 POST，也不创建新付款。

KOVA 的 invoke 与 status 接口均要求私密服务间令牌：`AIMARKET_CAPABILITY_TOKEN` 和 `KOVA_CAPABILITY_TOKEN` 必须一致；`AIMARKET_INVOKE_HOST_GATEWAY` 只允许运营方供应商的主机。公有证据不包含密钥或令牌。买方仍通过 Hub 的支付和授权检查。

这是需要供应商配合的恢复机制，并非对任意外部副作用承诺“恰好一次”。如果供应商在产生外部效果后、保存结果前崩溃，结果仍属未知，不自动重做。供应商必须将业务事务绑定到操作 ID，或先核实效果再记录结果。旧供应商仍需要人工核对；KOVA 的不确定记录阻止重复写入。

已付款发票可在过期后恢复，但已验证的区块时间必须严格早于有效期。过期后付款仍被拒绝，nonce 仍只能使用一次。逗号分隔的显式 RPC 现在正确形成独占列表。公开账单移除了内部 job grant 字段。测试覆盖重启、并发、修改输入、身份验证、篡改签名、双 Hub 无重复付款恢复、未知副作用以及发票有效期边界。

2026-09-30 生产验证：LOGOS → KOVA 花费 0.002 USDC，买方 Gas 为零。重启 KOVA 后，通过 GET 从持久日志恢复签名结果。响应丢失在卖方操作的隔离副本中模拟，没有修改生产账本，也没有新供应商调用或付款。恢复结果保留原 Base 区块 51984647。无令牌访问 status 返回 401，带授权查询不存在的操作返回 404。保守累计支出为 $0.1183241752052936711504319125 / $1。退款以及更多网络/代币仍是后续阶段。

`run_id: paid_7f29b95f0ebf51092a52883053172f93` · `job_id: job_4ca838ba5866031111ed1778`

[Base transaction](https://basescan.org/tx/0x633c83fcdf9dc2a086a218597068503df4165a230141f69e64fa0209d130e758) · [Evidence](evidence/provider-recovery-mainnet-2026-09-30.json)


## 卖家批准的退款 — SDK/Hub 3.13.0

`SELLER-REFUND/1` 可退回已确认的 Base USDC 直接付款。买家为已结束流水线中的步骤申请退款报价，原卖家在本地签署 EIP-3009 授权，赞助者支付网络 gas。双方均不向 Hub 提交私钥，也不需要持有 ETH 才能走此路径。准备报价不会转账，也不强制卖家同意退款。

HTTP 使用原 `X-Studio-Run-Token`：`POST /studio/paid-runs/{run_id}/refunds/{step_id}/prepare` 创建或读取签名报价；`POST /studio/paid-runs/{run_id}/refunds/{step_id}` 接收 `{"authorization":"0x…"}` 并推进同一退款；该路径的 `GET` 只读状态。HTTP 202 表示等待中。MCP 提供 `pipeline_refund_prepare`、`pipeline_refund`、`pipeline_refund_status`，参数为相同的 run ID、受限访问令牌和 step ID。只提交卖家签名，绝不提交钱包私钥。

SDK `refund_pipeline(state_path=..., step_id=...)` 仅返回报价，不转账。只把其中的 `offer` 对象交给卖家，不要分享买家的私有恢复文件。卖家通过 `aimarket_hub.refund_client` 调用 `sign_refund_offer(offer, seller_signer=..., buyer_wallet=..., original_tx_hash=..., max_usdc=..., trusted_hub_key=..., trusted_hub_pq_key=...)`。该方法在本地核验获批收款人、原付款、金额上限、代币、网络及 Hub 签名。买家用 `refund_pipeline(..., authorization=signature)` 提交返回的签名。再次使用同一私有文件会恢复同一退款；`RefundPending` 保留其身份。是否应退款由卖家应用在签名前决定。

Hub 仅允许原卖家向原买家退回已核验付款的完整准确金额。流水线必须为 completed 或 failed；供应商执行结果未知时必须先对账。已提交签名不可更改。交易字节在广播前持久化，并使用赞助者共享数据库中的 nonce 和预算协调器。回复丢失或重启后复用同一交易。授权过期后，只有 Hub 尚未签署交易时才能续期，退款 ID 和授权 nonce 保持不变，防止新旧授权执行两次转账。

原签名账单和结果保持不变。独立签名的 `pipeline.refund/1` 贷项凭证关联原付款与退款交易哈希、金额、代币、网络、双方和 gas 付款人。查询状态不转账。首版支持每笔无拆分手续费的 Base USDC 直接付款进行一次全额退款，并要求赞助者可用。尚不支持部分退款、MarketSplitter 费用退还、强制扣款或任意代币。卖家可能拒绝或余额不足；赞助者额度不足时同一退款保持等待。已经消耗的 gas 不退还。免费流水线仍无需支付来源。

测试涵盖错误签名者、金额篡改、并发状态保护、授权过期、已保存交易不可变、回复丢失、SDK/MCP，以及买卖双方无 ETH 时在 Anvil 完成购买和退款。完成后的主网验证将另行记录。


主网验证，2026-09-30：运营方临时静态 SKU 以 0.001 USDC 交付结果，其独立卖家钱包随后批准全额退回。这是实际结算与退款机制测试，不代表独立商业卖家。买卖双方 USDC 余额均恢复初始值，买家的 ETH 和 nonce 未变，两笔交易的 gas 均由赞助者支付。故意丢弃退款回复后恢复了同一贷项凭证；重启 Hub 后，原结果与退款的完整 JSON 值仍完全相同。临时商品已删除。保守累计支出为 $0.1193241752052936711504319125，低于 $1 限额，包含赞助者的全部充值和退款前的购买总额。没有部署新合约。

`run_id: paid_3c4ef00ca1b5f6eea9ec8b1c7aa9d1dc` · `refund_id: refund_95331477f4fb1e81b122b51b63857f0e`

[Purchase / Покупка / Compra / Achat / 购买](https://basescan.org/tx/0x21d72df0e40f843051fc1fcbd5ed01d80fe4bfe36974524254555a06229d4a58) · [Refund / Возврат / Reembolso / Remboursement / 退款](https://basescan.org/tx/0xd84c0cfb1a944df8e9344253872ffd397af2ca04a15eae14bef811a6b38b9dbf) · [Evidence](evidence/refund-mainnet-2026-09-30.json)


## 更多支付配置与多台客户端 — SDK/Hub 3.14.0

SDK 现在接受 **Base 8453 和 Ethereum 1** 上的原生 USDC，固定合约地址、6 位小数以及 EIP-712 `USD Coin` / `2`。一个付费图仍只使用一条链和一种资产；混合图应拆分为不同订单。Hub 必须提供对应路径：SDK 支持某网络并不会跨链搬运余额，也不会改变卖家报价币种。免费图不变。gas 赞助和卖家批准退款目前仍限于 Base USDC 直接付款；Ethereum 的 gas 由买家支付。`gas_mode="required"` 会在签名前拒绝无赞助者的付费路径。

`accepted_assets=[...]` 替换默认白名单。每项明确指定 `chain_id`、`token_contract`、`decimals`、`eip712_name`、`eip712_version`、`usd_pegged: true` 和 `authorization: "EIP-3009"`。这是买家对已审查美元代币的政策，不证明任意 ERC-20 都具备这些属性；Hub 无权扩充。金额采用十进制计算。非美元资产、仅支持 approve 的普通 ERC-20、其他链及原子跨链图会被拒绝，不会暗中兑换。CLI：`--accepted-assets approved-assets.json`。恢复文件固定此政策，resume 不可更改。

本地 Ethereum 卖家配置 `AIMARKET_X402_CHAIN=ethereum`。广播和核验使用已签名 chain ID；`AIMARKET_SETTLE_RPC_1`、`AIMARKET_SETTLE_RPC_8453` 分别指定节点。全局 `AIMARKET_SETTLE_RPC_URL` 仍是排他的后备列表，不能用仅 Base 的节点服务 Ethereum。核验 receipt 或广播之前，RPC 必须报告账单指定网络。自定义 Hub 资产还需正确配置地址、符号、小数位、`AIMARKET_X402_EIP712_NAME` 和 `AIMARKET_X402_EIP712_VERSION`，并与买家白名单一致。不可将非美元代币按美元计价。

Ethereum 通过两个不同 RPC 主机读取最新 ETH/USD，采用 25% 价格余量、gas 上限及 $0.05 储备，不计入 Base L1 附加费。固定 Chainlink feed 为 `0x5f4eC3Df9cbd43714FE2740f5E3616155c5b8419`，8 位小数，heartbeat 3600 秒，最大允许年龄 3900 秒。Base 保留 sequencer 检查及单独 L1 储备。错误网络、过旧区块或价格、超过 2% 的差异均停止付款。手动价格只能提高上限。

多台机器上的代理应安装 `postgres` extra，在创建订单前设置同一个**买家自有** `AIMARKET_WALLET_DATABASE_URL`。使用直连或 session pooling；PgBouncer transaction pooling 无法保留会话 advisory locks。协调器跨连接串行化每个 `(chain_id, wallet)`，在提交前保存私有恢复状态、Hub 受限令牌和确切签名交易字节，绝不保存钱包私钥。数据库只应开放给合作的买家代理。DSN 不写入订单，也不发给 Hub。

将私有恢复文件安全复制到下一台机器，并调用 `run_pipeline(resume=True, state_path=...)`。签名前的旧副本会从 PostgreSQL 获取已保存交易；已完成订单会在任何新签名前读取结果。其他订单不能抢占未完成保留。终态失败后，只有所有签名 nonce 已消耗，或授权过期且不存在 pending 交易，才能释放。数据库故障会阻止新提交，已完成的本地结果仍可读取。所有客户端必须使用相同数据库和 schema，不要混用独立协调器或其他钱包软件。默认仍为本地文件；gas 获赞助的买家无需 PostgreSQL。

测试使用真实临时 PostgreSQL，覆盖独立连接、客户端崩溃、旧副本和保存失败。chain ID 1 的本地 EVM 通过 SDK 执行了真实 EIP-3009 购买；oracle 因本地无 Chainlink 而单独测试。Ethereum 主网仅做只读检查：两个价格观测一致，USDC 的 name/version/decimals 与配置匹配。不声称完成 Ethereum 主网购买，没有新增支出。

[Circle 合约表](https://developers.circle.com/stablecoins/usdc-contract-addresses) · [Ethereum ETH/USD](https://data.chain.link/feeds/ethereum/mainnet/eth-usd) · [只读验证](evidence/ethereum-profile-2026-09-30.json)

版本交付：Hub 与可下载 wheel 为 3.14.0。2026-09-30 检查 PyPI 仍为 `aimarket-hub==3.10.3` 和 `aimarket-agent==2.4.0`。待发布产物是 `aimarket-hub==3.14.0` 以及独立供应商 SDK `aimarket-agent==2.5.0`。当前环境没有发布凭据，上传 PyPI 仍需运营方完成。下方固定 Hub wheel 已可安装。无需重新部署已有合约。

```bash
pip install "aimarket-hub[client,postgres] @ https://modelmarket.dev/clients/aimarket_hub-3.14.0-py3-none-any.whl"
# Optional: buyer-owned PostgreSQL, same database/schema on every client host.
export AIMARKET_WALLET_DATABASE_URL='postgresql://<buyer-user>:<password>@<buyer-db>/<database>'
aimarket-pipeline --resume --state pipeline-run.private.json
```
