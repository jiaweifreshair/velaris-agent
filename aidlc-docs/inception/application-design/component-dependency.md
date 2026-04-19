# Component Dependency

## 依赖原则

1. `OpenHarness` 作为基座，应被上层 `Velaris` 依赖，而不是反过来主导 `Velaris` 语义
2. `Velaris` 内部按“入口 -> 编译 -> 治理 -> 执行 -> 状态 -> 记忆/恢复”单向依赖
3. 默认路径优先语义收束，增强路径只扩容不补语义

## 高层依赖图

```text
OpenHarness Runtime Base
    |
    v
Velaris Decision Gateway
    |
    +--> Goal-To-Plan Compiler
    |
    +--> Governance Router
    |
    +--> Biz Execution Service
            |
            +--> Execution State Contract
            +--> Scenario Profile Layer
            +--> Persistence And Recovery Service
            +--> Memory And Learning Service
```

## 组件依赖矩阵

| 组件 | 直接依赖 | 说明 |
|------|----------|------|
| OpenHarness Runtime Base | 无 | 执行基座 |
| Velaris Decision Gateway | OpenHarness Runtime Base, Goal-To-Plan Compiler, Governance Router, Biz Execution Service | Velaris 决策入口 |
| Goal-To-Plan Compiler | Scenario Profile Layer（可选元数据） | 生成 plan |
| Governance Router | routing policy, authority model | 路由和授权 |
| Biz Execution Service | Governance Router, Scenario Profile Layer, Execution State Contract, Persistence And Recovery Service, Memory And Learning Service | 推进业务执行 |
| Execution State Contract | task/outcome/audit model | 统一执行语义 |
| Scenario Profile Layer | 领域协议与场景实现 | 场景执行 |
| Memory And Learning Service | DecisionMemory, PreferenceLearner, SelfEvolution | 长期学习 |
| Persistence And Recovery Service | file/postgres backends, session storage | 默认/增强路径和恢复 |

## 通信模式

### 1. Runtime To Gateway
- **模式**: 同进程直接调用
- **载体**: tool metadata + payload

### 2. Gateway To Planning / Governance / Execution
- **模式**: 同步服务编排
- **载体**: 结构化 dict / typed model

### 3. Execution To Scenario
- **模式**: 场景函数分发
- **载体**: scenario-specific payload

### 4. Execution To Persistence
- **模式**: 同步写入 + 可选增强后端
- **载体**:
  - task snapshot
  - outcome snapshot
  - audit snapshot

### 5. Execution To Memory
- **模式**: 执行完成后异步/同步回流
- **载体**:
  - decision record
  - preference update inputs
  - evolution review trigger

## 需要重点避免的反向依赖

### 反模式 1
- `OpenHarness` 知道太多 `Velaris` 内部业务语义
- **问题**: 会让基座与业务主体边界变脏

### 反模式 2
- `DecisionMemory` 承担运行态状态真相源职责
- **问题**: 长期记忆与执行状态混淆

### 反模式 3
- `session resume` 被误当成 `execution resume`
- **问题**: 恢复语义不一致

## 本轮依赖收束建议

1. 保持 `OpenHarness -> Velaris Entry` 的最小桥接关系
2. 把 execution 语义集中在 `Velaris`
3. 把运行态状态和长期学习状态从职责上拆开
4. 把默认 durable 路径与增强路径的切换点限制在 persistence 工厂层
