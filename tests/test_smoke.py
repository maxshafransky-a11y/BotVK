"""Smoke-тесты мини-MVP без VK token и сетевых запросов."""

import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.polza_client import GenerationResult
from app.prompts import BrandProfile, build_messages
from app.storage import SQLiteStore
from app.trace import TraceLogger


class PromptSmokeTests(unittest.TestCase):
    def test_prompt_marks_user_content_as_untrusted(self) -> None:
        messages = build_messages(
            "post",
            "Сделай анонс услуги",
            BrandProfile(business_name="Студия", facts=("По записи",)),
        )

        self.assertEqual([message["role"] for message in messages], ["system", "user"])
        self.assertIn("<untrusted_brief>", messages[1]["content"])
        self.assertIn("По записи", messages[0]["content"])

    def test_empty_brief_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_messages("post", "   ")


class StorageSmokeTests(unittest.TestCase):
    def test_wal_trace_and_owner_isolation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = SQLiteStore(Path(temp_dir) / "bot.sqlite3")
            store.save_profile(
                10,
                BrandProfile(
                    business_name="Студия",
                    offer="Маникюр",
                    audience="Клиенты",
                    tone="Спокойный",
                    facts=("По записи",),
                ),
            )
            loaded_profile = store.load_profile(10)
            self.assertIsNotNone(loaded_profile)
            self.assertEqual(loaded_profile.business_name, "Студия")
            result = GenerationResult(
                text="Черновик",
                provider="polza",
                model="test/model",
                usage={"total_tokens": 3},
                cost=0.01,
            )
            store.save_generation(10, "post", "Тема", result)
            TraceLogger(store).record(
                10,
                "generation",
                task_type="post",
                status="success",
                latency_ms=12,
            )

            connection = sqlite3.connect(store.path)
            try:
                self.assertEqual(
                    connection.execute(
                        "select count(*) from brand_profiles where user_id = 10"
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute(
                        "select count(*) from generations where user_id = 11"
                    ).fetchone()[0],
                    0,
                )
                self.assertEqual(
                    connection.execute("select count(*) from events where user_id = 10").fetchone()[0],
                    1,
                )
                self.assertEqual(
                    connection.execute("pragma journal_mode").fetchone()[0].lower(),
                    "wal",
                )
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
