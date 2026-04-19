# Components

## 设计原则

本轮组件划分遵循以下原则：

1. `Velaris` 是整体架构主体，承载业务语义、治理语义、恢复语义、学习语义
2. `OpenHarness` 是执行基座，承载会话循环、工具调度、模型调用、CLI/TUI/MCP
3. “会话”与“业务执行”是两个不同层级
4. 默认路径先收束语义，再扩张能力

## 组件清单

### 1. OpenHarness Runtime Base
- **定位**: 执行 Harness 基座
- **归属**: `OpenHarness`
- **职责**:
  - 会话循环
  - 工具注册与调度
  - 模型推理与流式事件
  - UI / CLI / MCP / 权限等通用运行时能力
- **不负责**:
  - 定义 Velaris 的业务执行语义
  - 定义 Velaris 的完成 contract / 恢复 contract

### 2. Velaris Decision Gateway
- **定位**: Velaris 面向外部的决策入口层
- **归属**: `Velaris`
- **职责**:
  - 接收来自 OpenHarness 工具面的业务请求
  - 标准化输入为决策请求
  - 组织 Planning / Governance / Execution / Memory 的调用顺序
  - 输出 Velaris 统一结果结构

### 3. Goal-To-Plan Compiler
- **定位**: 决策编译层
- **归属**: `Velaris`
- **职责**:
  - 场景识别
  - 能力规划
  - 权重初始化
  - 治理参数生成
  - 推荐工具链生成

### 4. Governance Router
- **定位**: 治理与路由层
- **归属**: `Velaris`
- **职责**:
  - 策略路由
  - 停止画像选择
  - 所需能力识别
  - 授权对象生成
- **关键约束**:
  - 授权不能只停留在说明层，应逐步具备执行语义

### 5. Biz Execution Service
- **定位**: 业务执行服务
- **归属**: `Velaris`
- **职责**:
  - 管理一次业务执行生命周期
  - 创建并推进 execution-level 状态
  - 调用具体 scenario profile 执行
  - 驱动结果收口与审计

### 6. Execution State Contract
- **定位**: 执行状态与结果契约层
- **归属**: `Velaris`
- **职责**:
  - 统一表达执行对象
  - 定义结构完成 / 约束完成 / 目标完成
  - 定义 task / outcome / audit / snapshot 的角色
  - 为恢复提供清晰边界

### 7. Scenario Profile Layer
- **定位**: 领域场景适配层
- **归属**: `Velaris`
- **职责**:
  - 领域意图解析
  - 候选项标准化
  - 规则筛选、多维评分、推荐解释
  - 场景特有的状态转换与返回协议

### 8. Memory And Learning Service
- **定位**: 记忆与学习层
- **归属**: `Velaris`
- **职责**:
  - 决策记录保存与召回
  - 偏好学习
  - 自进化复盘
  - 长期决策反馈回流

### 9. Persistence And Recovery Service
- **定位**: 默认路径与增强路径边界层
- **归属**: `Velaris`
- **职责**:
  - 决策记忆文件后端
  - PostgreSQL 增强后端
  - 执行恢复边界定义
  - 会话恢复与业务恢复拆分

## 建议的架构主视图

```text
Velaris Architecture
  |
  +-- OpenHarness Runtime Base
  |     - session loop
  |     - tool dispatch
  |     - model runtime
  |     - cli / ui / mcp
  |
  +-- Velaris Decision Gateway
        |
        +-- Goal-To-Plan Compiler
        +-- Governance Router
        +-- Biz Execution Service
        +-- Execution State Contract
        +-- Scenario Profile Layer
        +-- Memory And Learning Service
        +-- Persistence And Recovery Service
```

## 本轮设计结论

- `Velaris` 不是“挂在 OpenHarness 里的一个普通功能块”，而是上层业务架构主体
- `OpenHarness` 是“运行基座”，不是“业务语义主体”
- 后续代码改动应围绕 `Execution State Contract` 收束默认路径
