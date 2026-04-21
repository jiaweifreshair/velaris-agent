# SkillHub 业务技能分域接入与代理编排 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 SkillHub 上的真实业务 skills 拉进本地 registry，并按本地生活 / 优惠券 / 酒店行程 / 航班四个 domain agent 串接起来，让平台只编排候选集、`velaris-agent` 只做共享决策和解释输出。

**Architecture:** 新增一个 `SkillHubSource` 负责从 `api.skillhub.cn` 拉取真实 skill bundle，并把公开技能和内部技能分开处理：公开技能进入默认搜索/安装流，内部技能只在 internal smoke 路径中可见。再增加一个轻量的 `skill_routing` 模块，把 skill slug 映射到 domain agent；协调器只需要知道“该把哪个 query 交给哪个 agent”，而不是直接理解每个 supplier skill 的私有协议。最后用一个 smoke 脚本把真实技能下载、路由、安装和 report 输出串起来，保证 demo 用的是活的 SkillHub 数据。

**Tech Stack:** Python 3.11, `httpx`, `zipfile`, `pydantic`, `pytest`, 现有 `openharness` skills / coordinator / agent runtime, `VELARIS_CONFIG_DIR` 环境变量隔离 smoke 数据。

---

### Task 1: 接入 SkillHub 真实技能源

**Files:**
- Create: `src/openharness/skills/skillhub_source.py`
- Modify: `src/openharness/tools/skills_hub_tool.py`
- Create: `tests/test_skills/test_skillhub_source.py`
- Modify: `tests/test_tools/test_skills_hub_tool.py`

- [ ] **Step 1: 先写失败测试**

```python
@pytest.mark.asyncio
async def test_skillhub_source_search_hides_internal_skills_by_default() -> None:
    source = SkillHubSource()
    results = await source.search("coupon")
    slugs = {meta.identifier for meta in results}
    assert "skillhub/coupon" in slugs
    assert "skillhub/coupons" not in slugs


@pytest.mark.asyncio
async def test_skillhub_source_fetch_decodes_zip_bundle() -> None:
    source = SkillHubSource(internal_mode=True)
    bundle = await source.fetch("meituan")
    assert bundle.identifier == "skillhub/meituan"
    assert bundle.name == "Meituan"
    assert "SKILL.md" in bundle.files
    assert bundle.files["SKILL.md"].startswith("---")
```

测试里要把 `httpx.AsyncClient` 替换成假客户端，返回两类数据：

1. `/api/skills?page=1&pageSize=50&keyword=<query>` 的 JSON 搜索结果；
2. `/api/v1/download?slug=<slug>` 的 zip bytes，zip 内至少包含 `SKILL.md` 和 `_meta.json`。

- [ ] **Step 2: 跑测试确认当前会失败**

Run:

```bash
pytest tests/test_skills/test_skillhub_source.py tests/test_tools/test_skills_hub_tool.py -q
```

Expected: 失败，原因是 `SkillHubSource` 还不存在，`default_sources()` 也还没有把它接进去。

- [ ] **Step 3: 实现最小可用的 SkillHubSource**

```python
PUBLIC_SKILL_SLUGS = {
    "meituan",
    "meituan-hot-trend",
    "meituan-coupon-auto",
    "coupon",
    "tripgenie",
    "stayforge-api",
    "cabin",
    "flight-search-fast",
}

INTERNAL_SKILL_SLUGS = {
    "coupons",
    "obtain-coupons-all-in-one",
    "obtain-takeout-coupon",
    "tuniu-hotel",
}


class SkillHubSource(SkillSource):
    def __init__(self, *, base_url: str = "https://api.skillhub.cn", internal_mode: bool = False) -> None:
        self._base_url = base_url.rstrip("/")
        self._internal_mode = internal_mode

    def _normalize_identifier(self, identifier: str) -> str:
        slug = identifier.split("/", 1)[-1].strip()
        if not slug:
            raise ValueError(f"Invalid SkillHub identifier: {identifier!r}")
        return slug

    def source_id(self) -> str:
        return "skillhub"

    def trust_level_for(self, identifier: str) -> str:
        slug = self._normalize_identifier(identifier)
        return "community" if slug in INTERNAL_SKILL_SLUGS else "trusted"

    async def search(self, query: str) -> list[SkillMeta]:
        params = {"page": 1, "pageSize": 50, "keyword": query.strip()}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{self._base_url}/api/skills", params=params)
            resp.raise_for_status()
            payload = resp.json()

        results: list[SkillMeta] = []
        for item in payload.get("data", {}).get("skills", []):
            slug = str(item.get("slug", "")).strip()
            if not slug:
                continue
            if not self._internal_mode and slug not in PUBLIC_SKILL_SLUGS:
                continue
            if slug in INTERNAL_SKILL_SLUGS and not self._internal_mode:
                continue
            results.append(
                SkillMeta(
                    name=str(item.get("name") or item.get("displayName") or slug).strip(),
                    description=str(item.get("description_zh") or item.get("description") or ""),
                    source=self.source_id(),
                    identifier=f"skillhub/{slug}",
                    trust_level=self.trust_level_for(slug),
                    tags=["skillhub", "internal" if slug in INTERNAL_SKILL_SLUGS else "public"],
                )
            )
        return results
```

`fetch()` 需要做三件事：

1. 支持 `meituan` 和 `skillhub/meituan` 两种输入；
2. 跟随下载跳转，解压 zip，保留所有文本文件；
3. 在 `internal_mode=False` 时对 `INTERNAL_SKILL_SLUGS` 直接抛 `PermissionError`，避免公开 demo 误装敏感包；
4. 从 `SKILL.md` frontmatter 里解析 skill name，再用现有 `bundle_content_hash()` 计算 hash。

`default_sources()` 要改成：

```python
def default_sources() -> list:
    optional_dir = get_user_skills_dir()
    return [SkillHubSource(), OptionalSkillSource(optional_dir)]
```

- [ ] **Step 4: 跑测试确认 SkillHubSource 和默认 sources 通过**

Run:

```bash
pytest tests/test_skills/test_skillhub_source.py tests/test_tools/test_skills_hub_tool.py -q
```

Expected: 通过；`skills_hub search` 能看到 `skillhub` 源，`install` 能安装公开技能，内部技能只在 `internal_mode=True` 的路径里可见。

- [ ] **Step 5: 提交该步**

```bash
git add src/openharness/skills/skillhub_source.py src/openharness/tools/skills_hub_tool.py tests/test_skills/test_skillhub_source.py tests/test_tools/test_skills_hub_tool.py
git commit -m "feat(skills): 接入 SkillHub 真实技能源"
```

### Task 2: 把真实技能分发到 domain agents

**Files:**
- Create: `src/openharness/coordinator/skill_routing.py`
- Modify: `src/openharness/coordinator/agent_definitions.py`
- Modify: `src/openharness/coordinator/coordinator_mode.py`
- Modify: `tests/test_coordinator/test_agent_definitions.py`
- Create: `tests/test_coordinator/test_skill_routing.py`

- [ ] **Step 1: 先写失败测试**

```python
def test_skill_to_agent_routes_are_stable() -> None:
    assert resolve_agent_for_skill("meituan") == "local-life-agent"
    assert resolve_agent_for_skill("meituan-coupon-auto") == "local-life-agent"
    assert resolve_agent_for_skill("coupon") == "coupon-agent"
    assert resolve_agent_for_skill("tripgenie") == "travel-agent"
    assert resolve_agent_for_skill("cabin") == "flight-agent"


def test_internal_only_skills_require_internal_mode() -> None:
    assert resolve_agent_for_skill("tuniu-hotel", internal_mode=False) is None
    assert resolve_agent_for_skill("tuniu-hotel", internal_mode=True) == "travel-agent"
```

再补一个 agent definition 测试，保证 built-in agent 把 skill bundle 挂对了：

```python
def test_builtin_domain_agents_expose_expected_skill_bundles() -> None:
    names = {agent.name for agent in get_builtin_agent_definitions()}
    assert {"local-life-agent", "coupon-agent", "travel-agent", "flight-agent"} <= names

    travel = next(agent for agent in get_builtin_agent_definitions() if agent.name == "travel-agent")
    assert travel.skills == ["tripgenie", "stayforge-api", "tuniu-hotel"]
```

- [ ] **Step 2: 跑测试确认当前会失败**

Run:

```bash
pytest tests/test_coordinator/test_agent_definitions.py tests/test_coordinator/test_skill_routing.py tests/test_coordinator/test_coordinator_mode.py -q
```

Expected: 失败，原因是 domain agents 和 routing helper 还没有定义，coordinator prompt 里也还没有这些 agent 名称。

- [ ] **Step 3: 实现 skill_routing 模块和 domain agents**

```python
DOMAIN_SKILL_MAP = {
    "local-life-agent": ("meituan", "meituan-hot-trend", "meituan-coupon-auto"),
    "coupon-agent": ("coupon", "coupons", "obtain-coupons-all-in-one", "obtain-takeout-coupon"),
    "travel-agent": ("tripgenie", "stayforge-api", "tuniu-hotel"),
    "flight-agent": ("cabin", "flight-search-fast"),
}

INTERNAL_ONLY_SKILLS = {"coupons", "obtain-coupons-all-in-one", "obtain-takeout-coupon", "tuniu-hotel"}


def resolve_agent_for_skill(skill_name: str, *, internal_mode: bool = False) -> str | None:
    slug = skill_name.strip().lower()
    for agent_name, skills in DOMAIN_SKILL_MAP.items():
        if slug not in skills:
            continue
        if slug in INTERNAL_ONLY_SKILLS and not internal_mode:
            return None
        return agent_name
    return None


def resolve_skills_for_agent(agent_name: str, *, internal_mode: bool = False) -> list[str]:
    skills = list(DOMAIN_SKILL_MAP.get(agent_name, ()))
    if internal_mode:
        return skills
    return [slug for slug in skills if slug not in INTERNAL_ONLY_SKILLS]
```

`agent_definitions.py` 里新增四个 built-in agents，名字要和 routing map 完全一致：

```python
AgentDefinition(
    name="local-life-agent",
    description="Use this agent for Meituan local-life merchant, delivery, and coupon comparison tasks.",
    tools=["*"],
    skills=["meituan", "meituan-hot-trend", "meituan-coupon-auto"],
    system_prompt=_LOCAL_LIFE_AGENT_PROMPT,
    subagent_type="local-life-agent",
    source="builtin",
    base_dir="built-in",
),
```

`travel-agent`、`coupon-agent`、`flight-agent` 按同样结构补齐，`skills` 列表必须和 `DOMAIN_SKILL_MAP` 对齐。

`coordinator_mode.py` 的 system prompt 要新增一个明确段落，告诉 coordinator：

```text
- 不要把 supplier skills 平铺给平台层。
- 本地生活交给 local-life-agent。
- 优惠券交给 coupon-agent。
- 酒店 / 行程交给 travel-agent。
- 航班交给 flight-agent。
- 一个 query 先拆成 domain tasks，再把各 agent 的候选集交给 velaris-agent 排序。
```

最好把这段 prompt 生成逻辑收敛到 `skill_routing.format_skill_routing_block()`，避免 agent 名单在 prompt 和代码里重复维护。

- [ ] **Step 4: 跑测试确认 routing 和 built-in agents 通过**

Run:

```bash
pytest tests/test_coordinator/test_agent_definitions.py tests/test_coordinator/test_skill_routing.py tests/test_coordinator/test_coordinator_mode.py -q
```

Expected: 通过；`get_coordinator_system_prompt()` 里能看到 domain agent 说明，`get_builtin_agent_definitions()` 也能稳定返回四个 domain agents。

- [ ] **Step 5: 提交该步**

```bash
git add src/openharness/coordinator/skill_routing.py src/openharness/coordinator/agent_definitions.py src/openharness/coordinator/coordinator_mode.py tests/test_coordinator/test_agent_definitions.py tests/test_coordinator/test_skill_routing.py
git commit -m "feat(coordinator): 按技能分域路由 agent"
```

### Task 3: 用真实 SkillHub 数据跑通 demo 并同步文档

**Files:**
- Create: `scripts/skillhub_domain_smoke.py`
- Modify: `docs/HOTEL-BIZTRAVEL-DECISION-ARCHITECTURE.md`
- Modify: `docs/TECHNICAL-PLAN.md`

- [ ] **Step 1: 先写 smoke script**

```python
SAMPLE_CASES = [
    ("local-life-agent", "送机前买花，想看附近美团店和优惠信息"),
    ("coupon-agent", "给这家咖啡店找能用的优惠券"),
    ("travel-agent", "上海出发，两晚酒店加行程"),
    ("flight-agent", "北京到上海的航班"),
]


async def run_smoke(output: Path, *, internal_mode: bool) -> None:
    source = SkillHubSource(internal_mode=internal_mode)
    registry = load_skill_registry(Path.cwd())
    lines: list[str] = ["# SkillHub Domain Agent Smoke Report", ""]

    for agent_name, query in SAMPLE_CASES:
        routed_skills = resolve_skills_for_agent(agent_name, internal_mode=internal_mode)
        resolved_agent = resolve_agent_for_skill(routed_skills[0], internal_mode=internal_mode) if routed_skills else None
        lines.append(f"## {agent_name}")
        lines.append(f"- query: {query}")
        lines.append(f"- routed_agent: {resolved_agent or 'none'}")
        lines.append(f"- skills: {', '.join(routed_skills)}")
        for slug in routed_skills:
            try:
                await install_skill(slug, [source], force=False)
            except RuntimeError as exc:
                if "already installed" not in str(exc):
                    raise
        lines.append(f"- registry_hit: {registry.get(routed_skills[0]).name if routed_skills else 'none'}")
        lines.append("")

    output.write_text("\n".join(lines), encoding="utf-8")
```

脚本运行时必须把 `VELARIS_CONFIG_DIR` 指到临时目录，避免污染用户真实配置：

```bash
VELARIS_CONFIG_DIR="$(mktemp -d)" python3 scripts/skillhub_domain_smoke.py \
  --output /Users/apus/Documents/UGit/smart-travel-workspace/output/skillhub-domain-agent-smoke-report.md
```

- [ ] **Step 2: 跑 smoke，确认 report 真的落地**

Run:

```bash
VELARIS_CONFIG_DIR="$(mktemp -d)" python3 scripts/skillhub_domain_smoke.py \
  --output /Users/apus/Documents/UGit/smart-travel-workspace/output/skillhub-domain-agent-smoke-report.md
```

Expected: 生成 markdown report，内容里至少包含四个 domain agent、对应的真实 skill slug、以及每个 query 的路由结果。

- [ ] **Step 3: 同步 architecture / technical plan 文档**

把 `docs/HOTEL-BIZTRAVEL-DECISION-ARCHITECTURE.md` 补上一张明确的映射表：

```md
| Domain agent | Public skills | Internal-only skills |
| --- | --- | --- |
| local-life-agent | meituan, meituan-hot-trend, meituan-coupon-auto | - |
| coupon-agent | coupon | coupons, obtain-coupons-all-in-one, obtain-takeout-coupon |
| travel-agent | tripgenie, stayforge-api | tuniu-hotel |
| flight-agent | cabin, flight-search-fast | - |
```

同时把 `docs/TECHNICAL-PLAN.md` 里仍然写着 `meituan-travel` 的地方替换成真实的 SkillHub slugs，避免后续读文档的人继续用旧名。

- [ ] **Step 4: 跑最终验证**

Run:

```bash
pytest -q
```

再加一条手工核对，确认 report 和文档都在：

```bash
test -f /Users/apus/Documents/UGit/smart-travel-workspace/output/skillhub-domain-agent-smoke-report.md
rg -n "local-life-agent|coupon-agent|travel-agent|flight-agent|meituan|tripgenie|cabin" docs/HOTEL-BIZTRAVEL-DECISION-ARCHITECTURE.md docs/TECHNICAL-PLAN.md
```

Expected: `pytest` 全绿，report 文件存在，文档里能搜到四个 domain agent 和这批真实 skill slug。

- [ ] **Step 5: 提交该步**

```bash
git add scripts/skillhub_domain_smoke.py docs/HOTEL-BIZTRAVEL-DECISION-ARCHITECTURE.md docs/TECHNICAL-PLAN.md
git commit -m "docs: 补 SkillHub domain smoke 和路由说明"
```

## Self-Review

- [x] 需求覆盖：真实 SkillHub 源、公开/内部隔离、domain agent 路由、smoke report、文档同步都被任务覆盖。
- [x] Placeholder scan：没有留下 `TODO` / `TBD` / “similar to above” 之类的占位句。
- [x] 类型一致性：`SkillHubSource`、`resolve_agent_for_skill`、`resolve_skills_for_agent`、四个 domain agent 名称在所有任务里保持一致。
- [x] Scope check：本计划只覆盖一个子系统——SkillHub 业务 skill 的接入与 agent 编排，不把 payment / fulfillment / decision-core 再拆成别的计划。
