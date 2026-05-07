"""viking:// URI 解析与路由。

URI 格式：
  viking://user/{user_id}/preferences/     → 用户偏好
  viking://user/{user_id}/memories/         → 用户记忆
  viking://org/{org_id}/policies/           → 组织策略
  viking://org/{org_id}/compliance/         → 合规规则
  viking://agent/{agent_id}/skills/         → Agent 技能
  viking://agent/{agent_id}/snapshots/      → 执行快照
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlparse


class VikingSubject(str, Enum):
    """三维决策主体。"""

    USER = "user"
    ORG = "org"
    AGENT = "agent"


class VikingResource(str, Enum):
    """资源类型。"""

    PREFERENCES = "preferences"
    MEMORIES = "memories"
    POLICIES = "policies"
    COMPLIANCE = "compliance"
    SKILLS = "skills"
    SNAPSHOTS = "snapshots"


# 主体 → 允许的资源类型映射
_SUBJECT_RESOURCES: dict[VikingSubject, set[VikingResource]] = {
    VikingSubject.USER: {VikingResource.PREFERENCES, VikingResource.MEMORIES},
    VikingSubject.ORG: {VikingResource.POLICIES, VikingResource.COMPLIANCE},
    VikingSubject.AGENT: {VikingResource.SKILLS, VikingResource.SNAPSHOTS},
}


@dataclass(frozen=True)
class VikingURI:
    """viking:// URI 的结构化表示。

    Attributes:
        subject: 决策主体类型（user/org/agent）
        subject_id: 主体标识
        resource: 资源类型
        path: 额外子路径（如具体偏好ID或快照ID）
    """

    subject: VikingSubject
    subject_id: str
    resource: VikingResource
    path: str = ""

    def to_uri(self) -> str:
        """序列化为 viking:// URI 字符串。"""
        base = f"viking://{self.subject.value}/{self.subject_id}/{self.resource.value}"
        if self.path:
            base += f"/{self.path}"
        return base + "/"

    def to_openviking_path(self) -> str:
        """转换为 OpenViking 内部文件路径。

        viking://user/alice/preferences/ → /user/alice/preferences/
        """
        base = f"/{self.subject.value}/{self.subject_id}/{self.resource.value}"
        if self.path:
            base += f"/{self.path}"
        return base + "/"

    def validate(self) -> None:
        """校验 URI 是否合法（主体与资源类型是否匹配）。

        Raises:
            ValueError: 主体与资源类型不匹配
        """
        allowed = _SUBJECT_RESOURCES.get(self.subject, set())
        if self.resource not in allowed:
            raise ValueError(
                f"资源 '{self.resource.value}' 不属于主体 '{self.subject.value}'，"
                f"允许的资源: {[r.value for r in allowed]}"
            )


def parse_viking_uri(uri: str) -> VikingURI:
    """解析 viking:// URI 字符串。

    URI 格式：viking://{subject}/{subject_id}/{resource}[/{extra_path}]/

    urlparse 行为：viking://user/alice/preferences/ → hostname="user", path="/alice/preferences/"
    所以 hostname 承载了 subject，path 只需 2 段（id + resource）。

    Args:
        uri: viking:// 格式的 URI

    Returns:
        VikingURI 结构化表示

    Raises:
        ValueError: URI 格式不合法或主体/资源不匹配

    Examples:
        >>> parse_viking_uri("viking://user/alice/preferences/")
        VikingURI(subject=VikingSubject.USER, subject_id='alice', resource=VikingResource.PREFERENCES, path='')
        >>> parse_viking_uri("viking://agent/v1/snapshots/exec-abc123/")
        VikingURI(subject=VikingSubject.AGENT, subject_id='v1', resource=VikingResource.SNAPSHOTS, path='exec-abc123')
    """
    parsed = urlparse(uri)
    if parsed.scheme != "viking":
        raise ValueError(f"不支持的 URI scheme: '{parsed.scheme}'，期望 'viking'")

    # 移除首尾斜杠后按段拆分
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]

    # 解析主体：hostname 承载 subject（viking://user/...）或 path 首段承载（viking:///user/...）
    if parsed.hostname:
        subject_str = parsed.hostname
        # hostname 存在时，path 只需 2 段：subject_id + resource
        if len(path_parts) < 2:
            raise ValueError(
                f"viking:// URI 路径至少需要 subject_id 和 resource，"
                f"实际: '{parsed.path}'"
            )
        subject_id = path_parts[0]
        resource_str = path_parts[1]
        extra_path = "/".join(path_parts[2:]) if len(path_parts) > 2 else ""
    else:
        # hostname 为 None 时，path 需要 3 段：subject + subject_id + resource
        if len(path_parts) < 3:
            raise ValueError(
                f"viking:// URI 路径至少需要 3 段 (subject/id/resource)，"
                f"实际: '{parsed.path}'"
            )
        subject_str = path_parts[0]
        subject_id = path_parts[1]
        resource_str = path_parts[2]
        extra_path = "/".join(path_parts[3:]) if len(path_parts) > 3 else ""

    try:
        subject = VikingSubject(subject_str)
    except ValueError:
        raise ValueError(
            f"未知的决策主体: '{subject_str}'，"
            f"支持: {[s.value for s in VikingSubject]}"
        )

    try:
        resource = VikingResource(resource_str)
    except ValueError:
        raise ValueError(
            f"未知的资源类型: '{resource_str}'，"
            f"支持: {[r.value for r in VikingResource]}"
        )

    result = VikingURI(
        subject=subject,
        subject_id=subject_id,
        resource=resource,
        path=extra_path,
    )
    result.validate()
    return result


def build_viking_uri(
    subject: VikingSubject | str,
    subject_id: str,
    resource: VikingResource | str,
    path: str = "",
) -> VikingURI:
    """便捷构建 viking:// URI。

    Args:
        subject: 决策主体类型
        subject_id: 主体标识
        resource: 资源类型
        path: 额外子路径

    Returns:
        VikingURI 结构化表示
    """
    if isinstance(subject, str):
        subject = VikingSubject(subject)
    if isinstance(resource, str):
        resource = VikingResource(resource)
    result = VikingURI(
        subject=subject,
        subject_id=subject_id,
        resource=resource,
        path=path,
    )
    result.validate()
    return result
