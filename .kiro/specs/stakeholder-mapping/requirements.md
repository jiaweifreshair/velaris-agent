# Requirements Document

## Introduction

Velaris 决策智能引擎的利益相关方映射 (Stakeholder Mapping) 功能升级。灵感来自 Google Cassie Kozyrkov 的 Decision Intelligence 方法论，该方法论将利益相关方映射视为决策智能的关键组成部分。

当前 Velaris 已有基础的 `AlignmentReport`（用户-组织对齐分析）和 `PreferenceLearner.compute_alignment()`，但缺乏完整的利益相关方建模能力。本次升级将：

- 将三类决策主体（用户、组织、用户-组织关系）从隐式概念提升为显式的 Stakeholder 模型
- 为每个 Stakeholder 建立独立的目标图谱、影响力权重和利益维度
- 扩展 AlignmentReport 为多方利益相关方之间的全量映射
- 支持利益冲突检测、影响力传播分析和协商策略生成
- 将利益相关方上下文注入决策流程，使每次决策都能感知所有相关方的立场

## Glossary

- **Stakeholder**: 决策过程中的利益相关方实体，包含身份、角色、目标、影响力和利益维度。当前覆盖三类：用户 (user)、组织 (org)、用户-组织关系 (relationship)
- **Stakeholder_Registry**: 利益相关方注册表，负责 Stakeholder 的创建、检索、更新和删除
- **Stakeholder_Map**: 利益相关方映射图，描述一个决策场景中所有 Stakeholder 之间的关系、冲突和协同
- **Influence_Weight**: 某个 Stakeholder 在特定决策维度上的影响力权重 (0-1)，反映该方对决策结果的影响程度
- **Interest_Dimension**: 利益维度，描述 Stakeholder 关注的决策方面（如 cost、growth、compliance）及其偏好方向
- **Conflict_Detection_Engine**: 冲突检测引擎，分析多个 Stakeholder 之间在同一决策维度上的利益冲突
- **Negotiation_Strategy**: 协商策略，基于冲突分析生成的多方妥协方案，包含每方的让步幅度和优先级
- **Stakeholder_Context**: 利益相关方上下文，在决策流程中注入的所有相关方立场、权重和约束的聚合视图
- **Decision_Curve_Tracker**: 决策曲线追踪器，按 Stakeholder 维度追踪决策能力随时间的变化
- **Alignment_Matrix**: 对齐矩阵，多个 Stakeholder 两两之间的对齐度评分矩阵
- **Scenario_Engine**: 场景引擎，Velaris 中负责执行具体业务场景（如 lifegoal、travel）的模块
- **Preference_Learner**: 偏好学习器，从用户历史选择中学习个性化权重的模块
- **Serializer**: 将 Stakeholder_Map 等内存对象序列化为 JSON 格式的组件
- **Parser**: 将 JSON 格式数据反序列化为 Stakeholder_Map 等内存对象的组件

## Requirements

### Requirement 1: Stakeholder 数据模型

**User Story:** As a 决策引擎开发者, I want to 定义结构化的 Stakeholder 数据模型, so that 三类决策主体（用户、组织、用户-组织关系）都有统一的表示方式。

#### Acceptance Criteria

1. THE Stakeholder_Registry SHALL represent each Stakeholder with a unique identifier, a role (user, org, or relationship), a display name, a scenario scope, a set of Interest_Dimensions, and a set of Influence_Weights
2. WHEN a Stakeholder of role "relationship" is created, THE Stakeholder_Registry SHALL require references to exactly two other Stakeholder identifiers (one user, one org)
3. THE Stakeholder_Registry SHALL validate that each Interest_Dimension contains a dimension name, a preference direction (higher_is_better or lower_is_better), and a weight between 0.0 and 1.0 inclusive
4. THE Stakeholder_Registry SHALL validate that the sum of all Influence_Weights for a single Stakeholder is between 0.0 and 1.0 inclusive per decision dimension
5. IF a Stakeholder is created with a duplicate identifier within the same scenario, THEN THE Stakeholder_Registry SHALL return a validation error describing the conflict

### Requirement 2: Stakeholder 注册与生命周期管理

**User Story:** As a 决策引擎开发者, I want to 注册、更新和移除 Stakeholder, so that 利益相关方信息在决策过程中保持准确和最新。

#### Acceptance Criteria

1. WHEN a new Stakeholder is registered, THE Stakeholder_Registry SHALL persist the Stakeholder and return the assigned identifier
2. WHEN a Stakeholder is updated, THE Stakeholder_Registry SHALL merge the updated fields with existing data and increment an internal version counter
3. WHEN a Stakeholder is removed, THE Stakeholder_Registry SHALL mark the Stakeholder as inactive rather than deleting the record, preserving historical references
4. THE Stakeholder_Registry SHALL support listing all active Stakeholders filtered by scenario and role
5. IF a Stakeholder referenced by an active Stakeholder_Map is removed, THEN THE Stakeholder_Registry SHALL return an error indicating the Stakeholder is still in use

### Requirement 3: Stakeholder Map 构建

**User Story:** As a 决策引擎开发者, I want to 构建利益相关方映射图, so that 一个决策场景中所有相关方的关系和立场可以被整体分析。

#### Acceptance Criteria

1. WHEN a Stakeholder_Map is built for a scenario, THE Stakeholder_Map SHALL include all active Stakeholders registered for that scenario
2. THE Stakeholder_Map SHALL compute pairwise alignment scores between every pair of Stakeholders using their Interest_Dimensions and Influence_Weights
3. THE Stakeholder_Map SHALL classify each pairwise relationship as "aligned" (score >= 0.7), "neutral" (0.3 <= score < 0.7), or "conflicting" (score < 0.3)
4. WHEN a Stakeholder_Map contains fewer than two Stakeholders, THE Stakeholder_Map SHALL return a valid map with an empty Alignment_Matrix and no conflicts
5. THE Stakeholder_Map SHALL include a timestamp and a scenario identifier for traceability

### Requirement 4: 利益冲突检测

**User Story:** As a 决策引擎用户, I want to 自动检测利益相关方之间的冲突, so that 决策过程中的潜在矛盾可以被提前识别和处理。

#### Acceptance Criteria

1. WHEN a Stakeholder_Map is analyzed, THE Conflict_Detection_Engine SHALL identify all dimension-level conflicts where two Stakeholders have opposing preference directions on the same dimension
2. WHEN a Stakeholder_Map is analyzed, THE Conflict_Detection_Engine SHALL identify all weight-level conflicts where two Stakeholders assign weights differing by more than 0.3 on the same dimension
3. THE Conflict_Detection_Engine SHALL assign a severity score between 0.0 and 1.0 to each detected conflict based on the product of the two Stakeholders' Influence_Weights and the magnitude of the disagreement
4. THE Conflict_Detection_Engine SHALL return conflicts sorted by severity in descending order
5. IF no conflicts are detected, THEN THE Conflict_Detection_Engine SHALL return an empty conflict list with a summary indicating full alignment

### Requirement 5: 协商策略生成

**User Story:** As a 决策引擎用户, I want to 获得基于冲突分析的协商策略, so that 多方利益可以通过合理妥协达成平衡。

#### Acceptance Criteria

1. WHEN conflicts are detected in a Stakeholder_Map, THE Negotiation_Strategy SHALL generate a compromise proposal for each conflicting dimension
2. THE Negotiation_Strategy SHALL compute each Stakeholder's suggested concession proportional to the inverse of the Stakeholder's Influence_Weight on that dimension (lower influence concedes more)
3. THE Negotiation_Strategy SHALL ensure that the proposed compromise weight for each dimension falls between the minimum and maximum weights of the conflicting Stakeholders
4. THE Negotiation_Strategy SHALL include a feasibility score (0.0 to 1.0) for each proposal based on the total concession required from all parties
5. IF a conflict involves a hard constraint from an OrgPolicy, THEN THE Negotiation_Strategy SHALL mark that dimension as non-negotiable and exclude the constraint holder from concession calculations

### Requirement 6: Stakeholder 上下文注入决策流程

**User Story:** As a 决策引擎用户, I want to 在每次决策中自动注入利益相关方上下文, so that 推荐结果能反映所有相关方的立场和约束。

#### Acceptance Criteria

1. WHEN a decision is initiated for a scenario, THE Scenario_Engine SHALL retrieve the active Stakeholder_Map for that scenario
2. THE Scenario_Engine SHALL merge Stakeholder Influence_Weights into the decision weight computation alongside user preferences and org policy weights
3. THE Scenario_Engine SHALL include the Stakeholder_Context (active conflicts, alignment scores, negotiation status) in the DecisionRecord's env_snapshot field
4. WHILE a Stakeholder_Map contains unresolved conflicts with severity above 0.5, THE Scenario_Engine SHALL append a warning to the decision explanation indicating the unresolved stakeholder conflicts
5. IF no Stakeholder_Map exists for the scenario, THEN THE Scenario_Engine SHALL proceed with the existing weight computation logic (user preferences + org policy) without error

### Requirement 7: 决策曲线按 Stakeholder 维度追踪

**User Story:** As a 决策引擎用户, I want to 按利益相关方维度追踪决策曲线, so that 每个相关方的决策能力改进可以被独立量化。

#### Acceptance Criteria

1. WHEN a decision is completed, THE Decision_Curve_Tracker SHALL update the DecisionCurvePoint for each Stakeholder involved in the decision
2. THE Decision_Curve_Tracker SHALL compute per-Stakeholder metrics including decision count, acceptance rate, bias count, and weight stability
3. THE Decision_Curve_Tracker SHALL compute the alignment trend between each Stakeholder pair over a configurable time window (default: 30 days)
4. WHEN queried for a Stakeholder's decision curve, THE Decision_Curve_Tracker SHALL return a time-ordered list of DecisionCurvePoints for that Stakeholder
5. THE Decision_Curve_Tracker SHALL detect convergence (alignment score increasing over 3 consecutive periods) and divergence (alignment score decreasing over 3 consecutive periods) trends between Stakeholder pairs

### Requirement 8: Stakeholder Map 序列化与反序列化

**User Story:** As a 决策引擎开发者, I want to 将 Stakeholder_Map 序列化为 JSON 并从 JSON 反序列化, so that 利益相关方映射可以被持久化和跨会话恢复。

#### Acceptance Criteria

1. THE Serializer SHALL convert a Stakeholder_Map object into a JSON string that preserves all fields including nested Stakeholder objects, Alignment_Matrix entries, and conflict records
2. THE Parser SHALL convert a valid JSON string back into a Stakeholder_Map object with all fields restored to their original types and values
3. FOR ALL valid Stakeholder_Map objects, parsing the serialized JSON output and then serializing again SHALL produce a JSON string identical to the first serialization (round-trip property)
4. IF the Parser receives a JSON string with missing required fields, THEN THE Parser SHALL return a descriptive error listing the missing fields
5. IF the Parser receives a JSON string with invalid field types, THEN THE Parser SHALL return a descriptive error identifying the field and expected type

### Requirement 9: 从现有模型迁移兼容

**User Story:** As a 决策引擎开发者, I want to 确保新的 Stakeholder 模型与现有 AlignmentReport 和 OrgPolicy 兼容, so that 现有功能不会因升级而中断。

#### Acceptance Criteria

1. THE Stakeholder_Registry SHALL support constructing a user-type Stakeholder from an existing UserPreferences object by mapping weights to Interest_Dimensions and computing Influence_Weights from confidence scores
2. THE Stakeholder_Registry SHALL support constructing an org-type Stakeholder from an existing OrgPolicy object by mapping org weights to Interest_Dimensions and constraints to non-negotiable dimensions
3. WHEN compute_alignment is called with the existing two-parameter signature (user_id, org_policy), THE Preference_Learner SHALL produce results consistent with the current AlignmentReport format
4. THE Stakeholder_Map SHALL support exporting a two-party subset as an AlignmentReport for backward compatibility
5. WHEN a DecisionRecord created before the upgrade is loaded, THE Parser SHALL handle the absence of Stakeholder_Context in env_snapshot without error
