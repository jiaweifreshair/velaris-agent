# UOW-1 Functional Design Clarification Questions

我在你填写的 `uow-1-architecture-boundary-and-core-contract-functional-design-plan.md` 中识别到两处会直接影响 Functional Design 质量的歧义。
按照 AI-DLC 要求，需要先澄清后才能继续生成设计产物。

## 歧义 1：Completion 混合模型的主从关系

你在 Question 2 选择了：

- `C) 混合模型：既有主状态枚举，也保留三层完成字段用于解释`

当前仍不够明确的是：

- 主状态枚举和三层完成字段，谁是**主真相源**？
- 另一组字段是由它派生，还是二者并列维护？

## Question 1

在 `completion` 混合模型中，你希望谁作为主真相源？

A) 主状态枚举是主真相源；结构完成 / 约束完成 / 目标完成是解释性派生字段
B) 三层完成字段是主真相源；主状态枚举由三层完成组合推导得出
C) 二者并列持久化，允许显式覆盖，不强制单向推导
D) Other（请在 [Answer]: 后补充说明）

[Answer]: A

## 歧义 2：场景化执行门的风险判定与动作边界

你在 Question 3 选择了：

- `C) 场景化执行门：高风险场景 fail-closed，低风险场景允许降级继续`

当前仍不够明确的是：

- 谁来判定高风险 / 中风险 / 低风险
- 中风险场景应该 fail-closed 还是 degrade-continue
- “允许降级继续”具体降级到哪一层

## Question 2

风险等级应主要由哪一层判定？

A) 由 `PolicyRouter` / routing 决策中的 `risk.level` 判定，Functional Design 直接消费
B) 由 governance 规则单独判定，不直接复用 routing 的 `risk.level`
C) 由 scenario profile 根据场景上下文二次判定
D) Other（请在 [Answer]: 后补充说明）

[Answer]: C

## Question 3

对于**中风险**场景，你更希望执行门如何处理？

A) 与高风险一致：fail-closed
B) 与低风险一致：允许降级继续
C) 需要额外授权 / 明确 capability token 后才能继续
D) Other（请在 [Answer]: 后补充说明）

[Answer]: B

## Question 4

如果场景被允许“降级继续”，你更希望降级到哪种方式？

A) 只允许生成 plan / routing / authority / execution 草案，不进入真实 scenario 执行
B) 允许进入 scenario 执行，但禁止任何外部副作用能力
C) 允许完整执行，但必须强制记录审计并标记为 degraded mode
D) Other（请在 [Answer]: 后补充说明）

[Answer]: C
