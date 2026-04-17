# 依赖关系文档

## 包间依赖

```
velaris_agent  ──依赖──►  openharness
     │
     ├── velaris_agent.biz.engine      (独立，可选依赖 stakeholder)
     ├── velaris_agent.velaris.*       (独立，互相依赖)
     │     ├── router                  (依赖 YAML 配置)
     │     ├── authority               (无外部依赖)
     │     ├── task_ledger             (无外部依赖)
     │     ├── outcome_store           (无外部依赖)
     │     └── orchestrator            (依赖上述四个 + biz.engine)
     ├── velaris_agent.memory.*        (核心依赖链)
     │     ├── types                   (Pydantic 模型，无外部依赖)
     │     ├── decision_memory         (依赖 types)
     │     ├── preference_learner      (依赖 decision_memory)
     │     ├── stakeholder             (依赖 types)
     │     ├── conflict_engine         (依赖 types)
     │     └── negotiation             (依赖 types)
     ├── velaris_agent.evolution.*     (依赖 memory)
     │     └── self_evolution          (依赖 decision_memory + preference_learner)
     ├── velaris_agent.knowledge.*     (独立)
     └── velaris_agent.persistence.*   (依赖 memory.types)
```

## 组件依赖矩阵

| 组件　　　　　　　　　| 依赖　　　　　　　　　　　　　　　　　　　　　　　　　　　|
| -----------------------| -----------------------------------------------------------|
| QueryEngine　　　　　 | API Client, ToolRegistry, PermissionChecker, HookExecutor |
| BizEngine　　　　　　 | StakeholderMapModel (可选)　　　　　　　　　　　　　　　　|
| PolicyRouter　　　　　| YAML 配置文件　　　　　　　　　　　　　　　　　　　　　　 |
| AuthorityService　　　| 无　　　　　　　　　　　　　　　　　　　　　　　　　　　　|
| TaskLedger　　　　　　| 无　　　　　　　　　　　　　　　　　　　　　　　　　　　　|
| OutcomeStore　　　　　| 无　　　　　　　　　　　　　　　　　　　　　　　　　　　　|
| Orchestrator　　　　　| Router + Authority + Ledger + Outcome + BizEngine　　　　 |
| DecisionMemory　　　　| 文件系统　　　　　　　　　　　　　　　　　　　　　　　　　|
| PreferenceLearner　　 | DecisionMemory　　　　　　　　　　　　　　　　　　　　　　|
| SelfEvolutionEngine　 | DecisionMemory + PreferenceLearner　　　　　　　　　　　　|
| StakeholderRegistry　 | 无　　　　　　　　　　　　　　　　　　　　　　　　　　　　|
| PersonalKnowledgeBase | 文件系统　　　　　　　　　　　　　　　　　　　　　　　　　|
| SkillHub　　　　　　　| httpx (GitHub API), 文件系统　　　　　　　　　　　　　　　|
| CommandGuard　　　　　| 无　　　　　　　　　　　　　　　　　　　　　　　　　　　　|

## 外部依赖分析

### 运行时必需
- `anthropic` / `openai`: LLM API 调用（至少需要一个）
- `pydantic`: 数据模型验证（核心依赖）
- `rich`: 终端输出（CLI 必需）
- `typer`: CLI 框架
- `httpx`: HTTP 客户端（MCP、技能中心等）
- `pyyaml`: 路由策略配置

### 运行时可选
- `psycopg`: PostgreSQL 持久化（当前可用文件后端替代）
- `websockets`: WebSocket MCP transport
- `mcp`: MCP 协议（不使用 MCP 工具时可选）
- `textual`: TUI 界面
- `watchfiles`: 文件变更监听
- `pyperclip`: 剪贴板

### 数据流依赖
```
用户输入 → QueryEngine → ToolRegistry → 具体 Tool
                                           │
                              ┌────────────┼────────────┐
                              ▼            ▼            ▼
                         BizEngine    DecisionMemory  KnowledgeBase
                              │            │
                              ▼            ▼
                         Orchestrator  PreferenceLearner
                              │            │
                    ┌─────────┼─────┐      ▼
                    ▼         ▼     ▼  SelfEvolution
                 Router  Authority Ledger
                    │         │     │
                    ▼         ▼     ▼
                 YAML配置   令牌   内存/DB
```
