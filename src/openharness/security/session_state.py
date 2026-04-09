"""会话级安全状态：保存审批结果等仅应在当前会话生效的安全信息。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SecuritySessionState:
    """记录当前会话已审批的危险命令规则，避免跨会话串扰。"""

    approved_command_patterns: set[str] = field(default_factory=set)
