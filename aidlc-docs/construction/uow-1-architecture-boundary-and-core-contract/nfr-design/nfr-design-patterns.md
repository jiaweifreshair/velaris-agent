# NFR Design Patterns

## 1. 文档目标

本文件把 `UOW-1 - Architecture Boundary And Core Contract` 已批准的 NFR Requirements 落成可执行的设计模式。
这些模式直接服务于以下目标：

- 让 `execution / task / outcome / audit / session` 的 PostgreSQL 主线具备可实现的结构
- 让 `fail-closed`、高风险同步审计、中风险可追踪补审计具备明确落地方式
- 让 `DecisionExecutionEnvelope` 成为唯一主 contract，同时保持最小兼容窗口
- 让安全与性能约束在设计层被前置吸收，而不是等到实现阶段临时补丁

## 2. 已确认的设计输入

本文件基于以下已确认答案收束：

1. PostgreSQL 主存储逻辑建模：选择 `C`
   - `execution / session / task / outcome / audit` 全部采用更明确的显式结构表
2. fail-closed 持久化屏障：选择 `B`
   - 先在内存中完成 planning / gate，再在进入真实 scenario 前做一次集中落库；集中落库失败则阻断
3. 中风险补审计模式：选择 `B`
   - 在 `execution` 主记录中维护 `audit_status`，由主流程或恢复流程触发补写
4. envelope 兼容模式：选择 `A`
   - 内部全面切到 envelope，`biz_execute` 只在最外层补少量 alias
5. 敏感 payload 保护模式：选择 `A`
   - 默认只持久化脱敏后的 payload / audit 内容，原始敏感数据除非白名单允许，否则不进入长期存储

## 3. 设计模式总览

| 编号 | 模式名称 | 解决的问题 |
| --- | --- | --- |
| DP-01 | 显式关系型执行主模型 | 让五类核心对象拥有稳定、可查询、可恢复的单一主存储结构 |
| DP-02 | Gate 前集中落库屏障 | 在进入真实 scenario 之前形成 fail-closed 的持久化屏障 |
| DP-03 | 执行内嵌审计状态跟踪 | 在不引入额外中间件的前提下，让中风险补审计可追踪 |
| DP-04 | Envelope-First 兼容适配 | 让内部 contract 统一收束到 envelope，同时保留最小兼容窗口 |
| DP-05 | 默认脱敏持久化 | 控制 payload / audit 的长期暴露面 |
| DP-06 | 分层权限与失败分类 | 区分基础设施错误、治理阻断与业务失败，并绑定最小权限访问 |
| DP-07 | 单进程双阶段执行路径 | 保持 `planning + gate p95 < 500ms`，又不破坏前置落库屏障 |

## 4. 详细设计模式

### DP-01 显式关系型执行主模型

#### 目标

把 `BizExecutionRecord`、`SessionReference`、task、outcome、audit 从“统一 payload 容器”提升为显式结构对象，
使 execution 成为数据库中的一等主实体，并让恢复、追踪和权限控制可以依赖稳定列而不是弱结构 JSON。

#### 模式定义

1. `execution` 作为中心主表，至少拥有以下显式列：
   - `execution_id`
   - `session_id`（可空）
   - `scenario`
   - `execution_status`
   - `gate_status`
   - `effective_risk_level`
   - `degraded_mode`
   - `audit_status`
   - `structural_complete`
   - `constraint_complete`
   - `goal_complete`
   - `resume_cursor`
   - `created_at / updated_at`
2. `session` 作为独立表，表达 session snapshot / reference，不再只保留文件形态。
3. `task`、`outcome`、`audit` 分别采用显式结构表，并通过 `execution_id` 与主表关联。
4. 允许每张表保留 `snapshot_json` 或 `details_json` 辅助字段，用于承载短期扩展信息，但不再让核心语义只存在于 JSON。

#### 适用理由

- 用户已明确选择显式结构优先
- `execution_status / gate_status / audit_status` 都是后续查询、恢复和审计的硬约束，适合显式列化
- 安全与最小权限隔离在显式表结构下更容易落地

#### 约束

- 显式列承载主语义，JSON 只能承载补充上下文
- `execution` 是唯一主实体，task / outcome / audit 都不能越权定义主状态

### DP-02 Gate 前集中落库屏障

#### 目标

在不引入额外中间件的前提下，让 `fail-closed` 真正发生在真实 scenario 执行之前。

#### 模式定义

把执行路径拆为两个连续阶段：

1. **阶段一：内存内 planning / gate 计算**
   - 标准化请求
   - capability plan
   - routing
   - authority
   - effective risk
   - gate 决策草案
2. **阶段二：进入 scenario 前的集中落库屏障**
   - 持久化 `session`（如需要）
   - 持久化 `execution` 主记录
   - 持久化 `gate_decision` 相关快照
   - 对高风险或策略要求的场景写入必要审计前置记录
   - 所有关键写入成功后，才允许进入真实 scenario 执行

#### 关键语义

- 阶段一允许纯内存计算，是为了压缩同步写入路径长度
- 阶段二是唯一的“允许执行前屏障”
- 任何阶段二失败都归类为基础设施不可用或持久化失败，并直接阻断真实执行

#### 为什么不是逐步边算边写

逐步边算边写会放大往返次数，增加 `p95` 开销，并让失败边界分散。
集中落库更符合用户对 `fail-closed + p95 < 500ms` 的双重要求。

### DP-03 执行内嵌审计状态跟踪

#### 目标

在不引入 Redis / Kafka / 独立队列系统的前提下，为中风险 `degraded` 路径建立“可追踪但不强制同步”的补审计模式。

#### 模式定义

1. 在 `execution` 主表中加入 `audit_status` 显式状态字段。
2. `audit_status` 建议至少支持：
   - `not_required`
   - `pending`
   - `persisted`
   - `failed`
3. 状态推进规则：
   - 高风险：必须直接进入 `persisted`，否则 execution 不得成功返回
   - 中风险 degraded：允许先置为 `pending`，随后由主流程尾段或恢复流程继续补写
   - 低风险且无需审计：置为 `not_required`
4. 一旦补写失败，必须显式转为 `failed`，并保留错误摘要与最后尝试时间。

#### 触发机制

- 优先由主流程在返回前做一次补写尝试
- 若仍未落成，则由 execution 恢复 / repair 流程二次推进
- 本单元不要求额外 outbox worker，先以 execution 状态机承接补写可追踪性

#### 优点

- 不增加新基础设施
- 能让 `degraded` 路径的“还没补审计”成为显式状态，而不是隐式丢失
- 与 execution 主体保持一致的恢复中心

### DP-04 Envelope-First 兼容适配

#### 目标

让 `Velaris` 内部 contract 一次性收束到 `DecisionExecutionEnvelope`，同时避免对现有调用方造成不必要的立即断裂。

#### 模式定义

1. `Velaris` 内部所有编排输出统一先组装为 `DecisionExecutionEnvelope`。
2. `biz_execute` 不再直接以旧平铺结构作为主输出，而是：
   - 主输出：完整 envelope
   - 最外层 alias：仅补 `session_id / result / outcome / audit_event_count`
3. `plan / routing / authority / task` 等对象进入 envelope 内部命名空间，不再作为长期顶层字段承诺。
4. `OpenHarness` 只做薄适配，不再承担内部语义翻译。

#### 兼容窗口策略

- 本单元内保留极少数 alias，满足最小调用兼容
- 新测试、新文档、新实现全部面向 envelope
- 后续单元可继续缩减 alias，而不应再扩大兼容面

### DP-05 默认脱敏持久化

#### 目标

确保长期存储中默认只保留“完成治理、恢复、审计所需的最小信息”，而不是原始敏感上下文。

#### 模式定义

1. 对进入 PostgreSQL 的 execution payload、audit payload 执行默认脱敏。
2. 默认长期持久化内容应为：
   - 脱敏摘要
   - 原因码
   - 决策上下文摘要
   - 恢复所需最小定位信息
3. 原始敏感字段只有在白名单明确声明“恢复必须依赖”时才允许落库存储。
4. 日志输出复用同一脱敏策略，不允许日志旁路泄漏原始敏感信息。

#### 脱敏原则

- 先删减，再替换，最后才局部保留
- 可恢复性优先依赖结构字段，不优先依赖原始敏感正文
- 不为“将来可能调试方便”保存原始敏感大字段

### DP-06 分层权限与失败分类

#### 目标

把 PostgreSQL 访问与错误语义都收束到一致的最小边界。

#### 模式定义

1. 权限分层：
   - 运行时写路径角色：写 execution / task / outcome / audit / session
   - 只读查询角色：只读 execution / outcome / audit 摘要
   - 运维修复角色：可推进 `audit_status` 与恢复相关字段
2. 失败分类：
   - `infrastructure_unavailable`：数据库不可用、事务失败、连接失败
   - `gate_denied`：治理拒绝，不是基础设施故障
   - `execution_failed`：已进入 scenario 后执行失败
3. 这些失败分类必须能进入 envelope / 错误返回 / 审计记录，而不是只保留异常堆栈文本。

#### 设计收益

- 支撑 fail-closed 与治理阻断的语义区分
- 限制 OpenHarness 直接访问原始敏感持久化内容
- 为后续 focused tests 和运维修复提供清晰状态面

### DP-07 单进程双阶段执行路径

#### 目标

在不引入新服务编排层的前提下，满足 `planning + gate` 额外开销 `p95 < 500ms`。

#### 模式定义

1. 保持当前单进程 orchestrator 主线。
2. 通过“先算后集中落库”减少数据库往返次数。
3. 把 envelope 组装、alias 适配和 payload 脱敏放在明确边界执行，避免重复序列化。
4. 高风险同步审计只保留最小前置事件，不在前置阶段写入过多冗余数据。

#### 性能约束

- 允许 planning / gate 在内存中完成
- 不允许为了追求极限性能而取消集中落库屏障
- 不允许通过恢复文件 / 内存回退绕过 PostgreSQL 主线

## 5. 模式间协同关系

这些模式组合后的完整路径如下：

1. `OpenHarness` 提交标准化请求
2. `Velaris` 在内存中完成 planning / routing / authority / effective risk / gate 草案
3. `PreExecutionPersistenceBarrier` 执行集中落库
4. 若屏障成功，则进入 scenario 执行
5. 执行结束后写入 outcome / task 收尾与审计推进
6. `EnvelopeAssembler` 组装主 envelope
7. `CompatibilityAliasAdapter` 在最外层补少量 alias
8. 输出前由 `PayloadRedactor` 再次确保对外最小暴露

## 6. 本阶段设计结论

`UOW-1` 的 NFR Design 已确定为：

- 五类核心对象进入显式关系型结构表，而不是继续以 payload 表为主
- `fail-closed` 通过“先算后集中落库”的双阶段屏障实现
- 中风险补审计通过 `execution.audit_status` 显式追踪，而不是依赖额外中间件
- `DecisionExecutionEnvelope` 成为唯一主 contract，兼容性通过薄 alias 层实现
- 默认持久化脱敏内容，原始敏感信息不进入长期存储，除非白名单明确允许
