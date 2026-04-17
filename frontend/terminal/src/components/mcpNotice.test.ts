import assert from 'node:assert/strict';

import {describeMcpNotice} from './mcpNotice.js';

const failureNotice = describeMcpNotice('Auto-reconnect failed: broken pipe');
assert.deepEqual(failureNotice, {
	message: 'Auto-reconnect failed: broken pipe',
	tone: 'error',
	label: 'mcp error',
	color: 'red',
});

const recoveredNotice = describeMcpNotice('Auto-reconnect recovered after transport closed');
assert.deepEqual(recoveredNotice, {
	message: 'Auto-reconnect recovered after transport closed',
	tone: 'success',
	label: 'mcp recovered',
	color: 'green',
});

const neutralNotice = describeMcpNotice('Waiting for MCP server response');
assert.deepEqual(neutralNotice, {
	message: 'Waiting for MCP server response',
	tone: 'warning',
	label: 'mcp notice',
	color: 'yellow',
});

assert.equal(describeMcpNotice('   '), null);


const explicitErrorNotice = describeMcpNotice('Auto-reconnect recovered after transport closed', 'error');
assert.deepEqual(explicitErrorNotice, {
	message: 'Auto-reconnect recovered after transport closed',
	tone: 'error',
	label: 'mcp error',
	color: 'red',
});
