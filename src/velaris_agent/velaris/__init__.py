"""Velaris 原生治理运行时导出。

该包需要被多处轻量模块导入（例如 persistence、contracts 等），因此这里避免在 import
阶段拉起完整业务编排依赖树，改为按需懒加载重对象，降低循环依赖与缺失依赖的风险。
"""

from importlib import import_module

__all__ = [
    "AuthorityService",
    "OutcomeStore",
    "PolicyRouter",
    "TaskLedger",
    "VelarisBizOrchestrator",
]


def __getattr__(name: str):
    """按需暴露高层对象，避免 import 阶段引入重依赖。"""

    if name == "AuthorityService":
        from velaris_agent.velaris.authority import AuthorityService

        return AuthorityService
    if name == "OutcomeStore":
        from velaris_agent.velaris.outcome_store import OutcomeStore

        return OutcomeStore
    if name == "PolicyRouter":
        from velaris_agent.velaris.router import PolicyRouter

        return PolicyRouter
    if name == "TaskLedger":
        from velaris_agent.velaris.task_ledger import TaskLedger

        return TaskLedger
    if name == "VelarisBizOrchestrator":
        return import_module("velaris_agent.velaris.orchestrator").VelarisBizOrchestrator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
