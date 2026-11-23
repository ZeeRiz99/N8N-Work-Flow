"""Circuit breaker (master prompt §8.7): after 5 failures in a row, stop calling the provider
for 60 seconds, so an outage costs one fast fallback per lead instead of a slow timeout."""

import threading
import time


class CircuitBreaker:
    def __init__(self, threshold: int = 5, cooldown_seconds: float = 60.0) -> None:
        self.threshold, self.cooldown = threshold, cooldown_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            if time.monotonic() - self._opened_at >= self.cooldown:
                self._opened_at = None  # half-open: let one call try
                self._failures = self.threshold - 1
                return True
            return False

    def success(self) -> None:
        with self._lock:
            self._failures, self._opened_at = 0, None

    def failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.threshold:
                self._opened_at = time.monotonic()

    @property
    def is_open(self) -> bool:
        return self._opened_at is not None


gemini_breaker = CircuitBreaker()
