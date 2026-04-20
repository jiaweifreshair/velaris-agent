"""SkillHubSource 的单元测试。

这些测试先固定真实 SkillHub 接入的契约：
1. 默认模式下只暴露公开 skills。
2. internal_mode=True 时可以看到内部 skills。
3. 下载的 zip 包能被解包成完整 bundle。
4. 默认模式会阻止安装内部敏感 skill。
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any
from unittest.mock import patch

import pytest

from openharness.skills.skillhub_source import (
    INTERNAL_SKILL_SLUGS,
    PUBLIC_SKILL_SLUGS,
    SkillHubSource,
)


def _build_zip_bytes(skill_md: str, meta: dict[str, Any]) -> bytes:
    """构造一个最小可用的 SkillHub zip 包，用于稳定测试下载逻辑。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("SKILL.md", skill_md)
        zf.writestr("_meta.json", json.dumps(meta, ensure_ascii=False))
    return buf.getvalue()


class _FakeResponse:
    """模拟 httpx.Response，只保留 SkillHubSource 测试所需能力。"""

    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: dict[str, Any] | None = None,
        content: bytes = b"",
        url: str = "https://api.skillhub.cn",
    ) -> None:
        self.status_code = status_code
        self._json_data = json_data
        self.content = content
        self.url = url

    def raise_for_status(self) -> None:
        """状态码不是 2xx 时抛错，模拟 httpx 的行为。"""
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict[str, Any]:
        """返回预设 JSON 数据。"""
        return self._json_data or {}


class _FakeAsyncClient:
    """模拟 httpx.AsyncClient，按 URL 返回 SkillHub 的固定测试数据。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._search_payload = {
            "code": 0,
            "data": {
                "skills": [
                    {
                        "slug": "coupon",
                        "name": "通用优惠券",
                        "description_zh": "通用优惠券检索",
                        "source": "clawhub",
                    },
                    {
                        "slug": "coupons",
                        "name": "优惠券聚合",
                        "description_zh": "内部优惠券聚合",
                        "source": "clawhub",
                    },
                    {
                        "slug": "meituan-coupon-auto",
                        "name": "美团优惠券自动领取",
                        "description_zh": "自动领取美团优惠券",
                        "source": "clawhub",
                    },
                    {
                        "slug": "woocommerce",
                        "name": "WooCommerce",
                        "description_zh": "无关技能",
                        "source": "clawhub",
                    },
                ]
            },
        }
        self._download_payload = _build_zip_bytes(
            skill_md=(
                "---\n"
                "name: meituan-coupon-auto\n"
                'description: "自动领取美团优惠券。"\n'
                "---\n"
                "# 美团优惠券自动领取\n"
            ),
            meta={"slug": "meituan-coupon-auto", "version": "2.1.1"},
        )

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> _FakeResponse:
        del headers
        if url.endswith("/api/skills"):
            keyword = (params or {}).get("keyword", "")
            if keyword and keyword not in {"coupon", "meituan"}:
                return _FakeResponse(
                    json_data={"code": 0, "data": {"skills": []}},
                    url=url,
                )
            return _FakeResponse(json_data=self._search_payload, url=url)
        if url.endswith("/api/v1/download"):
            slug = (params or {}).get("slug")
            if slug in PUBLIC_SKILL_SLUGS or slug in INTERNAL_SKILL_SLUGS:
                return _FakeResponse(
                    status_code=302,
                    content=self._download_payload,
                    url=f"{url}?slug={slug}",
                )
            return _FakeResponse(status_code=404, url=url)
        raise AssertionError(f"Unexpected URL: {url}")


@pytest.mark.asyncio
async def test_search_hides_internal_skills_by_default() -> None:
    """默认模式下，内部 skill 不应出现在搜索结果里。"""
    source = SkillHubSource()

    with patch("openharness.skills.skillhub_source.httpx.AsyncClient", _FakeAsyncClient):
        results = await source.search("coupon")

    slugs = {meta.identifier for meta in results}
    assert "skillhub/coupon" in slugs
    assert "skillhub/meituan-coupon-auto" in slugs
    assert "skillhub/coupons" not in slugs
    assert "skillhub/woocommerce" not in slugs
    assert all(meta.source == "skillhub" for meta in results)
    assert all(meta.trust_level == "trusted" for meta in results)


@pytest.mark.asyncio
async def test_search_exposes_internal_skills_in_internal_mode() -> None:
    """internal_mode=True 时，搜索应允许看到内部 skill。"""
    source = SkillHubSource(internal_mode=True)

    with patch("openharness.skills.skillhub_source.httpx.AsyncClient", _FakeAsyncClient):
        results = await source.search("coupon")

    slugs = {meta.identifier for meta in results}
    assert "skillhub/coupon" in slugs
    assert "skillhub/coupons" in slugs
    assert "skillhub/meituan-coupon-auto" in slugs
    assert "skillhub/woocommerce" not in slugs


@pytest.mark.asyncio
async def test_fetch_decodes_zip_bundle() -> None:
    """下载 zip 包后，应该把 zip 内文本文件还原成 SkillBundle。"""
    source = SkillHubSource(internal_mode=True)

    with patch("openharness.skills.skillhub_source.httpx.AsyncClient", _FakeAsyncClient):
        bundle = await source.fetch("meituan")

    assert bundle.identifier == "skillhub/meituan"
    assert bundle.name == "meituan-coupon-auto"
    assert "SKILL.md" in bundle.files
    assert "_meta.json" in bundle.files
    assert bundle.files["SKILL.md"].startswith("---")
    assert bundle.content_hash.startswith("sha256:")


@pytest.mark.asyncio
async def test_fetch_blocks_internal_skill_by_default() -> None:
    """默认模式下，内部 skill 不应该被下载和安装。"""
    source = SkillHubSource()

    class _UnexpectedClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("internal skill should be blocked before HTTP access")

    with patch("openharness.skills.skillhub_source.httpx.AsyncClient", _UnexpectedClient):
        with pytest.raises(PermissionError):
            await source.fetch("coupons")
