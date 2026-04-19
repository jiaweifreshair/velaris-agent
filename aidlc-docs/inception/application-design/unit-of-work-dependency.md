# Unit Of Work Dependency

## 依赖原则

1. 先锁定语义边界，再锁定状态边界，再落到运行闭环
2. 依赖关系按单向流动设计，不允许后置单元反向决定前置单元的主语义
3. 持久化统一依赖于 contract 定义，而运行闭环依赖于 contract + 状态链共同稳定

## 高层依赖图

```text
UOW-1 Architecture Boundary And Core Contract
    |
    v
UOW-2 Default State Chain And Persistence Unification
    |
    v
UOW-3 Minimal Runtime Convergence
```

## 单元依赖矩阵

| Unit | 直接依赖 | 输出给谁 | 依赖原因 |
|------|----------|----------|----------|
| UOW-1 | 无 | UOW-2, UOW-3 | 先定义语义主体与 contract |
| UOW-2 | UOW-1 | UOW-3 | 主状态、恢复边界必须以 contract 为前提 |
| UOW-3 | UOW-1, UOW-2 | 后续 Functional Design | 运行闭环必须继承边界定义与状态链定义 |

## 关键交汇点

### 1. Execution Contract 交汇点
- **来源单元**: UOW-1
- **被谁消费**: UOW-2, UOW-3
- **说明**:
  - UOW-2 需要它来判断 execution snapshot 是否独立存在
  - UOW-3 需要它来判断 orchestrator 返回结构应如何收束

### 2. Completion / Resume Contract 交汇点
- **来源单元**: UOW-1
- **被谁消费**: UOW-2, UOW-3
- **说明**:
  - UOW-2 需要它区分“必须可恢复”与“可重建”
  - UOW-3 需要它决定工具面失败态 / 成功态的语义一致性

### 3. Default State Chain 交汇点
- **来源单元**: UOW-2
- **被谁消费**: UOW-3
- **说明**:
  - 决定 `task / outcome / audit / memory / snapshot` 的边界
  - 决定最小闭环返回结构中哪些字段是主表达，哪些只是派生视图

### 4. Minimal Runtime Entry 交汇点
- **来源单元**: UOW-3
- **被谁消费**: 后续 Functional Design / Code Generation
- **说明**:
  - 决定后续功能设计和代码实现围绕哪个最小入口推进
  - 决定 README / AI-DLC 文档需要同步哪些最小口径

## 阻塞关系

### Blocker A
- **如果 UOW-1 未完成**:
  - 无法确定 execution 与 session 的层级边界
  - 无法判断 `OpenHarness` 是否越界承载了业务语义
  - UOW-2 与 UOW-3 都不能稳定推进

### Blocker B
- **如果 UOW-2 未完成**:
  - 无法确定默认路径主状态
  - 无法确定 execution resume 与 session resume 的分界
  - UOW-3 只能得到表面一致的返回结构，得不到真正一致的语义

### Blocker C
- **如果 UOW-3 未完成**:
  - 前两个单元停留在设计层，不能形成最小可运行闭环
  - 后续 Functional Design 会缺少清晰的最小入口和接口收口点

## 建议执行顺序

### Step 1 - UOW-1
先锁定语义主体：
- `Velaris` 定义什么
- `OpenHarness` 负责什么
- execution / state / completion / resume contract 由谁主导

### Step 2 - UOW-2
再锁定默认状态链：
- 默认路径下主状态是什么
- 哪些记录只是派生表达
- 恢复边界如何表达
- PostgreSQL 与默认路径的关系如何约束

### Step 3 - UOW-3
最后收束最小运行闭环：
- orchestrator 返回结构
- `biz_execute` 工具面桥接方式
- 必要文档同步清单

## 不允许的反向依赖

### 反模式 1
- 先按现有工具返回结构倒推 execution contract
- **问题**: 这会让工具面反向定义业务主体语义

### 反模式 2
- 先按 PostgreSQL 运行时能力倒推默认状态链
- **问题**: 这会让增强路径替默认路径补语义

### 反模式 3
- 先按 session snapshot 结构倒推 execution resume 设计
- **问题**: 这会继续混淆会话恢复与业务执行恢复

## 对后续阶段的输入要求

Units Generation 完成后，后续 Functional Design 应按以下顺序展开：

1. 先针对 UOW-1 细化 contract 与执行对象建模
2. 再针对 UOW-2 细化状态模型、恢复策略与持久化边界
3. 最后针对 UOW-3 细化最小运行闭环的接口与返回结构
