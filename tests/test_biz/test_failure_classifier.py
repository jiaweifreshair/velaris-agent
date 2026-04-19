"""PersistenceFailureClassifier 测试。"""

from __future__ import annotations

from velaris_agent.velaris.failure_classifier import (
    GateDeniedError,
    PersistenceFailureClassifier,
)


def test_failure_classifier_maps_connection_error_to_infrastructure_unavailable() -> None:
    """数据库连接或事务类失败应稳定映射为基础设施不可用。"""

    classifier = PersistenceFailureClassifier()

    failure = classifier.classify(
        ConnectionError("postgres connect failed with token=abcd1234"),
        stage="execution_create",
    )

    assert failure.error_code == "infrastructure_unavailable"
    assert failure.stage == "execution_create"
    assert failure.retryable is True
    assert "abcd1234" not in failure.message
    assert "[REDACTED]" in failure.message


def test_failure_classifier_maps_gate_denied_error_to_gate_denied() -> None:
    """治理阻断必须与基础设施失败区分开。"""

    classifier = PersistenceFailureClassifier()

    failure = classifier.classify(
        GateDeniedError("high risk scenario denied before execution"),
        stage="gate",
    )

    assert failure.error_code == "gate_denied"
    assert failure.stage == "gate"
    assert failure.retryable is False
    assert "denied" in failure.message


def test_failure_classifier_maps_generic_runtime_error_to_execution_failed() -> None:
    """真实执行阶段的普通运行异常应映射为 execution_failed。"""

    classifier = PersistenceFailureClassifier()

    failure = classifier.classify(
        RuntimeError("scenario crashed while building contract"),
        stage="scenario_run",
    )

    assert failure.error_code == "execution_failed"
    assert failure.stage == "scenario_run"
    assert failure.retryable is False
    assert failure.to_dict()["message"] == "scenario crashed while building contract"
