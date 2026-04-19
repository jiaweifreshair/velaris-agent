# UOW-1 Functional Design Plan

## 单元范围

- **Unit**: `UOW-1 - Architecture Boundary And Core Contract`
- **目标**:
  - 锁定 `Velaris` 与 `OpenHarness` 的正式语义边界
  - 细化 `execution / state / completion / resume` 的核心 contract
  - 明确治理前置门在执行主流程中的消费位置
- **本阶段只处理**: 业务语义、领域对象、业务规则、状态转换、错误语义
- **本阶段不处理**: 基础设施选型、完整测试矩阵、PostgreSQL 细节、完整文档重写

## Functional Design Steps

- [x] 读取 `aidlc-docs/inception/application-design/unit-of-work.md` 中 UOW-1 定义
- [x] 读取 `aidlc-docs/inception/application-design/unit-of-work-story-map.md` 中 UOW-1 对应的 Core FR / Supporting FR / NFR 映射
- [x] 读取 Application Design 与相关代码上下文，提炼 UOW-1 的领域对象候选
- [x] 确认 execution-level 对象、completion 语义、resume 语义与治理前置门的核心设计方向
- [x] 生成 `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/functional-design/business-logic-model.md`
- [x] 生成 `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/functional-design/business-rules.md`
- [x] 生成 `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/functional-design/domain-entities.md`
- [x] 校验 Functional Design 与 UOW-1 范围、FR-1 / FR-2 / FR-4 / FR-6 / NFR-4 一致

## 需要你确认的问题

根据当前代码与 UOW-1 定义，以下点会直接影响 Functional Design 质量，因此需要你在本文件中填写答案。

## Question 1

`execution-level` 对象你更希望以哪种方式成为一等公民？

A) 独立显式实体：单独建模 `BizExecutionRecord`，task / outcome / audit 都围绕它展开
B) 轻量包络对象：保留现有 task / outcome 结构，只新增一个薄的 execution contract 包裹层
C) 先不引入独立 execution 对象，只在 orchestrator 返回结构中约定 execution 字段
D) Other（请在 [Answer]: 后补充说明）

[Answer]: A

## Question 2

对于 completion 语义，你希望 Functional Design 采用哪种主表达？

A) 分层完成模型：结构完成 / 约束完成 / 目标完成分别表达，再汇总总体状态
B) 单一主状态枚举：例如 `running / partially_completed / completed / failed`，分层完成作为派生解释
C) 混合模型：既有主状态枚举，也保留三层完成字段用于解释
D) Other（请在 [Answer]: 后补充说明）

[Answer]: C

## Question 3

治理与授权结果在执行主流程中应怎样消费？

A) 强执行门：在进入 scenario 执行前必须经过 `validate_execution_gate`，失败即 fail-closed
B) 弱执行门：默认继续执行，但记录警告与审计事件
C) 场景化执行门：高风险场景 fail-closed，低风险场景允许降级继续
D) Other（请在 [Answer]: 后补充说明）

[Answer]: C

## Question 4

`OpenHarness -> Velaris` 的最小桥接边界你更偏向哪种？

A) `OpenHarness` 只提交标准化请求，`Velaris` 返回标准化执行包络；内部语义完全留在 `Velaris`
B) `OpenHarness` 可以理解一部分 execution 状态，但不拥有 contract 定义权
C) 维持当前较松散方式，先以兼容为主，边界只在文档中收束
D) Other（请在 [Answer]: 后补充说明）

[Answer]: A

## Question 5

关于 session 与 execution 的关系，你希望 Functional Design 如何建模？

A) 一个 session 可关联多个 execution；execution 可脱离 session 单独恢复
B) 一个 session 只对应一个 execution；先保持简单映射
C) execution 必须依附 session 存在，但恢复语义仍单独表达
D) Other（请在 [Answer]: 后补充说明）

[Answer]: A
