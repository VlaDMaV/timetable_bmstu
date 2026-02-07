import os
import pytz
import httpx
import logging
import asyncio
from math import ceil
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from common.database import models
from config import config
import app.keyboards as kb
import app.text as cs
from app.utils.utils import format_timetable, format_teacher_timetable_simple



# Поменял для чётного семестра -6 и !=, в случае нечётного -35 и == у timetable, weekly_timetable, tomorrow_timetable, next_week и всех остальных



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

TEACHERS_PER_PAGE = 5
GROUPS_PER_PAGE = 6
DEGREE_MAX_COURSES = {
    "b": 4,  # бакалавриат
    "m": 2,  # магистратура
    "a": 4,  # аспирантура
}

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_NAME = os.getenv("DB_NAME", "timetable")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=60,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_faculty_keyboard():
    kb = InlineKeyboardBuilder()
    kb.button(text="💻 ИУК", callback_data="choose_faculty:uik")
    kb.button(text="🛠️ МК", callback_data="choose_faculty:mk")
    kb.adjust(2)
    kb.button(text="🔙 В меню", callback_data="back_to_main")
    kb.adjust(1)
    return kb.as_markup()


def get_degree_keyboard(faculty_code: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="👨‍🎓 Бакалавриат", callback_data=f"choose_degree:{faculty_code}:b")
    kb.button(text="👩‍🎓 Магистратура", callback_data=f"choose_degree:{faculty_code}:m")
    kb.button(text="👨‍🏫 Аспирантура", callback_data=f"choose_degree:{faculty_code}:a")
    kb.adjust(1)
    kb.button(text="⬅️ Назад", callback_data="back_to_faculty")
    kb.button(text="🔙 В меню", callback_data="back_to_main")
    kb.adjust(2)
    return kb.as_markup()


def calc_course_from_group(name: str) -> int | None:
    try:
        name = name.lower()

        # берём часть между '-' и последней буквой
        after_dash = name.split("-")[1]

        # первая цифра после '-'
        first_digit = int(after_dash[0])

        # если чётная — делим на 2
        if first_digit % 2 == 0:
            return first_digit // 2
        else:
            # если нечётная — (n - 1) / 2 + 1
            return (first_digit - 1) // 2 + 1

    except Exception:
        return None

def filter_groups(groups, faculty: str, degree: str, course: int | None = None):
    faculty = faculty.lower()
    degree = degree.lower()

    res = []
    for g in groups:
        name = (g.name or "").lower().strip()

        # 1. факультет (uik / mk)
        if not name.startswith(faculty):
            continue

        # 2. уровень (b / m / a)
        if not name.endswith(degree):
            continue

        # 3. курс (если задан)
        if course is not None:
            group_course = calc_course_from_group(name)
            if group_course != course:
                continue

        res.append(g)

    return res


def get_group_keyboard(groups, faculty: str, degree_letter: str, page: int = 0):
    kb = InlineKeyboardBuilder()

    start = page * GROUPS_PER_PAGE
    end = start + GROUPS_PER_PAGE
    page_groups = groups[start:end]

    for g in page_groups:
        kb.button(
            text=cs.groups.get(g.name, g.name),
            callback_data=f"choose_group:{g.id}"
        )
    kb.adjust(2)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(("⬅️ Назад", f"group_page:{faculty}:{degree_letter}:{page-1}"))
    if end < len(groups):
        nav_buttons.append(("Вперёд ➡️", f"group_page:{faculty}:{degree_letter}:{page+1}"))

    if nav_buttons:
        for text, data in nav_buttons:
            kb.button(text=text, callback_data=data)
        kb.adjust(len(nav_buttons))

    kb.button(text="⬅️ Назад", callback_data=f"back_to_degree:{faculty}")
    kb.button(text="🔙 В меню", callback_data="back_to_main")
    kb.adjust(2)

    return kb.as_markup()


def get_course_keyboard(faculty: str, degree: str):
    kb = InlineKeyboardBuilder()

    max_course = DEGREE_MAX_COURSES[degree]

    for course in range(1, max_course + 1):
        kb.button(
            text=f"{course} курс",
            callback_data=f"choose_course:{faculty}:{degree}:{course}"
        )

    kb.adjust(2)

    kb.button(text="⬅️ Назад", callback_data=f"back_to_degree:{faculty}")
    kb.button(text="🔙 В меню", callback_data="back_to_main")
    kb.adjust(2)

    return kb.as_markup()


@router.callback_query(F.data == "back_to_faculty")
async def back_to_faculty(callback: CallbackQuery):
    await callback.message.edit_text(
        "Выберите факультет:",
        reply_markup=get_faculty_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("choose_faculty:"))
async def choose_faculty(callback: CallbackQuery):
    faculty = callback.data.split(":")[1]
    await callback.message.edit_text(
        "Выберите уровень обучения:",
        reply_markup=get_degree_keyboard(faculty)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("back_to_degree:"))
async def back_to_degree(callback: CallbackQuery):
    faculty = callback.data.split(":")[1]
    await callback.message.edit_text(
        "Выберите уровень обучения:",
        reply_markup=get_degree_keyboard(faculty)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("choose_degree:"))
async def choose_degree(callback: CallbackQuery):
    _, faculty, degree = callback.data.split(":")

    await callback.message.edit_text(
        "Выберите курс:",
        reply_markup=get_course_keyboard(faculty, degree)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("choose_course:"))
async def choose_course(callback: CallbackQuery):
    _, faculty, degree, course_str = callback.data.split(":")
    course = int(course_str)

    with next(get_db()) as db:
        groups_all = db.query(models.Group).order_by(models.Group.name).all()

    groups = filter_groups(groups_all, faculty, degree, course)

    if not groups:
        await callback.message.edit_text(
            "❌ Групп для этого курса не найдено.",
            reply_markup=get_course_keyboard(faculty, degree)
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"Выберите группу ({course} курс):",
        reply_markup=get_group_keyboard(groups, faculty, degree, page=0)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("group_page:"))
async def paginate_groups(callback: CallbackQuery):
    _, faculty, degree_letter, page_str = callback.data.split(":")
    page = int(page_str)

    with next(get_db()) as db:
        groups_all = db.query(models.Group).order_by(models.Group.name).all()

    groups = filter_groups(groups_all, faculty, degree_letter)

    await callback.message.edit_reply_markup(
        reply_markup=get_group_keyboard(groups, faculty, degree_letter, page=page)
    )
    await callback.answer()


def get_teacher_keyboard(teachers, page: int = 0):
    kb = InlineKeyboardBuilder()

    start = page * TEACHERS_PER_PAGE
    end = start + TEACHERS_PER_PAGE
    page_teachers = teachers[start:end]

    for t in page_teachers:
        kb.button(text=t.full_name, callback_data=f"teacher:{t.id}")
    kb.adjust(1)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(("⬅️ Назад", f"teacher_page:{page-1}"))
    if end < len(teachers):
        nav_buttons.append(("Вперёд ➡️", f"teacher_page:{page+1}"))

    if nav_buttons:
        for text, data in nav_buttons:
            kb.button(text=text, callback_data=data)
        kb.adjust(len(nav_buttons))

    kb.button(text="🔙 В меню", callback_data="back_to_main")
    kb.adjust(1)

    return kb.as_markup()


class BroadcastStates(StatesGroup):
    waiting_for_group_ids = State()
    waiting_for_message = State()


@router.message(CommandStart())
async def start(message: Message):
    db = next(get_db())
    
    tg_id = message.from_user.id
    chat_type = message.chat.type
    title = chat_type or "Без названия"
    username = message.from_user.username or f"user_{tg_id}"

    if chat_type in ("group", "supergroup"):
        group_user = db.query(models.User).filter(models.User.tg_id == message.chat.id).first()
        if not group_user:

            new_group_user = models.User(
                tg_id=message.chat.id,
                username=username,
                title=title,
                group_id=None,
                is_active=0
            )
            db.add(new_group_user)
            db.commit()
            db.refresh(new_group_user)

            with next(get_db()) as db:
                groups = db.query(models.Group).order_by(models.Group.name).all()

            await message.answer(
                text=cs.reg_text.format(title=username),
                reply_markup=get_faculty_keyboard(),
                parse_mode="HTML"
            )
            return
        
        await message.answer(
            text=cs.welcome_text,
            parse_mode="HTML",
            reply_markup=kb.main_menu
        )

    else:
        user = db.query(models.User).filter(models.User.tg_id == tg_id).first()

        if not user:
            new_user = models.User(
                tg_id=tg_id,
                username=username,
                title=title,
                group_id=None,
                is_active=0
            )
            db.add(new_user)
            db.commit()
            db.refresh(new_user)

            with next(get_db()) as db:
                groups = db.query(models.Group).order_by(models.Group.name).all()

            await message.answer(
                text=cs.reg_text.format(title=username),
                reply_markup=get_faculty_keyboard(),
            )
            return

        await message.answer(
            text=cs.welcome_text,
            parse_mode="HTML",
            reply_markup=kb.main_menu
        )


@router.callback_query(F.data == "help")
async def help_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.tg_id == callback.message.chat.id).first()

        if user and user.is_active:
            podpis_text = "🛑 отписаться от"
            reply_markup = kb.podpis_button_off
        else:
            podpis_text = "🟢 подписаться на"
            reply_markup = kb.podpis_button_on 

        await callback.message.edit_text(
            text=cs.help_text.format(podpis=podpis_text),
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    finally:
        db.close()


@router.callback_query(F.data == "subscribe")
async def subscribe_user(callback: CallbackQuery):
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.tg_id == callback.message.chat.id).first()
        if user:
            user.is_active = 1  
            db.commit()
            await callback.message.edit_text(
                "Вы подписаны на рассылку ✅",
                reply_markup=kb.podpis_button_off
            )
        else:
            await callback.message.edit_text("Вы не зарегистрированы в боте.", parse_mode="HTML", reply_markup=kb.back_to_main)
    finally:
        db.close()


@router.callback_query(F.data == "unsubscribe")
async def unsubscribe_user(callback: CallbackQuery):
    if callback.message.chat.type != "private":
        await callback.answer("❌ Отписка доступна только в личных сообщениях с ботом.\nЕсли вы хотите отписать группу от рассылки, напишите @vladmav_11.", show_alert=True)
        return

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.tg_id == callback.message.chat.id).first()
        if user:
            user.is_active = 0
            db.commit()
            await callback.message.edit_text(
                "Вы отписаны от рассылки 🛑",
                
                reply_markup=kb.podpis_button_on
            )
        else:
            await callback.message.edit_text("Вы не зарегистрированы в боте.", parse_mode="HTML", reply_markup=kb.back_to_main)
    finally:
        db.close()


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        text=cs.welcome_text, 
        parse_mode="HTML",
        reply_markup=kb.main_menu
    )


@router.callback_query(F.data.startswith("choose_group:"))
async def choose_group(callback: CallbackQuery):
    db = next(get_db())
    group_id = int(callback.data.split(":")[1])

    chosen_group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not chosen_group:
        await callback.answer("❌ Группа не найдена", show_alert=True)
        return

    if callback.message.chat.type in ("group", "supergroup"):
        user_group = db.query(models.User).filter(models.User.tg_id == callback.message.chat.id).first()
        if user_group:
            user_group.group_id = chosen_group.id
            db.commit()
            await callback.message.edit_text(
                f"✅ Для группы <b>{user_group.title}</b> выбрана учебная группа <b>{cs.groups.get(chosen_group.name, chosen_group.name)}</b>",
                parse_mode="HTML",
                reply_markup=kb.back_to_main
            )
    else:
        user = db.query(models.User).filter(models.User.tg_id == callback.from_user.id).first()
        if user:
            user.group_id = chosen_group.id
            db.commit()
            await callback.message.edit_text(
                f"✅ Ваша учебная группа сохранена: <b>{cs.groups.get(chosen_group.name, chosen_group.name)}</b>",
                parse_mode="HTML",
                reply_markup=kb.back_to_main
            )

    await callback.answer()


@router.callback_query(F.data.startswith("timetable"))
async def get_today_timetable(callback: CallbackQuery):
    db = next(get_db())

    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)
    year, week_number, weekday = now.isocalendar()
    week_ord = (week_number + 1) % 2

    if weekday == 7:
        await callback.message.edit_text(
            f"Сегодня выходной! 💤",
            parse_mode="HTML",
            reply_markup=kb.back_to_main
        )
        return

    week_day = cs.WEEKDAYS.get(weekday)

    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    chat_title = callback.message.chat.title

    chat_record = db.query(models.User).filter(models.User.tg_id == chat_id).first()

    if not chat_record:
        await callback.message.edit_text(
            f"Этот чат не найден в базе.\nЧат: {chat_title} ({chat_type})",
            parse_mode="HTML",
            reply_markup=kb.back_to_main
        )
        return

    if not chat_record.group_rel:
        with next(get_db()) as db:
            groups = db.query(models.Group).order_by(models.Group.name).all()

        await callback.message.edit_text(
            "Ваша группа не выбрана. Сначала выберите группу.",
            parse_mode="HTML",
            reply_markup=get_faculty_keyboard(),
        )
        return

    current_group_name = chat_record.group_rel.name
    group_display_name = cs.groups.get(current_group_name, current_group_name)

    base_url = "http://backend:8000/dayboard/filter"
    params = {
        "ord": week_ord,
        "day": week_day,
        "group": current_group_name  
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            await callback.message.edit_text(
                f"Ошибка при запросе к API:\n{e}",
                parse_mode="HTML",
                reply_markup=kb.back_to_main
            )
            return

    timetable_text = format_timetable(data)

    await callback.message.edit_text(
        f"Расписание на сегодня:\n\n{timetable_text}"
        f"Группа: <b>{group_display_name}</b>\n"
        f"{week_number-6} неделя: {'Знаменатель' if week_ord != 0 else 'Числитель'}", 
        parse_mode="HTML",
        reply_markup=kb.back_to_main
    )


@router.callback_query(F.data.startswith("tomorrow_timetable"))
async def get_tomorrow_timetable(callback: CallbackQuery):
    db = next(get_db())

    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)
    year, week_number, weekday = now.isocalendar()

    if weekday == 6: 
        await callback.message.edit_text(
            f"Завтра выходной! 💤",
            parse_mode="HTML",
            reply_markup=kb.back_to_main
        )
        return
    elif weekday == 7:
        if week_number==0:
            week_number+=1
        else:
            week_number+=1
        weekday = 1
    else:
        weekday += 1

    week_day = cs.WEEKDAYS.get(weekday) 
    week_ord = (week_number + 1) % 2

    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    chat_title = callback.message.chat.title

    chat_record = db.query(models.User).filter(models.User.tg_id == chat_id).first()
    if not chat_record:
        await callback.message.edit_text(
            f"Этот чат не найден в базе.\nЧат: {chat_title} ({chat_type})",
            parse_mode="HTML",
            reply_markup=kb.back_to_main
        )
        return

    if not chat_record.group_rel:
        with next(get_db()) as db:
            groups = db.query(models.Group).order_by(models.Group.name).all()

        await callback.message.edit_text(
            "Ваша группа не выбрана. Сначала выберите группу.",
            parse_mode="HTML",
            reply_markup=get_faculty_keyboard(),
        )
        return

    current_group_name = chat_record.group_rel.name
    group_display_name = cs.groups.get(current_group_name, current_group_name)

    base_url = "http://backend:8000/dayboard/filter"
    params = {
        "ord": week_ord,
        "day": week_day,
        "group": current_group_name
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            await callback.message.edit_text(
                f"Ошибка при запросе к API:\n{e}",
                parse_mode="HTML",
                reply_markup=kb.back_to_main
            )
            return

    timetable_text = format_timetable(data)

    await callback.message.edit_text(
        f"Расписание на завтра:\n\n{timetable_text}"
        f"Группа: <b>{group_display_name}</b>\n"
        f"{week_number-6} неделя: {'Знаменатель' if week_ord != 0 else 'Числитель'}",
        parse_mode="HTML",
        reply_markup=kb.back_to_main
    )


@router.callback_query(F.data.startswith("weekly_timetable"))
async def get_weekly_timetable(callback: CallbackQuery):
    db = next(get_db())

    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)
    year, week_number, weekday = now.isocalendar()
    week_ord = (week_number + 1) % 2

    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    chat_title = callback.message.chat.title

    chat_record = db.query(models.User).filter(models.User.tg_id == chat_id).first()
    if not chat_record:
        await callback.message.edit_text(
            f"Этот чат не найден в базе.\nЧат: {chat_title} ({chat_type})",
            parse_mode="HTML",
            reply_markup=kb.back_to_main
        )
        return

    if not chat_record.group_rel:
        with next(get_db()) as db:
            groups = db.query(models.Group).order_by(models.Group.name).all()

        await callback.message.edit_text(
            "Ваша группа не выбрана. Сначала выберите группу.",
            parse_mode="HTML",
            reply_markup=get_faculty_keyboard(),
        )
        return

    current_group_name = chat_record.group_rel.name
    group_display_name = cs.groups.get(current_group_name, current_group_name)

    base_url = "http://backend:8000/dayboard/filter"
    params = {
        "ord": week_ord,
        "group": current_group_name 
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            await callback.message.edit_text(
                f"Ошибка при запросе к API:\n{e}",
                parse_mode="HTML",
                reply_markup=kb.back_to_main
            )
            return

    timetable_text = format_timetable(data)

    await callback.message.edit_text(
        f"Расписание на неделю:\n\n{timetable_text}"
        f"Группа: <b>{group_display_name}</b>\n"
        f"{week_number-6} неделя: {'Знаменатель' if week_ord != 0 else 'Числитель'}",
        parse_mode="HTML",
        reply_markup=kb.next_week
    )


@router.callback_query(F.data.startswith("next_week"))
async def get_weekly_timetable(callback: CallbackQuery):
    db = next(get_db())

    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)
    year, week_number, weekday = now.isocalendar()
    week_ord = week_number % 2

    chat_id = callback.message.chat.id
    chat_type = callback.message.chat.type
    chat_title = callback.message.chat.title

    chat_record = db.query(models.User).filter(models.User.tg_id == chat_id).first()
    if not chat_record:
        await callback.message.edit_text(
            f"Этот чат не найден в базе.\nЧат: {chat_title} ({chat_type})",
            parse_mode="HTML",
            reply_markup=kb.back_to_main
        )
        return

    if not chat_record.group_rel:
        with next(get_db()) as db:
            groups = db.query(models.Group).order_by(models.Group.name).all()

        await callback.message.edit_text(
            "Ваша группа не выбрана. Сначала выберите группу.",
            parse_mode="HTML",
            reply_markup=get_faculty_keyboard(),
        )
        return

    current_group_name = chat_record.group_rel.name
    group_display_name = cs.groups.get(current_group_name, current_group_name)

    base_url = "http://backend:8000/dayboard/filter"
    params = {
        "ord": week_ord,
        "group": current_group_name
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            await callback.message.edit_text(
                f"Ошибка при запросе к API:\n{e}",
                parse_mode="HTML",
                reply_markup=kb.back_to_main
            )
            return

    timetable_text = format_timetable(data)

    await callback.message.edit_text(
        f"Расписание на неделю:\n\n{timetable_text}"
        f"Группа: <b>{group_display_name}</b>\n"
        f"{week_number+1-6} неделя: {'Знаменатель' if week_ord != 0 else 'Числитель'}",
        parse_mode="HTML",
        reply_markup=kb.prev_week
    )


@router.callback_query(F.data.startswith("current_lesson"))
async def current_lesson(callback: CallbackQuery):
    db = next(get_db())

    chat_id = callback.message.chat.id
    chat_record = db.query(models.User).filter(models.User.tg_id == chat_id).first()

    if not chat_record:
        await callback.message.edit_text(
            "Этот чат не найден в базе.",
            parse_mode="HTML",
            reply_markup=kb.back_to_main
        )
        return

    if not chat_record.group_rel:
        with next(get_db()) as db:
            groups = db.query(models.Group).order_by(models.Group.name).all()

        await callback.message.edit_text(
            "Ваша группа не выбрана. Сначала выберите группу.",
            parse_mode="HTML",
            reply_markup=get_faculty_keyboard(),
        )
        return

    current_group_name = chat_record.group_rel.name

    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)

    weekday_index = now.isoweekday()
    if weekday_index == 7:
        await callback.message.edit_text(
            "Сегодня выходной! 💤",
            parse_mode="HTML",
            reply_markup=kb.back_to_main
        )
        return

    day_name = cs.WEEKDAYS.get(weekday_index, "Monday")

    week_ord = (now.isocalendar()[1] + 1) % 2

    base_url = "http://backend:8000/dayboard/filter"
    params = {"ord": week_ord, "day": day_name, "group": current_group_name}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(base_url, params=params)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            await callback.message.edit_text(
                f"Ошибка при запросе к API:\n{e}",
                parse_mode="HTML",
                reply_markup=kb.back_to_main
            )
            return

    if not data:
        await callback.message.edit_text(
            "На сегодня расписание пустое.",
            parse_mode="HTML",
            reply_markup=kb.back_to_main
        )
        return

    now_time = now.time()
    current_lesson = None
    for lesson in data:
        start = datetime.strptime(lesson.get('start_time', '00:00'), "%H:%M").time()
        end = datetime.strptime(lesson.get('end_time', '00:00'), "%H:%M").time()
        if start <= now_time <= end:
            current_lesson = lesson
            break

    if current_lesson:
        text = (
            f"Текущая пара:\n\n"
            f"{current_lesson.get('start_time', '??:??')}–{current_lesson.get('end_time', '??:??')}\n"
            f"{current_lesson.get('subject_name', 'Без предмета')}\n"
            f"({current_lesson.get('type', '')})\n"
            f"Аудитория: {current_lesson.get('place', 'Не указано')}\n"
            f"Преподаватель: {current_lesson.get('teacher_name', 'Не указан')}"
        )
    else:
        text = "Сейчас пары нет. 💤"

    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb.back_to_main)


@router.callback_query(F.data.startswith("change_group"))
async def change_group(callback: CallbackQuery):
    if callback.message.chat.type != "private":
        await callback.answer("❌ Смена группы доступна только в личных сообщениях с ботом.\nЕсли вы хотите сменить группу от рассылки, напишите @vladmav_11.", show_alert=True)
        return

    db = next(get_db())

    chat_id = callback.message.chat.id
    chat_record = db.query(models.User).filter(models.User.tg_id == chat_id).first()

    if not chat_record:
        await callback.message.edit_text(
            "Этот чат не найден в базе.",
            parse_mode="HTML",
            reply_markup=kb.back_to_main
        )
        return

    current_group_name = chat_record.group_rel.name if chat_record.group_rel else "не выбрана"

    with next(get_db()) as db:
            groups = db.query(models.Group).order_by(models.Group.name).all()

    await callback.message.edit_text(
        f"Текущая группа: <b>{cs.groups.get(current_group_name, current_group_name)}</b>\nВыберите новую группу:",
        parse_mode="HTML",
        reply_markup=get_faculty_keyboard(),
    )


# Старт рассылки — показать группы
@router.message(F.text == "/broadcast")
async def cmd_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != config.admin_id:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    db = next(get_db())
    groups = db.query(models.Group).all()
    
    text = "Список групп:\n"
    for g in groups:
        text += f"{g.id} — {g.name}\n"

    text += "\nВведи ID групп через запятую:"
    await message.answer(text)
    await state.set_state(BroadcastStates.waiting_for_group_ids)


@router.message(BroadcastStates.waiting_for_group_ids)
async def get_group_ids(message: Message, state: FSMContext):
    if message.from_user.id != config.admin_id:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return
    try:
        ids = [int(x.strip()) for x in message.text.split(",")]
    except ValueError:
        await message.answer("Ошибка: введи ID через запятую (например: 1,2,3)")
        return

    await state.update_data(group_ids=ids)
    await message.answer("Теперь введи сообщение для рассылки:")
    await state.set_state(BroadcastStates.waiting_for_message)


@router.message(BroadcastStates.waiting_for_message)
async def get_broadcast_message(message: Message, state: FSMContext):
    if message.from_user.id != config.admin_id:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return
    data = await state.get_data()
    group_ids = data["group_ids"]
    text = message.text

    db = next(get_db())
    users = db.query(models.User).filter(models.User.group_id.in_(group_ids)).all()

    sent_count = 0
    for user in users:
        try:
            await message.bot.send_message(user.tg_id, text)
            sent_count += 1
        except Exception as e:
            print(f"Не удалось отправить {user.tg_id}: {e}")

    await message.answer(f"Рассылка завершена ✅ Отправлено {sent_count} пользователям.")
    await state.clear()


@router.callback_query(F.data == "teacher_timetable")
async def teacher_timetable(callback: CallbackQuery):
    if callback.message.chat.type != "private":
        await callback.answer("❌ Доступно только в личных сообщениях.", show_alert=True)
        return

    db = next(get_db())
    teachers = (
        db.query(models.Teacher)
        .filter(models.Teacher.full_name != "Не указан")
        .order_by(models.Teacher.full_name)
        .all()
    )

    if not teachers:
        await callback.message.edit_text("❌ В базе нет преподавателей.", parse_mode="HTML", reply_markup=kb.back_to_main)
        return

    await callback.message.edit_text(
        cs.teacher_text,
        parse_mode="HTML",
        reply_markup=get_teacher_keyboard(teachers, page=0)
    )


@router.callback_query(F.data.startswith("teacher_page:"))
async def paginate_teachers(callback: CallbackQuery):
    page = int(callback.data.split(":")[1])

    db = next(get_db())
    teachers = (
        db.query(models.Teacher)
        .filter(models.Teacher.full_name != "Не указан")
        .order_by(models.Teacher.full_name)
        .all()
    )

    await callback.message.edit_text(
        cs.teacher_text,
        parse_mode="HTML",
        reply_markup=get_teacher_keyboard(teachers, page=page)
    )


@router.callback_query(F.data.startswith("teacher:"))
async def show_teacher_timetable(callback: CallbackQuery):
    teacher_id = int(callback.data.split(":")[1])

    db = next(get_db())
    teacher = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()
    if not teacher:
        await callback.answer("Преподаватель не найден", show_alert=True)
        return

    base_url = f"http://backend:8000/dayboard/teacher/{teacher.full_name}"

    async with httpx.AsyncClient() as client:
        r = await client.get(base_url)

    if r.status_code != 200:
        await callback.message.edit_text(
            f"❌ Ошибка при получении расписания ({r.status_code})",
            parse_mode="HTML"
        )
        return

    timetable_data = r.json()
    timetable_text = format_teacher_timetable_simple(timetable_data)

    await callback.message.edit_text(
        f"<b>{teacher.full_name}</b>\n\n{timetable_text}",
        parse_mode="HTML",
        reply_markup=kb.back_to_main
    )
