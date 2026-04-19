# UOW-1 NFR Requirements Clarification Questions

我在你填写的 `uow-1-architecture-boundary-and-core-contract-nfr-requirements-plan.md` 中识别到几处会直接影响 NFR 质量和技术决策落地的歧义。
按照 AI-DLC 要求，需要先澄清后才能继续生成 NFR 产物。

## 歧义 1：PostgreSQL 覆盖范围是否超出 UOW-1 当前边界

你在 Question 1 选择了：

- `C) 本单元所有持久化对象都以 PostgreSQL 为主，包括 session 与后续决策相关记录`

当前仍不够明确的是：

- 这里的“后续决策相关记录”是否只是技术方向约束，还是要求在 `UOW-1` 的 NFR 中就把更后面的持久化对象一并承诺下来
- 是否要把当前尚未进入设计的 `DecisionMemory` / 更后续对象也纳入本单元的 NFR 范围

## Question 1

关于 PostgreSQL 覆盖范围，你更希望本阶段如何表述？

A) 只在 UOW-1 中正式锁定 execution / task / outcome / audit / session 使用 PostgreSQL；更后续对象先写成“后续单元延续 PostgreSQL 主线”
B) 在 UOW-1 的 NFR 中就正式承诺：包括后续决策相关记录在内，整个 Phase 1 持久化主线都统一使用 PostgreSQL
C) 只锁定“PostgreSQL 是唯一允许的数据存储技术”，具体对象覆盖范围后续单元再分别展开
D) Other（请在 [Answer]: 后补充说明）

[Answer]: A

## 歧义 2：性能目标缺少可验证边界

你在 Question 3 选择了：

- `C) 先保证语义与可靠性，性能只要明显不拖垮交互即可`

当前仍不够明确的是：

- 需要一个最低可验证的性能门槛，否则 NFR 无法形成可检查标准

## Question 2

即使以可靠性优先，你仍希望我为本单元写入哪种最低性能门槛？

A) 先写宽松门槛：planning + gate 额外开销 p95 < 500ms
B) 写中等门槛：planning + gate 额外开销 p95 < 250ms
C) 不写固定数值，只写“不得显著拖慢交互”，接受本阶段不做量化
D) Other（请在 [Answer]: 后补充说明）

[Answer]: A

## 歧义 3：`biz_execute` 兼容性的“有选择地重排字段”不够具体

你在 Question 5 选择了：

- `B) 允许有选择地重排字段，只要整体结构更清晰`

当前仍不够明确的是：

- 哪些旧字段必须保留在顶层
- 哪些字段允许迁入新的 envelope 结构中
- 是否接受旧调用方需要少量适配

## Question 3

对于 `biz_execute` 输出兼容性，你更希望哪种重排策略？

A) 旧顶层字段（如 `plan` / `routing` / `authority` / `task` / `outcome` / `result`）全部保留，再新增 `execution` / `gate_decision`
B) 保留最核心旧字段（如 `plan` / `result` / `outcome`），其余逐步迁入新的 envelope 结构
C) 允许把大部分字段迁入 envelope，只保留极少数兼容别名字段
D) Other（请在 [Answer]: 后补充说明）

[Answer]: C
