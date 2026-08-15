"""Настройки учебного MVP «СвойТон»."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация из локального файла `.env` и переменных окружения."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    vk_bot_token: str = Field(default="", repr=False)
    polza_api_key: str = Field(default="", repr=False)
    polza_model: str = ""
    polza_base_url: str = "https://polza.ai/api/v1"
    request_timeout_seconds: float = Field(default=45.0, gt=0, le=180)
    max_tokens: int = Field(default=900, gt=0, le=4000)

    def require_vk_token(self) -> str:
        """Вернуть VK token или сообщить о незаполненной конфигурации."""

        if not self.vk_bot_token:
            raise ValueError("Не задан VK_BOT_TOKEN в файле .env")
        return self.vk_bot_token

    def require_polza_credentials(self) -> tuple[str, str]:
        """Вернуть ключ и модель Polza или сообщить о незаполненной конфигурации."""

        missing = []
        if not self.polza_api_key:
            missing.append("POLZA_API_KEY")
        if not self.polza_model:
            missing.append("POLZA_MODEL")
        if missing:
            raise ValueError(f"Не заданы настройки Polza: {', '.join(missing)}")
        return self.polza_api_key, self.polza_model

    @property
    def normalized_polza_base_url(self) -> str:
        """Вернуть base URL без завершающего слеша."""

        return self.polza_base_url.rstrip("/")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Создать и закэшировать настройки приложения."""

    return Settings()
