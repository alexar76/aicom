# 每周研究流程 合成示例

分析已保存的定义，以及工作流程需要进行的复测。

| 依赖 | 结果 | 需要检查的流程 |
|---|---|---|
| demo:research | 观测到变化 | 2 |
| demo:migration | 观测条件发生变化 | 1 |
| demo:offline | 数据不足 | 1 |

## demo:research

**观测到变化**

- 之前：2026\-10\-26T09:00:00Z；软件包版本 1\.0\.0；服务器版本 1\.0\.0；协议 2025\-06\-18。
- 之后：2026\-10\-27T09:00:00Z；软件包版本 1\.1\.0；服务器版本 1\.1\.0；协议 2025\-06\-18。


### 读取归档文档

需要复测。

- [ ] legacy\_fetch: 检查替代工具或固定旧版软件包；先审查流程，再执行。

### 准备每周文档综述

需要复测。

- [ ] export\_brief: 检查操作确认、权限和声明的价格；annotations 仅是服务器的声明。
- [ ] search\_docs: 阅读变更后的说明；重放常用请求并检查工具选择。
- [ ] search\_docs: 检查已保存的输入、必填字段和类型，并添加边界用例。
- [ ] search\_docs: 重放结果处理过程，检查流程读取的字段和类型。

### 所选工具的变化

**export\_brief: 已变更**

- destructiveHint: false → true。 这是服务器的声明。
- readOnlyHint: true → false。 这是服务器的声明。

**legacy\_fetch: 已移除**


**search\_docs: 已变更**

- 新增必填字段: workspace
- type 变化: $/properties/limit, $/properties/workspace
- inputSchema: $\.&quot;properties&quot;\.&quot;limit&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;workspace&quot;\.&quot;type&quot;, $\.&quot;required&quot;\[1\]
- outputSchema: $\.&quot;properties&quot;\.&quot;items&quot;\.&quot;type&quot;, $\.&quot;properties&quot;\.&quot;results&quot;\.&quot;type&quot;
- 移除描述: “using”
- 新增描述: “in”
- 移除描述: “query\.”
- 新增描述: “selected workspace\. Include source links in the result\.”

供模型读取的 JSON 的 UTF-8 大小：完整列表 534 → 627 字节；所选工具 534 → 451 字节。
这些数值不是 token 数，也不代表实际节省。

## demo:migration

**观测条件发生变化**

- 之前：2026\-10\-26T09:00:00Z；软件包版本 不适用；服务器版本 1；协议 2025\-06\-18。
- 之后：2026\-10\-27T09:00:00Z；软件包版本 不适用；服务器版本 2；协议 2026\-07\-28。

- 条件变化：protocol；不能仅将差异归因于软件包升级。

### 检查 MCP 迁移后的服务状态

需要可比的观测。

- [ ] 核对 protocol、launcher 和访问条件；在相同上下文中重新获取两份快照。

### 所选工具的变化

所选定义中未发现变化。

供模型读取的 JSON 的 UTF-8 大小：完整列表 94 → 94 字节；所选工具 94 → 94 字节。
这些数值不是 token 数，也不代表实际节省。

## demo:offline

**数据不足**

- 之前：2026\-10\-26T09:00:00Z；软件包版本 不适用；服务器版本 1；协议 2025\-06\-18。
- 之后：2026\-10\-27T09:00:00Z；软件包版本 不适用；服务器版本 未知；协议 未知。
没有成功获取的定义对；未比较工具字段。

- 限制: 缺少升级后完整且成功的观测。

### 获取外部服务的每日状态

需要可比的观测。

- [ ] 核对 protocol、launcher 和访问条件；在相同上下文中重新获取两份快照。
- [ ] read\_status: 在可比环境中取得两次完整且成功的观测。

### 所选工具的变化

**read\_status: 数据不足**


## 分析范围限制

- 仅比较观测到的定义，不验证服务器的运行时行为。
- 变化不能证明出现故障；定义不变也不能证明安全。
- 流程仅通过明确选择的工具关联，不进行语义分析。
- 紧凑 JSON 的 UTF\-8 大小以字节计量，不是 token 数、金额或实际节省。
- launch 仅显示哈希；不执行启动条件，也不展示环境中的秘密值。

[完整数据、版本和输入文件 SHA-256 哈希](report.json)。
