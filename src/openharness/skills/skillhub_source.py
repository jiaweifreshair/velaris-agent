"""SkillHub 真实技能来源适配器。

这个模块只负责一件事：把 `api.skillhub.cn` 上的真实 skill 变成当前仓库
能理解的 `SkillSource` / `SkillBundle`。公开技能默认可见，内部技能默认隐藏。
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from typing import Any

import httpx
import yaml

from openharness.skills.hub import (
    SkillBundle,
    SkillMeta,
    SkillSource,
    _normalize_bundle_path,
    _validate_bundle_rel_path,
    bundle_content_hash,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.skillhub.cn"

# 公开 skills 只放这里，避免默认搜索把整个平台的长尾 skill 全暴露出来。
PUBLIC_SKILL_SLUGS: frozenset[str] = frozenset(
    {
        "meituan",
        "meituan-hot-trend",
        "meituan-coupon-auto",
        "coupon",
        "tripgenie",
        "stayforge-api",
        "cabin",
        "flight-search-fast",
    }
)

# 这些 skill 含有更强的外部协议或内部供应链语义，默认必须隔离。
INTERNAL_SKILL_SLUGS: frozenset[str] = frozenset(
    {
        "coupons",
        "obtain-coupons-all-in-one",
        "obtain-takeout-coupon",
        "tuniu-hotel",
    }
)

# 这个仓库只接入上面这批业务 skill，避免把 SkillHub 的长尾内容直接摊给平台层。
CURATED_SKILL_SLUGS: frozenset[str] = PUBLIC_SKILL_SLUGS | INTERNAL_SKILL_SLUGS


def _normalize_skillhub_slug(identifier: str) -> str:
    """把 `skillhub/meituan` 或 `meituan` 规范化成纯 slug，便于统一判断。"""
    slug = identifier.strip()
    if "/" in slug:
        slug = slug.split("/", 1)[-1]
    if not slug:
        raise ValueError(f"Invalid SkillHub identifier: {identifier!r}")
    return slug


def _parse_skill_frontmatter(skill_md: str) -> dict[str, Any]:
    """从 `SKILL.md` 的 frontmatter 中尽量提取技能元信息。"""
    lines = skill_md.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end_index: int | None = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        return {}

    frontmatter_text = "\n".join(lines[1:end_index])
    try:
        parsed = yaml.safe_load(frontmatter_text)
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class SkillHubSource(SkillSource):
    """从 SkillHub 拉取真实业务 skills 的适配器。"""

    def __init__(self, *, base_url: str = _DEFAULT_BASE_URL, internal_mode: bool = False) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_mode = internal_mode

    def source_id(self) -> str:
        """返回统一的来源标识，便于安装 / 日志 / 测试使用。"""
        return "skillhub"

    def trust_level_for(self, identifier: str) -> str:
        """根据 slug 判断信任级别；内部技能给更谨慎的 community 等级。"""
        slug = _normalize_skillhub_slug(identifier)
        return "community" if slug in INTERNAL_SKILL_SLUGS else "trusted"

    async def search(self, query: str) -> list[SkillMeta]:
        """按关键词搜索 SkillHub，并按默认可见性规则过滤结果。"""
        params = {
            "page": 1,
            "pageSize": 50,
            "keyword": query.strip(),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self._base_url}/api/skills", params=params)
            resp.raise_for_status()
            payload = resp.json()

        skills = payload.get("data", {}).get("skills", [])
        results: list[SkillMeta] = []
        for item in skills:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug", "")).strip()
            if not slug:
                continue
            if slug not in CURATED_SKILL_SLUGS:
                continue
            if slug in INTERNAL_SKILL_SLUGS and not self._internal_mode:
                continue

            name = str(item.get("name") or slug).strip()
            description = str(
                item.get("description_zh")
                or item.get("description")
                or ""
            ).strip()
            results.append(
                SkillMeta(
                    name=name,
                    description=description,
                    source=self.source_id(),
                    identifier=f"skillhub/{slug}",
                    trust_level=self.trust_level_for(slug),
                    tags=[
                        "skillhub",
                        "internal" if slug in INTERNAL_SKILL_SLUGS else "public",
                    ],
                )
            )

        return results

    async def fetch(self, identifier: str) -> SkillBundle:
        """下载并解压 SkillHub 的 zip 包，返回完整 bundle。"""
        slug = _normalize_skillhub_slug(identifier)
        if slug not in CURATED_SKILL_SLUGS:
            raise PermissionError(f"SkillHub skill is not curated in this workspace: {slug}")
        if slug in INTERNAL_SKILL_SLUGS and not self._internal_mode:
            raise PermissionError(f"SkillHub internal skill is hidden by default: {slug}")

        download_url = f"{self._base_url}/api/v1/download"
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(download_url, params={"slug": slug})
            resp.raise_for_status()

        files: dict[str, str] = {}
        with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                rel_path = _normalize_bundle_path(member.filename)
                _validate_bundle_rel_path(rel_path)
                try:
                    raw = archive.read(member.filename)
                    files[rel_path] = raw.decode("utf-8")
                except (UnicodeDecodeError, KeyError) as exc:
                    logger.warning("Skipping unreadable SkillHub file %s: %s", member.filename, exc)

        if not files:
            raise RuntimeError(f"No readable files found for SkillHub skill: {slug}")

        skill_md = files.get("SKILL.md", "")
        frontmatter = _parse_skill_frontmatter(skill_md)
        skill_name = str(frontmatter.get("name") or slug).strip() or slug
        meta_json: dict[str, Any] = {}
        if "_meta.json" in files:
            try:
                parsed_meta = json.loads(files["_meta.json"])
                if isinstance(parsed_meta, dict):
                    meta_json = parsed_meta
            except json.JSONDecodeError:
                logger.debug("SkillHub meta JSON is invalid for %s", slug, exc_info=True)

        identifier_value = f"skillhub/{slug}"
        return SkillBundle(
            name=skill_name,
            files=files,
            source=self.source_id(),
            identifier=identifier_value,
            trust_level=self.trust_level_for(slug),
            content_hash=bundle_content_hash(files),
            metadata={
                "skillhub": {
                    "slug": slug,
                    "internal_mode": self._internal_mode,
                    "meta": meta_json,
                }
            },
        )
