# UOW-1 NFR Requirements Plan

## 单元范围

- **Unit**: `UOW-1 - Architecture Boundary And Core Contract`
- **阶段**: NFR Requirements
- **目标**:
  - 为 `BizExecutionRecord`、`GovernanceGateDecision`、`DecisionExecutionEnvelope` 建立非功能约束
  - 锁定本单元的可靠性、性能、可用性、安全性、兼容性边界
  - 结合用户新增要求，明确 PostgreSQL 在本单元中的角色与使用范围

## 已知输入

1. `UOW-1 Functional Design` 已批准继续
2. 用户新增明确要求：**数据存储就用 PostgreSQL 就行了**
3. 本单元仍保持以下约束：
   - `Velaris` 是业务语义主体
   - `OpenHarness` 是最小桥接基座
   - execution / completion / resume contract 由 `Velaris` 主导

## NFR Assessment Steps

- [x] 读取 `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/functional-design/` 下的全部产物
- [x] 提炼本单元对可靠性、性能、可用性、安全性、兼容性的关键压力点
- [x] 结合用户“使用 PostgreSQL”要求，识别需要立即锁定的技术栈决策
- [x] 明确 `execution / gate / audit / envelope` 的关键质量约束
- [x] 生成 `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/nfr-requirements/nfr-requirements.md`
- [x] 生成 `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/nfr-requirements/tech-stack-decisions.md`
- [x] 校验 NFR 约束与 UOW-1 Functional Design、FR-1 / FR-2 / FR-4 / FR-6 / NFR-1 / NFR-3 / NFR-4 一致

## 需要你确认的问题

下面的问题会直接影响 NFR 约束与技术栈决策，请填写 `[Answer]:`。

## Question 1

你说“数据存储就用 PostgreSQL”，你希望 PostgreSQL 在本单元覆盖到哪一层？

A) 只覆盖 execution / task / outcome / audit 这类运行态记录，session 暂不纳入
B) 覆盖 execution / task / outcome / audit，并且 session snapshot 也统一进入 PostgreSQL
C) 本单元所有持久化对象都以 PostgreSQL 为主，包括 session 与后续决策相关记录
D) Other（请在 [Answer]: 后补充说明）

[Answer]: C

## Question 2

如果 PostgreSQL 临时不可用，你希望 `UOW-1` 的默认策略是什么？

A) fail-closed：不允许继续执行，直接返回基础设施不可用
B) degrade-continue：允许执行，但标记为 degraded mode，并尽量补审计
C) 只允许生成 planning / gate 草案，不进入真实 scenario 执行
D) Other（请在 [Answer]: 后补充说明）

[Answer]: A

## Question 3

你希望本单元最优先满足的性能目标更接近哪种？

A) execution request + planning + gate 的额外开销 p95 < 100ms
B) execution request + planning + gate 的额外开销 p95 < 250ms
C) 先保证语义与可靠性，性能只要明显不拖垮交互即可
D) Other（请在 [Answer]: 后补充说明）

[Answer]: C

## Question 4

对于 `degraded mode` 和高/中风险执行记录，你希望审计持久化采取哪种保证？

A) 同步落库后才能返回结果，审计写入是强一致前置条件
B) 业务结果优先返回，但必须异步补写审计，失败要可追踪
C) 高风险同步审计，中风险允许异步补审计
D) Other（请在 [Answer]: 后补充说明）

[Answer]: C

## Question 5

关于兼容性，你希望 `DecisionExecutionEnvelope` 如何落地到现有 `biz_execute` 输出？

A) 保留旧字段，同时新增 `execution` / `gate_decision` 等新字段，尽量不破坏旧调用方
B) 允许有选择地重排字段，只要整体结构更清晰
C) 以新 envelope 为准，必要时接受 breaking change
D) Other（请在 [Answer]: 后补充说明）

[Answer]: B

## Question 6

关于安全与数据保护，本单元最需要优先满足哪种约束？

A) 审计与 envelope 中敏感 payload 必须支持脱敏/最小暴露
B) PostgreSQL 中相关 execution / audit 数据必须默认加密并可做最小权限隔离
C) 两者都必须优先纳入本单元 NFR
D) Other（请在 [Answer]: 后补充说明）

[Answer]: C


## 澄清收束结果（正式采用）

以下结论以 `uow-1-architecture-boundary-and-core-contract-nfr-requirements-clarification-questions.md` 为最终正式解释：

- Question 1：按澄清答案 `A` 收束，即本单元只正式锁定 `execution / task / outcome / audit / session` 使用 PostgreSQL；更后续对象先写成“后续单元延续 PostgreSQL 主线”
- Question 3：按澄清答案 `A` 收束，即最低性能门槛写为 `planning + gate` 额外开销 `p95 < 500ms`
- 兼容性策略：按澄清答案 `C` 收束，即允许把大部分字段迁入 envelope，只保留极少数兼容别名字段
