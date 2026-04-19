"""PayloadRedactor 测试。"""

from __future__ import annotations

from velaris_agent.velaris.payload_redactor import PayloadRedactor


def test_payload_redactor_redacts_sensitive_keys_and_nested_text() -> None:
    """脱敏器应递归处理敏感键和值中的敏感片段。"""

    payload = {
        "scenario": "procurement",
        "query": "联系供应商并生成推荐结果",
        "api_key": "sk-live-secret",
        "contact_email": "ceo@example.com",
        "nested": {
            "authorization": "Bearer secret-token",
            "notes": "token=abcd1234; next_step=call_vendor",
        },
        "items": [
            {
                "password": "top-secret-password",
                "sku": "vendor-a",
            }
        ],
    }

    redacted = PayloadRedactor().redact_mapping(payload)

    assert redacted["scenario"] == "procurement"
    assert redacted["query"] == "联系供应商并生成推荐结果"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["contact_email"] == "[REDACTED]"
    assert redacted["nested"]["authorization"] == "[REDACTED]"
    assert "[REDACTED]" in redacted["nested"]["notes"]
    assert "abcd1234" not in redacted["nested"]["notes"]
    assert redacted["items"][0]["password"] == "[REDACTED]"
    assert redacted["items"][0]["sku"] == "vendor-a"


def test_payload_redactor_does_not_mutate_input_and_preserves_safe_shapes() -> None:
    """脱敏器应返回新对象，不破坏原始输入结构。"""

    payload = {
        "result": {"recommended": {"id": "vendor-a"}},
        "audit": {"summary": "Bearer secret-token"},
        "metrics": [1, 2, 3],
    }

    redacted = PayloadRedactor().redact_mapping(payload)

    assert payload["audit"]["summary"] == "Bearer secret-token"
    assert redacted is not payload
    assert redacted["result"] == {"recommended": {"id": "vendor-a"}}
    assert redacted["metrics"] == [1, 2, 3]
    assert "[REDACTED]" in redacted["audit"]["summary"]
