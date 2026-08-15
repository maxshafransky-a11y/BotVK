"""Технический trace без внешнего observability-сервиса."""

from .prompts import TaskType
from .storage import SQLiteStore


class TraceLogger:
    """Записывает состояние операции, не сохраняя prompt и response."""

    def __init__(self, store: SQLiteStore) -> None:
        self._store = store

    def record(
        self,
        user_id: int,
        event_type: str,
        *,
        task_type: TaskType | None = None,
        status: str,
        latency_ms: int | None = None,
    ) -> None:
        self._store.record_event(
            user_id,
            event_type,
            task_type=task_type,
            status=status,
            latency_ms=latency_ms,
        )
