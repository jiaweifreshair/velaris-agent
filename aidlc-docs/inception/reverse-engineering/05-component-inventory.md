# 组件清单

## 核心组件

### 1. QueryEngine (Agent 循环)
- **位置**: `src/openharness/engine/query_engine.py`
- **依赖**: API Client, ToolRegistry, PermissionChecker, HookExecutor
- **职责**: 管理对话历史、流式推理、工具调用编排、后台技能复盘
- **状态**: 生产就绪

### 2. BizEngine (场景引擎)
- **位置**: `src/velaris_agent/biz/engine.py`
- **依赖**: StakeholderMapModel (可选)
- **职责**: 场景识别、能力规划、多维评分、场景执行分发
- **关键函数**: `infer_scenario`, `build_capability_plan`, `score_options`, `run_scenario`
- **状态**: 生产就绪，但场景注册为硬编码

### 3. PolicyRouter (策略路由)
- **位置**: `src/velaris_agent/velaris/router.py`
- **依赖**: YAML 策略文件 (`config/routing-policy.yaml`)
- **职责**: 基于规则引擎选择执行策略
- **状态**: 生产就绪，静态规则

### 4. AuthorityService (能力签发)
- **位置**: `src/velaris_agent/velaris/authority.py`
- **依赖**: 无外部依赖
- **职责**: 签发短时能力令牌
- **状态**: 生产就绪

### 5. TaskLedger (任务账本)
- **位置**: `src/velaris_agent/velaris/task_ledger.py`
- **依赖**: 无外部依赖
- **职责**: 任务状态跟踪
- **状态**: 内存实现，重启丢失 (P0 待改进)

### 6. OutcomeStore (结果存储)
- **位置**: `src/velaris_agent/velaris/outcome_store.py`
- **依赖**: 无外部依赖
- **职责**: 业务执行结果记录
- **状态**: 内存实现，重启丢失 (P0 待改进)

### 7. VelarisBizOrchestrator (业务编排器)
- **位置**: `src/velaris_agent/velaris/orchestrator.py`
- **依赖**: PolicyRouter, AuthorityService, TaskLedger, OutcomeStore, AuditStore (可选)
- **职责**: 串联完整业务闭环
- **状态**: 生产就绪

### 8. DecisionMemory (决策记忆)
- **位置**: `src/velaris_agent/memory/decision_memory.py`
- **依赖**: 文件系统 (`~/.velaris/decisions/`)
- **职责**: 决策记录存储、检索、反馈闭环
- **状态**: 生产就绪 (文件后端)

### 9. PreferenceLearner (偏好学习)
- **位置**: `src/velaris_agent/memory/preference_learner.py`
- **依赖**: DecisionMemory
- **职责**: 个性化权重学习、偏差检测、对齐分析
- **算法**: 贝叶斯先验 + 指数衰减 + 归一化
- **状态**: 生产就绪

### 10. SelfEvolutionEngine (自进化)
- **位置**: `src/velaris_agent/evolution/self_evolution.py`
- **依赖**: DecisionMemory, PreferenceLearner
- **职责**: 历史决策回顾、优化建议生成
- **状态**: 生产就绪

### 11. StakeholderRegistry (利益相关者)
- **位置**: `src/velaris_agent/memory/stakeholder.py`
- **依赖**: 无外部依赖
- **职责**: 利益相关者注册、决策曲线追踪
- **状态**: 生产就绪

### 12. PersonalKnowledgeBase (个人知识库)
- **位置**: `src/velaris_agent/knowledge/base.py`
- **依赖**: 文件系统
- **职责**: 资料摄取、搜索、健康检查
- **状态**: 生产就绪

### 13. SkillHub (技能中心)
- **位置**: `src/openharness/skills/hub.py`
- **依赖**: GitHub API (可选), 文件系统
- **职责**: 技能发现、安装、卸载、更新、安全扫描
- **状态**: 生产就绪

### 14. CommandGuard (命令守卫)
- **位置**: `src/openharness/security/command_guard.py`
- **依赖**: 无外部依赖
- **职责**: 危险命令识别、审批分级
- **状态**: 生产就绪

## 安全组件

| 组件 | 位置 | 职责 |
|------|------|------|
| CommandGuard | `security/command_guard.py` | 危险命令识别 + 审批 |
| ContextGuard | `security/context_guard.py` | 上下文注入扫描 |
| FileGuard | `security/file_guard.py` | 文件系统边界保护 |
| McpGuard | `security/mcp_guard.py` | MCP 凭据过滤 |
| Redaction | `security/redaction.py` | 敏感输出脱敏 |
| SessionState | `security/session_state.py` | 会话级审批状态 |

## 基础设施组件 (OpenHarness 继承)

| 子系统　　　| 说明　　　　　　　　　　　　 |
| -------------| ------------------------------|
| Engine　　　| 核心 Agent 循环　　　　　　　|
| Tools　　　 | 60+ 内置工具　　　　　　　　 |
| Skills　　　| Markdown 知识注入　　　　　　|
| Plugins　　 | 插件发现/加载/生命周期　　　 |
| Permissions | 多级权限 (tool/file/command) |
| Hooks　　　 | 生命周期事件　　　　　　　　 |
| Memory　　　| 基础记忆系统　　　　　　　　 |
| Swarm　　　 | 多 Agent 协调　　　　　　　　|
| Tasks　　　 | 后台任务管理　　　　　　　　 |
| MCP　　　　 | Model Context Protocol 集成　|
