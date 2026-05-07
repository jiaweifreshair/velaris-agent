"""调度引擎 + 评分器 + Agent 全流程测试。

注意：这些测试依赖于 velaris_agent.scenarios.robotclaw.agents,
velaris_agent.scenarios.robotclaw.dispatch, 
velaris_agent.scenarios.robotclaw.protocol 子模块，
这些模块尚未实现。暂时跳过这些测试。
"""

import pytest

pytest.skip("robotclaw submodules (agents/dispatch/protocol) not yet implemented", allow_module_level=True)
