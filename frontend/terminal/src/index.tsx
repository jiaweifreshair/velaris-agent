import React from 'react';
import {render} from 'ink';

import {App} from './App.js';
import {debugLog, getDebugLogPath, isProtocolDebugEnabled} from './debugProtocol.js';
import type {FrontendConfig} from './types.js';

if (process.stdin.setEncoding) {
  process.stdin.setEncoding('utf8');
}
if (process.stdout.setDefaultEncoding) {
  process.stdout.setDefaultEncoding('utf8');
}

const config = JSON.parse(
  process.env.VELARIS_FRONTEND_CONFIG ?? process.env.OPENHARNESS_FRONTEND_CONFIG ?? '{}',
) as FrontendConfig;

debugLog(
  `index start debug_enabled=${isProtocolDebugEnabled()} debug_log=${getDebugLogPath()} backend_command_len=${config.backend_command?.length ?? 0}`,
);
render(<App config={config} />);
