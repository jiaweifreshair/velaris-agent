# 安全架构文档

## 安全纵深防御体系

Velaris 把关键安全能力下沉到 `src/openharness/security/`，不依赖模型"自觉"。

## 安全组件

### 1. CommandGuard — 危险命令防护
- **文件**: `security/command_guard.py`
- **职责**: Shell 命令执行前做危险命令识别
- **审批模式**:
  - `manual`: 所有危险命令需用户确认
  - `smart`: 高/严重自动拒绝，中等需确认，低风险放行
  - `off`: 关闭审批
- **危险规则** (30+ 条):
  - critical: rm /, mkfs, dd, DROP TABLE, fork bomb, pipe remote script, 自终止进程
  - high: rm -r, chmod 递归, chown root, xargs rm, find -delete
  - medium: chmod 777, nohup gateway
  - low: shell -c, python -e
- **防绕过措施**:
  - ANSI 转义序列剥离
  - 空字节清除
  - Unicode NFKC 归一化
  - workdir 字符白名单校验

### 2. ContextGuard — 上下文注入扫描
- **文件**: `security/context_guard.py`
- **职责**: AGENTS.md、.cursorrules 等在注入系统提示前做威胁扫描
- **防护**: 防止恶意指令通过上下文文件注入

### 3. FileGuard — 文件系统边界
- **文件**: `security/file_guard.py`
- **职责**: 拒绝写入敏感位置
- **保护路径**: `.ssh`, `~/.velaris-agent`, `/etc` 等

### 4. McpGuard — MCP 凭据过滤
- **文件**: `security/mcp_guard.py`
- **职责**: stdio MCP 子进程默认只继承安全环境变量

### 5. Redaction — 敏感输出脱敏
- **文件**: `security/redaction.py`
- **职责**: Shell 输出与 MCP 错误文本统一做密钥/令牌脱敏

### 6. SessionState — 会话级审批状态
- **文件**: `security/session_state.py`
- **职责**: 已审批规则只在当前会话复用，不跨会话串联

## 权限系统

### PermissionChecker
- **文件**: `permissions/checker.py`
- **职责**: 多级权限检查 (tool/file/command)

### PermissionMode
- **文件**: `permissions/modes.py`
- **模式**: FULL_AUTO (全自动) / 其他模式

## 治理层安全

### 能力签发 (AuthorityService)
- 敏感能力需审批: write, exec, audit, contract_form
- 短时令牌 (默认 1800 秒 TTL)
- 会话级隔离

### 策略路由 (PolicyRouter)
- 高风险任务自动路由到治理优先路径
- 停止策略画像控制异常行为
- 审计链路全程可追溯
