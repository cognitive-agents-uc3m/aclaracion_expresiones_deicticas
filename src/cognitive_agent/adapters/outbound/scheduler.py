from __future__ import annotations

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable

logger = logging.getLogger(__name__)

class _FutureHandle:
    __slots__ = ("_future",)

    def __init__(self, future: Future) -> None:
        self._future = future

    def cancel(self) -> bool:
        return self._future.cancel()

    @property
    def done(self) -> bool:
        return self._future.done()

    def result(self, timeout: float | None = None) -> Any:
        return self._future.result(timeout=timeout)

class _TimerHandle:
    __slots__ = ("_timer",)

    def __init__(self, timer: threading.Timer) -> None:
        self._timer = timer

    def cancel(self) -> bool:
        self._timer.cancel()
        return True

    @property
    def done(self) -> bool:
        return not self._timer.is_alive()

class ThreadTaskScheduler:

    def __init__(self, *, workers: int = 2, name: str = "cognitive-agent") -> None:
        self._executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix=name)
        self._timers: set[threading.Timer] = set()
        self._lock = threading.Lock()
        self._closed = False

    def submit(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> _FutureHandle:
        if self._closed:
            raise RuntimeError("El planificador ya se ha cerrado.")
        return _FutureHandle(self._executor.submit(self._guard(fn), *args, **kwargs))

    def schedule_after(
        self, delay_seconds: float, fn: Callable[..., Any], /, *args: Any, **kwargs: Any
    ) -> _TimerHandle:
        if self._closed:
            raise RuntimeError("El planificador ya se ha cerrado.")

        def run() -> None:
            with self._lock:
                self._timers.discard(timer)
            self._guard(fn)(*args, **kwargs)

        timer = threading.Timer(max(0.0, delay_seconds), run)
        timer.daemon = True
        with self._lock:
            self._timers.add(timer)
        timer.start()
        return _TimerHandle(timer)

    def shutdown(self, *, wait: bool = True, timeout: float | None = None) -> None:
        self._closed = True
        with self._lock:
            timers = list(self._timers)
            self._timers.clear()
        for timer in timers:
            timer.cancel()
        self._executor.shutdown(wait=wait)

    @staticmethod
    def _guard(fn: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except Exception:
                logger.exception("Fallo una tarea en segundo plano: %s", getattr(fn, "__qualname__", fn))
                return None

        return wrapped

class ImmediateTaskScheduler:

    def __init__(self) -> None:
        self.deferred: list[tuple[float, Callable[..., Any], tuple, dict]] = []

    def submit(self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> _ImmediateHandle:
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            return _ImmediateHandle(error=exc)
        return _ImmediateHandle(result=result)

    def schedule_after(
        self, delay_seconds: float, fn: Callable[..., Any], /, *args: Any, **kwargs: Any
    ) -> _ImmediateHandle:

        self.deferred.append((delay_seconds, fn, args, kwargs))
        return _ImmediateHandle(result=None)

    def run_pending(self, *, max_rounds: int = 10) -> int:

        executed = 0
        for _ in range(max_rounds):
            if not self.deferred:
                break
            batch, self.deferred = self.deferred, []
            for _delay, fn, args, kwargs in batch:
                fn(*args, **kwargs)
                executed += 1
        return executed

    def shutdown(self, *, wait: bool = True, timeout: float | None = None) -> None:
        self.deferred.clear()

class _ImmediateHandle:
    __slots__ = ("result", "error")

    def __init__(self, *, result: Any = None, error: BaseException | None = None) -> None:
        self.result = result
        self.error = error

    def cancel(self) -> bool:
        return False

    @property
    def done(self) -> bool:
        return True
