"""OpenHarness 包入口。

这个模块负责在包导入时安装最小兼容层，避免 Python 3.13 改动导致
历史代码和测试在主线程里获取 event loop 时直接失败。
"""

from __future__ import annotations

import asyncio
import threading


class LegacyMainThreadEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    """主线程 event loop 兼容策略。

    这个策略在主线程没有当前 event loop 时自动创建一个新的 loop，
    尽量恢复 Python 3.12 及之前 `asyncio.get_event_loop()` 的常见行为。
    """

    def get_event_loop(self) -> asyncio.AbstractEventLoop:
        """返回当前 event loop，并在主线程缺失时自动补建。"""

        local_state = getattr(self, "_local", None)
        current_loop = getattr(local_state, "_loop", None)
        if current_loop is not None:
            return current_loop
        if threading.current_thread() is not threading.main_thread():
            return super().get_event_loop()

        loop = self.new_event_loop()
        self.set_event_loop(loop)
        return loop


def _install_asyncio_compatibility_policy() -> None:
    """安装主线程 event loop 兼容策略。

    这个函数只在当前策略还不是兼容策略时替换，避免重复覆盖外部自定义策略。
    """

    current_policy = asyncio.get_event_loop_policy()
    if isinstance(current_policy, LegacyMainThreadEventLoopPolicy):
        return
    asyncio.set_event_loop_policy(LegacyMainThreadEventLoopPolicy())


_install_asyncio_compatibility_policy()
