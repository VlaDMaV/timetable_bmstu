import asyncio
import logging
import os
import signal
import time
import httpx
from threading import Thread, Event
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramMigrateToChat
from common.database import models
from watchfiles import watch
from sqlalchemy.exc import OperationalError
from functools import partial

from config import config
from app.handlers import SessionLocal, router
from app.handlers import engine
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from app.utils.utils import format_timetable
from app import keyboards as kb
from app import text as cs
from app.handlers import SessionLocal


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def safe_send(bot, tg_id, text, **kwargs):
    db = SessionLocal()
    try:
        chat_id = int(tg_id) if tg_id is not None else None
        if not chat_id:
            return

        await bot.send_message(chat_id, text, **kwargs)
    except TelegramMigrateToChat as e:
        new_id = e.migrate_to_chat_id

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
    except Exception as e:
        print(f"Ошибка при отправке сообщения {tg_id}: {e}")
    finally:
        db.close()


async def send_daily_timetable(bot):
    """Рассылка расписания всем пользователям каждый день в 8:00 по МСК"""
    db = SessionLocal()
    try:
        users = db.query(models.User).filter(models.User.is_active == 1).all()
        now = datetime.now(ZoneInfo("Europe/Moscow"))
        year, week_number, weekday = now.isocalendar()
        weekday_index = now.isoweekday()  # 1–7
        weekday_name = cs.WEEKDAYS.get(weekday_index, "Monday")
        week_ord = (now.isocalendar()[1] + 1) % 2  # 0 — знаменатель, 1 — числитель

        for user in users:
            if not user.group_rel:
                await bot.send_message(user.tg_id, "Группа не выбрана")
                continue

            group = user.group_rel.name
            group_name = user.group_rel.name
            group_display_name = cs.groups.get(group_name, group_name)

            base_url = "http://backend:8000/dayboard/filter"
            params = {
                "ord": week_ord,
                "day": weekday_name,
                "group": group 
            }

            async with httpx.AsyncClient() as client:
                try:
                    response = await client.get(base_url, params=params)
                    response.raise_for_status()
                    data = response.json()
                except httpx.HTTPError:
                    await bot.send_message(user.tg_id, "Ошибка при получении расписания.")
                    continue

            timetable_text = format_timetable(data)

            message_text = (
                f"Доброе утро! ☀️\n"
                f"Расписание на сегодня для группы <b>{group_display_name}</b>:\n\n"
                f"{timetable_text}"
                f"{week_number-35} неделя: {'Знаменатель' if week_ord == 0 else 'Числитель'}"
            )

            for i in range(0, len(message_text), 4000):
                await safe_send(
                    bot,
                    user.tg_id,
                    message_text[i:i+4000],
                    parse_mode="HTML",
                    reply_markup=kb.back_to_main
                )

    finally:
        db.close()


async def daily_timetable_task(bot):
    """Задача для ежедневной рассылки в заданное время"""
    while True:
        db = SessionLocal()
        try:
            hour_setting = db.query(models.Settings).filter(models.Settings.key == "daily_timetable_hour").first()
            minute_setting = db.query(models.Settings).filter(models.Settings.key == "daily_timetable_minute").first()

            hour = int(hour_setting.value) if hour_setting else 8
            minute = int(minute_setting.value) if minute_setting else 0
        finally:
            db.close()

        now = datetime.now(ZoneInfo("Europe/Moscow"))
        target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target_time:
            target_time += timedelta(days=1)

        wait_seconds = (target_time - now).total_seconds()
        await asyncio.sleep(wait_seconds)

        weekday_index = datetime.now(ZoneInfo("Europe/Moscow")).isoweekday()

        if weekday_index == 7:
            continue

        await send_daily_timetable(bot)


def wait_for_db():
    for i in range(10):
        try:
            conn = engine.connect()
            conn.close()
            print("DB is ready")
            break
        except OperationalError:
            print("Waiting for DB...")
            time.sleep(3)
    else:
        raise Exception("Could not connect to DB")
    

class RestartTimer:
    def __init__(self, delay_seconds=30):
        self.delay = timedelta(seconds=delay_seconds)
        self.last_change_time = None
        self.event = Event()

    def change_detected(self):
        self.last_change_time = datetime.now()
        if not self.event.is_set():
            self.event.set()

    def should_restart(self):
        if self.last_change_time and datetime.now() - self.last_change_time >= self.delay:
            self.event.clear()
            self.last_change_time = None
            return True
        return False

class BotManager:
    def __init__(self):
        global bot
        self.bot = Bot(token=config.bot_token.get_secret_value())
        self.dp = Dispatcher()
        self.dp.include_router(router)
        self.restart_timer = RestartTimer(delay_seconds=15)

    async def start(self):
        """Основной цикл работы бота"""
        try:
            wait_for_db()
            logger.info("Бот запущен")
            await self.dp.start_polling(self.bot)
        finally:
            await self.stop()

    async def stop(self):
        """Корректное завершение работы"""
        await self.bot.session.close()
        logger.info("Бот остановлен")

def watch_files(manager):
    """Синхронный вотчер файлов в отдельном потоке"""
    for changes in watch('./app'):
        logger.info(f"Обнаружены изменения. Таймер перезапуска (15 сек) начат...")
        manager.restart_timer.change_detected()

async def restart_checker(manager):
    """Проверка необходимости перезапуска"""
    while True:
        if manager.restart_timer.event.is_set():
            if manager.restart_timer.should_restart():
                logger.info("Таймер перезапуска истек. Инициируем перезапуск...")
                os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(1)

async def main():
    while True:
        manager = BotManager()
        
        # Запускаем вотчер в отдельном потоке
        Thread(
            target=watch_files,
            args=(manager,),
            daemon=True
        ).start()
        
        # Запускаем таски
        asyncio.create_task(daily_timetable_task(manager.bot))
        asyncio.create_task(restart_checker(manager))
        
        try:
            await manager.start()
        except Exception as e:
            logger.error(f"Ошибка: {e}")
            await asyncio.sleep(5)
            continue

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Приложение завершено")
