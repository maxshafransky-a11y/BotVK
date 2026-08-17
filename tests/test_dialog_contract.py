"""Контракт brief-приглашений и безопасного prompt для задач."""

import unittest

from app.prompts import TASK_INPUT_PROMPTS, build_messages


class DialogContractTests(unittest.TestCase):
    def test_each_task_has_a_distinct_input_contract(self) -> None:
        self.assertEqual(len(TASK_INPUT_PROMPTS), 5)
        self.assertEqual(len(set(TASK_INPUT_PROMPTS.values())), 5)
        self.assertIn("исходный текст", TASK_INPUT_PROMPTS["rewrite"].casefold())
        self.assertIn("сообщение клиента", TASK_INPUT_PROMPTS["client_reply"].casefold())

    def test_prompt_requires_grounded_numeric_claims_and_task_contract(self) -> None:
        messages = build_messages("sales_text", "Опиши услугу")

        for term in ("цены", "скидки", "сроки"):
            self.assertIn(term, messages[0]["content"])
        self.assertIn("не нужно придумывать", messages[0]["content"])
        self.assertIn("Что продаём", messages[1]["content"])

    def test_content_ideas_are_a_week_plan(self) -> None:
        messages = build_messages("content_ideas", "Нужен план для кафе")

        self.assertIn("7 дней", messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
