from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MonitorConfig:
    database_url: str
    bot_token: str
    admin_id: int
    timezone: str = "Europe/Moscow"
    sunday_hour: int = 9
    sunday_minute: int = 0
    request_timeout: float = 20.0
    request_attempts: int = 5
    concurrency: int = 3
    include_postgraduates: bool = False
    run_on_start: bool = False

    structure_url: str = "https://lks.bmstu.ru/lks-back/api/v1/structure"
    schedule_url_template: str = (
        "https://lks.bmstu.ru/lks-back/api/v1/schedules/groups/{uuid}/public"
    )
    faculty_uuids: tuple[str, ...] = (
        "b79ea086-ae47-11ea-a8eb-005056960017",  # ИУК, КФ МГТУ
        "e24f698c-ae47-11ea-8f64-005056960017",  # МК, КФ МГТУ
    )

    @classmethod
    def from_env(cls) -> "MonitorConfig":
        database_url = os.getenv("DATABASE_URL") or (
            "postgresql+psycopg2://"
            f"{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', 'postgres')}"
            f"@{os.getenv('DB_HOST', 'db')}:{os.getenv('DB_PORT', '5432')}"
            f"/{os.getenv('DB_NAME', 'timetable')}"
        )
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        admin_raw = os.getenv("ADMIN_ID", "").strip()
        if not bot_token or ":" not in bot_token:
            raise RuntimeError("Для schedule-monitor требуется корректный BOT_TOKEN")
        try:
            admin_id = int(admin_raw)
        except ValueError as exc:
            raise RuntimeError("Для schedule-monitor требуется числовой ADMIN_ID") from exc
        if admin_id <= 0:
            raise RuntimeError("ADMIN_ID должен быть положительным")

        hour = int(os.getenv("SCHEDULE_MONITOR_HOUR", "9"))
        minute = int(os.getenv("SCHEDULE_MONITOR_MINUTE", "0"))
        concurrency = int(os.getenv("SCHEDULE_MONITOR_CONCURRENCY", "3"))
        attempts = int(os.getenv("SCHEDULE_MONITOR_ATTEMPTS", "5"))
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise RuntimeError("Время мониторинга должно быть в диапазоне 00:00-23:59")
        if not 1 <= concurrency <= 20:
            raise RuntimeError("SCHEDULE_MONITOR_CONCURRENCY должен быть от 1 до 20")
        if not 1 <= attempts <= 10:
            raise RuntimeError("SCHEDULE_MONITOR_ATTEMPTS должен быть от 1 до 10")

        return cls(
            database_url=database_url,
            bot_token=bot_token,
            admin_id=admin_id,
            timezone=os.getenv("SCHEDULE_MONITOR_TIMEZONE", "Europe/Moscow"),
            sunday_hour=hour,
            sunday_minute=minute,
            request_timeout=float(os.getenv("SCHEDULE_MONITOR_TIMEOUT", "20")),
            request_attempts=attempts,
            concurrency=concurrency,
            include_postgraduates=_env_bool("SCHEDULE_MONITOR_INCLUDE_ASPIRANTS", False),
            run_on_start=_env_bool("SCHEDULE_MONITOR_RUN_ON_START", False),
        )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "да"}
