"""Decision operator 基础契约。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class OperatorSpec:
    """算子静态描述。

    这个结构让 registry 与 trace 可以共享同一份版本元数据，
    避免后续在多个模块里重复维护 schema 版本常量。
    """

    operator_id: str
    operator_version: str = "v1"
    input_schema_version: str = "v1"
    output_schema_version: str = "v1"


class DecisionOperator(Protocol):
    """Decision operator 的最小运行协议。"""

    spec: OperatorSpec

    def run(self, context: "DecisionExecutionContext") -> "DecisionExecutionContext":
        """执行算子并返回更新后的上下文。"""

        raise NotImplementedError
