"""Tests for the retry decorator."""

from unittest.mock import MagicMock, patch

import pytest

from src.exceptions import RetryExhaustedError
from src.retry import retry


class TestRetryDecorator:
    """Tests for the retry decorator."""

    @patch("src.retry.time.sleep")
    def test_succeeds_first_attempt(self, mock_sleep: MagicMock) -> None:
        """Function succeeding on first attempt is called once."""
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def succeed() -> str:
            nonlocal call_count
            call_count += 1
            return "ok"

        result = succeed()
        assert result == "ok"
        assert call_count == 1
        mock_sleep.assert_not_called()

    @patch("src.retry.time.sleep")
    def test_succeeds_after_retry(self, mock_sleep: MagicMock) -> None:
        """Function succeeding on second attempt retries once."""
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01)
        def fail_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("temporary error")
            return "ok"

        result = fail_then_succeed()
        assert result == "ok"
        assert call_count == 2
        assert mock_sleep.call_count == 1

    @patch("src.retry.time.sleep")
    def test_exhausted_raises(self, mock_sleep: MagicMock) -> None:
        """All attempts exhausted raises RetryExhaustedError."""

        @retry(max_attempts=3, base_delay=0.01)
        def always_fail() -> None:
            raise ValueError("permanent error")

        with pytest.raises(RetryExhaustedError) as exc_info:
            always_fail()

        assert exc_info.value.attempts == 3
        assert isinstance(exc_info.value.last_exception, ValueError)

    @patch("src.retry.time.sleep")
    def test_non_retryable_exception_propagates(
        self, mock_sleep: MagicMock
    ) -> None:
        """Non-retryable exceptions propagate immediately."""

        @retry(
            max_attempts=3,
            base_delay=0.01,
            retryable_exceptions=(ValueError,),
        )
        def raise_type_error() -> None:
            raise TypeError("wrong type")

        with pytest.raises(TypeError, match="wrong type"):
            raise_type_error()

        mock_sleep.assert_not_called()

    @patch("src.retry.time.sleep")
    def test_on_retry_callback(self, mock_sleep: MagicMock) -> None:
        """on_retry callback is called before each retry."""
        callback = MagicMock()
        call_count = 0

        @retry(max_attempts=3, base_delay=0.01, on_retry=callback)
        def fail_twice() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("error")
            return "ok"

        fail_twice()
        assert callback.call_count == 2
        # First retry: attempt=1, second retry: attempt=2
        assert callback.call_args_list[0][0][0] == 1
        assert callback.call_args_list[1][0][0] == 2

    @patch("src.retry.time.sleep")
    def test_exponential_backoff(self, mock_sleep: MagicMock) -> None:
        """Delay increases exponentially between retries."""

        @retry(max_attempts=4, base_delay=1.0, exponential_base=2.0, max_delay=100.0)
        def always_fail() -> None:
            raise ValueError("error")

        with pytest.raises(RetryExhaustedError):
            always_fail()

        # 3 sleeps for 4 attempts
        assert mock_sleep.call_count == 3
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        # With jitter (0.5-1.0), delays should be roughly:
        # attempt 1: 1.0 * 2^0 * [0.5, 1.0] = [0.5, 1.0]
        # attempt 2: 1.0 * 2^1 * [0.5, 1.0] = [1.0, 2.0]
        # attempt 3: 1.0 * 2^2 * [0.5, 1.0] = [2.0, 4.0]
        assert delays[0] <= 1.0
        assert delays[1] <= 2.0
        assert delays[2] <= 4.0

    @patch("src.retry.time.sleep")
    def test_max_delay_cap(self, mock_sleep: MagicMock) -> None:
        """Delay is capped at max_delay."""

        @retry(max_attempts=3, base_delay=100.0, max_delay=5.0)
        def always_fail() -> None:
            raise ValueError("error")

        with pytest.raises(RetryExhaustedError):
            always_fail()

        delays = [call.args[0] for call in mock_sleep.call_args_list]
        for d in delays:
            assert d <= 5.0
