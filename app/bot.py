"""VK LongPoll и conversational UX мини-версии «СвойТон»."""

import re
from dataclasses import replace
from time import perf_counter

from vkbottle import Bot
from vkbottle.bot import Message

from .config import Settings
from .keyboards import INPUT_KEYBOARD, MAIN_KEYBOARD, MORE_KEYBOARD, RESULT_KEYBOARD
from .polza_client import PolzaClient, PolzaError
from .prompts import TASK_INPUT_PROMPTS, BrandProfile, TaskType, build_messages
from .states import Draft, Session, StateStore
from .storage import SQLiteStore
from .trace import TraceLogger


WELCOME = """Привет! Я «СвойТон» — AI-редактор черновиков для VK.

Я могу подготовить пост, продающий текст, ответ клиенту или идеи контента.
Результат всегда остаётся черновиком: я ничего не публикую и не отправляю.

Выбери задачу кнопкой ниже."""

TASKS: dict[str, TaskType] = {
    "написать пост": "post",
    "продающий текст": "sales_text",
    "ответить клиенту": "client_reply",
    "идеи контента": "content_ideas",
    "переписать текст": "rewrite",
}


def _profile_matches_brief(profile: BrandProfile, brief: str) -> bool:
    """Разрешить профиль только если brief явно относится к его предметной области."""

    profile_words = re.findall(
        r"[a-zа-яё0-9]{5,}",
        " ".join((profile.business_name, profile.offer, *profile.facts)).casefold(),
    )
    brief_words = re.findall(r"[a-zа-яё0-9]{5,}", brief.casefold())
    return any(
        profile_word[:5] == brief_word[:5]
        for profile_word in profile_words
        for brief_word in brief_words
    )


def _profile_for_brief(profile: BrandProfile, brief: str) -> BrandProfile:
    """Не переносить факты другого бизнеса в новый brief; тон безопасен как стиль."""

    if _profile_matches_brief(profile, brief):
        return profile
    return BrandProfile(tone=profile.tone)


def _normalize_vk_text(text: str) -> str:
    """Убрать базовые Markdown-маркеры, которые VK показывает как обычный текст."""

    without_bold = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    return re.sub(r"(?m)^\s*\*\s+", "• ", without_bold)


class SvoyTonBot:
    """Собирает VK-бота и регистрирует один безопасный dispatcher handler."""

    def __init__(
        self,
        settings: Settings,
        *,
        storage: SQLiteStore | None = None,
        trace: TraceLogger | None = None,
    ) -> None:
        self._settings = settings
        self._bot = Bot(settings.require_vk_token())
        self._states = StateStore()
        self._polza = PolzaClient(settings)
        self._storage = storage
        self._trace = trace
        self._register_handlers()

    @property
    def bot(self) -> Bot:
        """Вернуть настроенный экземпляр VKBottle."""

        return self._bot

    def _register_handlers(self) -> None:
        self._bot.on.message()(self._dispatch)

    async def _dispatch(self, message: Message) -> None:
        text = (message.text or "").strip()
        normalized = text.casefold()
        user_id = int(message.from_id or message.peer_id)
        session = self._states.get(user_id)
        if self._storage is not None and not session.profile.business_name:
            stored_profile = self._storage.load_profile(user_id)
            if stored_profile is not None:
                session.profile = stored_profile

        if normalized in {"/start", "начать", "старт"}:
            self._states.clear_flow(user_id)
            await message.answer(WELCOME, keyboard=MAIN_KEYBOARD)
            return
        if normalized in {"меню", "/menu"}:
            self._states.clear_flow(user_id)
            await message.answer("Главное меню. Выбери задачу:", keyboard=MAIN_KEYBOARD)
            return
        if normalized in {"помощь", "/help", "help"}:
            await message.answer(self._help_text(), keyboard=MORE_KEYBOARD)
            return
        if normalized in {"ещё", "еще", "/more"}:
            await message.answer("Дополнительные действия:", keyboard=MORE_KEYBOARD)
            return
        if normalized in {"назад", "/back"}:
            self._states.clear_flow(user_id)
            await message.answer("Вернул в главное меню.", keyboard=MAIN_KEYBOARD)
            return
        if normalized in {"отмена", "/cancel"}:
            self._states.clear_flow(user_id)
            await message.answer("Текущая задача отменена.", keyboard=MAIN_KEYBOARD)
            return
        if normalized.startswith("профиль:"):
            await self._save_profile_from_text(message, user_id, text)
            return
        if normalized == "профиль бренда":
            self._states.start_profile(user_id)
            await message.answer(
                "Отправь профиль одной строкой через |:\n"
                "название | предложение | аудитория | тон | факты",
                keyboard=INPUT_KEYBOARD,
            )
            return

        task = TASKS.get(normalized)
        if task:
            self._states.start_task(user_id, task)
            await message.answer(
                f"Задача: {task}.\n\n{TASK_INPUT_PROMPTS[task]}\n\n"
                "Отправь brief одним сообщением. Можно отменить в любой момент.",
                keyboard=INPUT_KEYBOARD,
            )
            return

        if normalized == "подходит":
            draft = session.current_draft
            if draft is None or draft.status == "accepted":
                await message.answer(
                    "Нет активного черновика для принятия. Сначала выбери задачу.",
                    keyboard=MAIN_KEYBOARD,
                )
                return
            if self._storage is not None and draft.id is not None:
                updated = self._storage.update_generation(
                    user_id,
                    draft.id,
                    status="accepted",
                )
                if not updated:
                    await message.answer(
                        "Не нашёл этот черновик. Сгенерируй новый вариант.",
                        keyboard=MAIN_KEYBOARD,
                    )
                    return
            draft.status = "accepted"
            await message.answer(
                "Принял этот черновик. Публикация и отправка не выполняются.",
                keyboard=MAIN_KEYBOARD,
            )
            self._states.clear_flow(user_id)
            return
        if normalized == "ещё вариант" or normalized == "еще вариант":
            if session.current_draft is not None and session.mode and session.last_brief:
                await self._generate(message, user_id, session, session.last_brief)
            else:
                await message.answer("Нет активного черновика для нового варианта.", keyboard=MAIN_KEYBOARD)
            return
        if normalized == "изменить вручную":
            if session.current_draft is not None and session.mode:
                self._states.await_manual_edit(user_id)
                await message.answer(
                    "Отправь свою версию текста. Она останется черновиком.",
                    keyboard=INPUT_KEYBOARD,
                )
            else:
                await message.answer("Пока нет черновика для редактирования.", keyboard=MAIN_KEYBOARD)
            return

        if session.awaiting == "profile":
            await self._save_profile_from_text(message, user_id, text)
            return
        if session.awaiting in {"brief", "manual_edit"}:
            if session.awaiting == "manual_edit":
                draft = session.current_draft
                if draft is None:
                    self._states.clear_flow(user_id)
                    await message.answer("Черновик уже недоступен. Начни новую задачу.", keyboard=MAIN_KEYBOARD)
                    return
                if self._storage is not None and draft.id is not None:
                    updated = self._storage.update_generation(
                        user_id,
                        draft.id,
                        output_text=text,
                        status="edited",
                    )
                    if not updated:
                        await message.answer(
                            "Не удалось сохранить правку. Сгенерируй новый черновик.",
                            keyboard=MAIN_KEYBOARD,
                        )
                        return
                draft.text = text
                draft.status = "edited"
                session.awaiting = None
                await message.answer(
                    "Сохранил ручную правку как черновик. Ничего не отправлено.",
                    keyboard=RESULT_KEYBOARD,
                )
                return
            self._states.set_brief(user_id, text)
            await self._generate(message, user_id, session, text)
            return

        await message.answer("Не понял команду. Нажми «Помощь» или «Меню».", keyboard=MAIN_KEYBOARD)

    async def _save_profile_from_text(self, message: Message, user_id: int, text: str) -> None:
        payload = text.split(":", 1)[1].strip() if ":" in text else text.strip()
        parts = [part.strip() for part in payload.split("|")]
        if len(parts) < 5 or any(not part for part in parts[:5]):
            await message.answer(
                "Нужны 5 частей через |:\n"
                "название | предложение | аудитория | тон | факты",
                keyboard=MORE_KEYBOARD,
            )
            return

        profile = BrandProfile(
            business_name=parts[0],
            offer=parts[1],
            audience=parts[2],
            tone=parts[3],
            facts=tuple(item.strip() for item in parts[4].split(",") if item.strip()),
        )
        self._states.save_profile(user_id, profile)
        if self._storage is not None:
            self._storage.save_profile(user_id, profile)
            confirmation = "Профиль сохранён в SQLite и доступен после перезапуска."
        else:
            confirmation = "Профиль сохранён до перезапуска текущего процесса."
        await message.answer(
            confirmation,
            keyboard=MAIN_KEYBOARD,
        )

    async def _generate(
        self,
        message: Message,
        user_id: int,
        session: Session,
        brief: str,
    ) -> None:
        if session.mode is None:
            await message.answer("Сначала выбери задачу.", keyboard=MAIN_KEYBOARD)
            return

        started_at = perf_counter()
        await message.answer("Готовлю черновик…")
        try:
            result = await self._polza.generate(
                build_messages(session.mode, brief, _profile_for_brief(session.profile, brief)),
                user_id=str(user_id),
            )
        except (PolzaError, ValueError) as exc:
            if self._trace is not None:
                self._trace.record(
                    user_id,
                    "generation",
                    task_type=session.mode,
                    status="failed",
                    latency_ms=int((perf_counter() - started_at) * 1000),
                )
            await message.answer(
                f"Не получилось подготовить черновик: {exc}\n"
                "Проверь настройки и попробуй ещё раз.",
                keyboard=MAIN_KEYBOARD,
            )
            return

        result = replace(result, text=_normalize_vk_text(result.text))

        if self._storage is not None:
            draft_id = self._storage.save_generation(
                user_id,
                session.mode,
                brief,
                result,
                status="draft",
            )
        else:
            draft_id = None
        self._states.set_draft(
            user_id,
            Draft(
                id=draft_id,
                task=session.mode,
                brief=brief,
                text=result.text,
            ),
        )
        if self._trace is not None:
            self._trace.record(
                user_id,
                "generation",
                task_type=session.mode,
                status="success",
                latency_ms=int((perf_counter() - started_at) * 1000),
            )

        await message.answer(
            f"ЧЕРНОВИК · сохранён · {result.provider} · {result.model}\n\n"
            f"{result.text}\n\n"
            "Проверь факты перед использованием. Этот текст не опубликован и не отправлен.",
            keyboard=RESULT_KEYBOARD,
        )

    @staticmethod
    def _help_text() -> str:
        return (
            "Главное меню помогает решить одну задачу за раз.\n\n"
            "Профиль бренда: нажми «Профиль бренда» или отправь:\n"
            "профиль: название | предложение | аудитория | тон | факты\n\n"
            "Команды: меню, назад, отмена, помощь.\n"
            "Все результаты — черновики для ручной проверки."
        )


def create_bot(settings: Settings) -> Bot:
    """Создать VKBottle для запуска из `main.py`."""

    return SvoyTonBot(settings).bot
