# NFR Requirements

## 1. 文档目标

本文件为 `UOW-1 - Architecture Boundary And Core Contract` 定义正式的非功能要求，
用于约束 `Velaris` 在 execution-level contract、governance gate、统一 envelope 与持久化主线上的质量边界。

本文件同时吸收并收束以下最新前提：

- 用户已确认 `Velaris` 是整体架构主体，`OpenHarness` 只是 Harness 执行基座
- 用户已确认本轮数据存储主线使用 PostgreSQL
- 本单元只正式锁定 `execution / task / outcome / audit / session` 五类对象进入 PostgreSQL 主线
- 更后续对象不在本单元超前承诺，但后续单元应延续 PostgreSQL 主线

## 2. 适用范围

### 2.1 本单元正式覆盖对象

本单元 NFR 只对以下对象形成强约束：

- `BizExecutionRecord`
- execution 关联的 `task` 记录
- execution 关联的 `outcome` 记录
- execution / gate / degrade 关联的 `audit` 记录
- `session` snapshot / session reference 对应的持久化记录

### 2.2 本单元明确不超前承诺的内容

以下内容不在 `UOW-1` 正式承诺范围内，但后续单元应继续沿用本文件中的质量主线：

- 更后续的决策记忆扩展对象
- 更复杂的跨 execution 聚合分析对象
- 额外基础设施中间件（如缓存、消息总线、搜索引擎）

## 3. 输入依据

本文件基于以下已批准或已确认输入生成：

1. `requirements.md` 中的 FR-1 / FR-2 / FR-4 / FR-6 / NFR-1 / NFR-3 / NFR-4
2. `UOW-1 Functional Design` 产物中对 execution 主体、gate、completion 和 envelope 的定义
3. 用户对 NFR 澄清问题的确认：
   - PostgreSQL 覆盖范围：本单元锁定 `execution / task / outcome / audit / session`
   - 性能底线：`planning + gate` 额外开销 `p95 < 500ms`
   - `biz_execute` 兼容策略：以 envelope 为主，只保留极少数兼容别名字段
4. 当前代码事实：
   - `src/velaris_agent/persistence/factory.py` 仍默认偏向文件 / 内存回退
   - `src/openharness/services/session_storage.py` 仍以文件方式保存 session snapshot
   - `src/velaris_agent/persistence/postgres_runtime.py` 已有 task / outcome / audit 的 PostgreSQL 最小落点
   - `src/velaris_agent/velaris/orchestrator.py` 与 `src/openharness/tools/biz_execute_tool.py` 仍未收束到 execution + gate 为核心的 envelope

## 4. NFR 总览

| 编号 | 维度 | 本单元正式要求 |
| --- | --- | --- |
| NFR-UOW1-01 | 可靠性 / 持久化真相源 | `execution / task / outcome / audit / session` 统一以 PostgreSQL 为主存储，默认生产语义不允许悄悄回退到文件 / 内存真相源 |
| NFR-UOW1-02 | 可用性 / 故障语义 | PostgreSQL 不可用时必须 fail-closed，禁止进入真实 scenario 执行 |
| NFR-UOW1-03 | 审计一致性 / 治理 | 高风险必须同步审计；中风险允许 degraded 继续，但补审计必须可追踪；低风险按普通策略 |
| NFR-UOW1-04 | 性能 | `request intake -> planning -> routing -> authority -> effective risk -> gate` 的额外开销 `p95 < 500ms` |
| NFR-UOW1-05 | 安全 / 数据保护 | payload、audit、envelope 均须脱敏 / 最小暴露；PostgreSQL 必须满足加密传输、静态加密与最小权限隔离 |
| NFR-UOW1-06 | 兼容性 | 对外以 `DecisionExecutionEnvelope` 为主 contract；旧顶层字段只保留极少数过渡别名 |
| NFR-UOW1-07 | 可维护性 / 可验证性 | `Velaris` 必须是唯一 contract 主语义源；NFR 必须能被 focused tests / contract tests 验证 |

## 5. 详细非功能要求

### NFR-UOW1-01 可靠性与持久化真相源

#### 要求

1. 本单元范围内的 `execution / task / outcome / audit / session` 必须统一以 PostgreSQL 作为正式主存储。
2. 文件型 session snapshot、内存 task ledger、文件型 decision memory 或其它回退实现，不能再被视为本单元默认业务真相源。
3. 同一 execution 的状态推进、审计引用与恢复锚点，必须能在 PostgreSQL 中得到可回放、可核验的持久化结果。
4. `session` 与 `execution` 虽然语义分离，但都必须落在同一持久化主线上，避免“一部分在文件、一部分在数据库”导致恢复边界模糊。

#### 验收边界

- 生产默认链路中，不允许“PostgreSQL 不可用但自动落到文件 / 内存后继续对外宣称成功”的行为
- 恢复 execution 时，不需要依赖文件系统上的 session snapshot 才能识别 execution 是否存在
- 后续单元若新增持久化对象，应延续 PostgreSQL 主线，而不是重新引入并行真相源

### NFR-UOW1-02 可用性与故障策略

#### 要求

1. PostgreSQL 不可用、写入失败或连接初始化失败时，`UOW-1` 默认策略为 **fail-closed**。
2. fail-closed 必须发生在真实 scenario 执行之前；不能先执行真实业务，再在返回时才发现持久化失败。
3. 基础设施不可用必须与业务 gate deny 区分表达：
   - infrastructure unavailable = 基础设施故障
   - denied = 治理阻断
4. fail-closed 时必须返回标准化错误语义，至少可区分：
   - 哪个阶段失败（session bind / execution create / audit persist / outcome persist 等）
   - 是否发生真实业务执行
   - 是否需要人工或系统重试

#### 验收边界

- PostgreSQL 不可用时，不产生“completed / partially_completed / degraded 成功结果”假象
- 任何真实执行前置落库失败，必须显式阻断并可追踪

### NFR-UOW1-03 审计一致性与治理保证

#### 要求

1. 高风险 execution 默认继承 Functional Design 中的 fail-closed 语义，并增加 **同步审计成功** 作为前置要求。
2. 中风险 execution 允许以 `degraded_mode = true` 继续，但补审计不得静默丢失，必须至少满足：
   - 有可追踪的补写任务、状态或错误标记
   - 最终审计仍以 PostgreSQL 为落点
3. 低风险 execution 可以沿用普通审计策略，但若 policy 要求审计，也必须保持可核验。
4. 审计记录必须能关联至少以下关键键值：
   - `execution_id`
   - `session_id`（若存在）
   - `gate_status`
   - `effective_risk_level`
   - 关键原因码或摘要
5. `degraded`、`denied`、`failed` 三类结果都必须拥有足够的审计可追溯性，不能只在内存中短暂出现。

#### 验收边界

- 高风险路径上，审计仓储不可用时必须阻断执行或阻断成功返回
- 中风险路径上，若选择异步补审计，必须能证明“待补 / 已补 / 补写失败”中的一种明确状态

### NFR-UOW1-04 性能要求

#### 要求

1. 在单次 execution 请求的默认路径中，`planning + routing + authority + effective risk + gate` 相对原 scenario 业务执行的新增开销必须满足 `p95 < 500ms`。
2. 该指标的测量边界定义为：
   - 起点：标准化请求进入 `Velaris`
   - 终点：`GovernanceGateDecision` 已形成，且可决定是否进入真实 scenario 执行
3. 该指标不包含真实 scenario 内部业务处理耗时，也不包含外部 LLM / 外部系统不可控网络延迟。
4. 对高风险同步审计路径，若因为同步审计导致性能超线，必须优先保证语义正确与审计正确，再通过后续设计优化，而不是牺牲同步保证。

#### 验收边界

- `p95 < 500ms` 是本单元最低性能门槛，不是长期最优目标
- 后续单元可继续收紧目标，但不得放宽本单元已承诺的上界

### NFR-UOW1-05 安全与数据保护

#### 要求

1. execution payload、audit payload 与对外 envelope 中的敏感字段必须遵循“脱敏优先、最小暴露优先”的原则。
2. 任何非必要的原始敏感上下文，不得直接进入审计长久存储或公开 contract。
3. PostgreSQL 必须满足以下最低安全基线：
   - 传输链路加密
   - 静态数据加密或依赖受控磁盘加密能力
   - 最小权限角色隔离
   - 凭据通过环境变量或受控 secret 注入，而非硬编码
4. 结构化日志中不得输出未经脱敏的敏感 payload。
5. `OpenHarness` 作为桥接层不得绕过 `Velaris` 自行定义敏感字段暴露规则。

#### 验收边界

- 新 envelope / audit 设计不能因为“方便调试”而扩大敏感字段暴露面
- PostgreSQL 访问权限必须允许按组件或职责做最小授权，而不是共享超级权限账号

### NFR-UOW1-06 兼容性与迁移边界

#### 要求

1. `DecisionExecutionEnvelope` 必须成为正式对外 contract 的真相源。
2. 现有 `biz_execute` 输出允许把大部分旧字段迁入新的 envelope 结构，只保留极少数兼容别名字段。
3. 本单元建议保留的过渡别名字段仅限：
   - `session_id`
   - `result`
   - `outcome`
   - `audit_event_count`
4. 除上述极少数别名外，旧顶层字段（如旧版 `plan / routing / authority / task` 的平铺稳定性）不再作为长期兼容承诺。
5. 桥接层兼容应通过过渡 alias 完成，而不是继续让 `OpenHarness` 承担内部 contract 的解释责任。

#### 验收边界

- 调用方若只依赖最小结果语义，仍可通过少量适配继续消费结果
- 新开发与后续文档必须面向 envelope，而不是继续面向旧平铺字段集合

### NFR-UOW1-07 可维护性与可验证性

#### 要求

1. execution、gate、completion、audit 的主语义必须只在 `Velaris` 中定义一次；`OpenHarness` 只能桥接，不得复制一套平行语义。
2. 本单元的 NFR 必须可以被 focused tests、contract tests 或最小运行验证直接检验，不能只停留在文字承诺层。
3. 文档、测试与实现必须围绕同一套术语：
   - `execution`
   - `gate_decision`
   - `degraded_mode`
   - `blocked / failed / partially_completed / completed`
4. PostgreSQL 作为唯一正式主存储后，不应再为同一对象维护多套长期并行持久化 contract。

#### 验收边界

- 若后续代码仍保留文件 / 内存后端，其角色必须明确为测试、过渡兼容或开发辅助，而非默认业务真相源
- 任何文档与测试中的 contract 命名都不应再把 `OpenHarness` 描述为 execution 语义拥有者

## 6. 与当前代码现状的主要差距

当前代码与本文件要求之间至少存在以下差距，后续 `NFR Design` 与 `Code Generation` 需要显式收敛：

1. `src/velaris_agent/persistence/factory.py` 目前仍把 PostgreSQL 作为“显式传入 DSN 才启用”的增强路径。
2. `src/openharness/services/session_storage.py` 目前仍以文件保存 session snapshot，不满足 session 进入 PostgreSQL 主线的要求。
3. `src/velaris_agent/velaris/orchestrator.py` 当前仍围绕 `task / outcome / audit_event_count` 返回，尚未把 `execution` 与 `gate_decision` 收束为一等输出核心。
4. `src/openharness/tools/biz_execute_tool.py` 当前仍把平铺 payload 直接序列化输出，尚未体现 envelope 主真相源 + 极少数兼容 alias 的策略。

## 7. 本单元 NFR 结论

`UOW-1` 的非功能主线已经明确：

- 语义主语义收束到 `Velaris`
- 持久化主线收束到 PostgreSQL
- PostgreSQL 不可用时默认 fail-closed
- 高风险审计必须同步，中风险可补审计但不能无痕丢失
- 对外 contract 以 envelope 为准，仅保留极少数兼容 alias
- 安全基线必须同时覆盖 payload 脱敏与 PostgreSQL 加密 / 最小权限

这些约束将作为下一阶段 `NFR Design` 的直接输入。
