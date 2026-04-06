"""人生目标决策 Demo 运行模块。

这个模块把 README 中展示的人生目标决策流程做成可复用的本地 Demo：
- 脚本可以直接调用
- CLI 子命令可以直接调用
- 测试也可以复用同一套逻辑

这样做的原因是避免把 demo 逻辑散落在脚本和 CLI 中，降低维护成本。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from openharness.tools.base import ToolExecutionContext
from openharness.tools.lifegoal_tool import LifeGoalTool, LifeGoalToolInput
from openharness.tools.recall_decisions_tool import RecallDecisionsInput, RecallDecisionsTool
from openharness.tools.recall_preferences_tool import RecallPreferencesInput, RecallPreferencesTool
from openharness.tools.save_decision_tool import SaveDecisionInput, SaveDecisionTool
from velaris_agent.memory.decision_memory import DecisionMemory
from velaris_agent.memory.types import DecisionRecord


def _build_context(decision_memory_dir: Path) -> ToolExecutionContext:
    """构造 Demo 运行上下文。

    这里显式注入临时的决策记忆目录，
    避免 demo 运行过程污染用户真实的长期决策数据。
    """
    return ToolExecutionContext(
        cwd=Path.cwd(),
        metadata={"decision_memory_dir": str(decision_memory_dir)},
    )


def _seed_career_history(decision_memory_dir: Path) -> None:
    """预置一组职业领域历史样本。

    样本设计目标是稳定表达“用户长期偏好成长而不是短期高薪”，
    这样 demo 才能清晰展示个性化权重学习的效果。
    """
    memory = DecisionMemory(base_dir=decision_memory_dir)
    seed_scores = [
        {
            "id": "high-pay",
            "scores": {
                "income": 0.95,
                "growth": 0.45,
                "fulfillment": 0.55,
                "stability": 0.7,
                "work_life_balance": 0.4,
            },
        },
        {
            "id": "growth-track",
            "scores": {
                "income": 0.65,
                "growth": 0.92,
                "fulfillment": 0.88,
                "stability": 0.62,
                "work_life_balance": 0.74,
            },
        },
    ]

    for index in range(4):
        record = DecisionRecord(
            decision_id=f"career-seed-{index:03d}",
            user_id="demo-user",
            scenario="career",
            query="两个 offer 怎么选，短期薪资和长期成长怎么平衡",
            user_choice={"id": "growth-track", "label": "薪资一般但成长更好"},
            user_feedback=4.6,
            scores=seed_scores,
            weights_used={
                "income": 0.25,
                "growth": 0.25,
                "fulfillment": 0.2,
                "stability": 0.15,
                "work_life_balance": 0.15,
            },
            recommended={"id": "high-pay", "label": "高薪但平台一般"},
            alternatives=[
                {"id": "growth-track", "label": "薪资一般但成长更好"},
            ],
            explanation="系统默认更均衡，但用户实际更偏向长期成长。",
            created_at=datetime.now(timezone.utc),
        )
        memory.save(record)


async def run_lifegoal_demo() -> dict[str, Any]:
    """执行人生目标决策 demo，并返回结构化结果。

    这里返回结构化字典而不是直接打印，
    是为了让脚本、CLI 和测试都能按自己的方式消费结果。
    """
    with TemporaryDirectory(prefix="velaris-lifegoal-demo-") as temp_dir:
        decision_memory_dir = Path(temp_dir) / "decisions"
        _seed_career_history(decision_memory_dir)
        context = _build_context(decision_memory_dir)

        recall_preferences = await RecallPreferencesTool().execute(
            RecallPreferencesInput(user_id="demo-user", scenario="career"),
            context,
        )
        recall_decisions = await RecallDecisionsTool().execute(
            RecallDecisionsInput(
                user_id="demo-user",
                scenario="career",
                query="现在有两个 offer，一个钱多一个成长更好，我该怎么选",
            ),
            context,
        )
        lifegoal_result = await LifeGoalTool().execute(
            LifeGoalToolInput(
                domain="career",
                user_id="demo-user",
                constraints=["下半年希望转管理岗", "不希望长期 996"],
                risk_tolerance="moderate",
                options=[
                    {
                        "id": "offer-a",
                        "label": "Offer A：大厂高薪岗",
                        "dimensions": {
                            "income": 0.93,
                            "growth": 0.58,
                            "fulfillment": 0.6,
                            "stability": 0.82,
                            "work_life_balance": 0.35,
                        },
                        "risks": ["加班强度较高", "岗位成长空间有限"],
                        "opportunities": ["短期现金流显著提升"],
                    },
                    {
                        "id": "offer-b",
                        "label": "Offer B：成长型核心岗位",
                        "dimensions": {
                            "income": 0.7,
                            "growth": 0.94,
                            "fulfillment": 0.88,
                            "stability": 0.68,
                            "work_life_balance": 0.76,
                        },
                        "risks": ["短期收入不如 Offer A"],
                        "opportunities": ["更快进入核心业务", "更适合转管理岗"],
                    },
                ],
            ),
            context,
        )

        decision_payload = json.loads(lifegoal_result.output)
        save_result = await SaveDecisionTool().execute(
            SaveDecisionInput(
                user_id="demo-user",
                scenario="career",
                query="现在有两个 offer，一个钱多一个成长更好，我该怎么选",
                recommended=decision_payload["recommended"],
                alternatives=decision_payload["alternatives"],
                weights_used=decision_payload["weights_used"],
                explanation="Demo 自动保存本次人生目标决策结果，便于后续继续学习。",
                options_discovered=decision_payload["all_ranked"],
                tools_called=[
                    "recall_preferences",
                    "recall_decisions",
                    "lifegoal_decide",
                    "save_decision",
                ],
            ),
            context,
        )

        return {
            "偏好召回": json.loads(recall_preferences.output),
            "历史决策召回": json.loads(recall_decisions.output),
            "人生目标决策结果": decision_payload,
            "保存结果": json.loads(save_result.output),
        }


def run_lifegoal_demo_sync() -> dict[str, Any]:
    """同步方式运行 demo。

    CLI 和脚本环境更适合直接调用同步入口，
    这样不用在各处重复写 `asyncio.run(...)`。
    """
    return asyncio.run(run_lifegoal_demo())


def render_lifegoal_demo_output(payload: dict[str, Any]) -> str:
    """把 demo 结果渲染成可读文本。

    当前输出以分段 JSON 为主，
    这样既便于人工阅读，也便于复制单段结果做进一步调试。
    """
    sections: list[str] = []
    for title, value in payload.items():
        sections.append(f"=== {title} ===")
        sections.append(json.dumps(value, ensure_ascii=False, indent=2))
    return "\n\n".join(sections)


def serialize_lifegoal_demo_output(payload: dict[str, Any]) -> str:
    """把 demo 结果序列化为 JSON 文本。

    这个函数用于 CLI 的 `--json` 输出和 `--save-to` 持久化，
    避免多处重复指定 JSON 序列化参数。
    """
    return json.dumps(payload, ensure_ascii=False, indent=2)


def save_lifegoal_demo_output(payload: dict[str, Any], path: str | Path) -> Path:
    """把 demo 输出保存到文件。

    会自动创建父目录，便于直接传入如 `out/demo.json` 这样的目标路径。
    """
    output_path = Path(path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialize_lifegoal_demo_output(payload), encoding="utf-8")
    return output_path
