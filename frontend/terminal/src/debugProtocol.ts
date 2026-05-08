import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const debugProtocol =
	process.env.VELARIS_FRONTEND_DEBUG_PROTOCOL === '1' ||
	process.env.OPENHARNESS_FRONTEND_DEBUG_PROTOCOL === '1';

function resolveLogPath(): string {
	const explicit = process.env.VELARIS_FRONTEND_DEBUG_LOG ?? process.env.OPENHARNESS_FRONTEND_DEBUG_LOG;
	if (explicit) {
		return explicit;
	}
	const logsDir =
		process.env.VELARIS_LOGS_DIR ??
		process.env.OPENHARNESS_LOGS_DIR ??
		path.join(os.homedir(), '.velaris-agent', 'logs');
	return path.join(logsDir, 'frontend-protocol.log');
}

const logPath = resolveLogPath();
let initialized = false;

export function debugLog(message: string): void {
	if (!debugProtocol) {
		return;
	}
	try {
		fs.mkdirSync(path.dirname(logPath), {recursive: true});
		if (!initialized) {
			initialized = true;
			fs.appendFileSync(
				logPath,
				`${new Date().toISOString()} | pid=${process.pid} | frontend debug session start\n`,
				'utf8',
			);
		}
		fs.appendFileSync(logPath, `${new Date().toISOString()} | pid=${process.pid} | ${message}\n`, 'utf8');
	} catch {
		// Debug logging must never affect the terminal UI.
	}
}

export function getDebugLogPath(): string {
	return logPath;
}

export function isProtocolDebugEnabled(): boolean {
	return debugProtocol;
}
