# 代码结构文档

## 顶层目录
```
velaris-agent/
├── src/                    # 源码
│   ├── openharness/        # 基础设施层 (Agent Runtime)
│   └── velaris_agent/      # 业务层 (Decision Intelligence)
├── tests/                  # 测试集
├── config/                 # 路由策略配置
├── docs/                   # 技术文档
├── scripts/                # 开发/测试脚本
├── frontend/               # 终端前端实验
├── assets/                 # 静态资源
├── _archive_ts/            # TypeScript 归档代码
├── pyproject.toml          # 项目配置 (hatchling)
└── uv.lock                 # 依赖锁文件
```

## src/openharness/ — 基础设施层

### engine/ — Agent 核心循环
| 文件 | 职责 |
|------|------|
| `query_engine.py` | 会话引擎：管理对话历史、工具注册、权限检查、后台技能复盘 |
| `query.py` | 底层查询循环：流式 LLM 推理 + 工具调用编排 |
| `messages.py` | 对话消息数据结构 (ConversationMessage) |
| `stream_events.py` | 流式事件类型定义 |
| `cost_tracker.py` | Token 用量与成本追踪 |

### tools/ — 工具系统 (60+ 工具)
| 类别　　　| 工具文件　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　| 说明　　　　　　　　　　　　　　　　　　|
| -----------| ---------------------------------------------------------------------------------------| -----------------------------------------|
| **基础**　| `base.py`　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　 | BaseTool 抽象、ToolRegistry、ToolResult |
| **文件**　| `file_read_tool.py`, `file_write_tool.py`, `file_edit_tool.py`　　　　　　　　　　　　| 文件读写编辑　　　　　　　　　　　　　　|
| **Shell** | `bash_tool.py`　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　　| Shell 命令执行　　　　　　　　　　　　　|
| **搜索**　| `grep_tool.py`, `glob_tool.py`, `web_search_tool.py`, `web_fetch_tool.py`　　　　　　 | 代码搜索、网页搜索　　　　　　　　　　　|
| **决策**　| `decision_score_tool.py`, `lifegoal_tool.py`, `save_decision_tool.py`　　　　　　　　 | 决策评分、保存　　　　　　　　　　　　　|
| **记忆**　| `recall_preferences_tool.py`, `recall_decisions_tool.py`　　　　　　　　　　　　　　　| 偏好/决策召回　　　　　　　　　　　　　 |
| **业务**　| `biz_execute_tool.py`, `biz_plan_tool.py`, `biz_score_tool.py`　　　　　　　　　　　　| 业务闭环执行　　　　　　　　　　　　　　|
| **场景**　| `travel_recommend_tool.py`, `tokencost_analyze_tool.py`, `robotclaw_dispatch_tool.py` | 领域场景工具　　　　　　　　　　　　　　|
| **知识**　| `knowledge_ingest_tool.py`, `knowledge_query_tool.py`, `knowledge_lint_tool.py`　　　 | 个人知识库　　　　　　　　　　　　　　　|
| **技能**　| `skill_tool.py`, `skill_manage_tool.py`, `skills_hub_tool.py`　　　　　　　　　　　　 | 技能管理　　　　　　　　　　　　　　　　|
| **进化**　| `self_evolution_review_tool.py`　　　　　　　　　　　　　　　　　　　　　　　　　　　 | 自进化复盘　　　　　　　　　　　　　　　|
| **任务**　| `task_create_tool.py`, `task_list_tool.py`, `task_stop_tool.py` 等　　　　　　　　　　| 后台任务管理　　　　　　　　　　　　　　|
| **MCP**　 | `mcp_tool.py`, `mcp_auth_tool.py`, `list_mcp_resources_tool.py`　　　　　　　　　　　 | MCP 协议集成　　　　　　　　　　　　　　|
| **协作**　| `agent_tool.py`, `send_message_tool.py`, `team_create_tool.py`　　　　　　　　　　　　| 多 Agent 协作　　　　　　　　　　　　　 |

### skills/ — 技能系统
| 文件 | 职责 |
|------|------|
| `registry.py` | 技能注册表 |
| `loader.py` | 技能加载器 |
| `hub.py` | 技能中心：多源发现 (GitHub/本地)、安全扫描、安装/卸载/更新 |
| `guard.py` | 技能安全守卫：内容扫描、信任等级评估 |
| `lock.py` | 技能锁文件：版本固定、完整性校验 |
| `prompt_index.py` | 技能索引注入系统提示 |
| `commands.py` | 技能 CLI 命令 |
| `helpers.py` | 辅助函数 |
| `types.py` | 技能数据类型 |
| `bundled/` | 内置技能 Markdown 文件 |

### security/ — 安全纵深防御
| 文件 | 职责 |
|------|------|
| `command_guard.py` | 危险命令识别 + 审批分级 (manual/smart/off) |
| `context_guard.py` | 上下文注入扫描 (AGENTS.md 等) |
| `file_guard.py` | 文件系统边界保护 (.ssh, /etc 等) |
| `mcp_guard.py` | MCP 凭据过滤 |
| `redaction.py` | 敏感输出脱敏 |
| `session_state.py` | 会话级审批状态管理 |
| `execution.py` | 执行安全协调 |

### permissions/ — 权限管理
| 文件 | 职责 |
|------|------|
| `checker.py` | 权限检查器 |
| `modes.py` | 权限模式定义 |

### 其他子系统
| 目录 | 职责 |
|------|------|
| `api/` | LLM API 客户端抽象 |
| `biz/` | 业务层桥接 |
| `bridge/` | 跨系统桥接 |
| `commands/` | CLI 命令 (skills_cli 等) |
| `config/` | 配置管理 (settings) |
| `coordinator/` | 协调器 |
| `hooks/` | 生命周期钩子 |
| `mcp/` | MCP 协议实现 |
| `memory/` | 基础记忆系统 |
| `plugins/` | 插件系统 |
| `prompts/` | 系统提示管理 |
| `services/` | 服务层 |
| `state/` | 状态管理 |
| `swarm/` | 多 Agent 协调 |
| `tasks/` | 后台任务管理 |
| `types/` | 公共类型定义 |
| `ui/` | UI 组件 |
| `utils/` | 工具函数 |
| `velaris/` | Velaris 特有组件 |
| `vim/` | Vim 模式支持 |
| `voice/` | 语音交互 |

## src/velaris_agent/ — 业务层

### memory/ — 决策记忆与偏好学习
| 文件 | 职责 |
|------|------|
| `types.py` | 核心数据模型 (DecisionRecord, UserPreferences, OrgPolicy, AlignmentReport, Stakeholder 等) |
| `decision_memory.py` | 决策记忆存储与检索 (JSONL 索引 + JSON 记录) |
| `preference_learner.py` | 偏好学习 (贝叶斯先验 + 指数衰减 + 偏差检测 + 对齐分析) |
| `stakeholder.py` | 利益相关者注册表 + 决策曲线追踪器 |
| `stakeholder_map.py` | 利益相关者地图 |
| `conflict_engine.py` | 冲突检测引擎 |
| `negotiation.py` | 协商引擎 |

### velaris/ — 治理运行时
| 文件 | 职责 |
|------|------|
| `router.py` | 策略路由器 (YAML 规则引擎) |
| `authority.py` | 能力签发服务 (短时令牌) |
| `task_ledger.py` | 任务账本 (状态机) |
| `outcome_store.py` | Outcome 存储 |
| `orchestrator.py` | 业务编排器 (串联完整闭环) |

### biz/ — 场景引擎
| 文件 | 职责 |
|------|------|
| `engine.py` | 场景识别 + 能力规划 + 多维评分 + 场景执行分发 (1300+ 行) |

### evolution/ — 自进化
| 文件 | 职责 |
|------|------|
| `self_evolution.py` | 自进化评估引擎 (接受率/满意度/漂移分析 → 优化动作) |
| `types.py` | 进化报告数据类型 |

### knowledge/ — 个人知识库
| 文件 | 职责 |
|------|------|
| `base.py` | 知识库核心 (摄取/搜索/健康检查) |
| `types.py` | 知识库数据类型 |

### scenarios/ — 场景实现
| 目录 | 说明 |
|------|------|
| `lifegoal/` | 人生目标决策 |
| `travel/` | 商旅推荐 |
| `tokencost/` | 成本优化 |
| `robotclaw/` | 调度治理 |
| `procurement/` | 采购决策 |

### 其他
| 文件/目录 | 职责 |
|-----------|------|
| `adapters/` | 数据源适配器 |
| `persistence/` | 持久化层 (PostgreSQL 等) |
| `cli.py` | Velaris CLI 入口 |

## tests/ — 测试结构
```
tests/
├── test_api/           # API 客户端测试
├── test_biz/           # 业务引擎测试 (router, orchestrator)
├── test_bridge/        # 桥接层测试
├── test_commands/      # CLI 命令测试
├── test_config/        # 配置测试
├── test_coordinator/   # 协调器测试
├── test_engine/        # Agent 引擎测试
├── test_evolution/     # 自进化测试
├── test_hooks/         # 钩子测试
├── test_knowledge/     # 知识库测试
├── test_mcp/           # MCP 测试
├── test_memory/        # 决策记忆/偏好学习/利益相关者测试
├── test_permissions/   # 权限测试
├── test_persistence/   # 持久化测试
├── test_plugins/       # 插件测试
├── test_prompts/       # 提示测试
├── test_scenarios/     # 场景测试
├── test_services/      # 服务测试
├── test_skills/        # 技能系统测试
├── test_swarm/         # 多 Agent 测试
├── test_tasks/         # 任务测试
├── test_tools/         # 工具测试
├── test_ui/            # UI 测试
├── conftest.py         # 测试 fixtures
└── ...
```
