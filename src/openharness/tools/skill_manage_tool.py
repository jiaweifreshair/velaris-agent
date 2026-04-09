"""技能管理工具。

该工具复用 Hermes 的核心思路：把技能视为可演进的程序化知识，
支持创建、定向补丁、支持文件写入和删除。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pydantic import BaseModel, Field
import yaml

from openharness.skills import get_user_skills_dir, load_skill_registry
from openharness.skills.helpers import normalize_skill_slug, parse_skill_markdown
from openharness.skills.prompt_index import clear_skills_system_prompt_cache
from openharness.tools.base import BaseTool, ToolExecutionContext, ToolResult

_ALLOWED_SUBDIRS = {"references", "templates", "scripts", "assets"}
_MAX_SKILL_CHARS = 100_000
_MAX_FILE_BYTES = 1_048_576


class SkillManageInput(BaseModel):
    """技能管理入参。"""

    action: str = Field(
        description="操作类型：create/edit/patch/delete/write_file/remove_file"
    )
    name: str = Field(description="技能名称或 slug")
    content: str | None = Field(
        default=None,
        description="完整 SKILL.md 内容，create/edit 时必填",
    )
    category: str | None = Field(
        default=None,
        description="可选分类目录，仅 create 时生效",
    )
    file_path: str | None = Field(
        default=None,
        description="支持文件路径，write_file/remove_file/patch 时可用",
    )
    file_content: str | None = Field(
        default=None,
        description="支持文件内容，write_file 时必填",
    )
    old_string: str | None = Field(
        default=None,
        description="patch 目标文本",
    )
    new_string: str | None = Field(
        default=None,
        description="patch 替换文本",
    )
    replace_all: bool = Field(
        default=False,
        description="patch 是否替换全部匹配项",
    )


class SkillManageTool(BaseTool):
    """创建、修补和维护本地技能。"""

    name = "skill_manage"
    description = (
        "Manage reusable skills as markdown-based procedural knowledge. "
        "Supports create, edit, patch, delete, and support file management."
    )
    input_model = SkillManageInput

    def is_read_only(self, arguments: SkillManageInput) -> bool:
        """该工具会修改技能文件。"""
        del arguments
        return False

    async def execute(
        self, arguments: SkillManageInput, context: ToolExecutionContext
    ) -> ToolResult:
        """执行技能管理操作。"""

        try:
            result = _dispatch_skill_action(arguments, context)
        except Exception as exc:
            return ToolResult(
                output=json.dumps(
                    {"success": False, "error": f"技能管理失败: {exc}"},
                    ensure_ascii=False,
                ),
                is_error=True,
            )

        if result.get("success"):
            clear_skills_system_prompt_cache()
        return ToolResult(
            output=json.dumps(result, ensure_ascii=False),
            is_error=not bool(result.get("success")),
        )


def _dispatch_skill_action(
    arguments: SkillManageInput, context: ToolExecutionContext
) -> dict[str, object]:
    """分发具体技能操作。"""

    action = arguments.action.strip().lower()
    if action == "create":
        return _create_skill(arguments)
    if action == "edit":
        return _edit_skill(arguments, context)
    if action == "patch":
        return _patch_skill(arguments, context)
    if action == "delete":
        return _delete_skill(arguments, context)
    if action == "write_file":
        return _write_skill_file(arguments, context)
    if action == "remove_file":
        return _remove_skill_file(arguments, context)
    return {
        "success": False,
        "error": f"未知 action: {arguments.action}",
    }


def _create_skill(arguments: SkillManageInput) -> dict[str, object]:
    """创建新技能。"""

    if not arguments.content:
        return {"success": False, "error": "create 需要 content。"}
    validation_error = _validate_skill_content(arguments.content)
    if validation_error:
        return {"success": False, "error": validation_error}

    skill_dir = _resolve_new_skill_dir(arguments.name, arguments.category)
    if skill_dir.exists():
        return {"success": False, "error": f"技能已存在: {arguments.name}"}

    skill_dir.mkdir(parents=True, exist_ok=False)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(arguments.content, encoding="utf-8")
    return {
        "success": True,
        "message": f"技能已创建: {arguments.name}",
        "path": str(skill_path),
    }


def _edit_skill(
    arguments: SkillManageInput,
    context: ToolExecutionContext,
) -> dict[str, object]:
    """全量替换技能主文件。"""

    if not arguments.content:
        return {"success": False, "error": "edit 需要 content。"}
    validation_error = _validate_skill_content(arguments.content)
    if validation_error:
        return {"success": False, "error": validation_error}

    skill_path = _ensure_editable_skill(arguments.name, context)
    if skill_path is None:
        return {"success": False, "error": f"找不到技能: {arguments.name}"}

    skill_path.write_text(arguments.content, encoding="utf-8")
    return {
        "success": True,
        "message": f"技能已更新: {arguments.name}",
        "path": str(skill_path),
    }


def _patch_skill(
    arguments: SkillManageInput,
    context: ToolExecutionContext,
) -> dict[str, object]:
    """对技能主文件或支持文件做定向补丁。"""

    if not arguments.old_string:
        return {"success": False, "error": "patch 需要 old_string。"}
    if arguments.new_string is None:
        return {"success": False, "error": "patch 需要 new_string。"}

    skill_path = _ensure_editable_skill(arguments.name, context)
    if skill_path is None:
        return {"success": False, "error": f"找不到技能: {arguments.name}"}

    target = skill_path
    if arguments.file_path:
        support_target = _resolve_support_file(skill_path.parent, arguments.file_path)
        if isinstance(support_target, str):
            return {"success": False, "error": support_target}
        if not support_target.exists():
            return {
                "success": False,
                "error": f"支持文件不存在: {arguments.file_path}",
            }
        target = support_target

    original = target.read_text(encoding="utf-8")
    occurrences = original.count(arguments.old_string)
    if occurrences == 0:
        return {"success": False, "error": "old_string 未命中任何内容。"}
    if occurrences > 1 and not arguments.replace_all:
        return {"success": False, "error": "old_string 命中多处内容，请提供更精确上下文或设置 replace_all=true。"}

    updated = (
        original.replace(arguments.old_string, arguments.new_string)
        if arguments.replace_all
        else original.replace(arguments.old_string, arguments.new_string, 1)
    )

    if target.name == "SKILL.md":
        validation_error = _validate_skill_content(updated)
        if validation_error:
            return {"success": False, "error": validation_error}

    target.write_text(updated, encoding="utf-8")
    return {
        "success": True,
        "message": f"技能已打补丁: {arguments.name}",
        "path": str(target),
        "replacements": occurrences if arguments.replace_all else 1,
    }


def _delete_skill(
    arguments: SkillManageInput,
    context: ToolExecutionContext,
) -> dict[str, object]:
    """删除用户技能目录。"""

    skill_path = _find_skill_path(arguments.name, context.cwd)
    if skill_path is None:
        return {"success": False, "error": f"找不到技能: {arguments.name}"}

    user_root = get_user_skills_dir().resolve()
    if not _is_relative_to(skill_path.resolve(), user_root):
        return {
            "success": False,
            "error": "只能删除用户目录下的技能；内置技能请通过创建覆盖版本再修改。",
        }

    if skill_path.is_file() and skill_path.name != "SKILL.md":
        skill_path.unlink()
        deleted_target = skill_path
    else:
        deleted_target = skill_path.parent if skill_path.name == "SKILL.md" else skill_path
        shutil.rmtree(deleted_target)
    return {
        "success": True,
        "message": f"技能已删除: {arguments.name}",
        "path": str(deleted_target),
    }


def _write_skill_file(
    arguments: SkillManageInput,
    context: ToolExecutionContext,
) -> dict[str, object]:
    """写入技能支持文件。"""

    if not arguments.file_path:
        return {"success": False, "error": "write_file 需要 file_path。"}
    if arguments.file_content is None:
        return {"success": False, "error": "write_file 需要 file_content。"}

    encoded = arguments.file_content.encode("utf-8")
    if len(encoded) > _MAX_FILE_BYTES:
        return {"success": False, "error": "支持文件超过大小限制。"}

    skill_path = _ensure_editable_skill(arguments.name, context)
    if skill_path is None:
        return {"success": False, "error": f"找不到技能: {arguments.name}"}

    target = _resolve_support_file(skill_path.parent, arguments.file_path)
    if isinstance(target, str):
        return {"success": False, "error": target}

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(arguments.file_content, encoding="utf-8")
    return {
        "success": True,
        "message": f"技能支持文件已写入: {arguments.file_path}",
        "path": str(target),
    }


def _remove_skill_file(
    arguments: SkillManageInput,
    context: ToolExecutionContext,
) -> dict[str, object]:
    """删除技能支持文件。"""

    if not arguments.file_path:
        return {"success": False, "error": "remove_file 需要 file_path。"}

    skill_path = _ensure_editable_skill(arguments.name, context)
    if skill_path is None:
        return {"success": False, "error": f"找不到技能: {arguments.name}"}

    target = _resolve_support_file(skill_path.parent, arguments.file_path)
    if isinstance(target, str):
        return {"success": False, "error": target}
    if not target.exists():
        return {"success": False, "error": f"支持文件不存在: {arguments.file_path}"}

    target.unlink()
    return {
        "success": True,
        "message": f"技能支持文件已删除: {arguments.file_path}",
        "path": str(target),
    }


def _ensure_editable_skill(name: str, context: ToolExecutionContext) -> Path | None:
    """确保目标技能可编辑。

    如果命中的是 bundled/plugin 技能，则复制一份到用户技能目录作为覆盖版本。
    """

    existing = _find_skill_path(name, context.cwd)
    if existing is None:
        return None

    user_root = get_user_skills_dir().resolve()
    if _is_relative_to(existing.resolve(), user_root):
        if existing.name != "SKILL.md":
            migrated_dir = _resolve_new_skill_dir(name, category=None)
            migrated_dir.mkdir(parents=True, exist_ok=True)
            migrated_path = migrated_dir / "SKILL.md"
            migrated_path.write_text(existing.read_text(encoding="utf-8"), encoding="utf-8")
            existing.unlink()
            return migrated_path
        return existing

    content = existing.read_text(encoding="utf-8")
    skill_name, _ = parse_skill_markdown(existing.parent.name if existing.name == "SKILL.md" else existing.stem, content)
    target_dir = _resolve_new_skill_dir(skill_name, category=None)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / "SKILL.md"
    target_path.write_text(content, encoding="utf-8")
    return target_path


def _find_skill_path(name: str, cwd: str | Path) -> Path | None:
    """从当前技能注册表中解析技能路径。"""

    registry = load_skill_registry(cwd)
    skill = registry.get(name)
    if skill is None or not skill.path:
        return None
    return Path(skill.path)


def _resolve_new_skill_dir(name: str, category: str | None) -> Path:
    """解析新技能目录。"""

    slug = normalize_skill_slug(name)
    base = get_user_skills_dir()
    if category and category.strip():
        base = base / normalize_skill_slug(category)
    return base / slug


def _validate_skill_content(content: str) -> str | None:
    """校验 SKILL.md 内容格式。"""

    if len(content) > _MAX_SKILL_CHARS:
        return "SKILL.md 内容过大，请拆分为支持文件。"
    stripped = content.strip()
    if not stripped:
        return "技能内容不能为空。"
    if not stripped.startswith("---"):
        return "SKILL.md 必须以 YAML frontmatter 开头。"
    if "\n---" not in stripped[3:]:
        return "SKILL.md frontmatter 缺少结束分隔符。"
    fm_text = stripped[3:].split("\n---", 1)[0]
    try:
        parsed = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        return f"frontmatter YAML 解析失败: {exc}"
    if not isinstance(parsed, dict):
        return "frontmatter 必须是 YAML 键值对。"
    if not str(parsed.get("name", "")).strip():
        return "frontmatter 中必须包含 name。"
    if not str(parsed.get("description", "")).strip():
        return "frontmatter 中必须包含 description。"
    name, description = parse_skill_markdown("skill", content)
    if not name.strip():
        return "frontmatter 中必须包含 name。"
    if not description.strip():
        return "frontmatter 中必须包含 description。"
    return None


def _resolve_support_file(skill_dir: Path, file_path: str) -> Path | str:
    """解析并校验支持文件路径。"""

    relative = Path(file_path)
    if relative.is_absolute():
        return "支持文件路径必须是相对路径。"
    if not relative.parts:
        return "无效的支持文件路径。"
    if relative.parts[0] not in _ALLOWED_SUBDIRS:
        return "支持文件只能写入 references/templates/scripts/assets 目录。"

    target = (skill_dir / relative).resolve()
    if not _is_relative_to(target, skill_dir.resolve()):
        return "支持文件路径不能逃逸技能目录。"
    return target


def _is_relative_to(path: Path, base: Path) -> bool:
    """兼容 Python 3.10 的相对路径判断。"""

    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
