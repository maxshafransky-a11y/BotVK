"""Регрессии для жизненного цикла текущего draft."""

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.polza_client import GenerationResult
from app.prompts import BrandProfile
from app.states import Draft, StateStore
from app.storage import SQLiteStore


class DraftStateTests(unittest.TestCase):
    def test_current_draft_is_replaced_when_new_task_starts(self) -> None:
        states = StateStore()
        states.start_task(10, "post")
        states.set_draft(
            10,
            Draft(id=7, task="post", brief="Тема", text="Черновик"),
        )

        states.start_task(10, "rewrite")

        session = states.get(10)
        self.assertIsNone(session.current_draft)
        self.assertEqual(session.mode, "rewrite")
        self.assertEqual(session.awaiting, "brief")

    def test_clear_flow_keeps_draft_available_for_result_action(self) -> None:
        states = StateStore()
        states.set_draft(
            10,
            Draft(id=7, task="post", brief="Тема", text="Черновик"),
        )

        states.clear_flow(10)

        self.assertIsNotNone(states.get(10).current_draft)
        self.assertIsNone(states.get(10).awaiting)


class DraftStorageTests(unittest.TestCase):
    def test_draft_status_and_owner_scoped_update(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteStore(Path(temp_dir) / "bot.sqlite3")
            result = GenerationResult(
                text="Черновик",
                provider="polza",
                model="test/model",
                usage={"total_tokens": 3},
                cost=0.01,
            )
            draft_id = store.save_generation(10, "post", "Тема", result)

            self.assertTrue(store.update_generation(10, draft_id, status="accepted"))
            self.assertFalse(store.update_generation(11, draft_id, status="accepted"))

            connection = sqlite3.connect(store.path)
            try:
                row = connection.execute(
                    "select output_text, status from generations where id = ?",
                    (draft_id,),
                ).fetchone()
            finally:
                connection.close()

            self.assertEqual(row, ("Черновик", "accepted"))


if __name__ == "__main__":
    unittest.main()
