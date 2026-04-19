"""Velaris payload 脱敏组件。"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from openharness.security.redaction import redact_sensitive_text


_FULLY_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(token|key|secret|password|passwd|authorization|auth|credential|api_key|email|phone|mobile|contact)"
)
_EMAIL_PATTERN = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")


class PayloadRedactor:
    """统一处理持久化前与输出前的 payload 脱敏。

    该组件负责递归遍历字典、列表和字符串，
    默认优先移除或替换敏感字段，避免原始敏感信息进入长期存储或对外 contract。
    """

    def redact_mapping(self, payload: Mapping[str, Any] | None) -> dict[str, Any]:
        """返回脱敏后的新字典，保持调用方原始输入不被原地修改。"""

        if payload is None:
            return {}
        return {
            str(key): self._redact_value(key=str(key), value=value)
            for key, value in payload.items()
        }

    def _redact_value(self, *, key: str | None, value: Any) -> Any:
        """按值类型递归脱敏，并在命中敏感键时直接替换整段内容。"""

        if value is None:
            return None
        if self._is_sensitive_key(key):
            return _FULLY_REDACTED
        if isinstance(value, Mapping):
            return {
                str(child_key): self._redact_value(key=str(child_key), value=child_value)
                for child_key, child_value in value.items()
            }
        if isinstance(value, list):
            return [self._redact_value(key=key, value=item) for item in value]
        if isinstance(value, tuple):
            return tuple(self._redact_value(key=key, value=item) for item in value)
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return [self._redact_value(key=key, value=item) for item in value]
        return value

    def redact_text(self, text: str) -> str:
        """对普通文本做保守脱敏，供日志、错误摘要和输出层复用。"""

        redacted = redact_sensitive_text(text)
        return _EMAIL_PATTERN.sub(_FULLY_REDACTED, redacted)

    def _is_sensitive_key(self, key: str | None) -> bool:
        """判断字段名是否属于默认应整段遮蔽的敏感键。"""

        if not key:
            return False
        return _SENSITIVE_KEY_PATTERN.search(key) is not None
