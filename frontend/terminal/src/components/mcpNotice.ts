/**
 * 表示 MCP 提示在终端中的语义级别，用于统一失败、恢复与普通提示的视觉反馈。
 */
export type McpNoticeTone = 'error' | 'success' | 'warning';

/**
 * 描述 MCP 提示在 React Terminal 中的展示结果，避免多个组件重复解析同一条文案。
 */
export type McpNoticePresentation = {
	message: string;
	tone: McpNoticeTone;
	label: string;
	color: 'red' | 'green' | 'yellow';
};

const ERROR_KEYWORDS = ['fail', 'error', 'denied', 'timeout', 'timed out', 'broken pipe', 'disconnected', 'not connected'];
const SUCCESS_KEYWORDS = ['recover', 'reconnected', 'connected', 'restored'];

/**
 * 解析 MCP 提示文案，给终端组件提供统一的语义标签与颜色。
 * 优先信任后端显式下发的 severity，缺失时再回退到关键字推断。
 */
export function describeMcpNotice(rawNotice: unknown, rawLevel?: unknown): McpNoticePresentation | null {
	const message = String(rawNotice ?? '').trim();
	if (!message) {
		return null;
	}

	const explicitTone = normalizeMcpNoticeTone(rawLevel);
	if (explicitTone) {
		return buildMcpNoticePresentation(message, explicitTone);
	}

	const normalized = message.toLowerCase();
	if (containsKeyword(normalized, ERROR_KEYWORDS)) {
		return buildMcpNoticePresentation(message, 'error');
	}

	if (containsKeyword(normalized, SUCCESS_KEYWORDS)) {
		return buildMcpNoticePresentation(message, 'success');
	}

	return buildMcpNoticePresentation(message, 'warning');
}

/**
 * 规范化后端传来的 severity 字段，兼容显式 level 与旧关键字别名。
 */
function normalizeMcpNoticeTone(rawLevel: unknown): McpNoticeTone | null {
	const normalized = String(rawLevel ?? '').trim().toLowerCase();
	if (!normalized) {
		return null;
	}
	if (['error', 'failed', 'failure'].includes(normalized)) {
		return 'error';
	}
	if (['success', 'ok', 'recovered'].includes(normalized)) {
		return 'success';
	}
	if (['warning', 'warn', 'notice', 'info'].includes(normalized)) {
		return 'warning';
	}
	return null;
}

/**
 * 根据统一 tone 生成终端展示对象，避免多个分支重复维护标签与颜色。
 */
function buildMcpNoticePresentation(message: string, tone: McpNoticeTone): McpNoticePresentation {
	if (tone === 'error') {
		return {
			message,
			tone,
			label: 'mcp error',
			color: 'red',
		};
	}
	if (tone === 'success') {
		return {
			message,
			tone,
			label: 'mcp recovered',
			color: 'green',
		};
	}
	return {
		message,
		tone,
		label: 'mcp notice',
		color: 'yellow',
	};
}

/**
 * 使用关键字匹配，避免在多个组件里重复维护同一套状态判断逻辑。
 */
function containsKeyword(message: string, keywords: string[]): boolean {
	return keywords.some((keyword) => message.includes(keyword));
}
