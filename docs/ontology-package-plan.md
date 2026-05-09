# Velaris 本体包设计方案

> 目标：把 `velaris-agent` 的本体能力收敛到 `src/velaris_agent/ontology/`，让“人本体”和“ROI 本体”成为统一、稳定、可学习的基础层。

## 1. 这个包解决什么问题

当前 `velaris-agent` 已经具备：

- 场景识别
- 决策图执行
- 路由治理
- 偏好学习
- 成本追踪

但这些能力的语义仍分散在 `memory/`、`decision/`、`velaris/`、`scenarios/` 中。  
`ontology/` 的目标不是推翻这些模块，而是补上一层“**稳定的领域对象中心**”。

它要解决的核心问题是：

1. 把人相关状态标准化
2. 把 ROI 相关评估标准化
3. 把场景语义映射标准化
4. 让不同场景共享同一套本体原语

## 2. 包边界

### 2.1 包的职责

`src/velaris_agent/ontology/` 只负责三件事：

- 定义本体对象
- 维护本体注册与版本
- 提供场景映射入口

### 2.2 不负责的内容

这个包不负责：

- 场景执行
- 路由策略
- 权限审批
- 具体业务落库
- UI 展示

这些工作分别属于 `decision/`、`velaris/`、`scenarios/`、`saibo_yanling`。

## 3. 推荐目录结构

```text
src/velaris_agent/ontology/
├── __init__.py
├── base.py
├── types.py
├── registry.py
├── human.py
├── roi.py
├── scene.py
└── scenes/
    ├── __init__.py
    ├── writing.py
    ├── travel.py
    ├── procurement.py
    ├── tokencost.py
    └── general.py
```

### 3.1 文件职责

| 文件 | 职责 |
|---|---|
| `base.py` | 定义本体基类、快照基类、版本化约束 |
| `types.py` | 枚举、量化类型、基础别名 |
| `registry.py` | 本体注册、版本查询、场景映射发现 |
| `human.py` | 人本体：习惯、行为、能力、约束、角色、偏好 |
| `roi.py` | ROI 本体：收益、成本、风险、时效、置信度、学习价值 |
| `scene.py` | 场景本体：场景特征模板、权重模板、约束模板 |
| `scenes/*` | 各场景的映射与校准逻辑 |

## 4. 本体对象设计

### 4.1 通用基类

建议先定义两个基础对象：

- `OntologyVersion`：记录版本号、来源、更新时间
- `OntologySnapshot`：记录某一时点的本体快照

它们是所有本体对象的共同元数据层。

### 4.2 人本体

#### 核心对象

- `UserProfileOntology`
- `HabitPattern`
- `BehaviorState`
- `RoleContext`
- `CapabilityState`
- `ConstraintState`
- `PreferenceState`

#### 语义说明

人本体回答的是：

- 这个用户是谁
- 这个用户当前处于什么状态
- 这个用户通常如何行动
- 这个用户现在受什么约束
- 这个用户更容易接受什么样的建议

#### 推荐字段

| 对象 | 关键字段 |
|---|---|
| `UserProfileOntology` | `subject_id`, `role_context`, `age_band`, `grade`, `region`, `language` |
| `HabitPattern` | `reading_window`, `writing_window`, `review_frequency`, `response_latency` |
| `BehaviorState` | `completion_rate`, `dropoff_pattern`, `follow_through`, `feedback_acceptance` |
| `RoleContext` | `primary_role`, `support_role`, `family_context`, `school_context`, `work_context` |
| `CapabilityState` | `structure_skill`, `language_skill`, `attention_span`, `independent_completion` |
| `ConstraintState` | `time_budget`, `device_limit`, `caregiver_availability`, `emotion_state` |
| `PreferenceState` | `preference_weights`, `topic_bias`, `format_preference`, `risk_tolerance` |

### 4.3 ROI 本体

#### 核心对象

- `DecisionROIProfile`
- `BenefitModel`
- `CostModel`
- `RiskModel`
- `HorizonModel`
- `ConfidenceModel`
- `LearningImpactModel`

#### 语义说明

ROI 本体回答的是：

- 当前动作带来什么收益
- 需要付出什么成本
- 风险有多大
- 多久能见效
- 对长期成长是否有帮助

#### 推荐字段

| 对象 | 关键字段 |
|---|---|
| `DecisionROIProfile` | `expected_roi`, `risk_adjusted_roi`, `learning_value`, `dependency_penalty`, `time_to_value`, `confidence` |
| `BenefitModel` | `short_term_gain`, `long_term_gain`, `learning_gain`, `transfer_gain` |
| `CostModel` | `time_cost`, `money_cost`, `cognitive_cost`, `execution_cost` |
| `RiskModel` | `failure_risk`, `dependency_risk`, `misguidance_risk`, `opportunity_cost` |
| `HorizonModel` | `immediate_value`, `weekly_value`, `monthly_value`, `decay_rate` |
| `ConfidenceModel` | `confidence`, `evidence_strength`, `observability` |
| `LearningImpactModel` | `habit_value`, `independence_gain`, `skill_growth` |

### 4.4 场景本体

场景本体不是核心语义，而是场景模板：

- 哪些字段有意义
- 哪些权重默认更高
- 哪些约束要优先检查
- 哪些反馈字段要回写

建议对象：

- `SceneOntologyProfile`
- `SceneFeatureSpec`
- `SceneWeightProfile`
- `SceneFeedbackMapping`

## 5. 数据流

### 5.1 输入

场景输入进入本体层后，按以下顺序处理：

1. 场景适配器收集结构化输入
2. 人本体编译器提炼状态
3. ROI 编译器评估收益与成本
4. 决策图执行器做排序与解释
5. 反馈回写更新本体快照

### 5.2 输出

本体层的输出应该是结构化的，而不是自然语言：

- 当前人本体快照
- 当前 ROI 画像
- 场景权重
- 决策建议
- 反馈写回提示

## 6. 版本与注册

### 6.1 为什么要版本化

本体不是写死一次就完事的。  
随着场景增多，字段会增加、权重会调整、映射会变化，因此必须版本化。

### 6.2 注册表职责

`registry.py` 建议负责：

- 根据场景名获取本体版本
- 获取人本体 schema
- 获取 ROI schema
- 获取场景模板
- 发现新场景的本体映射

### 6.3 兼容原则

- 旧版本快照要能被读取
- 新字段要可选且默认安全
- 不能用场景字段污染通用本体字段

## 7. 与现有模块的关系

### 7.1 可以直接复用

- `src/velaris_agent/memory/types.py`
  - 已经有 `DecisionGoal`、`OrgPolicy`、`DecisionRecord`、`UserPreferences`

- `src/velaris_agent/decision/context.py`
  - 已经适合作为运行期上下文

- `src/velaris_agent/decision/operators/*`
  - 已经是本体编译后的执行算子

- `src/velaris_agent/scenarios/registry.py`
  - 已经支持场景发现和注册

- `src/velaris_agent/velaris/router.py`
  - 可承接 ROI 风险与治理约束

### 7.2 需要补强

- `memory/types.py`
  - 增补人本体与 ROI 本体的字段，或在新包中建立更清晰的领域对象

- `decision/contracts.py`
  - 需要从场景词中解耦，逐步转成中性契约

- `biz/engine.py`
  - 应减少业务语义承载，转为场景适配层

## 8. 落地顺序

### Phase 1：基础类型

- 定义基类、版本、快照
- 定义人本体与 ROI 本体的最小字段集

### Phase 2：场景映射

- 为写作、旅价、采购、学习规划建立映射
- 为每个场景定义权重模板

### Phase 3：反馈学习

- 让本体对象参与偏好学习
- 让历史反馈更新能力、习惯和 ROI 置信度

### Phase 4：持久化

- 将本体快照与反馈写入持久层
- 保证可回放与可审计

## 9. 验收标准

- 该包能描述一个用户在任一场景下的状态
- 该包能描述一个动作在任一场景下的 ROI
- 新场景只需新增映射，不需要重写核心对象
- 快照可版本化、可回放、可学习
- 不同场景之间不会互相污染字段语义
