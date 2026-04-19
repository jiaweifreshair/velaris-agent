# Tech Stack Decisions

## 1. 决策目标

本文件记录 `UOW-1 - Architecture Boundary And Core Contract` 在 NFR Requirements 阶段正式锁定的技术栈与技术边界决策。
这些决策服务于三个目标：

- 保证 `Velaris` 的 execution-level contract 有单一、可验证的持久化主线
- 保证 governance gate、审计与恢复语义不再依赖增强路径补位
- 为后续 `NFR Design` 与 `Code Generation` 提供收敛方向，而不是继续保留并行技术路线

## 2. 决策摘要

| 编号 | 决策 | 结论 |
| --- | --- | --- |
| TSD-01 | 主存储技术 | `execution / task / outcome / audit / session` 统一使用 PostgreSQL |
| TSD-02 | 当前阶段覆盖边界 | 只正式锁定 UOW-1 当前对象；后续对象延续 PostgreSQL 主线，但不在本单元超前细化 |
| TSD-03 | 运行时后端策略 | 文件 / 内存实现不再是正式默认主线，只保留测试、过渡兼容或本地辅助角色 |
| TSD-04 | 审计与异步补写技术边界 | 不新增 Redis / Kafka；即使存在异步补审计，最终落点仍为 PostgreSQL |
| TSD-05 | 工具输出 contract | 以 `DecisionExecutionEnvelope` 为正式 contract，只保留极少数兼容 alias |
| TSD-06 | 安全基线 | PostgreSQL 访问必须满足传输加密、静态加密 / 受控磁盘加密、最小权限隔离与 secret 注入 |
| TSD-07 | 性能收束策略 | 保持当前单进程本地编排主线，不额外引入中间件，以满足 `planning + gate p95 < 500ms` |

## 3. 详细技术决策

### TSD-01 PostgreSQL 作为本单元唯一正式主存储

#### 决策

`UOW-1` 中正式承诺以下对象统一进入 PostgreSQL 主线：

- `BizExecutionRecord`
- task ledger records
- outcome records
- audit event records
- session snapshot / session reference records

#### 理由

1. 用户已明确要求“数据存储就用 PostgreSQL”。
2. execution、audit 与 session 若分散在多种持久化介质上，会直接破坏恢复与审计边界。
3. 当前仓库已经具备 PostgreSQL 最小运行时仓储基础，适合沿现有路线收束，而不是再开新路线。

#### 影响

- `src/velaris_agent/persistence/factory.py` 的默认后端策略后续需要翻转
- `src/openharness/services/session_storage.py` 需要从文件链路收敛到 PostgreSQL
- 任何继续依赖本地文件作为正式真相源的路径都应被降级为临时兼容方案

### TSD-02 只锁定 UOW-1 当前对象，不超前细化后续对象

#### 决策

本阶段只正式锁定 `execution / task / outcome / audit / session` 五类对象进入 PostgreSQL。
对更后续的决策记忆扩展对象，只写入“后续单元延续 PostgreSQL 主线”，不在本单元提前承诺表结构或具体持久化模型。

#### 理由

1. 这能避免 `UOW-1` 超范围承诺尚未设计的对象。
2. 这同时保留了用户对 PostgreSQL 主线的统一要求，不会让后续单元重新打开技术选型。

#### 影响

- `UOW-2` 和 `UOW-3` 只能在 PostgreSQL 主线上继续展开
- 后续设计可以细化对象，但不能重新引入第二套正式主存储

### TSD-03 文件 / 内存后端退居过渡或测试角色

#### 决策

文件型 session snapshot、内存 task ledger、未绑定 PostgreSQL 的 outcome / audit 后端，不再被视为本单元正式默认路径。
如果后续代码仍保留这些实现，其角色仅限于：

- 单元测试 / 本地开发辅助
- 过渡兼容
- 无持久化承诺的临时演示路径

#### 理由

1. 多真相源会放大恢复歧义。
2. 当前 Functional Design 已把 execution 视为一等主对象，不能继续让其真相源在文件、内存、数据库之间摇摆。

#### 影响

- 对生产或默认业务闭环，不允许静默回退
- 需要在实现中显式区分“正式路径”与“测试 / 兼容路径”

### TSD-04 审计最终落点统一为 PostgreSQL，不新增额外中间件

#### 决策

即使中风险 execution 允许异步补审计，`UOW-1` 也不引入 Redis、Kafka 或其它额外基础设施作为正式依赖。
异步补写若存在，最终审计落点仍必须是 PostgreSQL。

#### 理由

1. 本轮强调“最小可信闭环”，不优先扩张基础设施复杂度。
2. 用户并未要求额外中间件，且现有仓库已经具备 PostgreSQL 审计落点基础。

#### 影响

- NFR Design 需要在“不引入新中间件”的前提下设计补审计可追踪机制
- 异步补审计是流程策略，不是新的存储主线

### TSD-05 `DecisionExecutionEnvelope` 作为正式工具 contract

#### 决策

`biz_execute` 与后续相关桥接输出应以 `DecisionExecutionEnvelope` 为正式 contract 真相源。
旧字段兼容策略收束为“极少数 alias”，建议保留：

- `session_id`
- `result`
- `outcome`
- `audit_event_count`

除上述 alias 外，不再长期承诺旧平铺字段集合的稳定性。

#### 理由

1. 用户已明确接受“大部分字段迁入 envelope，只保留极少数兼容别名字段”。
2. 这能把 contract 主语义重新集中到 `Velaris`，避免 `OpenHarness` 继续扮演解释层。

#### 影响

- 现有依赖 `plan / routing / authority / task` 顶层平铺结构的调用方，需要在后续实现阶段做小规模适配
- 文档、测试与新开发都应面向 envelope 编写

### TSD-06 PostgreSQL 安全基线随主存储决策一并锁定

#### 决策

既然 PostgreSQL 是唯一正式主存储，则其安全基线也必须一起锁定：

- 连接链路使用加密传输
- 数据静态加密或受控磁盘加密
- 按职责做最小权限隔离
- 连接凭据通过环境变量 / secret 注入
- 结构化日志默认脱敏

#### 理由

1. 用户明确要求“payload 脱敏 / 最小暴露”与“PostgreSQL 加密 / 最小权限隔离”都优先纳入。
2. 如果只锁定 PostgreSQL 而不锁定最小安全基线，会导致后续实现出现不一致。

#### 影响

- 后续设计与实现不能再把“明文调试方便”当作默认理由
- OpenHarness 与 Velaris 共享数据库接入时必须显式区分权限边界

### TSD-07 保持单进程编排主线，优先收敛而非扩张

#### 决策

为满足本单元 `planning + gate p95 < 500ms` 的目标，当前阶段不新增缓存层、消息队列或新的独立协调服务。
优先沿用现有单进程编排 + PostgreSQL 最小持久化链路收敛。

#### 理由

1. 本轮目标是“默认路径收束 / 最小可信闭环”，不是性能极限优化。
2. 当前性能门槛较宽松，优先收敛主语义与持久化主线更符合阶段目标。

#### 影响

- 性能优化首先从减少不必要序列化、控制同步写入路径、减少无意义回退分支入手
- 若后续需要更激进性能优化，应在不破坏 execution / gate / audit 语义的前提下进行

## 4. 对当前代码的直接指导

这些技术决策对当前代码有以下直接指向：

1. `src/velaris_agent/persistence/postgres_runtime.py` 可作为 `task / outcome / audit` 的现有落点基础继续扩展。
2. `src/velaris_agent/persistence/factory.py` 后续需要把 PostgreSQL 从“可选增强路径”提升为“正式默认路径”。
3. `src/openharness/services/session_storage.py` 后续需要把 session snapshot 从文件保存迁移到 PostgreSQL 主线。
4. `src/velaris_agent/velaris/orchestrator.py` 与 `src/openharness/tools/biz_execute_tool.py` 后续需要围绕 envelope + gate + execution 收束输出结构。

## 5. 本阶段未做的技术承诺

为避免在 NFR Requirements 阶段超前进入实现细节，本文件明确不在本阶段承诺：

- 具体 PostgreSQL 表结构最终长什么样
- 是否继续沿用纯 JSONB payload 表，或引入更多显式列
- 中风险补审计的具体调度机制
- `DecisionExecutionEnvelope` 的最终 JSON 嵌套层级
- 精确到单 SQL 或单函数的性能优化手段

这些内容留待下一阶段 `NFR Design` 继续收束。
