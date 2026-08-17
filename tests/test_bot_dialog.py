"""Детерминированная проверка dispatcher-flow без VK и сети."""

import asyncio
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.bot import SvoyTonBot
from app.polza_client import GenerationResult
from app.states import StateStore
from app.storage import SQLiteStore


class FakeMessage:
    def __init__(self, text: str, user_id: int = 10) -> None:
        self.text = text
        self.from_id = user_id
        self.peer_id = user_id
        self.answers: list[tuple[str, str | None]] = []

    async def answer(self, text: str, *, keyboard: str | None = None) -> None:
        self.answers.append((text, keyboard))


class FakePolza:
    async def generate(self, messages: list[dict[str, str]], *, user_id: str) -> GenerationResult:
        return GenerationResult(
            text="Сгенерированный текст",
            provider="polza",
            model="test/model",
            usage={"total_tokens": 3},
            cost=0.01,
        )


def make_bot(storage: SQLiteStore) -> SvoyTonBot:
    bot = object.__new__(SvoyTonBot)
    bot._states = StateStore()
    bot._storage = storage
    bot._trace = None
    bot._polza = FakePolza()
    return bot


class BotDialogTests(unittest.TestCase):
    def test_generation_creates_current_draft_and_accepts_only_that_draft(self) -> None:
        with TemporaryDirectory() as temp_dir:
            bot = make_bot(SQLiteStore(Path(temp_dir) / "bot.sqlite3"))

            task_message = FakeMessage("Написать пост")
            asyncio.run(bot._dispatch(task_message))
            self.assertIn('"type": "text"', task_message.answers[-1][1])
            self.assertIn('"color": "secondary"', task_message.answers[-1][1])
            brief_message = FakeMessage("Пост о новой кофейне без цены и скидки")
            asyncio.run(bot._dispatch(brief_message))

            session = bot._states.get(10)
            self.assertIsNotNone(session.current_draft)
            self.assertEqual(session.current_draft.status, "draft")
            self.assertIn("ЧЕРНОВИК", brief_message.answers[-1][0])
            self.assertIn("не опубликован", brief_message.answers[-1][0])

            asyncio.run(bot._dispatch(FakeMessage("Подходит")))

            self.assertEqual(session.current_draft.status, "accepted")
            connection = sqlite3.connect(bot._storage.path)
            try:
                status = connection.execute(
                    "select status from generations where id = ?",
                    (session.current_draft.id,),
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(status, "accepted")

    def test_result_actions_without_draft_do_not_claim_acceptance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            bot = make_bot(SQLiteStore(Path(temp_dir) / "bot.sqlite3"))
            message = FakeMessage("Подходит")

            asyncio.run(bot._dispatch(message))

            self.assertIn("нет активного черновика", message.answers[-1][0].casefold())

    def test_manual_edit_updates_current_draft_text_and_status(self) -> None:
        with TemporaryDirectory() as temp_dir:
            bot = make_bot(SQLiteStore(Path(temp_dir) / "bot.sqlite3"))
            asyncio.run(bot._dispatch(FakeMessage("Написать пост")))
            asyncio.run(bot._dispatch(FakeMessage("Тема поста")))

            asyncio.run(bot._dispatch(FakeMessage("Изменить вручную")))
            asyncio.run(bot._dispatch(FakeMessage("Моя финальная версия")))

            draft = bot._states.get(10).current_draft
            self.assertEqual(draft.text, "Моя финальная версия")
            self.assertEqual(draft.status, "edited")


if __name__ == "__main__":
    unittest.main()
