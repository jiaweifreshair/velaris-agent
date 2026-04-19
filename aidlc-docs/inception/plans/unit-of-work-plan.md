# Unit Of Work Plan

## 拆分目标

本轮 `Units Generation` 针对的是 Brownfield 单仓库架构收束工作，
这里的“Unit of Work”定义为**可独立规划、可独立落地、可独立判断完成的最小变更单元**，
而不是新的独立部署服务。

结合用户这轮修改意见，本计划不再追求“覆盖更多面”，
而是优先追求 **精简、最快实现、最小但干净且可运行** 的收束路径。

因此，本轮只围绕以下主轴拆分工作单元：

1. `Velaris` / `OpenHarness` 边界与核心 contract
2. 默认状态链与持久化语义统一
3. `session resume` 与 `execution resume` 边界明确
4. 为最小可运行闭环保留必要的 orchestrator / tool 对接

## 拆分原则

1. 以“范围收缩”优先于“能力扩张”
2. 以“默认路径语义统一”优先于“增强路径能力扩展”
3. 以“最小干净可运行”优先于“文档面面俱到”
4. 采用 **Sequential** 方式推进，不并行、不拆新部署单元
5. 持久化相关问题不再分散表达，而是集中在统一的默认状态链单元中处理
6. `unit-of-work-story-map.md` 因本轮 `User Stories` 跳过，将采用 **Core FR / Supporting FR / NFR / Construction Intent** 映射替代传统 story mapping

## 用户修改意见吸收结果

根据 `aidlc-docs/inception/plans/unit-of-work-plan-change-questions.md` 中的答复，本计划做出以下调整：

1. **主修改方向**：从“完整覆盖多侧面”调整为“范围控制优先”，尤其强调持久化语义统一
2. **粒度策略**：不预设更多单元，而采用更精简的最小单元集合
3. **顺序策略**：保持 `Architecture Boundary Contract` 作为第一主线
4. **范围策略**：进一步聚焦，只保留 contract + 默认状态链 + resume 边界
5. **完成标准**：先以架构语义清晰为主，验证细节在后续设计阶段补强，不再在本阶段展开过多验证设计

## Clarification Status

本轮不新增新的 `[Answer]:` 跟进问题，原因如下：

1. 用户回答虽然使用了自由补充说明，但整体方向一致
2. 这些答案共同指向“更小范围、更快落地、先统一边界与持久化语义”
3. 已足够支撑对工作单元计划进行重写

## Unit Strategy

- **拆分粒度**: 最小变更单元（minimum viable change unit）
- **目标单元数**: 3
- **执行方式**: 顺序式推进
- **主优先级**:
  - P1: contract 边界清晰
  - P2: 默认状态链与持久化语义统一
  - P3: 最小可运行闭环对接
- **主要输入**:
  - `aidlc-docs/inception/requirements/requirements.md`
  - `aidlc-docs/inception/plans/execution-plan.md`
  - `aidlc-docs/inception/application-design/components.md`
  - `aidlc-docs/inception/application-design/component-methods.md`
  - `aidlc-docs/inception/application-design/services.md`
  - `aidlc-docs/inception/application-design/component-dependency.md`
  - `aidlc-docs/inception/plans/unit-of-work-plan-change-questions.md`
  - 相关代码边界：`src/velaris_agent/velaris/`、`src/velaris_agent/persistence/`、`src/openharness/tools/biz_execute_tool.py`、`src/openharness/services/session_storage.py`
- **主要输出**:
  - `aidlc-docs/inception/application-design/unit-of-work.md`
  - `aidlc-docs/inception/application-design/unit-of-work-dependency.md`
  - `aidlc-docs/inception/application-design/unit-of-work-story-map.md`

## Planned Units

### Unit 1 - Architecture Boundary And Core Contract
- **目标**:
  - 收束 `Velaris` 与 `OpenHarness` 的正式边界
  - 明确 `execution / state / completion / resume` 的核心 contract
  - 明确“会话”与“业务执行”不是同一层级
- **聚焦对象**:
  - 决策入口层
  - 治理层
  - 执行主语义层
  - 状态契约层
- **本单元必须回答的问题**:
  - 谁定义 execution-level 语义
  - 谁拥有 completion 语义
  - 谁拥有 resume 语义
  - `OpenHarness` 到 `Velaris` 的最小桥接边界是什么
- **非目标**:
  - 不展开完整测试设计
  - 不扩写全部工具面
  - 不单独展开文档整修工程

### Unit 2 - Default State Chain And Persistence Unification
- **目标**:
  - 统一默认路径下的状态真相源表达
  - 把 `task / outcome / audit / memory / snapshot` 的角色边界讲清楚
  - 明确默认 durable 路径与 PostgreSQL 增强路径的语义关系
  - 明确 `session resume != execution resume`
- **聚焦对象**:
  - `persistence.factory`
  - runtime stores
  - session storage
  - execution snapshot / outcome snapshot / audit snapshot 边界
- **本单元必须回答的问题**:
  - 默认路径下什么是主状态，什么是派生状态
  - 哪些对象必须可恢复，哪些可以重建
  - 持久化如何做到“统一语义，不强依赖 PostgreSQL”
- **非目标**:
  - 不引入新的中间件
  - 不把 PostgreSQL 提升为默认语义成立前提
  - 不做超出本轮范围的长期学习系统重构

### Unit 3 - Minimal Runtime Convergence
- **目标**:
  - 在前两个单元的基础上，为最小可运行闭环保留必要的 orchestrator / tool 对接
  - 只收束关键入口，使默认路径语义能落到一个最小调用面
  - 把必须同步的文档表述作为该单元的附属交付，而不是独立大单元
- **聚焦对象**:
  - `VelarisBizOrchestrator`
  - `biz_execute` 工具面
  - 最小必要的文档同步
- **本单元必须回答的问题**:
  - 最小闭环入口返回什么结构才算语义一致
  - 哪些文档表述必须同步，才能避免对外叙事继续跑偏
- **非目标**:
  - 不扩展更多场景工具
  - 不在本单元中展开完整验证矩阵
  - 不把 README / 全套文档清理做成独立工程

## Scope Handling

### Core Scope
本轮工作单元必须优先覆盖：
- FR-1 定位收束
- FR-2 一等执行单元
- FR-3 默认状态链说明清晰
- FR-4 完成 contract
- FR-5 恢复 contract
- NFR-2 默认路径优先
- NFR-4 控制复杂度

### Supporting Scope
以下内容不再作为独立大单元处理，而是折叠到核心单元中最小化处理：
- FR-6 授权到执行门
- FR-7 文档与实现一致性
- NFR-3 可验证性（只保留最小闭环证明要求，不在本阶段展开详细验证设计）

### Deferred Detail
以下内容明确留到后续设计阶段补强：
- 完整 focused test / contract test 设计
- 更完整的工具面对齐
- 更广范围的文档体系同步

## Generation Steps

- [x] 读取已批准的 requirements、workflow planning、application design、变更问题答案以及关键代码边界，确认新的最小化拆分基线
- [x] 生成 `aidlc-docs/inception/application-design/unit-of-work.md`，定义 3 个工作单元的目标、范围、关键问题、主要改动对象与最小完成标准
- [x] 在 `unit-of-work.md` 中明确每个工作单元的非目标（out of scope），确保本轮不再次横向扩张
- [x] 生成 `aidlc-docs/inception/application-design/unit-of-work-dependency.md`，说明 3 个工作单元的前后依赖、阻塞关系与关键 contract 交汇点
- [x] 生成 `aidlc-docs/inception/application-design/unit-of-work-story-map.md`，采用 Core FR / Supporting FR / NFR / Construction Intent 映射方式替代传统 story map
- [x] 校验核心范围中的 FR-1 至 FR-5 以及 NFR-2、NFR-4 至少映射到一个工作单元
- [x] 校验 FR-6、FR-7、NFR-3 被明确标记为“折叠处理”或“后续补强”，避免丢失追踪关系
- [x] 校验工作单元顺序体现“先边界 contract，再状态链统一，最后最小运行闭环”的主线
- [x] 校验工作单元拆分不会错误引入“新增部署服务”“先做大范围文档工程”或“默认依赖 PostgreSQL 才成立”的设计偏移
- [x] 汇总 revised Units Generation 结果并准备重新审批消息

## Approval Target

当以上修订版计划获批后，下一步将进入 `Units Generation` 的产物生成，届时会按该精简计划产出正式工作单元文档。
