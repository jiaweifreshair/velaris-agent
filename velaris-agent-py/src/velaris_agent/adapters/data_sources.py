"""Velaris 通用数据源加载器。

支持 inline / file / http 三种数据源, HTTP 支持超时、重试、鉴权和熔断。
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 默认 HTTP 配置
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 1.0  # 初始退避秒数
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# 熔断器默认配置
CIRCUIT_BREAKER_THRESHOLD = 5        # 连续失败次数触发熔断
CIRCUIT_BREAKER_RECOVERY_SECONDS = 60  # 熔断恢复时间


class CircuitBreakerOpen(Exception):
    """熔断器打开异常。"""

    def __init__(self, url: str, recovery_at: float) -> None:
        self.url = url
        self.recovery_at = recovery_at
        remaining = max(0, recovery_at - time.monotonic())
        super().__init__(f"Circuit breaker open for {url}, recovery in {remaining:.0f}s")


class _CircuitBreaker:
    """简单熔断器 (per-host)。"""

    def __init__(
        self,
        threshold: int = CIRCUIT_BREAKER_THRESHOLD,
        recovery_seconds: float = CIRCUIT_BREAKER_RECOVERY_SECONDS,
    ) -> None:
        self._threshold = threshold
        self._recovery_seconds = recovery_seconds
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}

    def _host_key(self, url: str) -> str:
        """提取 host 作为熔断粒度。"""
        try:
            parsed = httpx.URL(url)
            return str(parsed.host)
        except Exception:
            return url

    def check(self, url: str) -> None:
        """检查熔断状态, 如果熔断中则抛出异常。"""
        key = self._host_key(url)
        open_until = self._open_until.get(key, 0)
        if open_until > 0:
            if time.monotonic() < open_until:
                raise CircuitBreakerOpen(url, open_until)
            # 恢复: 重置状态 (half-open -> 允许一次尝试)
            self._failures[key] = 0
            self._open_until[key] = 0

    def record_success(self, url: str) -> None:
        """记录成功, 重置失败计数。"""
        key = self._host_key(url)
        self._failures[key] = 0
        self._open_until[key] = 0

    def record_failure(self, url: str) -> None:
        """记录失败, 达到阈值触发熔断。"""
        key = self._host_key(url)
        count = self._failures.get(key, 0) + 1
        self._failures[key] = count
        if count >= self._threshold:
            self._open_until[key] = time.monotonic() + self._recovery_seconds
            logger.warning(
                "Circuit breaker opened for %s after %d failures, recovery in %ds",
                key, count, self._recovery_seconds,
            )


# 全局熔断器实例
_circuit_breaker = _CircuitBreaker()


class StructuredDataSourceLoader:
    """结构化数据源加载器。

    HTTP 模式支持:
    - timeout: 超时控制 (默认 20s)
    - max_retries: 最大重试次数 (默认 3, 仅对 429/5xx 重试)
    - retry_backoff: 指数退避初始秒数 (默认 1s)
    - headers: 自定义请求头 (用于鉴权, 如 Authorization: Bearer xxx)
    - circuit_breaker: 熔断保护 (连续 5 次失败后熔断 60s)
    """

    async def load(self, source: dict[str, Any] | None) -> dict[str, Any]:
        """加载数据源。"""
        if not source:
            return {}

        source_type = str(source.get("type", "inline"))
        if source_type == "inline":
            payload = source.get("payload", {})
            return payload if isinstance(payload, dict) else {}
        if source_type == "file":
            path = Path(str(source["path"])).expanduser().resolve()
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"File source must contain a JSON object: {path}")
            return data
        if source_type == "http":
            return await self._load_http(source)

        raise ValueError(f"Unsupported source type: {source_type}")

    async def _load_http(self, source: dict[str, Any]) -> dict[str, Any]:
        """HTTP 数据源加载, 支持超时/重试/鉴权/熔断。"""
        url = str(source["url"])
        timeout = float(source.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
        max_retries = int(source.get("max_retries", DEFAULT_MAX_RETRIES))
        retry_backoff = float(source.get("retry_backoff", DEFAULT_RETRY_BACKOFF))
        headers = dict(source.get("headers", {}))
        method = str(source.get("method", "GET")).upper()

        # 熔断检查
        _circuit_breaker.check(url)

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    if method == "POST":
                        body = source.get("body", {})
                        response = await client.post(url, headers=headers, json=body)
                    else:
                        response = await client.get(url, headers=headers)

                    if response.status_code in RETRYABLE_STATUS_CODES:
                        last_error = httpx.HTTPStatusError(
                            f"HTTP {response.status_code}",
                            request=response.request,
                            response=response,
                        )
                        # 尊重 Retry-After 头
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                wait = float(retry_after)
                            except ValueError:
                                wait = retry_backoff * (2 ** attempt)
                        else:
                            wait = retry_backoff * (2 ** attempt)

                        logger.warning(
                            "HTTP %d from %s, retry %d/%d in %.1fs",
                            response.status_code, url, attempt + 1, max_retries, wait,
                        )
                        if attempt < max_retries - 1:
                            import asyncio
                            await asyncio.sleep(wait)
                            continue

                    response.raise_for_status()
                    data = response.json()

                if not isinstance(data, dict):
                    raise ValueError(f"HTTP source must return a JSON object: {url}")

                _circuit_breaker.record_success(url)
                return data

            except CircuitBreakerOpen:
                raise
            except Exception as exc:
                last_error = exc
                _circuit_breaker.record_failure(url)
                if attempt < max_retries - 1:
                    wait = retry_backoff * (2 ** attempt)
                    logger.warning(
                        "HTTP error from %s: %s, retry %d/%d in %.1fs",
                        url, exc, attempt + 1, max_retries, wait,
                    )
                    import asyncio
                    await asyncio.sleep(wait)

        # 所有重试用尽
        raise last_error or RuntimeError(f"Failed to load from {url}")

    async def merge(self, source: dict[str, Any] | None, overrides: dict[str, Any]) -> dict[str, Any]:
        base = await self.load(source)
        merged = dict(base)
        for key, value in overrides.items():
            if self._has_explicit_value(value):
                merged[key] = value
        return merged

    def _has_explicit_value(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, (list, dict, str)):
            return len(value) > 0
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return True
