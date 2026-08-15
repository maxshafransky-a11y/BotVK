"""Точка входа локального VK LongPoll-бота."""

from pathlib import Path

from .bot import SvoyTonBot
from .config import Settings, get_settings
from .storage import SQLiteStore
from .trace import TraceLogger


def build_application(settings: Settings | None = None) -> SvoyTonBot:
    """Собрать приложение с локальным SQLite и trace."""

    active_settings = settings or get_settings()
    database_path = Path(__file__).resolve().parents[1] / "data" / "botvk.sqlite3"
    storage = SQLiteStore(database_path)
    trace = TraceLogger(storage)
    return SvoyTonBot(active_settings, storage=storage, trace=trace)


def main() -> None:
    """Запустить VK LongPoll до остановки процесса."""

    build_application().bot.run_forever()


if __name__ == "__main__":
    main()
