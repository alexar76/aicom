# 使用 n8n 和自己的 Hub 检查购物清单

[English](n8n-workshop.md) · [Русский](n8n-workshop.ru.md) · [Español](n8n-workshop.es.md) · [Français](n8n-workshop.fr.md) · [中文](n8n-workshop.zh.md)

这是面向 n8n 集成开发者和小型 API 运营者的 60 分钟在线实践课。我们构建一个只读服务，回答：
**“这个供应商能否满足我的购物清单？商品小计是多少？”** 工作流和目录由运营者控制。
本地练习不需要购买商品、钱包、付费 LLM 或外部客户。

## 为什么选择这个场景

商店助手、销售助手和采购智能体可以调用同一个服务，使用供应商自己的库存与价格规则。
n8n 执行规则，Hub 展示服务并验证签名响应。n8n 已提供[原生 MCP](https://n8n.io/mcp/)，
如果只是让自己的智能体调用自己的工作流，原生功能可能已经足够。本课程进一步介绍独立运营的
服务目录、提供方签名，以及后续选择加入联邦的途径。

示例库存是**合成数据**，用于演示集成，不代表真实库存、商业需求或生产部署。
Hub 软件可免费运行，运营者承担托管成本，n8n 有自己的许可条款。联邦只是潜在的分发渠道。

## 示例与预期结果

[可导入的工作流](../examples/n8n-order-check/workflow.json) ·
[代码和运行细节](../examples/n8n-order-check/README.md) ·
[验证记录](../examples/n8n-order-check/VALIDATION.md)

```json
{"items":[{"sku":"BEANS-250","quantity":2},{"sku":"MUG-BLUE","quantity":1}]}
```

预期返回 `status: ready`、`can_fulfill: true`、`subtotal_minor: 3430` 和 `currency: USD`。
这表示商品小计为 34.30 美元。税费、运费和应付总额为 `null`，含义是尚未计算，而不是零。
响应包含 `demo: true`、`reservation_created: false` 和 `order_created: false`。

| 请求 | 预期行为 |
|---|---|
| 两件 BEANS-250 和一件 MUG-BLUE | 可以满足；商品小计 3430 |
| 四件 MUG-BLUE | 库存不足；只有三件 |
| 未知 SKU | 未知商品；不计算整单商品小计 |
| 两行各两件 MUG-BLUE | 先合并为四件，再判断库存不足 |
| 空清单、负数或非整数数量 | 拒绝输入 |
| 错误的 webhook 凭据或 n8n 不可用 | 拒绝或失败，不编造报价 |

`evaluated_at` 是执行时间，不是库存的新鲜度。签名确认声明来自提供方并与请求绑定，
不能证明仓库中确实存在这些商品。

## 课前准备

使用独立的本地实例、Python 3.11+、Node.js 24.14.0，确保 15678/13456/19083 端口可用。
在本仓库克隆的根目录执行：

```bash
python3 -m venv examples/n8n-order-check/.venv
examples/n8n-order-check/.venv/bin/python -m pip install -e './aimarket-hub[pqc]'
cd examples/n8n-order-check
source .venv/bin/activate
npm install --prefix .runtime/npm n8n@2.43.7 --no-audit --no-fund
export PATH="$PWD/.runtime/npm/node_modules/.bin:$PATH"
python run.py init
python run.py n8n-import
```

安装不计入课程的 60 分钟。密钥和随机凭据保存在 `.runtime/`，该目录不进入 Git，请勿分享。
工作流使用 Header Auth 凭据，不内嵌令牌。重新导入前应停止本课程的 n8n 实例。

在三个终端中进入示例目录并分别激活 `.venv`，依次运行：`python run.py n8n`、
`python run.py adapter`、`python run.py hub`。在 n8n 终端重复上述 PATH 设置。
编辑器地址为 `http://127.0.0.1:15678`；如有提示，请创建本地所有者账户。
导入步骤会发布工作流，适配器使用 `/webhook/` 路径。按 Ctrl+C 停止服务，本地状态会保留。

## 60 分钟课程安排

| 分钟 | 内容 |
|---|---|
| 0–5 | 明确运营者、调用方、只读结果和合成数据 |
| 5–15 | Webhook → Code → Respond to Webhook；进行带认证的调用 |
| 15–25 | 输入模式、重复 SKU 合并、库存和价格规则 |
| 25–40 | 启动适配器与 Hub；调用服务并查看结果和签名 |
| 40–50 | 测试缺货、未知商品、无效数量和错误凭据 |
| 50–60 | 讨论接入一个获授权的数据源；答疑 |

执行测试前，请等待 n8n 提示编辑器已就绪且工作流索引已完成。

```bash
curl --fail-with-body http://127.0.0.1:19083/ai-market/v2/invoke \
  -H 'Content-Type: application/json' --data-binary @request.json
python run.py check
node test_quote.cjs
```

本地 MCP 客户端地址：`http://127.0.0.1:19083/mcp`。提示词示例：
“找到课程中的购物清单检查工具。检查两件 BEANS-250 和一件 MUG-BLUE。报告商品小计和缺货情况，
说明数据是合成的，不要下单。” 仅在云端运行的客户端无法访问笔记本的回环地址。
HTTP/MCP 协议测试本身不等于在每个智能体应用中完成验证。

## 接入首位真实运营者

获取脱敏的目录响应样例和所有者授权的数据源。将合成数据阶段替换为只读数据访问，映射币种、
最小货币单位价格、可用库存和来源观测时间，并设定最大数据时效。同步更新适配器中仅支持演示
数据的响应契约及测试。库存检查与预留、下单应分别实现。私有价格或客户专属价格需要调用方
授权和客户隔离，本示例不提供这些功能。

公开部署需要持久化的 Hub 密钥与数据库、HTTPS 和请求限流；n8n 与适配器应处于私有网络并要求认证。
不要将实验中的 HTTP 设置直接用于公网。按照[运营者指南](https://github.com/alexar76/aimarket-hub/blob/main/docs/operator-quickstart.zh.md)
运行 `aimarket doctor`，然后自行决定是否 announce。本地测试通过并不代表联邦已准入。

成功标准：独立所有者控制部署和密钥，能重复执行有用的调用，并知道如何停止服务。
分别记录本地练习、真实数据接入、联邦准入和七天后的使用情况，不要求发生外部销售。
