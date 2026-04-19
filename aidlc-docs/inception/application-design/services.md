# Services

## 服务设计目标

本轮服务层设计要解决的不是“把代码拆成更多 service 名字”，而是明确：

1. 哪些服务属于 `OpenHarness` 基座
2. 哪些服务属于 `Velaris` 决策架构
3. 一次业务请求如何跨这些服务流动

## 服务分层

### 1. Runtime Harness Service
- **归属**: `OpenHarness`
- **职责**:
  - 承载 session
  - 调用工具
  - 管理权限
  - 组织模型调用
- **服务边界**:
  - 不直接定义 Velaris 的业务执行 contract

### 2. Decision Entry Service
- **归属**: `Velaris`
- **职责**:
  - 接收 `biz_execute` 类请求
  - 把工具层调用收敛到统一决策入口
  - 转换并返回标准化执行结果

### 3. Decision Planning Service
- **归属**: `Velaris`
- **职责**:
  - 生成 plan
  - 附加 stakeholder context
  - 初始化权重与治理配置

### 4. Governance Service
- **归属**: `Velaris`
- **职责**:
  - 路由
  - 授权
  - 执行门校验
  - 停止画像解释

### 5. Execution Orchestration Service
- **归属**: `Velaris`
- **职责**:
  - 创建 execution
  - 驱动 scenario 执行
  - 管理 task/outcome/audit 的收口
  - 聚合结果与异常

### 6. Scenario Execution Service
- **归属**: `Velaris`
- **职责**:
  - 承载 travel / tokencost / robotclaw / procurement / lifegoal 等场景实现
  - 处理领域规则、评分和推荐

### 7. Decision Memory Service
- **归属**: `Velaris`
- **职责**:
  - 保存/召回决策
  - 驱动偏好学习
  - 驱动自进化

### 8. Persistence And Recovery Service
- **归属**: `Velaris`
- **职责**:
  - 统一默认 durable 路径与增强路径
  - 拆分 session resume 与 execution resume

## 编排主链

```text
Runtime Harness Service
  -> Decision Entry Service
     -> Decision Planning Service
     -> Governance Service
     -> Execution Orchestration Service
        -> Scenario Execution Service
        -> Persistence And Recovery Service
        -> Decision Memory Service
```

## 关键服务约束

### 会话服务与执行服务分离
- 会话可以存在而没有业务执行
- 业务执行可以引用会话，但不等于会话

### 治理服务与执行服务分离
- Governance Service 负责“是否允许执行”
- Execution Orchestration Service 负责“如何推进执行”

### 持久化服务与记忆服务分离
- Memory Service 关注长期知识与学习
- Persistence And Recovery Service 关注运行态状态与恢复语义

## 本轮建议的首要服务改造

1. 在 `Decision Entry Service` 和 `Execution Orchestration Service` 之间加入 execution-level contract
2. 在 `Governance Service` 中增加执行门校验语义
3. 在 `Persistence And Recovery Service` 中明确：
   - session snapshot
   - execution snapshot
   - outcome snapshot
   - audit snapshot
   的边界与职责
