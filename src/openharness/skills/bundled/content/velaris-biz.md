# Velaris Biz

Velaris 业务能力说明：

- `biz_execute`：执行完整的 Velaris 路由、授权、账本和 outcome 闭环。
- `biz_plan`：把业务目标编译为场景、能力和治理计划。
- `biz_score`：对候选业务方案做多维权重评分。
- `biz_run_scenario`：执行 `lifegoal`、`travel`、`tokencost`、`robotclaw` 四类场景。
- `travel_recommend`：直接执行商旅方案筛选与推荐。
- `tokencost_analyze`：直接执行 Token 成本分析与降本测算。
- `robotclaw_dispatch`：直接执行 RobotClaw 调度提案筛选与合约就绪判断。

建议工作流：

1. 优先用 `biz_execute` 跑完整闭环，拿到路由、授权、任务和结果记录。
2. 需要拆步调试时，再用 `biz_plan`、`biz_score`、`biz_run_scenario` 分阶段执行。
3. 已知具体业务场景时，可直接调用对应领域工具，减少通用工具编排成本。
4. 高风险场景优先开启审计和严格审批。
