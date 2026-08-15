"""Минимальное in-memory состояние диалога пользователя."""

from dataclasses import dataclass, field
from typing import Literal

from .prompts import BrandProfile, TaskType


Awaiting = Literal["brief", "manual_edit", "profile"]


@dataclass
class Session:
    """Состояние одного VK-пользователя до подключения SQLite."""

    mode: TaskType | None = None
    awaiting: Awaiting | None = None
    last_brief: str | None = None
    profile: BrandProfile = field(default_factory=BrandProfile)


class StateStore:
    """Изолирует временное состояние пользователей в текущем процессе."""

    def __init__(self) -> None:
        self._sessions: dict[int, Session] = {}

    def get(self, user_id: int) -> Session:
        return self._sessions.setdefault(user_id, Session())

    def start_task(self, user_id: int, task: TaskType) -> Session:
        session = self.get(user_id)
        session.mode = task
        session.awaiting = "brief"
        session.last_brief = None
        return session

    def start_profile(self, user_id: int) -> Session:
        session = self.get(user_id)
        session.mode = None
        session.awaiting = "profile"
        return session

    def set_brief(self, user_id: int, brief: str) -> Session:
        session = self.get(user_id)
        session.last_brief = brief
        session.awaiting = None
        return session

    def await_manual_edit(self, user_id: int) -> Session:
        session = self.get(user_id)
        session.awaiting = "manual_edit"
        return session

    def clear_flow(self, user_id: int) -> Session:
        session = self.get(user_id)
        session.mode = None
        session.awaiting = None
        session.last_brief = None
        return session

    def save_profile(self, user_id: int, profile: BrandProfile) -> Session:
        session = self.get(user_id)
        session.profile = profile
        session.awaiting = None
        return session
