from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.database import models
from .config import MonitorConfig
from .monitor import run_once, telegram_request


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
# URL Telegram Bot API содержит токен, поэтому сетевые библиотеки не должны
# писать полные адреса запросов даже при общем уровне INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
MANUAL_REQUEST_POLL_SECONDS = 5


def next_sunday_run(now: datetime, hour: int, minute: int) -> datetime:
    days_until_sunday = (7 - now.isoweekday()) % 7
    target = (now + timedelta(days=days_until_sunday)).replace(
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
    )
    if target <= now:
        target += timedelta(days=7)
    return target


def recover_interrupted_manual_runs(session_factory: sessionmaker) -> None:
    with session_factory() as db:
        interrupted = (
            db.query(models.ScheduleMonitorRun)
            .filter(models.ScheduleMonitorRun.status == "running")
            .all()
        )
        for run in interrupted:
            run.status = "failed"
            run.finished_at = datetime.now(timezone.utc)
            run.error = "Сервис перезапущен во время выполнения проверки"
        db.commit()


def claim_manual_run(session_factory: sessionmaker) -> int | None:
    with session_factory() as db:
        run = (
            db.query(models.ScheduleMonitorRun)
            .filter(models.ScheduleMonitorRun.status == "queued")
            .order_by(models.ScheduleMonitorRun.id)
            .with_for_update(skip_locked=True)
            .first()
        )
        if run is None:
            return None
        run.status = "running"
        run.started_at = datetime.now(timezone.utc)
        run.error = None
        db.commit()
        return run.id


def finish_manual_run(
    session_factory: sessionmaker,
    run_id: int,
    *,
    error: str | None = None,
) -> None:
    with session_factory() as db:
        run = db.get(models.ScheduleMonitorRun, run_id)
        if run is None:
            return
        run.status = "failed" if error else "completed"
        run.finished_at = datetime.now(timezone.utc)
        run.error = error
        db.commit()


async def process_manual_run(
    config: MonitorConfig,
    session_factory: sessionmaker,
) -> bool:
    run_id = claim_manual_run(session_factory)
    if run_id is None:
        return False

    logger.info("Запущена ручная проверка расписаний №%s", run_id)
    try:
        await run_once(config, session_factory)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        finish_manual_run(session_factory, run_id, error=error)
        logger.exception("Ручная проверка расписаний №%s завершилась ошибкой", run_id)
        try:
            await telegram_request(
                config,
                "sendMessage",
                data={
                    "chat_id": str(config.admin_id),
                    "text": (
                        f"❌ Ручная проверка расписаний №{run_id} не выполнена. "
                        f"Причина: {error}"
                    )[:4000],
                },
            )
        except Exception:
            logger.exception("Не удалось уведомить администратора об ошибке")
    else:
        finish_manual_run(session_factory, run_id)
        logger.info("Ручная проверка расписаний №%s завершена", run_id)
    return True


async def daemon(config: MonitorConfig, session_factory: sessionmaker) -> None:
    recover_interrupted_manual_runs(session_factory)
    if config.run_on_start:
        try:
            await run_once(config, session_factory)
        except Exception:
            logger.exception("Стартовая проверка расписаний завершилась ошибкой")

    timezone = ZoneInfo(config.timezone)
    target = next_sunday_run(
        datetime.now(timezone),
        config.sunday_hour,
        config.sunday_minute,
    )
    logger.info("Следующая проверка расписаний: %s", target.isoformat())

    while True:
        now = datetime.now(timezone)
        if now >= target:
            try:
                await run_once(config, session_factory)
            except Exception as exc:
                logger.exception("Еженедельная проверка расписаний завершилась ошибкой")
                try:
                    await telegram_request(
                        config,
                        "sendMessage",
                        data={
                            "chat_id": str(config.admin_id),
                            "text": (
                                "❌ Еженедельная проверка расписаний не выполнена. "
                                f"Причина: {type(exc).__name__}: {exc}"
                            )[:4000],
                        },
                    )
                except Exception:
                    logger.exception(
                        "Не удалось уведомить администратора об ошибке мониторинга"
                    )
            target = next_sunday_run(
                datetime.now(timezone),
                config.sunday_hour,
                config.sunday_minute,
            )
            logger.info("Следующая проверка расписаний: %s", target.isoformat())
            continue

        if await process_manual_run(config, session_factory):
            continue

        wait_seconds = min(
            MANUAL_REQUEST_POLL_SECONDS,
            max(0.1, (target - datetime.now(timezone)).total_seconds()),
        )
        await asyncio.sleep(wait_seconds)


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="Монитор изменений расписаний КФ МГТУ")
    parser.add_argument("--once", action="store_true", help="Выполнить одну проверку и выйти")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Только вывести отчёт; не создавать заявку и не отправлять Telegram",
    )
    args = parser.parse_args()

    config = MonitorConfig.from_env()
    engine = create_engine(
        config.database_url,
        pool_pre_ping=True,
        pool_recycle=1800,
    )
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    models.Base.metadata.create_all(bind=engine)

    if args.once or args.dry_run:
        await run_once(config, session_factory, dry_run=args.dry_run)
    else:
        await daemon(config, session_factory)


if __name__ == "__main__":
    asyncio.run(async_main())
