# Unit Of Work Plan Change Questions

你刚刚对 `Units Generation Planning` 选择了 `Request Changes`。
为了按 AI-DLC 流程精确修改 `aidlc-docs/inception/plans/unit-of-work-plan.md`，
请在下面每个问题后的 `[Answer]:` 里填写字母。

如果你想补充具体要求，可以写成：
`[Answer]: B - 我希望把持久化和执行模型合并成一个单元`

## Question 1

你这次最主要想改的是哪一类内容？

A) 工作单元划分方式（例如 5 个单元太多/太少，边界不对）
B) 工作单元执行顺序（例如 先做什么、后做什么 需要调整）
C) 单元范围控制（例如 某些内容应移出本轮，或某些内容必须纳入本轮）
D) 验证与测试重点（例如 更强调 contract tests、focused tests、默认路径验证）
E) 文档映射方式（例如 FR / NFR / Construction Intent 的映射方式需要改）
F) Other（请在 [Answer]: 后补充说明）

[Answer]: C 例如持久化应该统一

## Question 2

你期望的工作单元粒度更接近哪种？

A) 保持 5 个工作单元，但调整边界定义
B) 合并为 3-4 个更粗粒度的工作单元
C) 拆成 6 个以上更细粒度的工作单元
D) 维持 5 个工作单元与当前边界，不改粒度，只改表述
E) Other（请在 [Answer]: 后补充说明）

[Answer]: E,保持精简最快实现的原则

## Question 3

如果要调整执行顺序，你更希望哪条主线排在前面？

A) 先做 `Architecture Boundary Contract`，再进入 execution / persistence
B) 先做 `Execution Model And Orchestrator Convergence`，把执行闭环先收拢
C) 先做 `Persistence And Resume Boundary Cleanup`，把默认 durable 语义先钉住
D) 保持当前顺序，不改主线顺序
E) Other（请在 [Answer]: 后补充说明）

[Answer]:  A，按照合理最小干净可运行的方式来调整

## Question 4

对于本轮 `Phase 1`，你更希望我怎样控制范围？

A) 进一步聚焦，只保留 contract + 默认状态链 + resume 边界
B) 保留当前范围，但弱化 Documentation Alignment，放到最后单独处理
C) 保留当前范围，但把 Tool Surface And Verification 提前
D) 保持当前范围与优先级，不改范围，只改表达方式
E) Other（请在 [Answer]: 后补充说明）

[Answer]: A

## Question 5

你希望后续 `Units Generation` 最强调哪种完成标准？

A) 每个工作单元都能映射到明确的代码改动边界
B) 每个工作单元都能映射到明确的默认路径验证闭环
C) 两者同等重要，都必须在单元定义中写清楚
D) 先以架构语义清晰为主，验证细节可在后续设计阶段补强
E) Other（请在 [Answer]: 后补充说明）

[Answer]: D
