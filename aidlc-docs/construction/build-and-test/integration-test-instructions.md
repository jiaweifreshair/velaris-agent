# Integration Test Instructions

## 目标
验证多组件协同链路，而不仅仅是单文件单函数逻辑。

当前仓库最重要的集成面包括：
- Velaris orchestrator -> routing -> authority -> persistence barrier -> scenario -> envelope
- PostgreSQL session / execution / task / outcome / audit 主存储链路
- MCP / WebSocket 运行时集成

## 场景 1：PostgreSQL 持久化集成

### 环境准备
```bash
export VELARIS_TEST_POSTGRES_DSN='postgresql://user:password@localhost:5432/velaris_test'
```

### 执行命令
```bash
./scripts/run_pytest.sh \
  tests/test_persistence/test_schema.py \
  tests/test_persistence/test_postgres_runtime.py \
  tests/test_persistence/test_postgres_execution.py \
  tests/test_services/test_session_storage.py \
  tests/test_biz/test_persistence_barrier.py -q
```

### 关注点
- schema bootstrap 能否完成
- `SessionRepository / ExecutionRepository` 能否读写
- barrier 是否在 scenario 之前 fail-closed
- `audit_status` 是否按 `pending / persisted / failed` 推进

## 场景 2：Velaris UOW-1 业务编排集成

### 执行命令
```bash
./scripts/run_pytest.sh \
  tests/test_biz/test_orchestrator.py \
  tests/test_tools/test_biz_execute_tool.py \
  tests/test_biz/test_velaris_agent_namespace.py -q
```

### 关注点
- `DecisionExecutionEnvelope` 是否为主输出
- 顶层 alias 是否只保留 `session_id / result / outcome / audit_event_count`
- `procurement` 是否为 `medium -> degraded`
- `robotclaw` 是否为 `high -> denied`

## 场景 3：MCP / WebSocket 集成

### 执行命令
```bash
./scripts/run_pytest.sh tests/test_mcp/test_ws_integration.py -q
```

### 关注点
- WebSocket fixture 能否正常握手
- 运行时事件链路是否完整
- 仅允许出现已知弃用 warning，不应出现失败

## 清理
```bash
unset VELARIS_TEST_POSTGRES_DSN
```
