"""High-level conversation engine."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

from openharness.config.settings import PermissionSettings
from openharness.api.client import SupportsStreamingMessages
from openharness.engine.cost_tracker import CostTracker
from openharness.engine.messages import ConversationMessage
from openharness.engine.query import AskUserPrompt, PermissionPrompt, QueryContext, run_query
from openharness.engine.stream_events import StreamEvent
from openharness.hooks import HookExecutor
from openharness.permissions.checker import PermissionChecker
from openharness.permissions.modes import PermissionMode
from openharness.tools.base import ToolRegistry
from openharness.tools.skill_manage_tool import SkillManageTool
from openharness.tools.skill_tool import SkillTool

_SKILL_REVIEW_PROMPT = (
    "Review the conversation above and decide whether a reusable skill should be created or updated.\n\n"
    "Focus on cases where the task required 5+ tool calls, trial and error, debugging, or a non-trivial workflow.\n"
    "If the approach is reusable, save it with skill_manage. If an existing skill is stale or incomplete, patch it.\n"
    "If nothing is worth saving, reply with exactly: Nothing to save."
)


class QueryEngine:
    """Owns conversation history and the tool-aware model loop."""

    def __init__(
        self,
        *,
        api_client: SupportsStreamingMessages,
        tool_registry: ToolRegistry,
        permission_checker: PermissionChecker,
        cwd: str | Path,
        model: str,
        system_prompt: str,
        max_tokens: int = 4096,
        permission_prompt: PermissionPrompt | None = None,
        ask_user_prompt: AskUserPrompt | None = None,
        hook_executor: HookExecutor | None = None,
        tool_metadata: dict[str, object] | None = None,
        skill_review_interval: int = 10,
    ) -> None:
        self._api_client = api_client
        self._tool_registry = tool_registry
        self._permission_checker = permission_checker
        self._cwd = Path(cwd).resolve()
        self._model = model
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens
        self._permission_prompt = permission_prompt
        self._ask_user_prompt = ask_user_prompt
        self._hook_executor = hook_executor
        self._tool_metadata = tool_metadata or {}
        self._messages: list[ConversationMessage] = []
        self._cost_tracker = CostTracker()
        self._skill_review_interval = max(0, skill_review_interval)
        self._tool_calls_since_skill_review = 0
        self._background_review_tasks: set[asyncio.Task[None]] = set()

    @property
    def messages(self) -> list[ConversationMessage]:
        """Return the current conversation history."""
        return list(self._messages)

    @property
    def total_usage(self):
        """Return the total usage across all turns."""
        return self._cost_tracker.total

    def clear(self) -> None:
        """Clear the in-memory conversation history."""
        self._messages.clear()
        self._cost_tracker = CostTracker()

    async def wait_for_background_tasks(self) -> None:
        """等待后台 review 任务完成。

        会话关闭前调用，尽量把已触发的技能沉淀落盘。
        """

        if not self._background_review_tasks:
            return
        await asyncio.gather(*list(self._background_review_tasks), return_exceptions=True)

    def set_system_prompt(self, prompt: str) -> None:
        """Update the active system prompt for future turns."""
        self._system_prompt = prompt

    def set_model(self, model: str) -> None:
        """Update the active model for future turns."""
        self._model = model

    def set_permission_checker(self, checker: PermissionChecker) -> None:
        """Update the active permission checker for future turns."""
        self._permission_checker = checker

    def load_messages(self, messages: list[ConversationMessage]) -> None:
        """Replace the in-memory conversation history."""
        self._messages = list(messages)

    async def submit_message(self, prompt: str) -> AsyncIterator[StreamEvent]:
        """Append a user message and execute the query loop."""
        self._messages.append(ConversationMessage.from_user_text(prompt))
        tool_calls_this_turn = 0
        used_skill_manage = False
        context = QueryContext(
            api_client=self._api_client,
            tool_registry=self._tool_registry,
            permission_checker=self._permission_checker,
            cwd=self._cwd,
            model=self._model,
            system_prompt=self._system_prompt,
            max_tokens=self._max_tokens,
            permission_prompt=self._permission_prompt,
            ask_user_prompt=self._ask_user_prompt,
            hook_executor=self._hook_executor,
            tool_metadata=self._tool_metadata,
        )
        async for event, usage in run_query(context, self._messages):
            if usage is not None:
                self._cost_tracker.add(usage)
            from openharness.engine.stream_events import ToolExecutionCompleted

            if isinstance(event, ToolExecutionCompleted):
                tool_calls_this_turn += 1
                if event.tool_name == "skill_manage" and not event.is_error:
                    used_skill_manage = True
            yield event
        self._maybe_schedule_skill_review(
            tool_calls_this_turn=tool_calls_this_turn,
            used_skill_manage=used_skill_manage,
        )

    def _maybe_schedule_skill_review(
        self,
        *,
        tool_calls_this_turn: int,
        used_skill_manage: bool,
    ) -> None:
        """根据本轮工具调用情况决定是否触发后台技能复盘。"""

        if self._skill_review_interval <= 0:
            return
        if self._tool_registry.get("skill_manage") is None:
            return
        if used_skill_manage:
            self._tool_calls_since_skill_review = 0
            return

        self._tool_calls_since_skill_review += tool_calls_this_turn
        if self._tool_calls_since_skill_review < self._skill_review_interval:
            return

        self._tool_calls_since_skill_review = 0
        snapshot = [message.model_copy(deep=True) for message in self._messages]
        task = asyncio.create_task(self._run_background_skill_review(snapshot))
        self._background_review_tasks.add(task)
        task.add_done_callback(self._background_review_tasks.discard)

    async def _run_background_skill_review(
        self,
        messages_snapshot: list[ConversationMessage],
    ) -> None:
        """在后台静默运行一次技能复盘。

        只暴露 `skill` 和 `skill_manage`，把复盘范围严格限制在技能沉淀本身。
        """

        review_registry = ToolRegistry()
        review_registry.register(SkillTool())
        review_registry.register(SkillManageTool())

        review_context = QueryContext(
            api_client=self._api_client,
            tool_registry=review_registry,
            permission_checker=PermissionChecker(
                PermissionSettings(
                    mode=PermissionMode.FULL_AUTO,
                    allowed_tools=["skill", "skill_manage"],
                )
            ),
            cwd=self._cwd,
            model=self._model,
            system_prompt=self._system_prompt,
            max_tokens=min(self._max_tokens, 4096),
            max_turns=6,
            ask_user_prompt=self._ask_user_prompt,
            tool_metadata=self._tool_metadata,
        )
        review_messages = list(messages_snapshot)
        review_messages.append(ConversationMessage.from_user_text(_SKILL_REVIEW_PROMPT))

        try:
            async for _, _ in run_query(review_context, review_messages):
                pass
        except Exception:
            return
