"""asyncio 兼容层测试。"""

from __future__ import annotations

import asyncio

import openharness  # noqa: F401


def test_openharness_restores_main_thread_event_loop() -> None:
    """验证主线程 event loop 被清空后，兼容层仍能恢复可用 loop。"""

    asyncio.set_event_loop(None)
    loop = asyncio.get_event_loop()

    assert loop is not None
    assert loop.is_closed() is False
