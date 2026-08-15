"""Минимальный безопасный клиент Polza.ai Chat Completions."""

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import httpx

from .config import Settings


class PolzaError(RuntimeError):
    """Ошибка вызова или разбора ответа Polza.ai."""


@dataclass(frozen=True)
class GenerationResult:
    """Нормализованный результат провайдера для application-слоя."""

    text: str
    provider: str
    model: str
    usage: Mapping[str, Any]
    cost: float | None = None


class PolzaClient:
    """Клиент текстовой генерации без утечки ключа в исключения и логи."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def generate(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        user_id: str | None = None,
    ) -> GenerationResult:
        """Создать ответ по OpenAI-compatible контракту Polza.ai."""

        api_key, model = self._settings.require_polza_credentials()
        payload: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "max_tokens": self._settings.max_tokens,
            "temperature": 0.7,
            "stream": False,
        }
        if user_id:
            payload["user"] = user_id

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            endpoint = (
                f"{self._settings.normalized_polza_base_url}"
                "/chat/completions"
            )
            async with httpx.AsyncClient(
                timeout=self._settings.request_timeout_seconds,
            ) as client:
                response = await client.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise PolzaError("Polza.ai не ответил вовремя") from exc
        except httpx.RequestError as exc:
            raise PolzaError("Не удалось связаться с Polza.ai") from exc

        if response.is_error:
            raise PolzaError(
                f"Polza.ai вернул ошибку HTTP {response.status_code}"
            )

        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise PolzaError("Polza.ai вернул неожиданный формат ответа") from exc

        if not isinstance(text, str) or not text.strip():
            raise PolzaError("Polza.ai вернул пустой ответ")

        usage = data.get("usage") or {}
        cost = data.get("cost_rub", data.get("cost"))
        if not isinstance(cost, (int, float)):
            cost = None

        return GenerationResult(
            text=text.strip(),
            provider="polza",
            model=model,
            usage=usage if isinstance(usage, Mapping) else {},
            cost=float(cost) if cost is not None else None,
        )
