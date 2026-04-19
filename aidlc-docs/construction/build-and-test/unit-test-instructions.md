# Unit Test Execution

## 推荐入口
```bash
./scripts/run_pytest.sh -q
```

## 说明
- 必须优先使用 `./scripts/run_pytest.sh`，不要直接调用 `pytest`
- 该脚本会自动挑选兼容本机架构与已安装依赖的 Python 解释器
- 当前仓库的 Python 单元 / 属性 / 集成级测试均统一通过该入口执行

## UOW-1 定向回归
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

## 本次实测结果
- 全量测试：`897 passed, 8 skipped, 3 warnings`
- UOW-1 聚焦测试：`32 passed, 3 skipped`

## 结果解读
- `skipped` 主要来自可选环境依赖场景，例如 PostgreSQL DSN 未配置时的集成用例
- 当前仓库未接入统一 coverage 输出，因此本阶段以 pytest 通过结果为主
- `warnings` 为 `websockets` 相关弃用提示，不阻塞当前构建与测试通过

## 失败时处理顺序
1. 先看失败是否为真实功能回归，还是环境 / deadline / 架构问题
2. 若是 PostgreSQL 用例失败，先确认 `VELARIS_TEST_POSTGRES_DSN`
3. 若是兼容层 contract 失败，优先核对 `DecisionExecutionEnvelope` 与最小 alias
4. 修复后重新执行全量命令，而不是只跑单个用例后宣称完成
