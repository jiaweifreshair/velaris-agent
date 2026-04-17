# 技术栈文档

## 运行时

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | ≥ 3.10 | 主语言 |
| Pydantic | v2 | 数据模型验证 |
| Typer | ≥ 0.12 | CLI 框架 |
| Rich | ≥ 13.0 | 终端美化输出 |
| prompt-toolkit | ≥ 3.0 | 交互式终端 |
| Textual | ≥ 0.80 | TUI 框架 |

## AI/LLM 集成

| 技术　　　| 版本　 | 用途　　　　　　　　　 |
| -----------| --------| ------------------------|
| anthropic | ≥ 0.40 | Anthropic Claude API　 |
| openai　　| ≥ 1.54 | OpenAI-compatible API　|
| MCP (mcp) | ≥ 1.0　| Model Context Protocol |

## 网络与通信

| 技术 | 版本 | 用途 |
|------|------|------|
| httpx | ≥ 0.27 | HTTP 客户端 |
| websockets | ≥ 12.0 | WebSocket 通信 (MCP) |

## 数据与存储

| 技术 | 版本 | 用途 |
|------|------|------|
| psycopg[binary] | ≥ 3.2.1 | PostgreSQL 驱动 |
| PyYAML | ≥ 6.0 | YAML 配置解析 |
| JSON/JSONL | - | 决策记忆文件存储 |
| Markdown | - | 技能/知识存储 |

## 其他

| 技术 | 版本 | 用途 |
|------|------|------|
| pyperclip | ≥ 1.9 | 剪贴板操作 |
| watchfiles | ≥ 0.20 | 文件变更监听 |

## 开发工具

| 技术 | 版本 | 用途 |
|------|------|------|
| uv | latest | 包管理器 |
| hatchling | latest | 构建后端 |
| pytest | ≥ 8.0 | 测试框架 |
| pytest-asyncio | ≥ 0.23 | 异步测试 |
| pytest-cov | ≥ 5.0 | 覆盖率 |
| ruff | ≥ 0.5 | Linter + Formatter |
| mypy | ≥ 1.10 | 类型检查 |
| hypothesis | ≥ 6.151 | 属性测试 |
| pexpect | ≥ 4.9 | CLI 交互测试 |

## 构建与部署

| 项目 | 说明 |
|------|------|
| 构建系统 | hatchling |
| 包管理 | uv (推荐) 或 pip |
| 入口点 | `velaris` / `vl` (Velaris), `oh` / `openharness` (兼容) |
| 包结构 | `src/openharness` + `src/velaris_agent` (双包) |
| Python 目标 | 3.11 (ruff/mypy), ≥3.10 (运行时) |
| 许可证 | Apache-2.0 |

## 存储策略

| 数据类型 | 当前存储 | 目标存储 |
|----------|----------|----------|
| 决策记录 | 文件系统 (JSONL + JSON) | PostgreSQL (已有 persistence 层) |
| 偏好权重 | 从决策记录实时计算 | 同上 |
| 任务账本 | 内存 dict | PostgreSQL |
| Outcome | 内存 list | PostgreSQL |
| 技能 | 文件系统 (~/.velaris-agent/skills/) | 文件系统 |
| 知识库 | 文件系统 | 文件系统 |
| 路由策略 | YAML 文件 | YAML 文件 |
| 进化报告 | 文件系统 (JSON) | 文件系统 |
| 配置 | settings.json + 环境变量 | 同上 |

## 支持的 LLM Provider

| Provider | 环境变量 | API 格式 |
|----------|----------|----------|
| Anthropic | ANTHROPIC_API_KEY | Anthropic native |
| OpenAI | OPENAI_API_KEY | OpenAI |
| Moonshot | MOONSHOT_API_KEY | OpenAI-compatible |
| DashScope | - | OpenAI-compatible |
| Gemini | - | OpenAI-compatible |
| DeepSeek | - | OpenAI-compatible |
| OpenRouter | - | OpenAI-compatible |
| Groq | - | OpenAI-compatible |
