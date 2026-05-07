import React from 'react';
import {render} from 'ink';

import {App} from './App.js';
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

render(<App config={config} />);
