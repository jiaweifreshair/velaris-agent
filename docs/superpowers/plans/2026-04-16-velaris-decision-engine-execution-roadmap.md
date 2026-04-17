# Velaris Decision Engine Execution Roadmap

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to执行当前任务；当进入具体实现阶段时，按阶段切换到对应的详细 plan。当前文档用于把设计 spec 拆成可落地、可 review、可回滚的执行顺序。

**Goal:** 把 `docs/superpowers/specs/2026-04-16-velaris-decision-engine-design.md` 拆成一组可以逐阶段交付的实施计划，并在进入每个下一阶段前用 gstack review 视角先收敛当前阶段风险与计划边界。

**Architecture:** 继续保持 `OpenHarness Runtime + Velaris Core + PostgreSQL + local evidence store` 的单体边界，不提前引入 Redis、Kafka、ClickHouse。执行顺序遵循“先收口持久化基座，再建立场景锚点与算子图，最后升级多目标求解、学习纠偏、rollup 分析”的路线。

**Tech Stack:** Python 3.11, PostgreSQL, psycopg 3, Pydantic 2, Typer, pytest, OpenHarness, Velaris Agent

---

## Current Baseline

- 当前工作分支是 `feat/phase1-persistence-foundation`，仓库内已经存在大量未提交变更，说明 `Phase 1` 实现正在进行中，后续执行必须避免覆盖现有修改。
- 仓库内已经有一份详细的 Phase 1 实施计划：`docs/superpowers/plans/2026-04-16-velaris-phase1-persistence-foundation.md`。
- 当前代码基线已经具备以下生产化雏形，可直接复用，不要推翻重写：
  - `src/velaris_agent/persistence/`：PostgreSQL schema / memory / runtime / job queue 雏形
  - `src/velaris_agent/velaris/orchestrator.py`：task / outcome / audit 三段式落盘入口
  - `src/velaris_agent/memory/`：preference / stakeholder / conflict / negotiation 基础模型
  - `src/velaris_agent/biz/engine.py`：场景识别、权重、评分、场景执行入口
- `procurement` 已经成为一等场景，`DecisionOptionSchema / DecisionAuditSchema / metrics registry` 已就位，可作为后续 operator graph 的稳定输入输出边界。
- `Phase 1` 的 3 个 review blocker 已完成修复：`psycopg` 延迟导入边界、`requires_audit` 场景下的严格审计、`job_runs` 的最小运行历史闭环。
- `Phase 2` 详细计划已经存在，且已完成一次 `/plan-eng-review` 风格收敛：当前 scope 明确为“只迁移 `procurement` 到 operator graph，`travel / tokencost / robotclaw` 保持 legacy 路径”。
- 当前仍未落地真正的 operator graph、Pareto frontier、learning v2 与 rollup pipeline，这些继续作为后续阶段增量建设。

## Status Snapshot

- `Task 1 / Phase 1 foundation`：已完成，并有 fresh verification 证据
- `Task 2 / procurement anchor + unified metrics registry`：已完成
- `Task 3 / Phase 2 detailed plan`：已完成，且已按工程评审收敛
- `Task 4 / Phase 3 detailed plan`：未开始
- `Task 5 / Phase 4 detailed plan`：未开始
- `Task 6 / Phase 5 detailed plan`：未开始
- `Task 7 / Phase 6 deferred gate`：未开始

## File Structure

### Existing Assets To Reuse

- `docs/superpowers/specs/2026-04-16-velaris-decision-engine-design.md`
- `docs/superpowers/plans/2026-04-16-velaris-phase1-persistence-foundation.md`
- `src/velaris_agent/biz/engine.py`
- `src/velaris_agent/memory/types.py`
- `src/velaris_agent/memory/preference_learner.py`
- `src/velaris_agent/memory/conflict_engine.py`
- `src/velaris_agent/memory/negotiation.py`
- `src/velaris_agent/persistence/schema.py`
- `src/velaris_agent/persistence/postgres_memory.py`
- `src/velaris_agent/persistence/postgres_runtime.py`
- `src/velaris_agent/persistence/job_queue.py`
- `src/velaris_agent/velaris/orchestrator.py`

### Detailed Plan Files

- Ready: `docs/superpowers/plans/2026-04-16-velaris-phase2-operator-graph.md`
- `docs/superpowers/plans/2026-04-16-velaris-phase3-multi-objective-solver.md`
- `docs/superpowers/plans/2026-04-16-velaris-phase4-learning-and-bias.md`
- `docs/superpowers/plans/2026-04-16-velaris-phase5-analytics-rollup.md`

---

### Task 1: 收口并复核当前 Phase 1 分支

**Files:**
- Review: `docs/superpowers/plans/2026-04-16-velaris-phase1-persistence-foundation.md`
- Review: `src/velaris_agent/persistence/__init__.py`
- Review: `src/velaris_agent/persistence/schema.py`
- Review: `src/velaris_agent/persistence/postgres_runtime.py`
- Review: `src/velaris_agent/persistence/job_queue.py`
- Review: `src/velaris_agent/velaris/orchestrator.py`
- Test: `tests/test_persistence/test_schema.py`
- Test: `tests/test_persistence/test_postgres.py`
- Test: `tests/test_persistence/test_postgres_memory.py`
- Test: `tests/test_persistence/test_postgres_runtime.py`
- Test: `tests/test_persistence/test_job_queue.py`
- Test: `tests/test_biz/test_orchestrator.py`

- [x] **Step 1: 对照现有 Phase 1 plan 与当前分支 diff 做一次 review 收口**

Run:
```bash
git diff --stat main -- src/velaris_agent src/openharness docs/superpowers
```

Expected:
- 明确 `Phase 1` 已覆盖的文件范围
- 把本文件 `## GSTACK REVIEW REPORT` 中列出的阻塞项全部转成待修复清单

- [x] **Step 2: 修掉 Phase 1 的 review blocker，再进入下一阶段**

Run:
```bash
rg -n "postgres_connection|job_runs|append_event|requires_audit" src/velaris_agent
```

Expected:
- `postgres` 相关导入不再破坏“未启用 PostgreSQL 时也能 import”的兼容性
- `job_runs` 不再只是空表，而是有最小写入闭环
- `requires_audit` 场景下不会静默丢失审计事件

- [x] **Step 3: 在项目指定 Python 3.11 环境内重跑 Phase 1 相关测试**

Run:
```bash
./scripts/run_pytest.sh tests/test_persistence/test_schema.py tests/test_persistence/test_postgres.py tests/test_persistence/test_postgres_memory.py tests/test_persistence/test_postgres_runtime.py tests/test_persistence/test_job_queue.py tests/test_biz/test_orchestrator.py -q
```

Expected:
- 所有 `Phase 1` 相关测试通过
- 若失败，失败原因必须区分为“环境问题”还是“代码问题”

- [x] **Step 4: 完成一次 gstack review 风格复核并更新 Phase 1 plan 状态**

Expected:
- Phase 1 计划文件里标出已完成任务、剩余 blocker、验证命令
- 没有 fresh verification 证据时，不进入 Phase 2

Observed:
- `18 passed, 3 skipped`

Acceptance:
- `Phase 1` 已具备继续进入 `Phase 2` 的验证门槛
- 后续所有 Python 验证统一走 `./scripts/run_pytest.sh`

---

### Task 2: 补齐 Phase 0 场景锚点，避免后续架构升级失焦

**Files:**
- Modify: `src/velaris_agent/biz/engine.py`
- Modify: `src/velaris_agent/memory/types.py`
- Create: `src/velaris_agent/scenarios/procurement/__init__.py`
- Create: `src/velaris_agent/scenarios/procurement/types.py`
- Create: `tests/test_biz/test_engine_procurement.py`
- Create: `tests/test_memory/test_decision_metrics_registry.py`
- Plan Output: `docs/superpowers/plans/2026-04-16-velaris-phase2-operator-graph.md`

- [x] **Step 1: 先写 `procurement` 场景与指标字典的失败测试**
- [x] **Step 2: 把企业采购 / 合规审计加入场景识别、默认权重与治理配置**
- [x] **Step 3: 固化统一 option schema / audit schema / metrics registry**
- [x] **Step 4: 为 Phase 2 算子化计划准备稳定输入输出模型**

Verification:
```bash
./scripts/run_pytest.sh tests/test_biz/test_engine_procurement.py tests/test_memory/test_decision_metrics_registry.py tests/test_biz/test_engine.py tests/test_biz/test_orchestrator.py -q
```

Observed:
- `19 passed, 1 skipped`

Acceptance:
- `procurement` 成为一等场景，而不是继续落到 `general`
- 指标字典可同时被 `travel / tokencost / robotclaw / procurement` 复用

---

### Task 3: 产出 Phase 2 详细计划，聚焦 operator graph

**Files:**
- Plan Input: `docs/superpowers/specs/2026-04-16-velaris-decision-engine-design.md`
- Plan Input: `src/velaris_agent/biz/engine.py`
- Plan Input: `src/velaris_agent/memory/conflict_engine.py`
- Plan Input: `src/velaris_agent/memory/negotiation.py`
- Plan Input: `src/velaris_agent/velaris/orchestrator.py`
- Plan Output: `docs/superpowers/plans/2026-04-16-velaris-phase2-operator-graph.md`

- [x] **Step 1: 把 `IntentOp / OptionDiscoveryOp / NormalizationOp / StakeholderOp / OptimizationOp / NegotiationOp / BiasAuditOp / ExplanationOp` 拆成独立模块**
- [x] **Step 2: 明确 operator contract、registry、execution trace 的文件边界**
- [x] **Step 3: 给每个算子计划对应失败测试、最小实现、验证命令**
- [x] **Step 4: 确保 Phase 2 plan 不直接改 UI / CLI，只改决策内核**

Output:
- `docs/superpowers/plans/2026-04-16-velaris-phase2-operator-graph.md`

Review Status:
- 已完成 `/plan-eng-review` 风格收敛
- 当前计划明确收敛到 `procurement` 单场景迁移
- registry 是编排单一真相，`accepted / rejected / rejection_reasons` 已进入 Phase 2 contract
- legacy adapter 要保留完整 `options / recommended / summary / audit_trace`

Acceptance:
- `biz/engine.py` 不再继续膨胀为“上帝文件”
- 每个算子都能输出 `operator_id / operator_version / confidence / evidence_refs / warnings`
- 非 `procurement` 场景在 Phase 2 不改协议，只保持 legacy 路径稳定

---

### Task 4: 产出 Phase 3 详细计划，升级多目标求解

**Files:**
- Plan Input: `src/velaris_agent/biz/engine.py`
- Plan Input: `src/velaris_agent/memory/types.py`
- Plan Output: `docs/superpowers/plans/2026-04-16-velaris-phase3-multi-objective-solver.md`

- [ ] **Step 1: 定义 `FeasibilityOp` 与可行域 schema**
- [ ] **Step 2: 定义 `ParetoFrontierOp` 与 frontier 输出模型**
- [ ] **Step 3: 定义 `OperatingPointSelector` 与当前落点解释**
- [ ] **Step 4: 让 weighted-sum 退到 operating point 选择阶段**

Acceptance:
- 不再把加权和当成唯一排序器
- 推荐结果能解释“为什么这个点在前沿上被选中”

---

### Task 5: 产出 Phase 4 详细计划，升级学习与纠偏

**Files:**
- Plan Input: `src/velaris_agent/memory/preference_learner.py`
- Plan Input: `src/velaris_agent/memory/types.py`
- Plan Output: `docs/superpowers/plans/2026-04-16-velaris-phase4-learning-and-bias.md`

- [ ] **Step 1: 设计 user / org / cohort 三层偏好融合模型**
- [ ] **Step 2: 设计 regret / calibration / counterfactual bias audit 的数据结构**
- [ ] **Step 3: 设计 preference profile v2 与 bias audit v2 的回写链路**
- [ ] **Step 4: 明确哪些信号进入在线推荐，哪些信号进入离线调优**

Acceptance:
- 偏好学习与偏差检测从启发式函数升级为可审计的数据产物
- 新模型不会破坏现有 `travel / tokencost / robotclaw` 回归测试

---

### Task 6: 产出 Phase 5 详细计划，升级 rollup 与分析平台

**Files:**
- Plan Input: `src/velaris_agent/persistence/job_queue.py`
- Plan Input: `src/velaris_agent/persistence/postgres_runtime.py`
- Plan Input: `src/velaris_agent/memory/types.py`
- Plan Output: `docs/superpowers/plans/2026-04-16-velaris-phase5-analytics-rollup.md`

- [ ] **Step 1: 设计 decision curve 原子事件与 rollup 表结构**
- [ ] **Step 2: 设计单进程 worker 下的定时汇总命令**
- [ ] **Step 3: 设计 user / org / scenario / operator 四类聚合输出**
- [ ] **Step 4: 为 dashboard-ready dataset 定义最小查询接口**

Acceptance:
- 能输出可追踪的 rollup lag / failed jobs / audit completeness 指标
- 保持“单体 + PostgreSQL + local evidence store”，不提前引入中间件

---

### Task 7: Phase 6 保持 deferred，只定义触发条件

**Files:**
- Reference: `docs/superpowers/specs/2026-04-16-velaris-decision-engine-design.md`

- [ ] **Step 1: 记录进入事件化架构的阈值**
- [ ] **Step 2: 记录需要观测的瓶颈指标**
- [ ] **Step 3: 只有当单体 worker 与 PostgreSQL rollup 明确成为瓶颈时，才新写 Phase 6 计划**

Acceptance:
- 当前阶段不引入 Kafka / Redpanda / ClickHouse
- Phase 6 只是升级预案，不抢占前 5 个阶段的交付资源

---

## GSTACK REVIEW REPORT

### Current Findings

1. **Resolved / High** `psycopg` import boundary 已修复，未启用 PostgreSQL 时不再因为导入时机导致测试或默认文件后端路径直接崩掉。
2. **Resolved / High** `requires_audit` 场景下的审计落盘已改为严格行为，不再 silently 丢失高风险审计事件。
3. **Resolved / Medium** `job_runs` 已接入最小运行历史写入闭环，为后续失败分析、重放与 worker 健康诊断保留基础证据。
4. **Open / Medium** `Phase 2` 仍保留 `weighted-sum` 作为 `OptimizationOp` 的临时排序器；`FeasibilityOp / ParetoFrontierOp / OperatingPointSelector` 延后到 `Phase 3` 落地。

### Fresh Verification Notes

- `./scripts/run_pytest.sh tests/test_persistence/test_schema.py tests/test_persistence/test_postgres.py tests/test_persistence/test_postgres_memory.py tests/test_persistence/test_postgres_runtime.py tests/test_persistence/test_job_queue.py tests/test_biz/test_orchestrator.py -q`
  - `18 passed, 3 skipped`
- `./scripts/run_pytest.sh tests/test_biz/test_engine.py tests/test_biz/test_engine_procurement.py tests/test_memory/test_decision_metrics_registry.py tests/test_biz/test_orchestrator.py -q`
  - `19 passed, 1 skipped`
- `docs/superpowers/plans/2026-04-16-velaris-phase2-operator-graph.md`
  - 已完成一次 `/plan-eng-review` 风格收敛，当前 verdict 为 `READY FOR EXECUTION AFTER REVISION`

## Recommended Execution Order

1. 直接按已收敛的 `docs/superpowers/plans/2026-04-16-velaris-phase2-operator-graph.md` 开始 `procurement` 单场景 operator graph 实现。
2. Phase 2 落地时严格保持 `travel / tokencost / robotclaw` 走 legacy 路径，不在本阶段修改它们的协议。
3. `Phase 3` 单独产出多目标求解计划，把 `FeasibilityOp / ParetoFrontierOp / OperatingPointSelector` 接上，替换当前临时 weighted-sum 排序。
4. `Phase 4`、`Phase 5` 各自独立成 plan，逐个落地、逐个 review。
5. `Phase 6` 保持 deferred，直到单体架构真的出现吞吐和分析瓶颈。
