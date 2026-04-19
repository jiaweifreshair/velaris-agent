# Performance Test Instructions

## 当前状态
当前仓库 **尚未接入独立的自动化性能测试套件**，因此本阶段没有可直接执行的 `k6 / JMeter / pytest-benchmark` 基准命令。

## 与本阶段相关的性能约束
根据 UOW-1 NFR：
- `planning + routing + authority + effective risk + gate` 的新增开销目标为 `p95 < 500ms`
- API `P95 < 100ms`
- 数据库查询 `P95 < 50ms`

## 当前建议
在未引入专门性能 harness 前，先完成以下最小动作：
1. 保持全量 pytest 通过，确保没有明显性能退化型 bug
2. 对 PostgreSQL 集成路径保留单独测试子集，便于后续接入 benchmark
3. 后续若进入下一 UOW，建议补充：
   - orchestrator 热路径 benchmark
   - PostgreSQL repository round-trip benchmark
   - 关键 scenario（如 procurement）多轮执行耗时采样

## 本阶段结论
- **性能自动化状态**: N/A
- **阻塞发布**: 否
- **后续建议**: 在下一轮 Construction 中补充基准测试脚手架
