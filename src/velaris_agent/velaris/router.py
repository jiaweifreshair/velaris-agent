"""Velaris 原生策略路由器。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from velaris_agent.scenarios.registry import ScenarioRegistry


@dataclass(frozen=True)
class SelectedRoute:
    """标准化路由结果。"""

    mode: str
    runtime: str
    autonomy: str
    score: float


@dataclass(frozen=True)
class RoutingDecision:
    """路由决策结果。"""

    selected_strategy: str
    selected_route: SelectedRoute
    stop_profile: str
    active_stop_conditions: list[str]
    reason_codes: list[str]
    required_capabilities: list[str]
    trace: dict[str, Any]
    governance: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """把路由决策转换为 JSON 友好的字典。"""
        return asdict(self)


class PolicyRouter:
    """Velaris 原生策略路由器。"""

    def __init__(self, policy_path: str | Path | None = None, scenario_registry: ScenarioRegistry | None = None) -> None:
        self.policy_path = Path(policy_path).resolve() if policy_path is not None else self._resolve_default_policy_path()
        self.policy = self._load_policy(self.policy_path)
        self._registry = scenario_registry or ScenarioRegistry()

    def route(self, plan: dict[str, Any], query: str) -> RoutingDecision:
        routing_context = self._build_routing_context(plan=plan, query=query)
        sorted_rules = sorted(self.policy["rules"], key=lambda item: int(item["priority"]), reverse=True)
        evaluated_rules: list[str] = []
        selected_rule: dict[str, Any] | None = None

        for rule in sorted_rules:
            evaluated_rules.append(str(rule["id"]))
            if self._matches(rule["when"], routing_context):
                selected_rule = rule
                break

        route_config = selected_rule["route"] if selected_rule is not None else self.policy["fallback"]
        selected_rule_id = str(selected_rule["id"]) if selected_rule is not None else "FALLBACK"
        strategy_name = str(route_config["strategy"])
        strategy = self.policy["strategies"][strategy_name]
        stop_profile_name = str(route_config["stop_profile"])
        stop_profile = self.policy["stop_profiles"][stop_profile_name]

        required_capabilities = list(dict.fromkeys(strategy.get("required_capabilities", [])))
        confidence = self._compute_confidence(selected_rule=selected_rule, sorted_rules=sorted_rules)

        return RoutingDecision(
            selected_strategy=strategy_name,
            selected_route=SelectedRoute(
                mode=str(strategy["mode"]),
                runtime=str(strategy["runtime"]),
                autonomy=str(strategy["autonomy"]),
                score=confidence,
            ),
            stop_profile=stop_profile_name,
            active_stop_conditions=[str(condition["id"]) for condition in stop_profile.get("conditions", [])],
            reason_codes=[
                selected_rule_id,
                str(route_config.get("reason", self.policy["fallback"].get("reason", "fallback"))),
                str(plan.get("scenario", "general")),
            ],
            required_capabilities=required_capabilities,
            trace={
                "evaluated_rules": evaluated_rules,
                "selected_rule": selected_rule_id,
                "timestamp": datetime.now(UTC).isoformat(),
                "policy_id": self.policy.get("policy_id"),
                "routing_context": routing_context,
            },
            governance=dict(plan.get("governance", {})),
        )

    def _resolve_default_policy_path(self) -> Path:
        """多策略查找 config/routing-policy.yaml: CWD 优先, __file__ 回退。"""
        # 策略1: 从当前工作目录向上查找
        cwd = Path.cwd().resolve()
        for parent in [cwd, *cwd.parents]:
            candidate = parent / "config" / "routing-policy.yaml"
            if candidate.exists():
                return candidate
        # 策略2: 从 __file__ 所在目录向上查找 (原有逻辑, 作为回退)
        current = Path(__file__).resolve()
        for parent in current.parents:
            candidate = parent / "config" / "routing-policy.yaml"
            if candidate.exists():
                return candidate
        raise FileNotFoundError("Unable to locate config/routing-policy.yaml for Velaris routing policy.")

    def _load_policy(self, policy_path: Path) -> dict[str, Any]:
        data = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Invalid routing policy file: {policy_path}")
        return data

    def _build_routing_context(self, plan: dict[str, Any], query: str) -> dict[str, Any]:
        scenario = str(plan.get("scenario", "general") or "general")
        governance = dict(plan.get("governance", {}))
        constraints = dict(plan.get("constraints", {}))
        capabilities = set(plan.get("capabilities", []))

        write_code = self._constraint_bool(constraints, "write_code", ("capability_demand", "writeCode"), default=False)
        # 默认外部副作用：高风险场景（如 robotclaw/procurement）需要审计
        _default_external_side_effects = self._registry.get_risk_level(scenario) == "high"
        external_side_effects = self._constraint_bool(
            constraints,
            "external_side_effects",
            ("capability_demand", "externalSideEffects"),
            default=_default_external_side_effects,
        )
        requires_audit = self._constraint_bool(
            constraints,
            "requires_audit",
            ("governance", "requiresAuditTrail"),
            default=bool(governance.get("requires_audit", False)),
        )
        task_complexity = self._constraint_str(
            constraints,
            "task_complexity",
            ("state", "taskComplexity"),
            default=self._infer_task_complexity(
                scenario=scenario,
                write_code=write_code,
                external_side_effects=external_side_effects,
                capability_count=len(capabilities),
            ),
        )
        risk_level = self._constraint_str(
            constraints,
            "risk_level",
            ("risk", "level"),
            default=self._infer_risk_level(
                scenario=scenario,
                requires_audit=requires_audit,
                external_side_effects=external_side_effects,
            ),
        )

        return {
            "goal": {
                "scenario": scenario,
                "query": query,
            },
            "risk": {
                "level": risk_level,
            },
            "state": {
                "taskComplexity": task_complexity,
            },
            "capabilityDemand": {
                "writeCode": write_code,
                "externalSideEffects": external_side_effects,
                "write": "contract_form" in capabilities,
            },
            "governance": {
                "requiresAuditTrail": requires_audit,
            },
        }

    def _constraint_bool(self, constraints: dict[str, Any], flat_key: str, nested_key: tuple[str, str], default: bool) -> bool:
        if flat_key in constraints:
            return bool(constraints[flat_key])
        parent = constraints.get(nested_key[0])
        if isinstance(parent, dict) and nested_key[1] in parent:
            return bool(parent[nested_key[1]])
        return default

    def _constraint_str(self, constraints: dict[str, Any], flat_key: str, nested_key: tuple[str, str], default: str) -> str:
        if flat_key in constraints and constraints[flat_key]:
            return str(constraints[flat_key])
        parent = constraints.get(nested_key[0])
        if isinstance(parent, dict) and nested_key[1] in parent and parent[nested_key[1]]:
            return str(parent[nested_key[1]])
        return default

    def _infer_task_complexity(self, scenario: str, write_code: bool, external_side_effects: bool, capability_count: int) -> str:
        if write_code or external_side_effects:
            return "complex"
        # 使用 registry 查询 risk_level 替代硬编码场景判断
        spec = self._registry.get(scenario)
        risk_level = spec.risk_level if spec else "medium"
        if capability_count >= 4 and risk_level == "high":
            return "complex"
        if risk_level == "low":
            return "simple"
        return "medium"

    def _infer_risk_level(self, scenario: str, requires_audit: bool, external_side_effects: bool) -> str:
        if requires_audit:
            return "high"
        if external_side_effects:
            return "medium"
        # 使用 registry 查询 risk_level 替代硬编码场景名判断
        return self._registry.get_risk_level(scenario)

    def _matches(self, condition: dict[str, Any], context: dict[str, Any]) -> bool:
        if "all" in condition:
            return all(self._matches(item, context) for item in condition["all"])
        if "any" in condition:
            return any(self._matches(item, context) for item in condition["any"])
        actual = self._read_path(context, str(condition["field"]))
        return self._compare(actual, str(condition["op"]), condition.get("value"))

    def _read_path(self, data: dict[str, Any], path: str) -> Any:
        cursor: Any = data
        for segment in path.split("."):
            if not isinstance(cursor, dict) or segment not in cursor:
                return None
            cursor = cursor[segment]
        return cursor

    def _compare(self, actual: Any, operator: str, expected: Any) -> bool:
        if operator == "eq":
            return actual == expected
        if operator == "ne":
            return actual != expected
        if operator == "gt":
            return isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual > expected
        if operator == "gte":
            return isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual >= expected
        if operator == "lt":
            return isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual < expected
        if operator == "lte":
            return isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and actual <= expected
        if operator == "in":
            return isinstance(expected, list) and actual in expected
        if operator == "not_in":
            return isinstance(expected, list) and actual not in expected
        return False

    def _compute_confidence(self, selected_rule: dict[str, Any] | None, sorted_rules: list[dict[str, Any]]) -> float:
        if selected_rule is None or not sorted_rules:
            return 0.55
        selected_id = str(selected_rule["id"])
        for index, rule in enumerate(sorted_rules):
            if str(rule["id"]) == selected_id:
                normalized = 1 - index / max(len(sorted_rules), 1)
                return round(0.6 + normalized * 0.4, 3)
        return 0.6
