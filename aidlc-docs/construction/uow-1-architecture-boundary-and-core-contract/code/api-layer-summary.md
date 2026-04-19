# UOW-1 代码总结 - API / Tool Layer

## 范围
本文件总结 `UOW-1` 在对外暴露面的收束，包括 `biz_execute` 的 envelope-first 输出、最小兼容 alias，以及本阶段可复跑的测试入口。

## 关键实现文件
- `src/openharness/tools/biz_execute_tool.py`
- `src/velaris_agent/velaris/orchestrator.py`
- `src/velaris_agent/velaris/execution_contract.py`

## 已落地设计对照

### 1. 对外 contract 切到 envelope-first
- `biz_execute` 不再自己拼平铺 payload，而是直接透传 orchestrator 的 envelope-first 结果。
- 工具输出固定包含：
  - `envelope`
  - `session_id`
  - `result`
  - `outcome`
  - `audit_event_count`

### 2. alias 收敛到最小集合
- 顶层仅保留用户已确认的四个 alias：
  - `session_id`
  - `result`
  - `outcome`
  - `audit_event_count`
- execution / plan / routing / authority / audit 语义全部进入 `envelope`。

### 3. 错误输出保持结构化
- orchestrator 在高风险 deny、barrier fail-closed、业务执行失败等场景下，会抛出结构化 envelope payload。
- `biz_execute` 捕获 `RuntimeError` 后仍将结构化内容按错误结果返回，便于上层 UI / CLI 继续消费标准字段。

## 本阶段验证入口

### focused 回归
```bash
./scripts/run_pytest.sh tests/test_biz/test_orchestrator.py tests/test_tools/test_biz_execute_tool.py -q
```

### UOW-1 汇总回归
```bash
./scripts/run_pytest.sh \
  tests/test_biz/test_execution_contract.py \
  tests/test_biz/test_payload_redactor.py \
  tests/test_biz/test_failure_classifier.py \
  tests/test_biz/test_persistence_barrier.py \
  tests/test_biz/test_orchestrator.py \
  tests/test_persistence/test_schema.py \
  tests/test_persistence/test_postgres_runtime.py \
  tests/test_persistence/test_postgres_execution.py \
  tests/test_services/test_session_storage.py \
  tests/test_tools/test_biz_execute_tool.py -q
```

## 本阶段实际验证结果
- focused orchestrator / tool 回归：`11 passed, 1 skipped`
- UOW-1 汇总回归：`32 passed, 3 skipped`

## 剩余风险
- `biz_execute` 当前仍以 `RuntimeError` 作为 orchestrator 错误边界；后续若要继续细分 CLI / API 错误码，可再引入专门异常层，但不应破坏现有 envelope-first contract。
