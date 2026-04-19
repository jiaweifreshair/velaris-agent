# Phase 1 需求澄清问题

> 说明：该问题文件已被 2026-04-18 的用户明确指令部分覆盖。
> 用户最新口径为：`Velaris` 是整体架构主体，`OpenHarness` 只是 Harness 执行基座，并要求基于逆向工程信息继续执行。
> 因此本文件不再阻塞工作流推进，保留为审计留痕。

当前默认假设如下：

- 本次要执行的是上一轮方案里的 `Phase 1：默认路径收束 / 最小可信闭环`
- 目标是把 `Velaris` 收敛为 `OpenHarness` 之上的“决策执行子运行时”
- 本轮重点不是继续扩场景，而是先收束默认路径下的定位、状态链、完成语义和恢复边界

如果上述假设不准确，请直接在下面的问题中改正。

## Question 1
本次要执行的具体 Phase 是哪一个？

A) Phase 1：默认路径收束 / 最小可信闭环
B) Phase 2：治理与恢复闭环
C) Phase 3：平台化扩展
D) 只做 AI-DLC 文档，不做代码改动
X) Other (please describe after [Answer]: tag below)

[Answer]: A（沿用默认假设：执行 Phase 1）

## Question 2
这一次你希望推进到什么深度？

A) 只完成 Inception 文档（requirements + workflow planning）
B) 完成 Inception 文档，并落一小批“定位/契约/模型”级改动
C) 直接推进到可运行的第一批代码改动与测试验证
D) 先完成 Requirements Analysis，等你审核后再决定是否进入后续阶段
X) Other (please describe after [Answer]: tag below)

[Answer]: B（先完成 Inception，并收敛到可执行的 Construction 计划）

## Question 3
Phase 1 里的“默认权威状态链”你更倾向哪种落法？

A) 默认走本地文件 durable 链，PostgreSQL 继续作为增强路径
B) 配置了 PostgreSQL 就走 PostgreSQL，否则走本地文件 durable 链
C) 本轮只先定义统一契约，不立即统一默认 durable 后端
D) 暂时保持现状，只修定位与接口，不动状态持久化
X) Other (please describe after [Answer]: tag below)

[Answer]: A（默认优先走本地文件 durable 链，PostgreSQL 继续作为增强路径）

## Question 4
Phase 1 是否要求把“业务执行”提升为一等对象（例如 `BizExecution` / `ExecutionRecord` 一类模型）？

A) 是，必须引入一等执行对象
B) 是，但先用轻量包装层，不大改现有编排器
C) 否，先沿用现有 `session/task/outcome` 组合
D) 延后到 Phase 2 再做
X) Other (please describe after [Answer]: tag below)

[Answer]: B（引入轻量一等执行对象/执行契约层，但不在本轮大改现有编排器）

## Question 5
这一轮是否要同步修正文档和对外叙事？

A) 是，README / 设计文档 / AI-DLC 文档都要同步到新定位
B) 只改内部设计文档与 AI-DLC 文档，不动 README
C) 只做代码，不做文档修正
D) 只修 README 表述，不动代码
X) Other (please describe after [Answer]: tag below)

[Answer]: A（同步修正文档和对外叙事）

## Question 6
你希望把哪种结果作为本轮“完成”门槛？

A) 需求文档与执行计划确认完成即可
B) 必须有代码改动、测试和文档，且默认路径语义更清晰
C) 必须至少证明一条默认路径可验证闭环（含 focused tests）
D) 先产出可评审方案，不追求本轮一次落地完成
X) Other (please describe after [Answer]: tag below)

[Answer]: C（至少证明一条默认路径可验证闭环，含 focused tests）
