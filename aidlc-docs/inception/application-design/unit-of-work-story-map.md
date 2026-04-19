# Unit Of Work Story Map

## 说明

本轮没有执行传统 `User Stories` 阶段，
因此这里不做 persona / story / acceptance criteria 的常规映射，
而改用以下四类来源进行映射：

1. **Core FR**：本轮必须优先落地的功能性要求
2. **Supporting FR**：需要被折叠处理或保持追踪的功能性要求
3. **NFR**：本轮必须保持的非功能约束
4. **Construction Intent**：来自执行计划和用户反馈的落地意图

## 工作单元总览

| Unit  | 核心主线             |
| ----- | ---------------- |
| UOW-1 | 边界与核心 contract   |
| UOW-2 | 默认状态链、持久化统一、恢复边界 |
| UOW-3 | 最小运行闭环与最小文档同步    |

## Core FR 映射

| Requirement | 说明          | Primary Unit | Secondary Unit | 处理方式                                     |
| ----------- | ----------- | ------------ | -------------- | ---------------------------------------- |
| FR-1        | 定位收束        | UOW-1        | UOW-3          | UOW-1 定义边界，UOW-3 同步最小外部表述                |
| FR-2        | 一等执行单元      | UOW-1        | UOW-3          | UOW-1 定义 execution contract，UOW-3 落到最小入口 |
| FR-3        | 默认状态链说明清晰   | UOW-2        | UOW-3          | UOW-2 定义主状态与派生状态，UOW-3 体现在返回结构           |
| FR-4        | 完成 contract | UOW-1        | UOW-3          | UOW-1 定义完成语义，UOW-3 反映到最小闭环输出             |
| FR-5        | 恢复 contract | UOW-2        | UOW-1          | UOW-2 定义恢复边界，UOW-1 提供 contract 主语义       |

## Supporting FR 映射

| Requirement | 说明       | Primary Unit | Secondary Unit | 处理方式                                    |
| ----------- | -------- | ------------ | -------------- | --------------------------------------- |
| FR-6        | 授权到执行门   | UOW-1        | UOW-3          | 不独立成单元；在 UOW-1 中明确消费层，在 UOW-3 中保留最小入口体现 |
| FR-7        | 文档与实现一致性 | UOW-3        | UOW-1          | 不独立成单元；只同步最小必要口径，避免叙事继续跑偏               |

## NFR 映射

| Requirement | 说明     | Primary Unit | Secondary Unit | 处理方式                                       |
| ----------- | ------ | ------------ | -------------- | ------------------------------------------ |
| NFR-1       | 向后兼容   | UOW-3        | UOW-1          | 主要通过最小运行闭环兼容旧入口，边界定义不破坏基础调用方式              |
| NFR-2       | 默认路径优先 | UOW-2        | UOW-1          | UOW-2 保证默认状态链成立，UOW-1 确保 contract 不由增强路径主导 |
| NFR-3       | 可验证性   | UOW-3        | UOW-2          | 本轮只保留最小闭环证明要求，详细验证设计后续补强                   |
| NFR-4       | 控制复杂度  | UOW-1        | UOW-2          | 通过减少单元数、限制范围与避免新增平台层实现                     |

## Construction Intent 映射

| Intent            | 来源                            | Primary Unit | Secondary Unit | 说明                |
| ----------------- | ----------------------------- | ------------ | -------------- | ----------------- |
| 先边界、后状态、再运行闭环     | 用户修改 + Execution Plan         | UOW-1        | UOW-2, UOW-3   | 决定整体执行顺序          |
| 保持精简、最快实现         | 用户修改问题回答                      | UOW-1        | 全部单元           | 决定不再扩展为 5 个以上单元   |
| 持久化语义统一           | 用户修改问题回答                      | UOW-2        | UOW-3          | 决定持久化成为核心单元而非附属话题 |
| 最小但干净且可运行         | 用户修改问题回答                      | UOW-3        | UOW-1, UOW-2   | 决定最终必须形成最小可运行闭环   |
| PostgreSQL 只是增强路径 | Requirements + Execution Plan | UOW-2        | UOW-1          | 决定默认语义不能由增强路径补位   |

## 覆盖性检查

### 必须被覆盖的核心要求

- FR-1: 已覆盖，Primary UOW-1
- FR-2: 已覆盖，Primary UOW-1
- FR-3: 已覆盖，Primary UOW-2
- FR-4: 已覆盖，Primary UOW-1
- FR-5: 已覆盖，Primary UOW-2
- NFR-2: 已覆盖，Primary UOW-2
- NFR-4: 已覆盖，Primary UOW-1

### 被折叠处理但未丢失的要求

- FR-6: 已折叠到 UOW-1 / UOW-3
- FR-7: 已折叠到 UOW-3
- NFR-3: 已折叠到 UOW-3，详细设计延后

### 延后补强的内容

- 完整 focused test / contract test 设计
- 更全面的工具面对齐
- 更广范围的 README / 文档体系重写

## 为什么这种映射足够

因为本轮不是围绕最终用户故事拆功能，
而是围绕“默认路径语义收束”拆最小变更单元。

因此，真正需要保证的是：

1. 核心 FR 不遗漏
2. Supporting FR 仍可追踪
3. 关键 NFR 不被忽略
4. 用户明确要求的“精简、最快实现、持久化统一、最小可运行”可以直接反映到单元划分中
