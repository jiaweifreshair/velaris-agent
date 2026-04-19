"""Velaris 持久化与执行失败分类组件。"""

from __future__ import annotations

from dataclasses import dataclass

from openharness.security.redaction import redact_sensitive_text


_INFRASTRUCTURE_MARKERS = (
    "database",
    "connection",
    "connect",
    "transaction",
    "pool",
    "timeout",
)


class GateDeniedError(RuntimeError):
    """表达治理门拒绝执行的显式错误。

    使用独立异常类型是为了把“策略拒绝”与“基础设施不可用”稳定区分，
    避免后续 envelope 与 tool error 只能依赖原始异常文本推断。
    """


@dataclass(frozen=True)
class FailureClassification:
    """稳定的错误分类结果。

    该对象为 orchestrator、barrier 和 tool 层提供统一错误面，
    保证 fail-closed、治理阻断和真实执行失败可以被一致消费。
    """

    error_code: str
    stage: str
    retryable: bool
    message: str

    def to_dict(self) -> dict[str, str | bool]:
        """返回 JSON 友好的错误分类结构。"""

        return {
            "error_code": self.error_code,
            "stage": self.stage,
            "retryable": self.retryable,
            "message": self.message,
        }


class PersistenceFailureClassifier:
    """把持久化故障、治理阻断与执行失败映射为稳定语义。

    当前阶段先提供最小分类规则，
    供后续 `PreExecutionPersistenceBarrier` 与 orchestrator 统一复用。
    """

    def classify(self, exc: BaseException, *, stage: str) -> FailureClassification:
        """根据异常类型、阶段和错误文本返回稳定分类结果。"""

        message = self._sanitize_message(exc)
        if self._is_gate_denied(exc=exc, stage=stage, message=message):
            return FailureClassification(
                error_code="gate_denied",
                stage=stage,
                retryable=False,
                message=message,
            )
        if self._is_infrastructure_failure(exc=exc, stage=stage, message=message):
            return FailureClassification(
                error_code="infrastructure_unavailable",
                stage=stage,
                retryable=True,
                message=message,
            )
        return FailureClassification(
            error_code="execution_failed",
            stage=stage,
            retryable=False,
            message=message,
        )

    def _sanitize_message(self, exc: BaseException) -> str:
        """统一清洗异常文本，避免原始 secret 直接外泄。"""

        raw = str(exc).strip() or exc.__class__.__name__
        return redact_sensitive_text(raw)

    def _is_gate_denied(self, *, exc: BaseException, stage: str, message: str) -> bool:
        """识别治理门拒绝，确保其不会被误记成基础设施故障。"""

        lowered = message.lower()
        if isinstance(exc, GateDeniedError):
            return True
        if isinstance(exc, PermissionError):
            return True
        return stage.startswith("gate") and any(marker in lowered for marker in ("deny", "denied", "blocked"))

    def _is_infrastructure_failure(self, *, exc: BaseException, stage: str, message: str) -> bool:
        """识别数据库、事务、连接和超时类故障。"""

        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return True
        lowered = message.lower()
        if any(marker in lowered for marker in _INFRASTRUCTURE_MARKERS):
            return True
        return stage.startswith("persistence") or stage in {
            "session_bind",
            "execution_create",
            "audit_persist",
            "outcome_persist",
        }
