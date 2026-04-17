# 需求文档：Skills Hub 与技能自更新

## 简介

为 velaris-agent 引入完整的 Skills Hub 系统，参考 hermes-agent 的技能自更新架构。该系统支持多源技能发现、安装隔离与安全扫描、基于内容哈希的自动更新检测、锁文件溯源追踪，以及 CLI 命令行管理。同时新增 skill-creator 内置技能用于引导用户创建新技能，并更新架构图以反映 Skills Hub 层。

## 术语表

- **Skills_Hub**: 技能中心服务，负责技能的搜索、安装、更新、卸载等全生命周期管理
- **Skill_Source**: 技能来源适配器，每个来源实现统一的搜索与获取接口
- **Lock_File**: 锁文件（`lock.json`），记录每个已安装技能的来源、哈希、信任等级等溯源信息
- **Content_Hash**: 技能文件内容的 SHA-256 哈希值，用于检测上游变更
- **Quarantine_Dir**: 隔离目录，技能安装前的临时存放区域，用于安全扫描
- **Security_Scanner**: 安全扫描器，对隔离区中的技能文件执行静态安全检查
- **Tap**: 自定义技能源，指向一个 GitHub 仓库，通过 `taps.json` 配置管理
- **Skill_Registry**: 现有的技能注册表，负责加载和查询已注册技能
- **Skill_Creator_Skill**: 内置技能创建向导技能，引导用户通过交互式流程创建符合规范的新技能
- **Architecture_Diagram**: 位于 `docs/diagrams/velaris-architecture.svg` 的系统架构图

## 需求

### 需求 1：技能来源适配器

**用户故事：** 作为开发者，我希望 Skills Hub 支持多种技能来源，以便从不同渠道发现和获取技能。

#### 验收标准

1. THE Skills_Hub SHALL 提供统一的 Skill_Source 抽象接口，包含 `search(query)` 和 `fetch(identifier)` 方法
2. THE Skills_Hub SHALL 内置以下 Skill_Source 实现：内置可选技能源（OptionalSkillSource）、GitHub 仓库源（GitHubSource）
3. WHEN 调用 `search(query)` 时，THE Skills_Hub SHALL 并行查询所有已注册的 Skill_Source 并合并去重结果
4. WHEN 调用 `fetch(identifier)` 时，THE Skill_Source SHALL 返回技能文件内容及其 Content_Hash
5. IF 某个 Skill_Source 在查询过程中发生网络错误，THEN THE Skills_Hub SHALL 记录错误日志并跳过该来源，继续返回其他来源的结果

### 需求 2：技能安装与隔离

**用户故事：** 作为开发者，我希望安装技能时经过隔离和安全扫描，以便防止恶意技能损害系统。

#### 验收标准

1. WHEN 用户请求安装一个技能时，THE Skills_Hub SHALL 先将技能文件下载到 Quarantine_Dir
2. WHILE 技能文件位于 Quarantine_Dir 中，THE Security_Scanner SHALL 对技能文件执行静态安全检查
3. WHEN Security_Scanner 检查通过时，THE Skills_Hub SHALL 将技能文件从 Quarantine_Dir 移动到 `~/.velaris-agent/skills/<slug>/` 目录
4. IF Security_Scanner 检测到安全风险，THEN THE Skills_Hub SHALL 拒绝安装并向用户返回具体的风险描述
5. WHEN 安装完成时，THE Skills_Hub SHALL 在 Lock_File 中写入该技能的溯源记录，包含 source、identifier、trust_level、content_hash、install_path、files 列表、installed_at 时间戳
6. IF 目标技能已存在且未指定强制安装，THEN THE Skills_Hub SHALL 拒绝安装并提示用户使用更新命令

### 需求 3：基于哈希的自更新检测

**用户故事：** 作为开发者，我希望系统能自动检测已安装技能是否有上游更新，以便及时获取最新版本。

#### 验收标准

1. WHEN 用户执行更新检查时，THE Skills_Hub SHALL 读取 Lock_File 中每个技能的 Content_Hash
2. THE Skills_Hub SHALL 从对应的 Skill_Source 获取该技能的最新 Content_Hash
3. WHEN 本地 Content_Hash 与上游 Content_Hash 不一致时，THE Skills_Hub SHALL 将该技能标记为"有可用更新"
4. WHEN 用户确认更新时，THE Skills_Hub SHALL 重新执行安装流程（含隔离与安全扫描），并以 `force=True` 覆盖已有文件
5. WHEN 更新完成时，THE Skills_Hub SHALL 更新 Lock_File 中的 content_hash 和 updated_at 字段
6. IF 上游来源不可达，THEN THE Skills_Hub SHALL 报告该技能的更新检查失败并继续检查其余技能


### 需求 4：Lock File 溯源管理

**用户故事：** 作为开发者，我希望每个已安装技能都有完整的溯源记录，以便追踪技能来源和变更历史。

#### 验收标准

1. THE Skills_Hub SHALL 在 `~/.velaris-agent/skills/lock.json` 维护全局锁文件
2. THE Lock_File SHALL 为每个已安装技能记录以下字段：name、source、identifier、trust_level、content_hash、install_path、files、installed_at、updated_at
3. WHEN 技能被卸载时，THE Skills_Hub SHALL 从 Lock_File 中移除对应记录
4. WHEN Lock_File 被修改时，THE Skills_Hub SHALL 以原子写入方式更新文件，防止并发写入导致数据损坏
5. IF Lock_File 不存在或格式损坏，THEN THE Skills_Hub SHALL 创建新的空锁文件并记录警告日志

### 需求 5：Taps 自定义来源管理

**用户故事：** 作为开发者，我希望能添加自定义的 GitHub 仓库作为技能来源，以便使用团队或社区维护的私有技能集。

#### 验收标准

1. THE Skills_Hub SHALL 在 `~/.velaris-agent/taps.json` 维护自定义来源配置
2. WHEN 用户添加一个 Tap 时，THE Skills_Hub SHALL 验证该 GitHub 仓库可访问，并将其注册为新的 Skill_Source
3. WHEN 用户移除一个 Tap 时，THE Skills_Hub SHALL 从 taps.json 中删除对应记录
4. THE Skills_Hub SHALL 在技能搜索时自动包含所有已注册 Tap 来源
5. IF 添加的 Tap 仓库地址格式无效，THEN THE Skills_Hub SHALL 拒绝添加并返回格式错误提示

### 需求 6：CLI 命令行管理

**用户故事：** 作为开发者，我希望通过 CLI 命令管理技能的完整生命周期，以便高效地搜索、安装、更新和卸载技能。

#### 验收标准

1. THE CLI SHALL 提供 `velaris skills search <query>` 命令，在所有来源中搜索技能并展示结果列表
2. THE CLI SHALL 提供 `velaris skills install <identifier>` 命令，执行技能安装流程
3. THE CLI SHALL 提供 `velaris skills check [name]` 命令，检查指定技能或全部技能的可用更新
4. THE CLI SHALL 提供 `velaris skills update [name]` 命令，更新指定技能或全部有更新的技能
5. THE CLI SHALL 提供 `velaris skills uninstall <name>` 命令，卸载指定技能并清理 Lock_File 记录
6. THE CLI SHALL 提供 `velaris skills list` 命令，展示所有已安装技能及其来源和版本信息
7. THE CLI SHALL 提供 `velaris skills tap add|remove|list` 子命令，管理自定义 Tap 来源
8. WHEN CLI 命令执行成功时，THE CLI SHALL 输出操作结果摘要
9. IF CLI 命令执行失败，THEN THE CLI SHALL 输出错误信息并返回非零退出码

### 需求 7：安全扫描与审计

**用户故事：** 作为开发者，我希望技能安装前经过安全扫描，并能随时重新审计已安装技能，以便确保技能内容安全可信。

#### 验收标准

1. THE Security_Scanner SHALL 检查技能文件中是否包含可疑的代码模式（如 shell 命令注入、文件系统越权访问路径）
2. THE Security_Scanner SHALL 对每次扫描生成结构化的扫描报告，包含扫描时间、风险等级、发现项列表
3. THE CLI SHALL 提供 `velaris skills audit [name]` 命令，对已安装技能重新执行安全扫描
4. WHEN 扫描发现高风险项时，THE Security_Scanner SHALL 将风险等级标记为 "high" 并阻止自动安装
5. THE Skills_Hub SHALL 记录所有安装和卸载操作到审计日志文件

### 需求 8：Skill Creator 内置技能

**用户故事：** 作为用户，我希望系统内置 skill-creator 技能，以便通过交互式引导快速创建符合规范的新技能。

#### 验收标准

1. THE Skill_Registry SHALL 包含名为 "skill-creator" 的内置技能
2. THE Skill_Creator_Skill SHALL 以 YAML frontmatter 格式定义 name 和 description
3. THE Skill_Creator_Skill SHALL 提供结构化的技能创建向导，引导用户完成以下步骤：确定技能名称与描述、定义技能内容结构、生成符合 YAML frontmatter 规范的 SKILL.md 文件、可选创建 references/templates/scripts/assets 支持文件
4. WHEN 用户通过 `skill(name="skill-creator")` 或 `/skill-creator` 调用时，THE Skill_Registry SHALL 返回完整的技能内容
5. THE Skill_Creator_Skill SHALL 内含技能文件格式规范说明，包括 frontmatter 必填字段（name、description）和可选字段（version、metadata.hermes.tags）

**用户故事：** 作为开发者，我希望架构图反映新增的 Skills Hub 层，以便团队成员理解系统的完整架构。

#### 验收标准

1. THE Architecture_Diagram SHALL 在 L1（Agent Loop）层中新增 Skills Hub 组件，展示其与 Skills 模块的关系
2. THE Architecture_Diagram SHALL 展示 Skills Hub 与外部来源（GitHub、Taps）之间的数据流
3. THE Architecture_Diagram SHALL 展示 Lock_File 和 Quarantine_Dir 作为 Skills Hub 的关联存储
4. THE Architecture_Diagram SHALL 保持与现有架构图一致的视觉风格（Style-1 Flat Icon）

### 需求 11：与现有技能系统集成

**用户故事：** 作为开发者，我希望 Skills Hub 与现有的 SkillRegistry 和 skill_manage 工具无缝集成，以便不破坏已有功能。

#### 验收标准

1. THE Skills_Hub SHALL 复用现有的 SkillDefinition 数据模型和 SkillRegistry 注册机制
2. WHEN Skills_Hub 安装新技能后，THE Skill_Registry SHALL 能通过 `load_skill_registry()` 自动发现并加载该技能
3. THE Skills_Hub SHALL 与现有的 `skill_manage` 工具共享用户技能目录 `~/.velaris-agent/skills/`
4. WHEN 用户通过 `skill_manage` 手动创建技能时，THE Lock_File SHALL 不受影响，手动创建的技能不纳入自更新管理
5. THE Skills_Hub SHALL 与现有的 `build_skills_system_prompt()` 索引机制兼容，Hub 安装的技能同样出现在系统提示索引中

### 需求 12：Lock File 序列化往返一致性

**用户故事：** 作为开发者，我希望 Lock File 的读写操作保持数据一致性，以便避免序列化过程中丢失或损坏数据。

#### 验收标准

1. THE Lock_File SHALL 使用 JSON 格式存储，编码为 UTF-8
2. FOR ALL 合法的 Lock_File 内容，读取后再写入再读取 SHALL 产生等价的数据对象（往返一致性）
3. THE Lock_File 解析器 SHALL 在遇到无效 JSON 时返回描述性错误信息
4. THE Lock_File 格式化器 SHALL 将 Lock_File 数据对象格式化为合法的 JSON 文件
