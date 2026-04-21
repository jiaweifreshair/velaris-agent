import React from 'react';
import {Box, Text} from 'ink';

import type {DemoCase} from '../types.js';

/** SkillHub 演示台顶部提示条，用来展示案例、路由链和切换说明。 */
export function SkillHubDemoBanner({
	cases,
	selectedIndex,
}: {
	cases: DemoCase[];
	selectedIndex: number;
}): React.JSX.Element | null {
	if (cases.length === 0) {
		return null;
	}

	return (
		<Box flexDirection="column" borderStyle="round" borderColor="magenta" paddingX={1} marginBottom={1}>
			<Text color="magenta" bold>
				SkillHub 内部演示台
			</Text>
			<Text dimColor>
				1-4 切换案例，Enter 发送；当前会先安装真实 SkillHub skills，再交给对应 domain agent。
			</Text>
			{cases.map((demoCase, index) => {
				const active = index === selectedIndex;
				return (
					<Box key={demoCase.case_id} flexDirection="column" marginTop={1}>
						<Text color={active ? 'magenta' : undefined} bold={active}>
							{index + 1}. {demoCase.title}
							{demoCase.internal_only ? ' [internal]' : ''}
						</Text>
						<Text>{demoCase.query}</Text>
						<Text dimColor>route: {demoCase.route_agents.join(' + ')}</Text>
						<Text dimColor>skills: {demoCase.skill_slugs.join(', ')}</Text>
						<Text dimColor>{demoCase.description}</Text>
					</Box>
				);
			})}
		</Box>
	);
}
