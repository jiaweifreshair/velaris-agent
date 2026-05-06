"""OpenViking 上下文管理器。

核心类 OpenVikingContext，封装 OpenViking SDK 的读写/检索/会话能力，
提供 viking:// URI 驱动的上下文存取 + 三层加载策略。

支持两种运行模式：
- Local 模式：数据存储在本地文件系统，单用户 CLI 使用
- HTTP 模式：连接远程 OpenViking 服务，多租户 SaaS 使用
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from velaris_agent.context.loading_strategy import (
    LoadingTier,
    get_tier_token_budget,
    resolve_loading_tier,
    resolve_target_path,
    truncate_to_budget,
)
from velaris_agent.context.uri_scheme import (
    VikingResource,
    VikingSubject,
    VikingURI,
    build_viking_uri,
    parse_viking_uri,
)

logger = logging.getLogger(__name__)


class OpenVikingContext:
    """OpenViking 上下文管理器。

    封装 OpenViking SDK，提供：
    - viking:// URI 驱动的读写
    - L0/L1/L2 三层加载
    - 会话上下文管理
    - 语义检索（find/search）

    Usage:
        ctx = OpenVikingContext(local_path="/data/viking")
        ctx.write("viking://user/alice/preferences/", {"theme": "dark"})
        prefs = ctx.read("viking://user/alice/preferences/", tier=LoadingTier.L1_CONTEXT)
    """

    def __init__(
        self,
        *,
        local_path: str | Path | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        agent_id: str = "velaris-default",
    ) -> None:
        """初始化 OpenViking 上下文管理器。

        Args:
            local_path: 本地模式的数据目录路径
            base_url: HTTP 模式的 OpenViking 服务地址
            api_key: HTTP 模式的 API 密钥
            agent_id: Agent 标识，默认 "velaris-default"
        """
        self._local_path = Path(local_path) if local_path else None
        self._base_url = base_url
        self._api_key = api_key
        self._agent_id = agent_id
        self._client: Any = None

        if local_path and base_url:
            logger.warning("同时指定了 local_path 和 base_url，优先使用 local_path（本地模式）")

    @property
    def mode(self) -> str:
        """返回当前运行模式：'local' 或 'http'。"""
        if self._local_path is not None:
            return "local"
        if self._base_url is not None:
            return "http"
        return "local"  # 默认本地模式

    @property
    def agent_id(self) -> str:
        """返回当前 Agent 标识。"""
        return self._agent_id

    def _get_client(self) -> Any:
        """懒加载 OpenViking 客户端。"""
        if self._client is not None:
            return self._client

        try:
            from openviking import SyncOpenViking
        except ImportError:
            raise ImportError(
                "openviking 包未安装，请运行: pip install openviking"
            )

        if self.mode == "local":
            self._client = SyncOpenViking(
                storage_path=str(self._local_path or Path.home() / ".velaris" / "viking"),
            )
        else:
            self._client = SyncOpenViking(
                base_url=self._base_url,
                api_key=self._api_key,
            )

        # 初始化目录结构
        self._ensure_schema()
        return self._client

    def _ensure_schema(self) -> None:
        """确保 OpenViking 中的基础目录结构已创建。"""
        client = self._client
        if client is None:
            return

        # 为三维主体创建基础目录
        for subject in VikingSubject:
            try:
                client.mkdir(f"/{subject.value}/{self._agent_id}/")
            except Exception:
                pass  # 目录可能已存在

            for resource in VikingResource:
                try:
                    uri_str = f"/{subject.value}/{self._agent_id}/{resource.value}/"
                    client.mkdir(uri_str)
                except Exception:
                    pass

    def write(
        self,
        uri: str | VikingURI,
        content: str | dict[str, Any],
        tier: LoadingTier | None = None,
    ) -> None:
        """通过 viking:// URI 写入上下文数据。

        Args:
            uri: viking:// URI 或 VikingURI 对象
            content: 要写入的内容（字符串或字典）
            tier: 可选的加载层级（用于选择写入目标文件）
        """
        if isinstance(uri, str):
            uri = parse_viking_uri(uri)

        client = self._get_client()
        text_content = json.dumps(content, ensure_ascii=False, indent=2) if isinstance(content, dict) else str(content)

        # 写入完整数据
        target_path = uri.to_openviking_path().rstrip("/") + "/data.json"
        client.write(target_path, text_content)

        # 自动生成 L0 摘要（取前 200 字符）
        summary = text_content[:200] + "..." if len(text_content) > 200 else text_content
        summary_path = uri.to_openviking_path().rstrip("/") + "/_summary.md"
        client.write(summary_path, summary)

        # 自动生成 L1 上下文（取前 4000 字符）
        context = text_content[:4000] + "..." if len(text_content) > 4000 else text_content
        context_path = uri.to_openviking_path().rstrip("/") + "/_context.md"
        client.write(context_path, context)

        logger.debug(f"已写入 {uri.to_uri()} (完整+摘要+上下文)")

    def read(
        self,
        uri: str | VikingURI,
        tier: LoadingTier = LoadingTier.L1_CONTEXT,
        token_budget: int | None = None,
        scenario: str | None = None,
    ) -> str:
        """通过 viking:// URI 读取上下文数据。

        Args:
            uri: viking:// URI 或 VikingURI 对象
            tier: 加载层级，默认 L1
            token_budget: 可选的 Token 预算
            scenario: 可选的场景提示

        Returns:
            读取到的内容
        """
        if isinstance(uri, str):
            uri = parse_viking_uri(uri)

        # 根据预算和场景决定加载层级
        effective_tier = resolve_loading_tier(
            uri=uri, token_budget=token_budget, scenario=scenario
        )
        # 显式 tier 优先级更高（仅在未指定 budget/scenario 时使用）
        if token_budget is None and scenario is None:
            effective_tier = tier

        client = self._get_client()
        target_path = resolve_target_path(uri, effective_tier)

        try:
            content = client.read(target_path)
        except Exception as exc:
            logger.warning(f"读取 {target_path} 失败: {exc}，尝试降级到 L0")
            # 降级到 L0
            if effective_tier != LoadingTier.L0_SUMMARY:
                try:
                    fallback_path = resolve_target_path(uri, LoadingTier.L0_SUMMARY)
                    content = client.read(fallback_path)
                except Exception:
                    return ""
            else:
                return ""

        # 截断到预算
        return truncate_to_budget(content, effective_tier)

    def find(
        self,
        query: str,
        target_uri: str | VikingURI | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """语义快速检索。

        Args:
            query: 查询文本
            target_uri: 限定搜索范围的 viking:// URI
            limit: 返回结果数上限

        Returns:
            匹配的记录列表
        """
        client = self._get_client()
        uri_str = target_uri.to_openviking_path() if isinstance(target_uri, VikingURI) else target_uri or ""
        return client.find(query=query, target_uri=uri_str, limit=limit)

    def search(
        self,
        query: str,
        target_uri: str | VikingURI | None = None,
        session_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """复杂语义检索（意图分析 + 层次化检索）。

        Args:
            query: 查询文本
            target_uri: 限定搜索范围的 viking:// URI
            session_id: 可选的会话 ID
            limit: 返回结果数上限

        Returns:
            匹配的记录列表
        """
        client = self._get_client()
        uri_str = target_uri.to_openviking_path() if isinstance(target_uri, VikingURI) else target_uri or ""
        return client.search(
            query=query,
            target_uri=uri_str,
            session_id=session_id,
            limit=limit,
        )

    def save_snapshot(
        self,
        execution_id: str,
        snapshot: dict[str, Any],
        agent_id: str | None = None,
    ) -> str:
        """保存执行快照到 viking://agent/{id}/snapshots/。

        Args:
            execution_id: 执行 ID
            snapshot: 快照数据
            agent_id: Agent 标识（默认使用当前 agent_id）

        Returns:
            快照的 viking:// URI
        """
        aid = agent_id or self._agent_id
        uri = build_viking_uri(
            subject=VikingSubject.AGENT,
            subject_id=aid,
            resource=VikingResource.SNAPSHOTS,
            path=execution_id,
        )
        self.write(uri, snapshot)
        return uri.to_uri()

    def load_snapshot(
        self,
        execution_id: str,
        agent_id: str | None = None,
        tier: LoadingTier = LoadingTier.L1_CONTEXT,
    ) -> dict[str, Any] | None:
        """从 viking://agent/{id}/snapshots/ 加载执行快照。

        Args:
            execution_id: 执行 ID
            agent_id: Agent 标识
            tier: 加载层级

        Returns:
            快照数据，不存在时返回 None
        """
        aid = agent_id or self._agent_id
        uri = build_viking_uri(
            subject=VikingSubject.AGENT,
            subject_id=aid,
            resource=VikingResource.SNAPSHOTS,
            path=execution_id,
        )
        content = self.read(uri, tier=tier)
        if not content:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw": content}

    def save_preferences(
        self,
        user_id: str,
        preferences: dict[str, Any],
    ) -> str:
        """保存用户偏好到 viking://user/{id}/preferences/。

        Args:
            user_id: 用户标识
            preferences: 偏好数据

        Returns:
            偏好的 viking:// URI
        """
        uri = build_viking_uri(
            subject=VikingSubject.USER,
            subject_id=user_id,
            resource=VikingResource.PREFERENCES,
        )
        self.write(uri, preferences)
        return uri.to_uri()

    def load_preferences(
        self,
        user_id: str,
        tier: LoadingTier = LoadingTier.L1_CONTEXT,
    ) -> dict[str, Any] | None:
        """从 viking://user/{id}/preferences/ 加载用户偏好。

        Args:
            user_id: 用户标识
            tier: 加载层级

        Returns:
            偏好数据，不存在时返回 None
        """
        uri = build_viking_uri(
            subject=VikingSubject.USER,
            subject_id=user_id,
            resource=VikingResource.PREFERENCES,
        )
        content = self.read(uri, tier=tier)
        if not content:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw": content}

    def close(self) -> None:
        """关闭 OpenViking 客户端连接。"""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def __enter__(self) -> OpenVikingContext:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
