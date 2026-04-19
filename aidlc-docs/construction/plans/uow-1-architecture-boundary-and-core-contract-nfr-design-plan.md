# UOW-1 NFR Design Plan

## 单元范围

- **Unit**: `UOW-1 - Architecture Boundary And Core Contract`
- **阶段**: NFR Design
- **目标**:
  - 把已批准的 NFR Requirements 落为可执行的设计模式与逻辑组件
  - 为 PostgreSQL 主存储、fail-closed、同步/补审计、envelope 兼容与安全隔离建立明确设计策略
  - 为下一阶段 Code Generation 提供可直接落地的 NFR 设计输入

## 已知输入

1. `UOW-1 Functional Design` 已批准
2. `UOW-1 NFR Requirements` 已批准并确认以下约束：
   - `execution / task / outcome / audit / session` 统一进入 PostgreSQL 主线
   - PostgreSQL 不可用时默认 `fail-closed`
   - 高风险同步审计，中风险允许 `degraded` 继续但补审计必须可追踪
   - `planning + gate` 额外开销目标为 `p95 < 500ms`
   - `DecisionExecutionEnvelope` 为主 contract，仅保留极少数兼容 alias
3. 当前代码仍存在以下差距：
   - `src/velaris_agent/persistence/factory.py` 仍把 PostgreSQL 视为显式开启的增强路径
   - `src/openharness/services/session_storage.py` 仍是文件型 session snapshot
   - `src/velaris_agent/velaris/orchestrator.py` 尚未围绕 `execution + gate_decision + envelope` 收束
   - `src/openharness/tools/biz_execute_tool.py` 仍直接返回平铺 payload

## NFR Design Steps

- [x] 复核 `functional-design/` 与 `nfr-requirements/` 中对 execution、gate、audit、session、envelope 的已批准约束
- [x] 选择 PostgreSQL 主存储的逻辑建模模式，明确哪些对象采用显式核心列、哪些对象保留 snapshot / payload 模式
- [x] 设计 fail-closed 与 gate 前置落库模式，确保真实 scenario 执行前完成关键持久化屏障
- [x] 设计高风险同步审计与中风险补审计的模式，明确是否需要 PostgreSQL 内 outbox / retry 组件
- [x] 设计 `DecisionExecutionEnvelope` 的兼容扩展模式，明确 alias 保留位置与过渡边界
- [x] 设计 payload 脱敏、权限隔离与日志最小暴露的安全模式
- [x] 生成 `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/nfr-design/nfr-design-patterns.md`
- [x] 生成 `aidlc-docs/construction/uow-1-architecture-boundary-and-core-contract/nfr-design/logical-components.md`
- [x] 校验 NFR Design 与 Functional Design / NFR Requirements / PostgreSQL 主线约束一致

## 需要你确认的问题

下面的问题将直接影响本单元 NFR Design 中的模式选择与逻辑组件拆分，请填写 `[Answer]:`。

## Question 1

对于 PostgreSQL 主存储的逻辑建模，你更希望本单元采用哪种主模式？

A) `execution / session` 使用显式核心列 + snapshot 字段，`task / outcome / audit` 继续保留最小 payload 表模式
B) 五类对象都继续沿用统一 payload 表思路，先不引入更多显式列
C) `execution / session / task / outcome / audit` 全部做成更明确的显式结构表，尽量少依赖 payload snapshot
D) Other（请在 [Answer]: 后补充说明）

[Answer]: C

## Question 2

关于 fail-closed 的持久化屏障，你更希望哪种设计？

A) 在真实 scenario 执行前，先同步完成 `execution` 创建、`gate_decision` 持久化以及必要审计前置；任一步失败都直接阻断
B) 允许先在内存里完成 planning / gate，再在进入 scenario 前做一次集中落库；集中落库失败则阻断
C) 只要求高风险路径严格前置落库，低/中风险允许部分对象在执行后补写
D) Other（请在 [Answer]: 后补充说明）

[Answer]: B

## Question 3

对于中风险 `degraded` 路径的“补审计必须可追踪”，你更倾向哪种模式？

A) 在 PostgreSQL 内增加 outbox / retry job 表，由后台 worker 负责补审计
B) 在 `execution` 主记录中维护 `audit_status`（如 pending / persisted / failed），由主流程或后续恢复流程触发补写
C) 直接把中风险也提升为同步审计，放弃异步补审计设计，优先简化一致性
D) Other（请在 [Answer]: 后补充说明）

[Answer]: B

## Question 4

关于 `DecisionExecutionEnvelope` 的兼容落地，你更希望哪种适配模式？

A) 内部实现全面切到 envelope，`biz_execute` 仅在最外层补少量 alias，兼容窗口只保留本阶段最小集合
B) 内部与外部都暂时双轨输出一段时间，直到后续单元再完全收束到 envelope
C) 在 `OpenHarness` 桥接层做较厚适配，Velaris 内部可以暂时不完全收束
D) Other（请在 [Answer]: 后补充说明）

[Answer]: A

## Question 5

关于敏感 payload 的保护模式，你更希望本单元优先采用哪种设计？

A) 默认只持久化脱敏后的 payload / audit 内容，原始敏感数据除非白名单明确允许，否则不落长期存储
B) 允许持久化原始 payload，但必须通过严格角色隔离和序列化脱敏控制对外暴露
C) 把敏感原始内容拆到受限子载体（如受限字段区或受限附表），主 execution / audit 只保留脱敏摘要
D) Other（请在 [Answer]: 后补充说明）

[Answer]: A
