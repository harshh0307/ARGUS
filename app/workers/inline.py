from __future__ import annotations

import logging
import queue
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)


class InlineTaskQueue:
    """In-process task queue with worker threads.

    Used as a fallback when Redis/Celery is unavailable.
    """

    def __init__(self, max_workers: int = 4):
        self._queue: queue.Queue = queue.Queue()
        self._workers: list[threading.Thread] = []
        self._max_workers = max_workers
        self._results: dict[str, dict] = {}
        self._lock = threading.Lock()
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        for i in range(self._max_workers):
            t = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name=f"inline-worker-{i}",
            )
            t.start()
            self._workers.append(t)

    def submit(self, task_id: str, func: Callable, args: tuple = (), kwargs: dict | None = None) -> str:
        self._queue.put((task_id, func, args, kwargs or {}))
        return task_id

    def get_result(self, task_id: str) -> dict | None:
        with self._lock:
            return self._results.get(task_id)

    def wait_for(self, task_id: str, timeout: float = 300) -> dict | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.get_result(task_id)
            if result is not None:
                return result
            time.sleep(0.5)
        return None

    def _worker_loop(self) -> None:
        while self._running:
            try:
                task_id, func, args, kwargs = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                result = func(*args, **kwargs)
                with self._lock:
                    self._results[task_id] = {"status": "success", "result": result}
            except Exception as exc:  # noqa: BLE001
                logger.warning("inline task %s failed: %s", task_id, exc)
                with self._lock:
                    self._results[task_id] = {"status": "failed", "error": str(exc)}
            finally:
                self._queue.task_done()

    def shutdown(self) -> None:
        self._running = False
        for t in self._workers:
            t.join(timeout=5)
        self._workers.clear()


_inline_queue = InlineTaskQueue()
