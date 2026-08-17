"""Локальное SQLite-хранилище мини-MVP."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from .polza_client import GenerationResult
from .prompts import BrandProfile, TaskType


class SQLiteStore:
    """Хранилище с короткими транзакциями и WAL-режимом."""

    def __init__(self, path: str | Path = "data/botvk.sqlite3") -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS brand_profiles (
                    user_id INTEGER PRIMARY KEY,
                    business_name TEXT NOT NULL,
                    offer TEXT NOT NULL,
                    audience TEXT NOT NULL,
                    tone TEXT NOT NULL,
                    facts_json TEXT NOT NULL,
                    sample_posts_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_type TEXT NOT NULL,
                    brief TEXT NOT NULL,
                    output_text TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    status TEXT NOT NULL,
                    usage_json TEXT NOT NULL,
                    cost REAL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    task_type TEXT,
                    status TEXT NOT NULL,
                    latency_ms INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def save_profile(self, user_id: int, profile: BrandProfile) -> None:
        """Сохранить только профиль владельца, заменив его прежнюю версию."""

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO brand_profiles (
                    user_id, business_name, offer, audience, tone,
                    facts_json, sample_posts_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    business_name = excluded.business_name,
                    offer = excluded.offer,
                    audience = excluded.audience,
                    tone = excluded.tone,
                    facts_json = excluded.facts_json,
                    sample_posts_json = excluded.sample_posts_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    profile.business_name,
                    profile.offer,
                    profile.audience,
                    profile.tone,
                    json.dumps(profile.facts, ensure_ascii=False),
                    json.dumps(profile.sample_posts, ensure_ascii=False),
                ),
            )

    def load_profile(self, user_id: int) -> BrandProfile | None:
        """Загрузить профиль владельца после перезапуска процесса."""

        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT business_name, offer, audience, tone,
                       facts_json, sample_posts_json
                FROM brand_profiles
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

        if row is None:
            return None

        try:
            facts = tuple(json.loads(row["facts_json"]))
            sample_posts = tuple(json.loads(row["sample_posts_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

        return BrandProfile(
            business_name=row["business_name"],
            offer=row["offer"],
            audience=row["audience"],
            tone=row["tone"],
            facts=facts,
            sample_posts=sample_posts,
        )

    def save_generation(
        self,
        user_id: int,
        task_type: TaskType,
        brief: str,
        result: GenerationResult,
        *,
        status: str = "draft",
    ) -> int:
        """Сохранить успешный черновик и вернуть его локальный ID."""

        with self._connection() as connection:
            cursor = connection.execute(
                """
                INSERT INTO generations (
                    user_id, task_type, brief, output_text, provider, model,
                    status, usage_json, cost
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    task_type,
                    brief,
                    result.text,
                    result.provider,
                    result.model,
                    status,
                    json.dumps(dict(result.usage), ensure_ascii=False),
                    result.cost,
                ),
            )
            return int(cursor.lastrowid)

    def update_generation(
        self,
        user_id: int,
        generation_id: int,
        *,
        output_text: str | None = None,
        status: str | None = None,
    ) -> bool:
        """Обновить draft только его владельцу и вернуть факт изменения."""

        changes: list[str] = []
        values: list[object] = []
        if output_text is not None:
            changes.append("output_text = ?")
            values.append(output_text)
        if status is not None:
            changes.append("status = ?")
            values.append(status)
        if not changes:
            return False

        values.extend((generation_id, user_id))
        with self._connection() as connection:
            cursor = connection.execute(
                f"UPDATE generations SET {', '.join(changes)} "
                "WHERE id = ? AND user_id = ?",
                values,
            )
            return cursor.rowcount == 1

    def record_event(
        self,
        user_id: int,
        event_type: str,
        *,
        task_type: TaskType | None = None,
        status: str,
        latency_ms: int | None = None,
    ) -> None:
        """Записать техническое событие без prompt/response и секретов."""

        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO events (
                    user_id, event_type, task_type, status, latency_ms
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, event_type, task_type, status, latency_ms),
            )
