"""UOW-4 测试：viking:// URI 解析。"""

from __future__ import annotations

import pytest

from velaris_agent.context.uri_scheme import (
    VikingResource,
    VikingSubject,
    build_viking_uri,
    parse_viking_uri,
)


class TestVikingURIParsing:
    """viking:// URI 解析测试。"""

    def test_parse_user_preferences(self):
        """解析用户偏好 URI。"""
        uri = parse_viking_uri("viking://user/alice/preferences/")
        assert uri.subject == VikingSubject.USER
        assert uri.subject_id == "alice"
        assert uri.resource == VikingResource.PREFERENCES
        assert uri.path == ""

    def test_parse_user_memories(self):
        """解析用户记忆 URI。"""
        uri = parse_viking_uri("viking://user/bob/memories/")
        assert uri.subject == VikingSubject.USER
        assert uri.subject_id == "bob"
        assert uri.resource == VikingResource.MEMORIES

    def test_parse_org_policies(self):
        """解析组织策略 URI。"""
        uri = parse_viking_uri("viking://org/acme/policies/")
        assert uri.subject == VikingSubject.ORG
        assert uri.subject_id == "acme"
        assert uri.resource == VikingResource.POLICIES

    def test_parse_org_compliance(self):
        """解析合规规则 URI。"""
        uri = parse_viking_uri("viking://org/acme/compliance/")
        assert uri.subject == VikingSubject.ORG
        assert uri.resource == VikingResource.COMPLIANCE

    def test_parse_agent_skills(self):
        """解析 Agent 技能 URI。"""
        uri = parse_viking_uri("viking://agent/v1/skills/")
        assert uri.subject == VikingSubject.AGENT
        assert uri.subject_id == "v1"
        assert uri.resource == VikingResource.SKILLS

    def test_parse_agent_snapshots(self):
        """解析执行快照 URI（含子路径）。"""
        uri = parse_viking_uri("viking://agent/v1/snapshots/exec-abc123/")
        assert uri.subject == VikingSubject.AGENT
        assert uri.subject_id == "v1"
        assert uri.resource == VikingResource.SNAPSHOTS
        assert uri.path == "exec-abc123"

    def test_parse_rejects_invalid_scheme(self):
        """拒绝非 viking scheme。"""
        with pytest.raises(ValueError, match="不支持的 URI scheme"):
            parse_viking_uri("http://user/alice/preferences/")

    def test_parse_rejects_unknown_subject(self):
        """拒绝未知的决策主体。"""
        with pytest.raises(ValueError, match="未知的决策主体"):
            parse_viking_uri("viking://device/d1/preferences/")

    def test_parse_rejects_unknown_resource(self):
        """拒绝未知的资源类型。"""
        with pytest.raises(ValueError, match="未知的资源类型"):
            parse_viking_uri("viking://user/alice/unknown/")

    def test_parse_rejects_mismatched_subject_resource(self):
        """拒绝主体与资源类型不匹配。"""
        with pytest.raises(ValueError, match="不属于主体"):
            parse_viking_uri("viking://user/alice/skills/")

    def test_parse_rejects_too_short_path(self):
        """拒绝路径段不足的 URI。"""
        with pytest.raises(ValueError, match="至少需要 subject_id 和 resource"):
            parse_viking_uri("viking://user/alice/")

    def test_to_uri_roundtrip(self):
        """URI 序列化后重新解析应一致。"""
        original = "viking://agent/v1/snapshots/exec-abc123/"
        uri = parse_viking_uri(original)
        assert uri.to_uri() == original

    def test_to_openviking_path(self):
        """VikingURI 转换为 OpenViking 内部路径。"""
        uri = parse_viking_uri("viking://user/alice/preferences/")
        assert uri.to_openviking_path() == "/user/alice/preferences/"


class TestBuildVikingURI:
    """便捷构建 viking:// URI 测试。"""

    def test_build_user_preferences(self):
        """构建用户偏好 URI。"""
        uri = build_viking_uri("user", "alice", "preferences")
        assert uri.subject == VikingSubject.USER
        assert uri.to_uri() == "viking://user/alice/preferences/"

    def test_build_agent_snapshot_with_path(self):
        """构建带子路径的 Agent 快照 URI。"""
        uri = build_viking_uri("agent", "v1", "snapshots", path="exec-abc")
        assert uri.to_uri() == "viking://agent/v1/snapshots/exec-abc/"

    def test_build_rejects_mismatch(self):
        """构建时拒绝主体与资源不匹配。"""
        with pytest.raises(ValueError):
            build_viking_uri("user", "alice", "skills")

    def test_build_with_enum_values(self):
        """使用枚举值构建 URI。"""
        uri = build_viking_uri(
            VikingSubject.ORG, "acme", VikingResource.COMPLIANCE
        )
        assert uri.subject == VikingSubject.ORG
        assert uri.resource == VikingResource.COMPLIANCE
