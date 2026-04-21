/** 前端启动配置，包含后端命令和 SkillHub demo 的透传字段。 */
export type FrontendConfig = {
	/** 启动后端 host 的命令。 */
	backend_command: string[];
	/** 初始写入输入框的 query。 */
	initial_prompt?: string | null;
	/** 当前是否处于 SkillHub demo 模式。 */
	demo_mode?: string | null;
	/** 默认选中的 demo 案例下标。 */
	demo_case_index?: number | null;
	/** 传给前端渲染的 demo 案例列表。 */
	demo_cases?: DemoCase[];
};

/** SkillHub demo 中展示的单个案例元数据。 */
export type DemoCase = {
	/** 案例的稳定标识。 */
	case_id: string;
	/** 页面上显示的案例标题。 */
	title: string;
	/** 进入 demo 后自动填入的 query。 */
	query: string;
	/** 这个案例会被路由到的 domain agent。 */
	skill_slugs: string[];
	/** 这个案例会展示的 agent 路由链。 */
	route_agents: string[];
	/** 给演示者看的简短说明。 */
	description: string;
	/** 是否只允许内部演示可见。 */
	internal_only?: boolean;
};

export type TranscriptItem = {
	role: 'system' | 'user' | 'assistant' | 'tool' | 'tool_result' | 'log';
	text: string;
	tool_name?: string;
	tool_input?: Record<string, unknown>;
	is_error?: boolean;
};

export type TaskSnapshot = {
	id: string;
	type: string;
	status: string;
	description: string;
	metadata: Record<string, string>;
};

export type McpServerSnapshot = {
	name: string;
	state: string;
	detail?: string;
	detail_level?: string;
	transport?: string;
	auth_configured?: boolean;
	tool_count?: number;
	resource_count?: number;
};

export type BridgeSessionSnapshot = {
	session_id: string;
	command: string;
	cwd: string;
	pid: number;
	status: string;
	started_at: number;
	output_path: string;
};

export type SelectOptionPayload = {
	value: string;
	label: string;
	description?: string;
};

export type BackendEvent = {
	type: string;
	message?: string | null;
	item?: TranscriptItem | null;
	state?: Record<string, unknown> | null;
	tasks?: TaskSnapshot[] | null;
	mcp_servers?: McpServerSnapshot[] | null;
	bridge_sessions?: BridgeSessionSnapshot[] | null;
	commands?: string[] | null;
	modal?: Record<string, unknown> | null;
	select_options?: SelectOptionPayload[] | null;
	tool_name?: string | null;
	output?: string | null;
	is_error?: boolean | null;
};
