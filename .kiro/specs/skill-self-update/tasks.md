# 实施计划：Skills Hub 与技能自更新

## 概述

从 hermes-agent 移植 Skills Hub 核心逻辑到 velaris-agent，按增量开发顺序实施：数据模型与锁文件 → 安全扫描器 → Hub 操作 → Agent Tool 与 CLI → 内置技能 → 架构图更新 → 属性测试与集成测试。所有代码使用 Python，测试使用 pytest + Hypothesis。

## Tasks

- [x] 1. 数据模型、锁文件与 Taps 管理
  - [x] 1.1 创建 `src/openharness/skills/lock.py`，实现 LockEntry Pydantic model、HubLockFile 类（load/save/record_install/record_uninstall/get_installed/list_installed）和 TapsManager 类（load/save/add/remove/list_taps）
    - LockEntry 包含 name、source、identifier、trust_level、content_hash、install_path、files、installed_at、updated_at 字段
    - HubLockFile 默认路径为 `get_user_skills_dir() / "lock.json"`，使用原子写入（先写临时文件再 `os.replace()`）
    - TapsManager 默认路径为 `get_config_dir() / "taps.json"`，add 时验证 `owner/repo` 格式
    - Lock File JSON 格式包含 `version` 和 `skills` 字典
    - 无效 JSON 时 load() 返回空字典并记录警告
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.3, 5.5, 12.1, 12.2, 12.3, 12.4_

  - [x] 1.2 为 LockEntry/HubLockFile 编写单元测试 `tests/test_skills/test_lock.py`
    - 测试 load/save 往返一致性、损坏文件恢复、原子写入、空文件处理
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 12.1, 12.2_

  - [x] 1.3 为 TapsManager 编写单元测试
    - 测试 add/remove/list、格式验证、空文件处理
    - _Requirements: 5.1, 5.3, 5.5_

- [x] 2. 安全扫描器
  - [x] 2.1 创建 `src/openharness/skills/guard.py`，从 hermes-agent `tools/skills_guard.py` 移植安全扫描器
    - 实现 Finding dataclass、ScanResult dataclass、ThreatPattern 定义
    - 实现 `scan_file()`、`scan_skill()`、`should_allow_install()` 函数
    - 移植威胁模式正则（数据外泄、命令注入、破坏性操作、持久化后门、网络访问、代码混淆、路径穿越、挖矿、供应链攻击、权限提升、凭证暴露）
    - 实现结构性检查：文件数量限制、单文件大小限制、二进制文件检测、符号链接逃逸检测、不可见 Unicode 字符检测
    - verdict 为 "pass"/"fail"/"warn" 之一
    - _Requirements: 2.2, 2.4, 7.1, 7.2, 7.4_

  - [x] 2.2 编写安全扫描器单元测试 `tests/test_skills/test_guard.py`
    - 测试具体威胁模式匹配、结构性检查、边界情况
    - _Requirements: 2.2, 2.4, 7.1, 7.2_

- [x] 3. 检查点 — 确保基础模块测试通过
  - 确保所有测试通过，如有疑问请询问用户。

- [x] 4. Hub 核心操作与技能来源
  - [x] 4.1 创建 `src/openharness/skills/hub.py`，实现技能来源抽象层和 Hub 操作函数
    - 实现 SkillMeta Pydantic model（name、description、source、identifier、trust_level、repo、path、tags）
    - 实现 SkillBundle Pydantic model（name、files、source、identifier、trust_level、content_hash、metadata）
    - 实现 SkillSource ABC（search、fetch、source_id、trust_level_for）
    - 实现 GitHubAuth（认证链：PAT 环境变量 → `gh auth token` CLI → 匿名）
    - 实现 GitHubSource（通过 GitHub Contents API 搜索 SKILL.md、通过 Git Tree API 获取完整技能目录）
    - 实现 OptionalSkillSource（扫描本地 `optional-skills/` 目录）
    - 实现 `content_hash()`、`bundle_content_hash()` 哈希计算函数
    - 实现 `_validate_skill_name()`、`_validate_bundle_rel_path()`、`_normalize_bundle_path()` 路径验证
    - _Requirements: 1.1, 1.2, 1.4_

  - [x] 4.2 实现 Hub 安装/卸载/更新/搜索操作函数
    - 实现 `ensure_hub_dirs()` 确保 quarantine/ 和 audit/ 目录存在
    - 实现 `quarantine_bundle()` 将技能包写入隔离目录
    - 实现 `install_from_quarantine()` 从隔离区安装到用户技能目录
    - 实现 `install_skill()` 完整安装流程：fetch → quarantine → scan → install → record
    - 实现 `uninstall_skill()` 卸载技能并清理锁文件记录
    - 实现 `check_for_skill_updates()` 检查所有已安装技能的可用更新
    - 实现 `update_skill()` 更新指定技能
    - 实现 `parallel_search_sources()` 并行搜索所有来源并合并去重
    - 实现 `append_audit_log()` 追加审计日志条目
    - 已安装技能 force=False 时拒绝重复安装
    - _Requirements: 1.3, 1.5, 2.1, 2.3, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.3, 7.5_

  - [x] 4.3 编写 Hub 操作单元测试 `tests/test_skills/test_hub.py`
    - 测试 install、uninstall、update、search 的具体示例
    - 使用 mock 替代实际网络请求
    - _Requirements: 1.3, 2.1, 2.5, 2.6, 3.3, 4.3_

- [x] 5. 检查点 — 确保 Hub 核心逻辑测试通过
  - 确保所有测试通过，如有疑问请询问用户。

- [x] 6. Agent Tool 与 CLI 命令
  - [x] 6.1 创建 `src/openharness/tools/skills_hub_tool.py`，实现 SkillsHubTool
    - 继承 BaseTool，定义 SkillsHubInput Pydantic model（action、query、name、force）
    - 支持 action: search/install/check/update/uninstall/audit
    - 在 execute() 中调用 hub.py 对应操作函数
    - _Requirements: 1.3, 2.1, 3.1, 4.3_

  - [x] 6.2 创建 `src/openharness/commands/skills_cli.py`，实现 Typer CLI 子命令组
    - 创建 `skills_app = typer.Typer(name="skills")`
    - 实现 search、install、check、update、uninstall、list、audit 命令
    - 创建 `tap_app = typer.Typer(name="tap")` 子命令组，实现 add、remove、list
    - 在 `src/openharness/cli.py` 中注册 `app.add_typer(skills_app)` 和 `skills_app.add_typer(tap_app)`
    - 成功时输出操作结果摘要，失败时输出错误信息并返回非零退出码
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9_

  - [x] 6.3 编写 Agent Tool 单元测试 `tests/test_tools/test_skills_hub_tool.py`
    - 测试各 action 的输入输出验证
    - _Requirements: 6.1, 6.2_

  - [x] 6.4 编写 CLI 命令单元测试 `tests/test_skills/test_skills_cli.py`
    - 测试命令注册、参数解析、输出格式
    - _Requirements: 6.1, 6.2, 6.7, 6.8, 6.9_

- [x] 7. Skill Creator 内置技能
  - [x] 7.1 创建 `src/openharness/skills/bundled/content/skill-creator.md`
    - 从 `FrancyJGLisboa/agent-skill-creator` 适配内容
    - 包含 YAML frontmatter（name: skill-creator, description: ...）
    - 移除跨平台安装逻辑，集成现有 `skill_manage` 工具
    - 使用 velaris-agent 路径约定（`~/.velaris-agent/skills/`）
    - 5 阶段引导流程：发现 → 设计 → 架构 → 检测 → 实现
    - 内含技能文件格式规范说明（frontmatter 必填字段 name/description，可选字段 version/metadata.hermes.tags）
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 7.2 编写 skill-creator 内置技能测试 `tests/test_skills/test_skill_creator.py`
    - 测试 frontmatter 解析、注册表发现
    - _Requirements: 8.1, 8.2, 8.4_

- [x] 8. 检查点 — 确保用户面向功能测试通过
  - 确保所有测试通过，如有疑问请询问用户。

- [x] 9. 架构图更新
  - [x] 9.1 更新 `docs/diagrams/velaris-architecture.svg`
    - 在 L1（Agent Loop）层中新增 Skills Hub 组件节点，放置在 Skills 模块旁
    - 添加 Skills Hub → GitHub / Taps 的外部数据流箭头
    - 添加 Lock File 和 Quarantine Dir 关联存储标注
    - 保持 Style-1 Flat Icon 视觉风格一致
    - _Requirements: 8（架构图验收标准 1, 2, 3, 4）_

- [x] 10. 属性测试
  - [x] 10.1 编写 Hub 属性测试 `tests/test_skills/test_hub_properties.py` — Property 1: 搜索结果去重
    - **Property 1: 搜索结果去重**
    - 生成随机 SkillMeta 列表（部分 identifier 重复），验证 `parallel_search_sources()` 合并后无重复 identifier
    - **Validates: Requirements 1.3**

  - [x] 10.2 编写 Hub 属性测试 — Property 2: 内容哈希一致性
    - **Property 2: 内容哈希一致性**
    - 生成随机 files 字典（路径→内容），验证 `bundle.content_hash == bundle_content_hash(bundle.files)`
    - **Validates: Requirements 1.4**

  - [x] 10.3 编写 Hub 属性测试 — Property 3: 来源故障容错
    - **Property 3: 来源故障容错**
    - 生成随机来源列表（随机标记部分为失败），验证 `parallel_search_sources()` 仍返回未出错来源的结果
    - **Validates: Requirements 1.5, 3.6**

  - [x] 10.4 编写 Guard 属性测试 `tests/test_skills/test_guard_properties.py` — Property 4: 威胁模式检测
    - **Property 4: 威胁模式检测**
    - 生成随机文件内容并注入已知高危威胁模式，验证 `scan_file()` 返回 severity="high" 的 Finding
    - **Validates: Requirements 2.4, 7.1, 7.4**

  - [x] 10.5 编写 Lock 属性测试 `tests/test_skills/test_lock_properties.py` — Property 5: 安装后锁文件完整性
    - **Property 5: 安装后锁文件完整性**
    - 生成随机 LockEntry，验证 record_install 后 get_installed 返回完整记录且 content_hash 一致
    - **Validates: Requirements 2.5, 4.2**

  - [x] 10.6 编写 Hub 属性测试 — Property 6: 重复安装拒绝
    - **Property 6: 重复安装拒绝**
    - 生成随机已安装技能名，验证 force=False 时 install_skill() 返回错误且 Lock_File 不变
    - **Validates: Requirements 2.6**

  - [x] 10.7 编写 Hub 属性测试 — Property 7: 哈希变更检测
    - **Property 7: 哈希变更检测**
    - 生成随机哈希对（相同/不同），验证 check_for_skill_updates() 正确标记有更新的技能
    - **Validates: Requirements 3.3**

  - [x] 10.8 编写 Lock 属性测试 — Property 8: 更新后锁文件刷新
    - **Property 8: 更新后锁文件刷新**
    - 生成随机 LockEntry + 新哈希，验证更新后 content_hash 更新且 updated_at 非空
    - **Validates: Requirements 3.5**

  - [x] 10.9 编写 Lock 属性测试 — Property 9: 卸载清理
    - **Property 9: 卸载清理**
    - 生成随机已安装技能列表，验证卸载后 Lock_File 中不再包含该技能记录
    - **Validates: Requirements 4.3**

  - [x] 10.10 编写 Lock 属性测试 — Property 10: Tap 移除
    - **Property 10: Tap 移除**
    - 生成随机 Tap 列表，验证移除后 list_taps() 不包含该 Tap
    - **Validates: Requirements 5.3**

  - [x] 10.11 编写 Lock 属性测试 — Property 11: Tap 地址格式验证
    - **Property 11: Tap 地址格式验证**
    - 生成随机无效字符串（空字符串、缺少 `/`、包含空格或特殊字符），验证 TapsManager.add() 拒绝添加
    - **Validates: Requirements 5.5**

  - [x] 10.12 编写 Guard 属性测试 — Property 12: 扫描报告结构完整性
    - **Property 12: 扫描报告结构完整性**
    - 生成随机技能目录结构，验证 ScanResult 包含所有必填字段且 verdict 为合法值
    - **Validates: Requirements 7.2**

  - [x] 10.13 编写 Hub 属性测试 — Property 13: 审计日志追加
    - **Property 13: 审计日志追加**
    - 生成随机操作序列，验证每次操作后审计日志新增一条包含 action、skill name 和 timestamp 的记录
    - **Validates: Requirements 7.5**

  - [x] 10.14 编写集成属性测试 `tests/test_skills/test_integration_properties.py` — Property 14: Hub 安装技能可被注册表发现
    - **Property 14: Hub 安装技能可被注册表发现**
    - 生成随机 SKILL.md 内容写入用户技能目录，验证 load_skill_registry() 能发现该技能
    - **Validates: Requirements 11.2**

  - [x] 10.15 编写集成属性测试 — Property 15: 手动技能不影响锁文件
    - **Property 15: 手动技能不影响锁文件**
    - 生成随机手动技能写入用户技能目录，验证 Lock_File 内容不变
    - **Validates: Requirements 11.4**

  - [x] 10.16 编写 Lock 属性测试 — Property 16: Lock File 往返一致性
    - **Property 16: Lock File 序列化往返一致性**
    - 生成随机 LockEntry 字典，验证 save() 后 load() 产生等价数据对象
    - **Validates: Requirements 12.2**

  - [x] 10.17 编写 Lock 属性测试 — Property 17: 无效 JSON 错误处理
    - **Property 17: 无效 JSON 解析错误处理**
    - 生成随机非法 JSON 字符串，验证 HubLockFile.load() 返回空字典而非抛出异常
    - **Validates: Requirements 12.3, 4.5**

- [x] 11. 最终检查点 — 确保所有测试通过
  - 确保所有测试通过，如有疑问请询问用户。

## Notes

- 标记 `*` 的任务为可选任务，可跳过以加速 MVP 交付
- 每个任务引用具体需求编号以确保可追溯性
- 检查点确保增量验证
- 属性测试使用 Hypothesis 库，每个属性至少运行 100 次
- 单元测试验证具体示例和边界情况
- 从 hermes-agent 移植时需调整 import 路径和配置目录函数
