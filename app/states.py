"""Минимальное in-memory состояние диалога пользователя."""

from dataclasses import dataclass, field
from typing import Literal

from .prompts import BrandProfile, TaskType


Awaiting = Literal["brief", "manual_edit", "profile"]
DraftStatus = Literal["draft", "edited", "accepted"]


@dataclass
class Draft:
    """Текущий результат, над которым пользователь выполняет action."""

    id: int | None
    task: TaskType
    brief: str
    text: str
    status: DraftStatus = "draft"


@dataclass
class Session:
    """Состояние одного VK-пользователя до подключения SQLite."""

    mode: TaskType | None = None
    awaiting: Awaiting | None = None
    last_brief: str | None = None
    current_draft: Draft | None = None
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
        session.current_draft = None
        return session

    def start_profile(self, user_id: int) -> Session:
        session = self.get(user_id)
        session.mode = None
        session.awaiting = "profile"
        session.current_draft = None
        return session

    def set_brief(self, user_id: int, brief: str) -> Session:
        session = self.get(user_id)
        session.last_brief = brief
        session.awaiting = None
        return session

    def set_draft(self, user_id: int, draft: Draft) -> Session:
        session = self.get(user_id)
        session.current_draft = draft
        session.last_brief = draft.brief
        session.mode = draft.task
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
        session.current_draft = None
        return session

    def save_profile(self, user_id: int, profile: BrandProfile) -> Session:
        session = self.get(user_id)
        session.profile = profile
        session.awaiting = None
        return session
