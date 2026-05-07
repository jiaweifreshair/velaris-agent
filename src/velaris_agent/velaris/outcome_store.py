"""Velaris 原生 Outcome 存储。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import timezone, datetime
from typing import Any


@dataclass(frozen=True)
class OutcomeRecord:
    """业务执行结果记录。

    这个数据结构承载编排器对一次业务执行的最小结论，
    让不同存储后端都能复用同一份读写契约。
    """

    session_id: str
    scenario: str
    selected_strategy: str
    success: bool
    reason_codes: list[str]
    summary: str
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        """把 outcome 记录转换为 JSON 友好的字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "OutcomeRecord":
        """从持久化 payload 还原 outcome 记录。

        PostgreSQL 后端通过这个入口复用现有模型，确保返回结构与内存后端一致。
        """

        return cls(
            session_id=str(payload["session_id"]),
            scenario=str(payload["scenario"]),
            selected_strategy=str(payload["selected_strategy"]),
            success=_parse_success_flag(payload.get("success", False)),
            reason_codes=[str(item) for item in payload.get("reason_codes", [])],
            summary=str(payload["summary"]),
            metrics=dict(payload.get("metrics", {})),
            created_at=str(payload.get("created_at", "")),
        )


def _parse_success_flag(value: Any) -> bool:
    """显式解析持久化 success 字段。

    这样可以避免 `"false"`、`"0"` 这类字符串被 Python 的 truthy 规则误判成 `True`，
    减少历史脏数据恢复时的静默语义漂移。
    """

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off", ""}:
            return False
    if isinstance(value, (int, float)):
        return value != 0
    return bool(value)


class OutcomeStore:
    """Outcome 存储服务。"""

    def __init__(self) -> None:
        """初始化空 outcome 存储。"""
        self._records: list[OutcomeRecord] = []

    def record(
        self,
        session_id: str,
        scenario: str,
        selected_strategy: str,
        success: bool,
        reason_codes: list[str],
        summary: str,
        metrics: dict[str, Any] | None = None,
    ) -> OutcomeRecord:
        """写入一条 outcome 记录。"""
        record = OutcomeRecord(
            session_id=session_id,
            scenario=scenario,
            selected_strategy=selected_strategy,
            success=success,
            reason_codes=reason_codes,
            summary=summary,
            metrics=metrics or {},
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._records.append(record)
        return record

    def list_by_session(self, session_id: str) -> list[OutcomeRecord]:
        """按会话检索 outcome。"""
        return [record for record in self._records if record.session_id == session_id]
