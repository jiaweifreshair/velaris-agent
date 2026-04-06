"""HTTP 适配器超时/重试/熔断测试。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from velaris_agent.adapters.data_sources import (
    CircuitBreakerOpen,
    StructuredDataSourceLoader,
    _circuit_breaker,
)


@pytest.fixture(autouse=True)
def _reset_circuit_breaker() -> None:
    """每个测试前重置熔断器状态。"""
    _circuit_breaker._failures.clear()
    _circuit_breaker._open_until.clear()


class TestHttpRetry:
    """HTTP 重试测试。"""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self) -> None:
        loader = StructuredDataSourceLoader()
        mock_response = httpx.Response(
            200,
            json={"result": "ok"},
            request=httpx.Request("GET", "http://test.local/data"),
        )
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
            data = await loader.load({
                "type": "http",
                "url": "http://test.local/data",
                "max_retries": 1,
            })
        assert data == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_retry_on_500(self) -> None:
        loader = StructuredDataSourceLoader()
        fail_response = httpx.Response(
            500,
            json={"error": "internal"},
            request=httpx.Request("GET", "http://test.local/data"),
        )
        ok_response = httpx.Response(
            200,
            json={"result": "recovered"},
            request=httpx.Request("GET", "http://test.local/data"),
        )
        call_count = 0

        async def mock_get(*args: object, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return fail_response
            return ok_response

        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            data = await loader.load({
                "type": "http",
                "url": "http://test.local/data",
                "max_retries": 2,
                "retry_backoff": 0.01,
            })
        assert data == {"result": "recovered"}
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted(self) -> None:
        loader = StructuredDataSourceLoader()
        fail_response = httpx.Response(
            503,
            json={"error": "unavailable"},
            request=httpx.Request("GET", "http://test.local/data"),
        )

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=fail_response):
            with pytest.raises(httpx.HTTPStatusError):
                await loader.load({
                    "type": "http",
                    "url": "http://test.local/data",
                    "max_retries": 2,
                    "retry_backoff": 0.01,
                })

    @pytest.mark.asyncio
    async def test_connection_error_retry(self) -> None:
        loader = StructuredDataSourceLoader()
        call_count = 0
        ok_response = httpx.Response(
            200,
            json={"result": "ok"},
            request=httpx.Request("GET", "http://test.local/data"),
        )

        async def mock_get(*args: object, **kwargs: object) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ConnectError("connection refused")
            return ok_response

        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            data = await loader.load({
                "type": "http",
                "url": "http://test.local/data",
                "max_retries": 2,
                "retry_backoff": 0.01,
            })
        assert data == {"result": "ok"}


class TestHttpAuth:
    """HTTP 鉴权测试。"""

    @pytest.mark.asyncio
    async def test_custom_headers_passed(self) -> None:
        loader = StructuredDataSourceLoader()
        captured_headers: dict[str, str] = {}

        async def mock_get(*args: object, **kwargs: object) -> httpx.Response:
            headers = kwargs.get("headers", {})
            captured_headers.update(headers)
            return httpx.Response(
                200,
                json={"auth": "ok"},
                request=httpx.Request("GET", "http://test.local/data"),
            )

        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            await loader.load({
                "type": "http",
                "url": "http://test.local/data",
                "headers": {"Authorization": "Bearer test-token-123"},
                "max_retries": 1,
            })
        assert captured_headers.get("Authorization") == "Bearer test-token-123"


class TestCircuitBreaker:
    """熔断器测试。"""

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold(self) -> None:
        loader = StructuredDataSourceLoader()

        async def mock_get(*args: object, **kwargs: object) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        with patch("httpx.AsyncClient.get", side_effect=mock_get):
            # 连续失败直到熔断
            for i in range(5):
                with pytest.raises(Exception):
                    await loader.load({
                        "type": "http",
                        "url": "http://breaker-test.local/data",
                        "max_retries": 1,
                        "retry_backoff": 0.01,
                    })

            # 第6次应触发 CircuitBreakerOpen
            with pytest.raises(CircuitBreakerOpen):
                await loader.load({
                    "type": "http",
                    "url": "http://breaker-test.local/data",
                    "max_retries": 1,
                    "retry_backoff": 0.01,
                })

    def test_circuit_breaker_records_success(self) -> None:
        _circuit_breaker.record_failure("http://test.local")
        _circuit_breaker.record_failure("http://test.local")
        _circuit_breaker.record_success("http://test.local")
        # 成功后重置, 不应熔断
        _circuit_breaker.check("http://test.local")  # 不抛异常

    @pytest.mark.asyncio
    async def test_post_method_supported(self) -> None:
        loader = StructuredDataSourceLoader()
        mock_response = httpx.Response(
            200,
            json={"method": "post"},
            request=httpx.Request("POST", "http://test.local/data"),
        )
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            data = await loader.load({
                "type": "http",
                "url": "http://test.local/data",
                "method": "POST",
                "body": {"key": "value"},
                "max_retries": 1,
            })
        assert data == {"method": "post"}
