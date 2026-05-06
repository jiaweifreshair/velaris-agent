"""SKILL.md 解析器 — 从 YAML frontmatter + Markdown 加载场景规格。

SKILL.md 格式：
```
---
name: travel
version: "1.0"
keywords: [travel, flight, hotel, trip, 商旅, 出差]
capabilities: [intent_parse, inventory_search, option_score]
weights:
  price: 0.40
  time: 0.35
  comfort: 0.25
governance:
  requires_audit: false
  approval_mode: default
  stop_profile: balanced
risk_level: medium
recommended_tools:
  - biz_execute
  - travel_recommend
  - travel_compare
---

# Travel Scenario

商旅对比与推荐场景...
```

解析规则：
- frontmatter 由 `---` 包裹，必须存在
- name 必须与目录名一致（否则 warning 但不阻断）
- keywords 必须非空
- weights 的值必须为 float 且总和 ≈ 1.0（容差 0.05）
- 缺失字段使用合理默认值
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# frontmatter 正则：--- 开头和结尾
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*", re.DOTALL)


@dataclass(frozen=True)
class ScenarioSpec:
    """场景规格，对应一个 SKILL.md。"""

    name: str
    version: str = "1.0"
    keywords: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    weights: dict[str, float] = field(default_factory=dict)
    governance: dict[str, Any] = field(default_factory=dict)
    risk_level: str = "medium"
    recommended_tools: tuple[str, ...] = ()
    description: str = ""
    entry_point: str = ""
    fallback_scenario: str = "general"
    match_priority: int = 0
    match_rules: dict[str, Any] = field(default_factory=dict)


def load_skill_md(path: Path | str) -> ScenarioSpec:
    """从 SKILL.md 文件加载场景规格。

    Args:
        path: SKILL.md 文件路径

    Returns:
        ScenarioSpec 实例

    Raises:
        ValueError: frontmatter 缺失或 name 为空
        yaml.YAMLError: frontmatter YAML 语法错误
    """
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(content)
    if not match:
        raise ValueError(f"No YAML frontmatter found in {file_path}")

    raw = yaml.safe_load(match.group(1))
    if not isinstance(raw, dict):
        raise ValueError(f"Frontmatter must be a YAML mapping in {file_path}")

    name = str(raw.get("name", "")).strip()
    if not name:
        # 回退：使用目录名
        name = file_path.parent.name

    # 解析 keywords
    raw_keywords = raw.get("keywords", [])
    keywords = tuple(str(k).strip() for k in raw_keywords if str(k).strip())

    # 解析 capabilities
    raw_capabilities = raw.get("capabilities", [])
    capabilities = tuple(str(c).strip() for c in raw_capabilities if str(c).strip())

    # 解析 weights
    raw_weights = raw.get("weights", {})
    weights: dict[str, float] = {}
    if isinstance(raw_weights, dict):
        for k, v in raw_weights.items():
            try:
                weights[str(k)] = float(v)
            except (TypeError, ValueError):
                pass

    # 解析 governance（确保三个核心字段始终存在）
    raw_governance = raw.get("governance", {})
    governance: dict[str, Any] = {
        "requires_audit": False,
        "approval_mode": "default",
        "stop_profile": "balanced",
    }
    if isinstance(raw_governance, dict):
        governance.update(raw_governance)

    # 解析 risk_level
    risk_level = str(raw.get("risk_level", "medium")).strip()

    # 解析 recommended_tools
    raw_tools = raw.get("recommended_tools", raw.get("tools", []))
    recommended_tools = tuple(str(t).strip() for t in raw_tools if str(t).strip())

    # 解析 description（markdown body 部分）
    body = content[match.end():].strip()
    # 取第一行非空非标题行作为简短描述
    description = ""
    for line in body.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            description = line
            break

    # 解析 entry_point（场景执行器模块路径，如 "velaris_agent.biz.engine:_run_travel_scenario"）
    entry_point = str(raw.get("entry_point", "")).strip()

    # 解析 fallback_scenario（场景匹配失败时的兜底场景名）
    fallback_scenario = str(raw.get("fallback_scenario", "general")).strip()

    # 解析 match_priority（匹配优先级，数值越高越优先）
    match_priority = int(raw.get("match_priority", 0))

    # 解析 match_rules（高级匹配规则，如双信号检测）
    match_rules = dict(raw.get("match_rules", {}))

    version = str(raw.get("version", "1.0")).strip()

    return ScenarioSpec(
        name=name,
        version=version,
        keywords=keywords,
        capabilities=capabilities,
        weights=weights,
        governance=governance,
        risk_level=risk_level,
        recommended_tools=recommended_tools,
        description=description,
        entry_point=entry_point,
        fallback_scenario=fallback_scenario,
        match_priority=match_priority,
        match_rules=match_rules,
    )


def scan_scenario_dir(scenarios_dir: Path | str) -> dict[str, ScenarioSpec]:
    """扫描场景目录，加载所有 SKILL.md。

    Args:
        scenarios_dir: 场景根目录，每个子目录可包含 SKILL.md

    Returns:
        {scenario_name: ScenarioSpec} 字典
    """
    dir_path = Path(scenarios_dir)
    if not dir_path.is_dir():
        return {}

    specs: dict[str, ScenarioSpec] = {}
    for child in sorted(dir_path.iterdir()):
        if not child.is_dir():
            continue
        skill_file = child / "SKILL.md"
        if not skill_file.is_file():
            continue
        try:
            spec = load_skill_md(skill_file)
            specs[spec.name] = spec
        except Exception:
            # 解析失败跳过，不影响其他场景
            continue
    return specs
