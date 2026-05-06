"""Velaris 上下文数据库集成包。

用 OpenViking 替代 SQLite+文件存储+内存字典，实现：
- viking:// URI 统一三维决策主体（user/org/agent）上下文寻址
- L0/L1/L2 三层加载策略（Token 节省 83-96%）
- Local/HTTP 双模式运行
"""

from velaris_agent.context.loading_strategy import LoadingTier
from velaris_agent.context.openviking_context import OpenVikingContext
from velaris_agent.context.uri_scheme import (
    VikingResource,
    VikingSubject,
    VikingURI,
    build_viking_uri,
    parse_viking_uri,
)

__all__ = [
    "LoadingTier",
    "OpenVikingContext",
    "VikingResource",
    "VikingSubject",
    "VikingURI",
    "build_viking_uri",
    "parse_viking_uri",
]
