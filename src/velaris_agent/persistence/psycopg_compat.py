"""psycopg 兼容层。

该模块用于把 Phase 1 的单元测试与“可选 PostgreSQL 依赖”解耦：
1. 真正连接数据库时，仍然优先使用 psycopg 原生 `Jsonb`；
2. 若当前环境缺少可用的 psycopg/libpq，则退化为带 `.obj` 属性的轻量包装，
   让纯单元测试继续验证 payload 读写逻辑，而不是在 import 阶段直接崩溃。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from psycopg.types.json import Jsonb as _PsycopgJsonb
except Exception:  # pragma: no cover - 是否触发取决于本机 PostgreSQL 驱动环境
    @dataclass(frozen=True)
    class Jsonb:
        """测试友好的 Jsonb 退化包装。

        `tests/test_persistence/*` 会通过 `.obj` 读取原始 payload，
        因此这里保持与 psycopg `Jsonb` 的最小外观兼容。
        """

        obj: Any

else:
    Jsonb = _PsycopgJsonb

__all__ = ["Jsonb"]
