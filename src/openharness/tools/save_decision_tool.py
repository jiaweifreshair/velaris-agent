"""保存决策记录工具 - 将完整决策上下文持久化到磁盘。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult


class SaveDecisionInput(BaseModel):
    """保存决策工具入参。"""

    user_id: str = Field(description="用户 ID")
    scenario: str = Field(
        description="业务场景或人生领域, 如 travel / tokencost / robotclaw / career"
    )
    query: str = Field(description="用户原始查询文本")
    recommended: dict[str, Any] = Field(description="系统推荐的选项, 至少包含 id 和 label")
    alternatives: list[dict[str, Any]] = Field(
        default_factory=list, description="备选方案列表"
    )
    weights_used: dict[str, float] = Field(
        default_factory=dict, description="本次决策使用的权重"
    )
    explanation: str = Field(default="", description="推荐理由说明")
    options_discovered: list[dict[str, Any]] = Field(
        default_factory=list, description="发现的所有候选项"
    )
    tools_called: list[str] = Field(
        default_factory=list, description="本次决策调用的工具列表"
    )


class SaveDecisionTool(BaseTool):
    """将一次决策的完整上下文保存到磁盘。

    保存内容包括: 用户查询、候选项、推荐结果、使用的权重、推荐理由等。
    这些数据用于后续的偏好学习和历史决策参考。
    """

    name = "save_decision"
    description = (
        "Save a complete decision record to disk. "
        "Records the full context: query, options, recommendation, "
        "weights used, and explanation for future preference learning."
    )
    input_model = SaveDecisionInput

    def is_read_only(self, arguments: SaveDecisionInput) -> bool:
        """写操作, 会持久化数据到磁盘。"""
        del arguments
        return False

    async def execute(
        self, arguments: SaveDecisionInput, context: ToolExecutionContext
    ) -> ToolResult:
        """执行决策保存。"""
        try:
            from velaris_agent.evolution.self_evolution import (
                SELF_EVOLUTION_REVIEW_JOB_TYPE,
                SelfEvolutionEngine,
                build_self_evolution_review_job_payload,
            )
            from velaris_agent.memory.types import DecisionRecord
            from velaris_agent.persistence.factory import (
                build_decision_memory,
                build_job_queue,
            )

            base_dir = context.metadata.get("decision_memory_dir")
            postgres_dsn = context.metadata.get("postgres_dsn", "")
            memory = build_decision_memory(
                postgres_dsn=postgres_dsn,
                base_dir=base_dir,
            )

            decision_id = memory.generate_id()
            record = DecisionRecord(
                decision_id=decision_id,
                user_id=arguments.user_id,
                scenario=arguments.scenario,
                query=arguments.query,
                options_discovered=arguments.options_discovered,
                weights_used=arguments.weights_used,
                tools_called=arguments.tools_called,
                recommended=arguments.recommended,
                alternatives=arguments.alternatives,
                explanation=arguments.explanation,
                created_at=datetime.now(timezone.utc),
            )

            saved_id = memory.save(record)
            review_interval = int(context.metadata.get("evolution_review_interval", 10))
            self_evolution_payload: dict[str, Any] = {
                "triggered": False,
                "queued": False,
                "next_trigger_in": None,
            }

            # 参考 Hermes 的后台 review 机制：每 N 条决策触发一次轻量复盘，
            # 不阻塞主链路，但把“是否该进化”变成可追踪信号。
            if review_interval > 0:
                current_count = memory.count_by_user(
                    user_id=arguments.user_id,
                    scenario=arguments.scenario,
                )
                remain = review_interval - (current_count % review_interval)
                self_evolution_payload["next_trigger_in"] = 0 if remain == review_interval else remain

                if current_count % review_interval == 0:
                    window = max(10, review_interval * 2)
                    if postgres_dsn.strip():
                        queue = build_job_queue(postgres_dsn=postgres_dsn)
                        if queue is not None:
                            job_id = queue.enqueue(
                                SELF_EVOLUTION_REVIEW_JOB_TYPE,
                                idempotency_key=f"{arguments.user_id}:{arguments.scenario}:{current_count}",
                                payload=build_self_evolution_review_job_payload(
                                    user_id=arguments.user_id,
                                    scenario=arguments.scenario,
                                    window=window,
                                    persist_report=True,
                                    report_dir=context.metadata.get("evolution_report_dir"),
                                    decision_memory_dir=base_dir,
                                ),
                            )
                            self_evolution_payload = {
                                "triggered": False,
                                "queued": True,
                                "job_id": job_id,
                                "next_trigger_in": 0,
                            }
                        else:
                            engine = SelfEvolutionEngine(
                                memory=memory,
                                report_dir=context.metadata.get("evolution_report_dir"),
                            )
                            report = engine.review(
                                user_id=arguments.user_id,
                                scenario=arguments.scenario,
                                window=window,
                                persist_report=True,
                            )
                            self_evolution_payload = {
                                "triggered": True,
                                "queued": False,
                                "report_path": report.report_path,
                                "sample_size": report.sample_size,
                                "actions": [a.model_dump(mode="json") for a in report.actions],
                            }
                    else:
                        engine = SelfEvolutionEngine(
                            memory=memory,
                            report_dir=context.metadata.get("evolution_report_dir"),
                        )
                        report = engine.review(
                            user_id=arguments.user_id,
                            scenario=arguments.scenario,
                            window=window,
                            persist_report=True,
                        )
                        self_evolution_payload = {
                            "triggered": True,
                            "queued": False,
                            "report_path": report.report_path,
                            "sample_size": report.sample_size,
                            "actions": [a.model_dump(mode="json") for a in report.actions],
                        }

            result = {
                "decision_id": saved_id,
                "status": "saved",
                "message": f"决策记录已保存, ID: {saved_id}",
                "self_evolution": self_evolution_payload,
            }
            return ToolResult(output=json.dumps(result, ensure_ascii=False))

        except Exception as e:
            return ToolResult(
                output=f"保存决策记录失败: {e}", is_error=True
            )
