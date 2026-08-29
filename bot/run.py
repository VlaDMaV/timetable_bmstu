import asyncio
import logging
import httpx
from datetime import datetime
from zoneinfo import ZoneInfo
from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.exceptions import TelegramMigrateToChat
from common.database import models
from common.calendar_days import is_day_off
from common.semester import academic_week_number, schedule_ord_for_week, week_type_name
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import joinedload

from config import config
from app.handlers import SessionLocal, router
from app.handlers import engine
from app.schedule_updates import router as schedule_updates_router
from app.utils.utils import format_timetable
from app.utils.telegram import split_message_text
from app.notifications import due_notification_target
from app import keyboards as kb
from app import text as cs


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def safe_send(bot, tg_id, text, **kwargs):
    try:
        chat_id = int(tg_id) if tg_id is not None else None
        if not chat_id:
            return False

        await bot.send_message(chat_id, text, **kwargs)
        return True
    except TelegramMigrateToChat as e:
        new_id = e.migrate_to_chat_id
        with SessionLocal() as db:
            existing_user = db.query(models.User).filter_by(tg_id=new_id).first()
            if existing_user:
                old_user = db.query(models.User).filter_by(tg_id=tg_id).first()
                if old_user:
                    db.delete(old_user)
                    db.commit()
            else:
                db.query(models.User).filter_by(tg_id=tg_id).update({"tg_id": new_id})
                db.commit()

        await bot.send_message(new_id, text, **kwargs)
        return True
    except Exception as e:
        logger.warning("Ошибка при отправке сообщения %s: %s", tg_id, e)
        return False


async def send_daily_timetable(bot):
    """Рассылка расписания всем пользователям в учебный день."""
    now = datetime.now(ZoneInfo("Europe/Moscow"))
    with SessionLocal() as db:
        if now.isoweekday() == 7 or is_day_off(db, now.date()):
            logger.info("Рассылка пропущена: %s отмечен как выходной", now.date())
            return 0

        users = (
            db.query(models.User.tg_id, models.Group.name)
            .outerjoin(models.Group, models.User.group_id == models.Group.id)
            .filter(models.User.is_active == 1)
            .all()
        )

    _, week_number, weekday = now.isocalendar()
    weekday_name = cs.WEEKDAYS.get(weekday, "Monday")
    week_ord = schedule_ord_for_week(week_number)

    async with httpx.AsyncClient(timeout=15.0) as client:
        for tg_id, group_name in users:
            try:
                if not group_name:
                    await safe_send(bot, tg_id, "Группа не выбрана")
                    continue

                group_display_name = cs.group_display_name(group_name)
                params = {
                    "ord": week_ord,
                    "day": weekday_name,
                    "group": group_name,
                }

                try:
                    response = await client.get(
                        "http://backend:8000/dayboard/filter",
                        params=params,
                    )
                    response.raise_for_status()
                    data = response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    logger.warning(
                        "Не удалось получить расписание для %s: %s",
                        group_name,
                        exc,
                    )
                    await safe_send(bot, tg_id, "Ошибка при получении расписания.")
                    continue

                if not data:
                    logger.info(
                        "Рассылка пользователю %s пропущена: у группы %s нет пар",
                        tg_id,
                        group_name,
                    )
                    continue

                timetable_text = format_timetable(data)
                message_text = cs.append_support_footer(
                    f"Доброе утро! ☀️\n"
                    f"Расписание на сегодня для группы <b>{group_display_name}</b>:\n\n"
                    f"{timetable_text}",
                    trailing_text=(
                        f"{academic_week_number(week_number)} неделя: "
                        f"{week_type_name(week_number)}"
                    ),
                )

                chunks = split_message_text(message_text)
                for index, chunk in enumerate(chunks):
                    await safe_send(
                        bot,
                        tg_id,
                        chunk,
                        parse_mode="HTML",
                        reply_markup=kb.back_to_main if index == len(chunks) - 1 else None,
                    )
            except Exception:
                logger.exception("Ошибка рассылки для пользователя %s", tg_id)


async def send_user_schedule_notification(bot, user, target_date):
    """Возвращает True при отправке, False без пар и None при ошибке."""
    if not user.group_rel:
        return None

    week_number = target_date.isocalendar()[1]
    weekday_name = cs.WEEKDAYS.get(target_date.isoweekday(), "Monday")
    week_ord = schedule_ord_for_week(week_number)
    params = {
        "ord": week_ord,
        "day": weekday_name,
        "group": user.group_rel.name,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "http://backend:8000/dayboard/filter",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(
            "Не удалось получить расписание для %s: %s",
            user.group_rel.name,
            exc,
        )
        return None

    if not data:
        logger.info(
            "Уведомление пользователю %s пропущено: у группы %s нет пар на %s",
            user.tg_id,
            user.group_rel.name,
            target_date,
        )
        return False

    timetable_text = format_timetable(
        data,
        include_empty_days=True,
        day_dates={weekday_name: target_date},
        days=[weekday_name],
    )
    message_text = cs.append_support_footer(
        f"🔔 Расписание на <b>{target_date.strftime('%d.%m.%Y')}</b> "
        f"для группы <b>{cs.group_display_name(user.group_rel.name)}</b>:\n\n"
        f"{timetable_text}",
        trailing_text=(
            f"{academic_week_number(week_number)} неделя: "
            f"{week_type_name(week_number)}"
        ),
    )

    chunks = split_message_text(message_text)
    sent = True
    for index, chunk in enumerate(chunks):
        chunk_sent = await safe_send(
            bot,
            user.tg_id,
            chunk,
            parse_mode="HTML",
            reply_markup=kb.back_to_main if index == len(chunks) - 1 else None,
        )
        sent = sent and chunk_sent
    return sent


async def process_due_notifications(bot, now=None):
    """Проверяет индивидуальные настройки и отправляет только наступившие уведомления."""
    now = now or datetime.now(ZoneInfo("Europe/Moscow"))
    sent_count = 0
    with SessionLocal() as db:
        users = (
            db.query(models.User)
            .options(joinedload(models.User.group_rel))
            .filter(models.User.is_active == 1)
            .all()
        )
        for user in users:
            target_date = due_notification_target(db, user, now)
            if target_date is None:
                continue
            try:
                result = await send_user_schedule_notification(bot, user, target_date)
                if result is not None:
                    user.last_notification_date = target_date
                    db.commit()
                    if result:
                        sent_count += 1
            except Exception:
                db.rollback()
                logger.exception(
                    "Ошибка персональной рассылки пользователю %s",
                    user.tg_id,
                )
    return sent_count


async def daily_timetable_task(bot):
    """Проверяет персональное время оповещения каждые 30 секунд."""
    while True:
        try:
            await process_due_notifications(bot)
        except Exception:
            logger.exception("Ошибка проверки персональных уведомлений")
        await asyncio.sleep(30)


async def wait_for_db():
    for i in range(10):
        try:
            with engine.connect():
                pass
            logger.info("DB is ready")
            return
        except OperationalError:
            logger.warning("БД пока недоступна, попытка %s/10", i + 1)
            await asyncio.sleep(3)
    raise RuntimeError("Не удалось подключиться к БД после 10 попыток")


class DatabaseSessionMiddleware(BaseMiddleware):
    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    async def __call__(self, handler, event, data):
        db = self.session_factory()
        data["db"] = db
        try:
            return await handler(event, data)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

async def main():
    await wait_for_db()

    bot = Bot(token=config.bot_token.get_secret_value())
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(DatabaseSessionMiddleware())
    # Подтверждение отчёта должно проверяться раньше FSM поиска/рассылки:
    # обработчик узкий и срабатывает только на ответ администратора на отчёт.
    dispatcher.include_router(schedule_updates_router)
    dispatcher.include_router(router)
    daily_task = asyncio.create_task(daily_timetable_task(bot))

    try:
        logger.info("Бот запущен")
        await dispatcher.start_polling(bot)
    finally:
        daily_task.cancel()
        await asyncio.gather(daily_task, return_exceptions=True)
        await bot.session.close()
        logger.info("Бот остановлен")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Приложение завершено")
