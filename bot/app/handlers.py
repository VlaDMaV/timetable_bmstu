import os
import pytz
import httpx
import logging
import asyncio
from html import escape
from math import ceil
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from sqlalchemy import create_engine, or_
from sqlalchemy.orm import Session, sessionmaker, declarative_base

from common.database import models
from common.calendar_days import get_days_off, is_day_off
from common.semester import academic_week_number, schedule_ord_for_week, week_type_name
from config import config
import app.keyboards as kb
import app.text as cs
from app.utils.utils import format_timetable, format_teacher_timetable_simple
from app.notifications import notification_mode_label, parse_notification_time
from app.admin_auth import (
    is_admin_authenticated,
    mark_admin_authenticated,
    password_matches,
)
from app.admin_control import AdminControlError, set_admin_container_enabled
from app.utils.telegram import (
    edit_or_send_long_message,
    safe_edit_reply_markup,
    safe_edit_text,
    split_message_text,
)



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = Router()

TEACHERS_PER_PAGE = 5
GROUPS_PER_PAGE = 6
GROUP_SELECTION_TEXT = "Выберите факультет или введите название группы:"
DEGREE_MAX_COURSES = {
    "b": 4,  # бакалавриат
    "m": 2,  # магистратура
    "a": 4,  # аспирантура
    "s": 6,  # специалитет
    "p": 6,  # пилотные программы (срок обучения указан после "/")
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
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def department_display_ru(dep: str) -> str:
    """
    uik1 -> ИК1
    mk2  -> МК2
    """
    s = (dep or "").lower().strip()
    if s.startswith("uik"):
        return "ИУК" + s[3:]
    if s.startswith("mk"):
        return "МК" + s[2:]
    return dep.upper()


def get_department_from_group(name: str) -> str | None:
    try:
        s = (name or "").lower().strip()
        left = s.split("-")[0]   # "uik2" / "mk3" / "uik6"
        return left if left else None
    except Exception:
        return None


def normalize_group_search(value: str) -> str:
    """Приводит пользовательский ввод и имя группы к одному формату поиска."""
    normalized = (value or "").lower().strip().replace(" ", "")
    normalized = normalized.replace("—", "-").replace("–", "-")

    if normalized.startswith("иук"):
        normalized = "uik" + normalized[3:]
    elif normalized.startswith("уик"):
        normalized = "uik" + normalized[3:]
    elif normalized.startswith("мк"):
        normalized = "mk" + normalized[2:]

    return normalized.translate(str.maketrans({"б": "b", "м": "m", "а": "a"}))


def filter_groups_by_search(groups, query: str):
    needle = normalize_group_search(query)
    if not needle:
        return []

    result = []
    for group in groups:
        stored_name = normalize_group_search(group.name)
        display_name = normalize_group_search(cs.group_display_name(group.name))
        if needle in stored_name or needle in display_name:
            result.append(group)
    return result
    

@router.callback_query(F.data.startswith("choose_department:"))
async def choose_department(callback: CallbackQuery, db: Session):
    _, faculty, degree, course_str, department = callback.data.split(":")
    course = int(course_str)
    department = department.lower()

    groups_all = db.query(models.Group).order_by(models.Group.name).all()

    # сначала фильтр по faculty/degree/course
    groups = filter_groups(groups_all, faculty, degree, course)

    # потом добиваем кафедрой (часть до "-")
    groups = [g for g in groups if (get_department_from_group(g.name) == department)]

    if not groups:
        await callback.message.edit_text(
            "❌ Групп для этой кафедры не найдено.",
            reply_markup=get_department_keyboard(faculty, degree, course, [department])
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        f"Выберите группу ({department_display_ru(department)}, {course} курс):",
        reply_markup=get_group_keyboard(groups, faculty, degree, course, department, page=0)
    )
    await callback.answer()


def get_department_keyboard(faculty: str, degree: str, course: int, departments: list[str]):
    kb = InlineKeyboardBuilder()

    departments = sorted(set(departments))

    for dep in departments:
        kb.button(
            text=department_display_ru(dep),
            callback_data=f"choose_department:{faculty}:{degree}:{course}:{dep}"
        )

    kb.adjust(2)

    kb.button(text="⬅️ Назад", callback_data=f"back_to_course:{faculty}:{degree}")
    kb.button(text="🔙 В меню", callback_data="back_to_main")
    kb.adjust(2)

    return kb.as_markup()


def get_faculty_keyboard(include_group_search: bool = True):
    kb = InlineKeyboardBuilder()
    kb.button(text="💻 ИУК", callback_data="choose_faculty:uik")
    kb.button(text="🛠️ МК", callback_data="choose_faculty:mk")
    kb.adjust(2)
    if include_group_search:
        kb.button(text="🔎 Ввести название группы", callback_data="search_group")
        kb.adjust(1)
    kb.button(text="🔙 В меню", callback_data="back_to_main")
    kb.adjust(1)
    return kb.as_markup()


def get_degree_keyboard(faculty_code: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="👨‍🎓 Бакалавриат", callback_data=f"choose_degree:{faculty_code}:b")
    kb.button(text="👩‍🎓 Магистратура", callback_data=f"choose_degree:{faculty_code}:m")
    kb.button(text="👨‍🏫 Аспирантура", callback_data=f"choose_degree:{faculty_code}:a")
    kb.button(text="🎓 Специалитет", callback_data=f"choose_degree:{faculty_code}:s")
    kb.button(text="✈️ Пилот", callback_data=f"choose_degree:{faculty_code}:p")
    kb.adjust(1)
    kb.button(text="⬅️ Назад", callback_data="back_to_faculty")
    kb.button(text="🔙 В меню", callback_data="back_to_main")
    kb.adjust(2)
    return kb.as_markup()


def calc_course_basic_first_digit(name: str) -> int | None:
    """
    Общая логика (как у бакалавриата):
    берём первую цифру после '-'
    """
    try:
        name = name.lower().strip()
        after_dash = name.split("-")[1]   # например "62b" или "21" или "101"
        first_digit = int(after_dash[0])  # 6 / 2 / 1

        if first_digit % 2 == 0:
            return first_digit // 2
        else:
            return (first_digit - 1) // 2 + 1
    except Exception:
        return None


def calc_course_specialist(name: str) -> int | None:
    """
    Специалитет:
    - если после '-' число 101 -> 5 курс
    - если 121..129 -> 6 курс
    - иначе (первые 4 курса) считаем как у бакалавриата (по первой цифре после '-')
    """
    try:
        s = name.lower().strip()
        after_dash = s.split("-")[1]  # "21" / "101" / "121" / "62b"(но у спец без буквы)
        # на всякий случай уберём буквы, если вдруг попадутся
        num_str = "".join(ch for ch in after_dash if ch.isdigit())
        if not num_str:
            return None

        n = int(num_str)

        if n == 101:
            return 5
        if 121 <= n <= 129:
            return 6

        # первые 1-4 курса — как у бакалавриата
        return calc_course_basic_first_digit(s)

    except Exception:
        return None


def get_pilot_duration(name: str) -> int | None:
    """Возвращает срок пилотной программы из суффикса группы: uik2-62/6 -> 6."""
    try:
        _, separator, duration = (name or "").lower().strip().rpartition("/")
        if not separator or not duration.isdigit():
            return None

        duration_years = int(duration)
        return duration_years if duration_years in (5, 6) else None
    except Exception:
        return None


def calc_course_pilot(name: str) -> int | None:
    """Считает курс по части имени до суффикса срока обучения."""
    base_name, separator, _ = (name or "").lower().strip().rpartition("/")
    if not separator:
        return None
    return calc_course_specialist(base_name)


def calc_course_from_group(name: str, degree: str) -> int | None:
    degree = degree.lower()
    if degree == "s":
        return calc_course_specialist(name)
    if degree == "p":
        return calc_course_pilot(name)
    # b/m/a
    return calc_course_basic_first_digit(name)


def filter_groups(groups, faculty: str, degree: str, course: int | None = None):
    faculty = faculty.lower()
    degree = degree.lower()

    res = []
    for g in groups:
        name = (g.name or "").lower().strip()

        # 1) факультет
        if not name.startswith(faculty):
            continue

        # 2) уровень
        if degree in ("b", "m", "a"):
            if not name.endswith(degree):
                continue
        elif degree == "s":
            # специалитет: без суффикса b/m/a и без пилотного "/5" или "/6"
            if name.endswith(("b", "m", "a")) or "/" in name:
                continue
        elif degree == "p":
            # пилот: срок обучения хранится после "/", например uik2-62/6
            if get_pilot_duration(name) is None:
                continue
        else:
            continue

        # 3) курс
        if course is not None:
            group_course = calc_course_from_group(name, degree)
            if group_course != course:
                continue
            if degree == "p" and course > get_pilot_duration(name):
                continue

        res.append(g)

    return res


@router.callback_query(F.data.startswith("back_to_course:"))
async def back_to_course(callback: CallbackQuery):
    _, faculty, degree = callback.data.split(":")
    await callback.message.edit_text(
        "Выберите курс:",
        reply_markup=get_course_keyboard(faculty, degree)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("back_to_departments:"))
async def back_to_departments(callback: CallbackQuery, db: Session):
    _, faculty, degree, course_str = callback.data.split(":")
    course = int(course_str)

    groups_all = db.query(models.Group).order_by(models.Group.name).all()

    groups = filter_groups(groups_all, faculty, degree, course)

    deps = []
    for g in groups:
        dep = get_department_from_group(g.name)
        if dep:
            deps.append(dep)

    await callback.message.edit_text(
        "Выберите кафедру:",
        reply_markup=get_department_keyboard(faculty, degree, course, deps)
    )
    await callback.answer()


def get_group_keyboard(groups, faculty: str, degree: str, course: int, department: str, page: int = 0):
    kb = InlineKeyboardBuilder()

    start = page * GROUPS_PER_PAGE
    end = start + GROUPS_PER_PAGE
    page_groups = groups[start:end]

    for g in page_groups:
        kb.button(
            text=cs.group_display_name(g.name),
            callback_data=f"choose_group:{g.id}"
        )
    kb.adjust(2)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(("⬅️ Назад", f"group_page:{faculty}:{degree}:{course}:{department}:{page-1}"))
    if end < len(groups):
        nav_buttons.append(("Вперёд ➡️", f"group_page:{faculty}:{degree}:{course}:{department}:{page+1}"))

    if nav_buttons:
        for text, data in nav_buttons:
            kb.button(text=text, callback_data=data)
        kb.adjust(len(nav_buttons))

    kb.button(text="⬅️ Назад", callback_data=f"back_to_departments:{faculty}:{degree}:{course}")
    kb.button(text="🔙 В меню", callback_data="back_to_main")
    kb.adjust(2)

    return kb.as_markup()


def get_group_search_keyboard(groups, page: int = 0):
    kb = InlineKeyboardBuilder()

    start = page * GROUPS_PER_PAGE
    end = start + GROUPS_PER_PAGE
    for group in groups[start:end]:
        kb.button(
            text=cs.group_display_name(group.name),
            callback_data=f"choose_group:{group.id}",
        )
    kb.adjust(2)

    navigation = []
    if page > 0:
        navigation.append(("⬅️ Назад", f"group_search_page:{page - 1}"))
    if end < len(groups):
        navigation.append(("Вперёд ➡️", f"group_search_page:{page + 1}"))
    for text, callback_data in navigation:
        kb.button(text=text, callback_data=callback_data)
    if navigation:
        kb.adjust(len(navigation))

    kb.button(text="🔎 Новый поиск", callback_data="search_group")
    kb.button(text="⬅️ К выбору факультета", callback_data="back_to_faculty")
    kb.adjust(1)
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
async def back_to_faculty(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        GROUP_SELECTION_TEXT,
        reply_markup=get_faculty_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("choose_faculty:"))
async def choose_faculty(callback: CallbackQuery, state: FSMContext):
    await state.clear()
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
async def choose_course(callback: CallbackQuery, db: Session):
    _, faculty, degree, course_str = callback.data.split(":")
    course = int(course_str)

    groups_all = db.query(models.Group).order_by(models.Group.name).all()

    # фильтруем по факультету+уровню+курсу (кафедру пока не учитываем)
    groups = filter_groups(groups_all, faculty, degree, course)

    if not groups:
        await safe_edit_text(
            callback.message,
            "❌ Групп для этого курса не найдено.",
            reply_markup=get_course_keyboard(faculty, degree)
        )
        await callback.answer()
        return

    # собираем доступные кафедры из найденных групп
    deps = []
    for g in groups:
        dep = get_department_from_group(g.name)
        if dep:
            deps.append(dep)

    if not deps:
        await safe_edit_text(
            callback.message,
            "❌ Кафедры не найдены (не могу разобрать названия групп).",
            reply_markup=get_course_keyboard(faculty, degree)
        )
        await callback.answer()
        return

    await safe_edit_text(
        callback.message,
        "Выберите кафедру:",
        reply_markup=get_department_keyboard(faculty, degree, course, deps)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("group_page:"))
async def paginate_groups(callback: CallbackQuery, db: Session):
    _, faculty, degree, course_str, department, page_str = callback.data.split(":")
    course = int(course_str)
    page = int(page_str)
    department = department.lower()

    groups_all = db.query(models.Group).order_by(models.Group.name).all()

    groups = filter_groups(groups_all, faculty, degree, course)
    groups = [g for g in groups if (get_department_from_group(g.name) == department)]

    await safe_edit_reply_markup(
        callback.message,
        reply_markup=get_group_keyboard(groups, faculty, degree, course, department, page=page)
    )
    await callback.answer()


def get_teacher_keyboard(
    teachers,
    page: int = 0,
    include_search: bool = True,
    page_callback_prefix: str = "teacher_page",
):
    kb = InlineKeyboardBuilder()

    start = page * TEACHERS_PER_PAGE
    end = start + TEACHERS_PER_PAGE
    page_teachers = teachers[start:end]

    for t in page_teachers:
        kb.button(text=t.full_name, callback_data=f"teacher:{t.id}")
    kb.adjust(1)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(("⬅️ Назад", f"{page_callback_prefix}:{page-1}"))
    if end < len(teachers):
        nav_buttons.append(("Вперёд ➡️", f"{page_callback_prefix}:{page+1}"))

    if nav_buttons:
        for text, data in nav_buttons:
            kb.button(text=text, callback_data=data)
        kb.adjust(len(nav_buttons))

    if include_search:
        kb.button(text="🔎 Поиск по ФИО или предмету", callback_data="search_teacher")
        kb.adjust(1)
    else:
        kb.button(text="⬅️ К списку преподавателей", callback_data="teacher_timetable")
        kb.adjust(1)

    kb.button(text="🔙 В меню", callback_data="back_to_main")
    kb.adjust(1)

    return kb.as_markup()


class BroadcastStates(StatesGroup):
    waiting_for_group_ids = State()
    waiting_for_message = State()


class BroadcastAllStates(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirmation = State()


class GroupSearchStates(StatesGroup):
    waiting_for_query = State()


class TeacherSearchStates(StatesGroup):
    waiting_for_query = State()


class NotificationStates(StatesGroup):
    waiting_for_time = State()


class FeedbackStates(StatesGroup):
    waiting_for_text = State()


class FeedbackReplyStates(StatesGroup):
    waiting_for_text = State()


class AdminStates(StatesGroup):
    waiting_for_password = State()
    authenticated = State()


ADMIN_MENU_TEXT = (
    "🔐 <b>Админ-меню</b>\n\n"
    "Выберите действие:"
)


async def _open_admin_menu(message, state: FSMContext, *, edit: bool = False) -> None:
    await state.clear()
    await state.set_state(AdminStates.authenticated)
    await mark_admin_authenticated(state)
    if edit:
        await safe_edit_text(
            message,
            ADMIN_MENU_TEXT,
            parse_mode="HTML",
            reply_markup=kb.admin_menu_keyboard(),
        )
    else:
        await message.answer(
            ADMIN_MENU_TEXT,
            parse_mode="HTML",
            reply_markup=kb.admin_menu_keyboard(),
        )


async def _require_admin_session(event, state: FSMContext) -> bool:
    user_id = event.from_user.id
    if user_id != config.admin_id:
        if isinstance(event, CallbackQuery):
            await event.answer("У вас нет прав администратора.", show_alert=True)
        else:
            await event.answer("У вас нет прав для выполнения этой команды.")
        return False
    if not await is_admin_authenticated(state, user_id, config.admin_id):
        text = "Сначала выполните /admin и введите пароль."
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        else:
            await event.answer(text)
        return False
    return True


@router.message(Command("admin"))
async def admin_login(message: Message, state: FSMContext):
    if message.chat.type != "private":
        await message.answer("Команда /admin доступна только в личном чате с ботом.")
        return
    if message.from_user.id != config.admin_id:
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    await state.clear()
    await state.set_state(AdminStates.waiting_for_password)
    await state.update_data(admin_password_attempts=0)
    await message.answer(
        "🔐 Введите пароль администратора:",
        reply_markup=kb.back_to_main,
    )


@router.message(
    AdminStates.waiting_for_password,
    F.text,
    ~F.text.startswith("/"),
)
async def admin_password_input(message: Message, state: FSMContext):
    if message.from_user.id != config.admin_id or message.chat.type != "private":
        await state.clear()
        await message.answer("У вас нет прав для выполнения этой команды.")
        return

    provided_password = message.text
    try:
        await message.delete()
    except Exception:
        logger.debug("Не удалось удалить сообщение с паролем администратора")

    expected_password = config.admin_password.get_secret_value()
    if not password_matches(provided_password, expected_password):
        data = await state.get_data()
        attempts = int(data.get("admin_password_attempts", 0)) + 1
        if attempts >= 3:
            await state.clear()
            await message.answer(
                "❌ Неверный пароль. Вход отменён после трёх попыток.",
                reply_markup=kb.back_to_main,
            )
            return
        await state.update_data(admin_password_attempts=attempts)
        await message.answer(
            f"❌ Неверный пароль. Осталось попыток: {3 - attempts}.",
            reply_markup=kb.back_to_main,
        )
        return

    await _open_admin_menu(message, state)


@router.callback_query(F.data == "admin_menu")
async def admin_menu(callback: CallbackQuery, state: FSMContext):
    if not await _require_admin_session(callback, state):
        return
    await callback.answer()
    await _open_admin_menu(callback.message, state, edit=True)


@router.callback_query(F.data == "admin_logout")
async def admin_logout(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.admin_id:
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return
    await callback.answer("Вы вышли из админ-меню")
    await state.clear()
    await safe_edit_text(
        callback.message,
        cs.welcome_text,
        parse_mode="HTML",
        reply_markup=kb.main_menu,
    )


async def _set_admin_container(
    event: Message | CallbackQuery,
    state: FSMContext,
    *,
    enabled: bool,
) -> None:
    if not await _require_admin_session(event, state):
        return

    message = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(event, CallbackQuery):
        await event.answer("Выполняю…")

    if enabled and not config.admin_public_url:
        await message.answer(
            "❌ В .env не задана переменная ADMIN_PUBLIC_URL.",
            reply_markup=kb.admin_menu_keyboard(),
        )
        return

    try:
        result = await set_admin_container_enabled(enabled)
    except AdminControlError as exc:
        logger.error("Не удалось изменить состояние контейнера admin: %s", exc)
        await message.answer(
            f"❌ Не удалось {'включить' if enabled else 'выключить'} веб-админку.",
            reply_markup=kb.admin_menu_keyboard(),
        )
        return

    if enabled:
        status_text = "включена" if result.get("changed") else "уже была включена"
        safe_url = escape(config.admin_public_url, quote=True)
        text = (
            f"✅ Веб-админка {status_text}.\n\n"
            "🔗 Ссылка на админку:\n"
            f'<a href="{safe_url}">{safe_url}</a>'
        )
        hostname = (urlsplit(config.admin_public_url).hostname or "").lower()
        button_url = (
            None
            if hostname in {"localhost", "127.0.0.1", "::1"}
            else config.admin_public_url
        )
        reply_markup = kb.admin_enabled_keyboard(button_url)
    else:
        status_text = "выключена" if result.get("changed") else "уже была выключена"
        text = f"✅ Веб-админка {status_text}."
        reply_markup = kb.admin_menu_keyboard()

    try:
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
    except TelegramBadRequest:
        logger.warning("Telegram отклонил оформление ответа о веб-админке")
        fallback_text = (
            f"✅ Веб-админка {status_text}.\n\n"
            f"🔗 Ссылка на админку:\n{config.admin_public_url}"
            if enabled
            else text
        )
        await message.answer(
            fallback_text,
            reply_markup=kb.admin_menu_keyboard(),
        )


@router.message(Command("admin_on"))
async def admin_container_on_command(message: Message, state: FSMContext):
    await _set_admin_container(message, state, enabled=True)


@router.message(Command("admin_off"))
async def admin_container_off_command(message: Message, state: FSMContext):
    await _set_admin_container(message, state, enabled=False)


@router.callback_query(F.data == "admin_container_on")
async def admin_container_on_callback(callback: CallbackQuery, state: FSMContext):
    await _set_admin_container(callback, state, enabled=True)


@router.callback_query(F.data == "admin_container_off")
async def admin_container_off_callback(callback: CallbackQuery, state: FSMContext):
    await _set_admin_container(callback, state, enabled=False)


def find_teachers(db: Session, query: str):
    """Ищет преподавателей по части ФИО или названию связанного предмета."""
    query = (query or "").strip()
    if not query:
        return []

    pattern = f"%{query}%"
    return (
        db.query(models.Teacher)
        .outerjoin(models.Dayboard, models.Dayboard.teacher_id == models.Teacher.id)
        .outerjoin(models.Subject, models.Subject.id == models.Dayboard.subject_id)
        .filter(
            models.Teacher.full_name != "Не указан",
            or_(
                models.Teacher.full_name.ilike(pattern),
                models.Subject.name.ilike(pattern),
            ),
        )
        .distinct()
        .order_by(models.Teacher.full_name)
        .all()
    )


@router.callback_query(F.data == "search_group")
async def start_group_search(callback: CallbackQuery, state: FSMContext):
    await state.set_state(GroupSearchStates.waiting_for_query)
    await state.update_data(group_search_query=None)
    await callback.message.edit_text(
        "Введите полное название группы или его часть.\n"
        "Например: <code>ИУК6-11/5</code>, <code>uik6</code> или <code>62б</code>.",
        parse_mode="HTML",
        reply_markup=get_faculty_keyboard(include_group_search=False),
    )
    await callback.answer()


@router.message(GroupSearchStates.waiting_for_query, F.text, ~F.text.startswith("/"))
async def search_group_by_name(message: Message, state: FSMContext, db: Session):
    query = message.text.strip()
    if not query:
        await message.answer("Введите хотя бы один символ названия группы.")
        return

    groups_all = db.query(models.Group).order_by(models.Group.name).all()
    groups = filter_groups_by_search(groups_all, query)

    if not groups:
        await message.answer(
            f"По запросу <b>{escape(query)}</b> группы не найдены. Попробуйте ввести другое название.",
            parse_mode="HTML",
            reply_markup=get_faculty_keyboard(include_group_search=False),
        )
        return

    await state.update_data(group_search_query=query)
    await message.answer(
        f"Найдено групп: <b>{len(groups)}</b>. Выберите нужную:",
        parse_mode="HTML",
        reply_markup=get_group_search_keyboard(groups, page=0),
    )


@router.callback_query(F.data.startswith("group_search_page:"))
async def paginate_group_search(callback: CallbackQuery, state: FSMContext, db: Session):
    page = int(callback.data.split(":")[1])
    query = (await state.get_data()).get("group_search_query")
    if not query:
        await callback.answer("Поиск устарел. Введите название группы заново.", show_alert=True)
        return

    groups_all = db.query(models.Group).order_by(models.Group.name).all()
    groups = filter_groups_by_search(groups_all, query)

    max_page = max(0, ceil(len(groups) / GROUPS_PER_PAGE) - 1)
    page = min(max(page, 0), max_page)
    await safe_edit_reply_markup(
        callback.message,
        reply_markup=get_group_search_keyboard(groups, page=page)
    )
    await callback.answer()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, db: Session):
    await state.clear()
    
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
async def help_menu(callback: CallbackQuery, state: FSMContext, db: Session):
    await callback.answer()
    await state.clear()
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


@router.callback_query(F.data == "send_idea")
async def start_idea_input(callback: CallbackQuery, state: FSMContext):
    if callback.message.chat.type != "private":
        await callback.answer(
            "Идеи и предложения можно отправить только в личном чате с ботом.",
            show_alert=True,
        )
        return

    await callback.answer()
    await state.clear()
    await state.set_state(FeedbackStates.waiting_for_text)
    await safe_edit_text(
        callback.message,
        "💡 <b>Идеи и предложения</b>\n\n"
        "Напишите одним сообщением, что хотелось бы добавить или улучшить. "
        "Я передам текст администратору вместе со ссылкой на ваш профиль.",
        parse_mode="HTML",
        reply_markup=kb.idea_input_keyboard(),
    )


def _format_idea_for_admin(message: Message) -> str:
    author_id = message.from_user.id
    author_name = escape(message.from_user.full_name or f"Пользователь {author_id}")
    author_link = f'<a href="tg://user?id={author_id}">{author_name}</a>'
    username = message.from_user.username
    username_line = f"\nUsername: @{escape(username)}" if username else ""
    idea_text = escape(message.text.strip())
    return (
        "💡 <b>Новая идея или предложение</b>\n\n"
        f"От: {author_link}{username_line}\n"
        f"ID: <code>{author_id}</code>\n\n"
        f"{idea_text}"
    )


@router.message(FeedbackStates.waiting_for_text, F.text, ~F.text.startswith("/"))
async def submit_idea(message: Message, state: FSMContext):
    idea_text = message.text.strip()
    if not idea_text:
        await message.answer(
            "Сообщение не может быть пустым. Напишите идею текстом.",
            reply_markup=kb.idea_input_keyboard(),
        )
        return
    if len(idea_text) > 3500:
        await message.answer(
            f"Сообщение слишком длинное: {len(idea_text)} символов. Максимум — 3500.",
            reply_markup=kb.idea_input_keyboard(),
        )
        return

    try:
        await message.bot.send_message(
            config.admin_id,
            _format_idea_for_admin(message),
            parse_mode="HTML",
            reply_markup=kb.admin_idea_reply_keyboard(message.from_user.id),
        )
    except Exception as exc:
        logger.exception("Не удалось передать идею администратору: %s", exc)
        await message.answer(
            "Не удалось отправить сообщение администратору. Попробуйте ещё раз позже.",
            reply_markup=kb.idea_input_keyboard(),
        )
        return

    await state.clear()
    await message.answer(
        "✅ Спасибо! Идея отправлена администратору.",
        reply_markup=kb.idea_input_keyboard(),
    )


async def _finish_feedback_reply_state(state: FSMContext) -> None:
    was_admin_authenticated = bool(
        (await state.get_data()).get("feedback_admin_was_authenticated")
    )
    await state.clear()
    if was_admin_authenticated:
        await state.set_state(AdminStates.authenticated)
        await mark_admin_authenticated(state)


@router.callback_query(F.data.startswith("feedback_reply:"))
async def start_feedback_reply(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.admin_id:
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return

    try:
        recipient_id = int(callback.data.split(":", 1)[1])
    except (TypeError, ValueError):
        await callback.answer("Некорректный получатель.", show_alert=True)
        return

    was_admin_authenticated = await is_admin_authenticated(
        state,
        callback.from_user.id,
        config.admin_id,
    )
    await state.clear()
    await state.set_state(FeedbackReplyStates.waiting_for_text)
    await state.update_data(
        feedback_recipient_id=recipient_id,
        feedback_admin_was_authenticated=was_admin_authenticated,
    )
    await callback.answer()
    await callback.message.answer(
        "↩️ Введите ответ автору идеи одним сообщением:",
        reply_markup=kb.admin_idea_reply_cancel_keyboard(),
    )


@router.callback_query(
    FeedbackReplyStates.waiting_for_text,
    F.data == "feedback_reply_cancel",
)
async def cancel_feedback_reply(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != config.admin_id:
        await callback.answer("У вас нет прав администратора.", show_alert=True)
        return
    await callback.answer("Ответ отменён")
    await _finish_feedback_reply_state(state)
    await safe_edit_text(
        callback.message,
        "❌ Ответ отменён.",
        reply_markup=kb.feedback_main_menu_keyboard(),
    )


@router.callback_query(F.data == "feedback_main_menu")
async def feedback_main_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        cs.welcome_text,
        parse_mode="HTML",
        reply_markup=kb.main_menu,
    )


@router.message(
    FeedbackReplyStates.waiting_for_text,
    F.text,
    ~F.text.startswith("/"),
)
async def submit_feedback_reply(message: Message, state: FSMContext):
    if message.from_user.id != config.admin_id:
        await state.clear()
        await message.answer("У вас нет прав администратора.")
        return

    reply_text = message.text.strip()
    if not reply_text:
        await message.answer(
            "Ответ не может быть пустым.",
            reply_markup=kb.admin_idea_reply_cancel_keyboard(),
        )
        return
    if len(reply_text) > 3500:
        await message.answer(
            f"Ответ слишком длинный: {len(reply_text)} символов. Максимум — 3500.",
            reply_markup=kb.admin_idea_reply_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    recipient_id = data.get("feedback_recipient_id")
    if not isinstance(recipient_id, int):
        await _finish_feedback_reply_state(state)
        await message.answer("Получатель не найден. Нажмите «Ответить» ещё раз.")
        return

    try:
        await message.bot.send_message(
            recipient_id,
            "💬 Ответ администратора на вашу идею:\n\n" + reply_text,
            reply_markup=kb.feedback_main_menu_keyboard(),
        )
    except Exception as exc:
        logger.exception("Не удалось отправить ответ автору идеи %s: %s", recipient_id, exc)
        await message.answer(
            "❌ Не удалось доставить ответ. Возможно, пользователь заблокировал бота.",
            reply_markup=kb.admin_idea_reply_cancel_keyboard(),
        )
        return

    await _finish_feedback_reply_state(state)
    await message.answer(
        "✅ Ответ отправлен пользователю.",
        reply_markup=kb.feedback_main_menu_keyboard(),
    )


@router.callback_query(F.data == "subscribe")
async def subscribe_user(callback: CallbackQuery, db: Session):
    await callback.answer()
    user = db.query(models.User).filter(models.User.tg_id == callback.message.chat.id).first()
    if user:
        user.is_active = 1
        db.commit()
        await safe_edit_text(
            callback.message,
            "Вы подписаны на рассылку ✅",
            reply_markup=kb.podpis_button_off,
        )
    else:
        await callback.message.edit_text("Вы не зарегистрированы в боте.", parse_mode="HTML", reply_markup=kb.back_to_main)


@router.callback_query(F.data == "unsubscribe")
async def unsubscribe_user(callback: CallbackQuery, db: Session):
    if callback.message.chat.type != "private":
        await callback.answer("❌ Отписка доступна только в личных сообщениях с ботом.\nЕсли вы хотите отписать группу от рассылки, напишите @vladmav_11.", show_alert=True)
        return

    await callback.answer()
    user = db.query(models.User).filter(models.User.tg_id == callback.message.chat.id).first()
    if user:
        user.is_active = 0
        db.commit()
        await safe_edit_text(
            callback.message,
            "Вы отписаны от рассылки 🛑",
            reply_markup=kb.podpis_button_on,
        )
    else:
        await callback.message.edit_text("Вы не зарегистрированы в боте.", parse_mode="HTML", reply_markup=kb.back_to_main)


def _notification_settings_text(user: models.User) -> str:
    mode = user.notification_mode or "same_day"
    mode_text = notification_mode_label(mode)
    if mode == "hour_before":
        value_text = mode_text
    else:
        configured_time = user.notification_time.strftime("%H:%M") if user.notification_time else "08:00"
        value_text = f"{mode_text}, в {configured_time}"
    return (
        "⏰ <b>Время оповещения</b>\n\n"
        f"Сейчас: <b>{value_text}</b>.\n"
        "Когда присылать расписание?"
    )


async def _get_subscribed_private_user(callback: CallbackQuery, db: Session):
    if callback.message.chat.type != "private":
        await callback.answer(
            "Настройка времени доступна только в личных сообщениях с ботом.",
            show_alert=True,
        )
        return None
    user = db.query(models.User).filter(models.User.tg_id == callback.message.chat.id).first()
    if not user or not user.is_active:
        await callback.answer("Сначала подпишитесь на рассылку.", show_alert=True)
        return None
    return user


@router.callback_query(F.data == "notification_settings")
async def notification_settings(callback: CallbackQuery, state: FSMContext, db: Session):
    user = await _get_subscribed_private_user(callback, db)
    if not user:
        return
    await callback.answer()
    await state.clear()
    await safe_edit_text(
        callback.message,
        _notification_settings_text(user),
        parse_mode="HTML",
        reply_markup=kb.notification_settings_keyboard(),
    )


@router.callback_query(F.data == "notification_choose_time")
async def notification_choose_time(callback: CallbackQuery, state: FSMContext, db: Session):
    user = await _get_subscribed_private_user(callback, db)
    if not user:
        return
    await callback.answer()
    await state.clear()
    await safe_edit_text(
        callback.message,
        "Выберите, для какого дня задаётся время оповещения:",
        reply_markup=kb.notification_day_keyboard(),
    )


@router.callback_query(F.data == "notification_mode:hour_before")
async def notification_hour_before(callback: CallbackQuery, state: FSMContext, db: Session):
    user = await _get_subscribed_private_user(callback, db)
    if not user:
        return
    user.notification_mode = "hour_before"
    user.last_notification_date = None
    db.commit()
    await callback.answer("Настройка сохранена")
    await state.clear()
    await safe_edit_text(
        callback.message,
        _notification_settings_text(user),
        parse_mode="HTML",
        reply_markup=kb.notification_settings_keyboard(),
    )


@router.callback_query(F.data.startswith("notification_timing:"))
async def notification_timing(callback: CallbackQuery, state: FSMContext, db: Session):
    user = await _get_subscribed_private_user(callback, db)
    if not user:
        return
    mode = callback.data.split(":", 1)[1]
    if mode not in ("same_day", "day_before"):
        await callback.answer("Неизвестный режим", show_alert=True)
        return
    await callback.answer()
    timing_text = "за день до занятий" if mode == "day_before" else "в день занятий"
    await state.set_state(NotificationStates.waiting_for_time)
    await state.update_data(notification_mode=mode)
    await safe_edit_text(
        callback.message,
        f"Выбрано: <b>{timing_text}</b>.\n\n"
        "Введите время в формате <b>ЧЧ:ММ</b>.\n"
        "Например: <code>08:30</code>.",
        parse_mode="HTML",
        reply_markup=kb.notification_time_keyboard(),
    )


@router.message(NotificationStates.waiting_for_time, F.text, ~F.text.startswith("/"))
async def notification_time_input(message: Message, state: FSMContext, db: Session):
    mode = (await state.get_data()).get("notification_mode")
    if mode not in ("same_day", "day_before"):
        await state.clear()
        await message.answer("Настройка устарела. Откройте её заново.", reply_markup=kb.back_to_main)
        return

    raw_time = message.text.strip()
    parsed_time = parse_notification_time(raw_time)
    if parsed_time is None:
        await message.answer(
            "Некорректное время. Введите его в формате <b>ЧЧ:ММ</b>, например <code>08:30</code>.",
            parse_mode="HTML",
            reply_markup=kb.notification_time_keyboard(),
        )
        return

    user = db.query(models.User).filter(models.User.tg_id == message.chat.id).first()
    if not user or not user.is_active:
        await state.clear()
        await message.answer("Сначала подпишитесь на рассылку.", reply_markup=kb.podpis_button_on)
        return

    user.notification_mode = mode
    user.notification_time = parsed_time
    user.last_notification_date = None
    db.commit()
    await state.clear()
    await message.answer(
        "✅ Настройка сохранена.\n\n" + _notification_settings_text(user),
        parse_mode="HTML",
        reply_markup=kb.notification_settings_keyboard(),
    )


@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.edit_text(
        text=cs.welcome_text,
        parse_mode="HTML",
        reply_markup=kb.main_menu
    )


@router.callback_query(F.data.startswith("choose_group:"))
async def choose_group(callback: CallbackQuery, state: FSMContext, db: Session):
    group_id = int(callback.data.split(":")[1])

    chosen_group = db.query(models.Group).filter(models.Group.id == group_id).first()
    if not chosen_group:
        await callback.answer("❌ Группа не найдена", show_alert=True)
        return

    await state.clear()

    if callback.message.chat.type in ("group", "supergroup"):
        user_group = db.query(models.User).filter(models.User.tg_id == callback.message.chat.id).first()
        if user_group:
            user_group.group_id = chosen_group.id
            db.commit()
            await callback.message.edit_text(
                f"✅ Для группы <b>{user_group.title}</b> выбрана учебная группа <b>{cs.group_display_name(chosen_group.name)}</b>",
                parse_mode="HTML",
                reply_markup=kb.back_to_main
            )
    else:
        user = db.query(models.User).filter(models.User.tg_id == callback.from_user.id).first()
        if user:
            user.group_id = chosen_group.id
            db.commit()
            await callback.message.edit_text(
                f"✅ Ваша учебная группа сохранена: <b>{cs.group_display_name(chosen_group.name)}</b>",
                parse_mode="HTML",
                reply_markup=kb.back_to_main
            )

    await callback.answer()


@router.callback_query(F.data.startswith("timetable"))
async def get_today_timetable(callback: CallbackQuery, db: Session):
    await callback.answer()

    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)
    year, week_number, weekday = now.isocalendar()
    week_ord = schedule_ord_for_week(week_number)

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
        await callback.message.edit_text(
            "Ваша группа не выбрана. Сначала выберите группу.",
            parse_mode="HTML",
            reply_markup=get_faculty_keyboard(),
        )
        return

    current_group_name = chat_record.group_rel.name
    group_display_name = cs.group_display_name(current_group_name)
    day_off_dates = {now.date()} if is_day_off(db, now.date()) else set()

    data = []
    if not day_off_dates:
        base_url = "http://backend:8000/dayboard/filter"
        params = {
            "ord": week_ord,
            "day": week_day,
            "group": current_group_name,
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

    timetable_text = format_timetable(
        data,
        include_empty_days=True,
        day_dates={week_day: now.date()},
        days=[week_day],
        day_off_dates=day_off_dates,
    )

    await edit_or_send_long_message(
        callback.message,
        f"Расписание на сегодня:\n\n{timetable_text}"
        f"Группа: <b>{group_display_name}</b>\n"
        f"{academic_week_number(week_number)} неделя: {week_type_name(week_number)}",
        parse_mode="HTML",
        reply_markup=kb.back_to_main
    )


@router.callback_query(F.data.startswith("tomorrow_timetable"))
async def get_tomorrow_timetable(callback: CallbackQuery, db: Session):
    await callback.answer()

    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)
    tomorrow = (now + timedelta(days=1)).date()
    year, week_number, weekday = tomorrow.isocalendar()

    week_day = cs.WEEKDAYS.get(weekday) 
    week_ord = schedule_ord_for_week(week_number)

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
        await callback.message.edit_text(
            "Ваша группа не выбрана. Сначала выберите группу.",
            parse_mode="HTML",
            reply_markup=get_faculty_keyboard(),
        )
        return

    current_group_name = chat_record.group_rel.name
    group_display_name = cs.group_display_name(current_group_name)
    day_off_dates = {tomorrow} if is_day_off(db, tomorrow) else set()

    data = []
    if not day_off_dates:
        base_url = "http://backend:8000/dayboard/filter"
        params = {
            "ord": week_ord,
            "day": week_day,
            "group": current_group_name,
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

    timetable_text = format_timetable(
        data,
        include_empty_days=True,
        day_dates={week_day: tomorrow},
        days=[week_day],
        day_off_dates=day_off_dates,
    )

    await edit_or_send_long_message(
        callback.message,
        f"Расписание на завтра:\n\n{timetable_text}"
        f"Группа: <b>{group_display_name}</b>\n"
        f"{academic_week_number(week_number)} неделя: {week_type_name(week_number)}",
        parse_mode="HTML",
        reply_markup=kb.back_to_main
    )


@router.callback_query(F.data.startswith("weekly_timetable"))
async def get_weekly_timetable(callback: CallbackQuery, db: Session):
    await callback.answer()

    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)
    year, week_number, weekday = now.isocalendar()
    week_ord = schedule_ord_for_week(week_number)
    week_start = now.date() - timedelta(days=weekday - 1)
    week_days = cs.DAY_ORDER[:6]
    day_dates = {
        day: week_start + timedelta(days=index)
        for index, day in enumerate(week_days)
    }

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
        await callback.message.edit_text(
            "Ваша группа не выбрана. Сначала выберите группу.",
            parse_mode="HTML",
            reply_markup=get_faculty_keyboard(),
        )
        return

    current_group_name = chat_record.group_rel.name
    group_display_name = cs.group_display_name(current_group_name)
    day_off_dates = get_days_off(
        db,
        week_start,
        week_start + timedelta(days=len(week_days) - 1),
    )

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

    timetable_text = format_timetable(
        data,
        include_empty_days=True,
        day_dates=day_dates,
        days=week_days,
        day_off_dates=day_off_dates,
    )

    await edit_or_send_long_message(
        callback.message,
        f"Расписание на неделю:\n\n{timetable_text}"
        f"Группа: <b>{group_display_name}</b>\n"
        f"{academic_week_number(week_number)} неделя: {week_type_name(week_number)}",
        parse_mode="HTML",
        reply_markup=kb.next_week
    )


@router.callback_query(F.data.startswith("next_week"))
async def get_weekly_timetable(callback: CallbackQuery, db: Session):
    await callback.answer()

    moscow_tz = pytz.timezone("Europe/Moscow")
    now = datetime.now(moscow_tz)
    year, week_number, weekday = now.isocalendar()
    target_week_number = week_number + 1
    week_ord = schedule_ord_for_week(target_week_number)
    week_start = now.date() - timedelta(days=weekday - 1) + timedelta(weeks=1)
    week_days = cs.DAY_ORDER[:6]
    day_dates = {
        day: week_start + timedelta(days=index)
        for index, day in enumerate(week_days)
    }

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
        await callback.message.edit_text(
            "Ваша группа не выбрана. Сначала выберите группу.",
            parse_mode="HTML",
            reply_markup=get_faculty_keyboard(),
        )
        return

    current_group_name = chat_record.group_rel.name
    group_display_name = cs.group_display_name(current_group_name)
    day_off_dates = get_days_off(
        db,
        week_start,
        week_start + timedelta(days=len(week_days) - 1),
    )

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

    timetable_text = format_timetable(
        data,
        include_empty_days=True,
        day_dates=day_dates,
        days=week_days,
        day_off_dates=day_off_dates,
    )

    await edit_or_send_long_message(
        callback.message,
        f"Расписание на неделю:\n\n{timetable_text}"
        f"Группа: <b>{group_display_name}</b>\n"
        f"{academic_week_number(target_week_number)} неделя: {week_type_name(target_week_number)}",
        parse_mode="HTML",
        reply_markup=kb.prev_week
    )


@router.callback_query(F.data.startswith("current_lesson"))
async def current_lesson(callback: CallbackQuery, db: Session):
    await callback.answer()

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
    if weekday_index == 7 or is_day_off(db, now.date()):
        await callback.message.edit_text(
            "Сегодня выходной! 💤",
            parse_mode="HTML",
            reply_markup=kb.back_to_main
        )
        return

    day_name = cs.WEEKDAYS.get(weekday_index, "Monday")

    week_ord = schedule_ord_for_week(now.isocalendar()[1])

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
async def change_group(callback: CallbackQuery, state: FSMContext, db: Session):
    if callback.message.chat.type != "private":
        await callback.answer("❌ Смена группы доступна только в личных сообщениях с ботом.\nЕсли вы хотите сменить группу от рассылки, напишите @vladmav_11.", show_alert=True)
        return

    await callback.answer()
    await state.clear()

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

    await callback.message.edit_text(
        f"Текущая группа: <b>{cs.group_display_name(current_group_name)}</b>\n"
        f"{GROUP_SELECTION_TEXT}",
        parse_mode="HTML",
        reply_markup=get_faculty_keyboard(),
    )


async def _begin_broadcast(message: Message, state: FSMContext, db: Session) -> None:
    groups = db.query(models.Group).all()

    text = "Список групп:\n"
    for g in groups:
        text += f"{g.id} — {g.name}\n"

    text += "\nВведи ID групп через запятую:"
    chunks = split_message_text(text)
    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk,
            reply_markup=kb.admin_back_keyboard() if index == len(chunks) - 1 else None,
        )
    await state.set_state(BroadcastStates.waiting_for_group_ids)


@router.message(Command("broadcast"))
async def cmd_broadcast(message: Message, state: FSMContext, db: Session):
    if not await _require_admin_session(message, state):
        return
    await _begin_broadcast(message, state, db)


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext, db: Session):
    if not await _require_admin_session(callback, state):
        return
    await callback.answer()
    await _begin_broadcast(callback.message, state, db)


@router.message(BroadcastStates.waiting_for_group_ids)
async def get_group_ids(message: Message, state: FSMContext):
    if not await _require_admin_session(message, state):
        return
    try:
        ids = [int(x.strip()) for x in message.text.split(",")]
    except ValueError:
        await message.answer(
            "Ошибка: введи ID через запятую (например: 1,2,3)",
            reply_markup=kb.admin_back_keyboard(),
        )
        return

    await state.update_data(group_ids=ids)
    await message.answer("Теперь введи сообщение для рассылки:")
    await state.set_state(BroadcastStates.waiting_for_message)


@router.message(BroadcastStates.waiting_for_message)
async def get_broadcast_message(message: Message, state: FSMContext, db: Session):
    if not await _require_admin_session(message, state):
        return
    data = await state.get_data()
    group_ids = data["group_ids"]
    text = message.text

    user_ids = [
        tg_id
        for (tg_id,) in db.query(models.User.tg_id)
        .filter(models.User.group_id.in_(group_ids))
        .all()
    ]

    sent_count = 0
    for tg_id in user_ids:
        try:
            await message.bot.send_message(tg_id, text)
            sent_count += 1
        except Exception as e:
            logger.warning("Не удалось отправить %s: %s", tg_id, e)

    await state.clear()
    await state.set_state(AdminStates.authenticated)
    await mark_admin_authenticated(state)
    await message.answer(
        f"Рассылка завершена ✅ Отправлено {sent_count} пользователям.",
        reply_markup=kb.admin_menu_keyboard(),
    )


def get_broadcast_all_user_ids(db: Session) -> list[int]:
    """Возвращает личные чаты всех пользователей, запускавших бота."""
    return [
        tg_id
        for (tg_id,) in db.query(models.User.tg_id)
        .filter(models.User.title == "private", models.User.tg_id > 0)
        .order_by(models.User.id)
        .all()
    ]


async def _begin_broadcast_all(message: Message, state: FSMContext, db: Session) -> None:
    recipients_count = len(get_broadcast_all_user_ids(db))
    await message.answer(
        "📢 <b>Рассылка всем пользователям</b>\n\n"
        f"Получателей: <b>{recipients_count}</b>.\n"
        "Отправьте сообщение с HTML-разметкой. Например:\n\n"
        "<code>&lt;b&gt;Важная новость&lt;/b&gt;\n"
        "Обычный текст и &lt;i&gt;курсив&lt;/i&gt;\n"
        "&lt;a href=&quot;https://example.com&quot;&gt;Ссылка&lt;/a&gt;</code>\n\n"
        "Поддерживаются теги Telegram: <code>b</code>, <code>i</code>, "
        "<code>u</code>, <code>s</code>, <code>a</code>, <code>code</code>, "
        "<code>pre</code>. Максимум 4000 символов.",
        parse_mode="HTML",
        reply_markup=kb.admin_back_keyboard(),
    )
    await state.set_state(BroadcastAllStates.waiting_for_message)


@router.message(Command("broadcast_all"))
async def cmd_broadcast_all(message: Message, state: FSMContext, db: Session):
    if not await _require_admin_session(message, state):
        return
    await _begin_broadcast_all(message, state, db)


@router.callback_query(F.data == "admin_broadcast_all")
async def admin_broadcast_all(callback: CallbackQuery, state: FSMContext, db: Session):
    if not await _require_admin_session(callback, state):
        return
    await callback.answer()
    await _begin_broadcast_all(callback.message, state, db)


@router.message(BroadcastAllStates.waiting_for_message, F.text)
async def get_broadcast_all_message(message: Message, state: FSMContext):
    if not await _require_admin_session(message, state):
        return

    text = message.text.strip()
    if not text:
        await message.answer("Сообщение не может быть пустым.")
        return
    if len(text) > 4000:
        await message.answer(
            f"Сообщение слишком длинное: {len(text)} символов. Максимум — 4000.",
            reply_markup=kb.admin_back_keyboard(),
        )
        return

    try:
        await message.answer("👁 <b>Предпросмотр сообщения:</b>", parse_mode="HTML")
        await message.answer(text, parse_mode="HTML")
    except TelegramBadRequest as exc:
        logger.info("Некорректная HTML-разметка общей рассылки: %s", exc)
        await message.answer(
            "❌ Telegram не смог разобрать HTML-разметку. Исправьте теги и "
            "отправьте сообщение ещё раз.",
            reply_markup=kb.admin_back_keyboard(),
        )
        return

    await state.update_data(broadcast_all_text=text)
    await state.set_state(BroadcastAllStates.waiting_for_confirmation)
    await message.answer(
        "Отправить это сообщение всем личным пользователям бота?",
        reply_markup=kb.admin_broadcast_all_confirm_keyboard(),
    )


@router.callback_query(
    BroadcastAllStates.waiting_for_confirmation,
    F.data == "admin_broadcast_all_cancel",
)
async def cancel_broadcast_all(callback: CallbackQuery, state: FSMContext):
    if not await _require_admin_session(callback, state):
        return
    await callback.answer("Рассылка отменена")
    await _open_admin_menu(callback.message, state, edit=True)


@router.callback_query(
    BroadcastAllStates.waiting_for_confirmation,
    F.data == "admin_broadcast_all_confirm",
)
async def confirm_broadcast_all(
    callback: CallbackQuery,
    state: FSMContext,
    db: Session,
):
    if not await _require_admin_session(callback, state):
        return

    data = await state.get_data()
    text = data.get("broadcast_all_text")
    if not text:
        await callback.answer("Текст рассылки не найден. Начните заново.", show_alert=True)
        await _open_admin_menu(callback.message, state, edit=True)
        return

    # Убираем состояние подтверждения до начала отправки, чтобы повторное нажатие
    # на кнопку не запустило вторую такую же массовую рассылку.
    await state.set_state(AdminStates.authenticated)
    await callback.answer("Рассылка запущена")
    await safe_edit_text(
        callback.message,
        "⏳ Отправляю сообщение всем пользователям…",
        reply_markup=None,
    )

    user_ids = get_broadcast_all_user_ids(db)
    sent_count = 0
    failed_count = 0
    for tg_id in user_ids:
        try:
            await callback.bot.send_message(tg_id, text, parse_mode="HTML")
            sent_count += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await callback.bot.send_message(tg_id, text, parse_mode="HTML")
                sent_count += 1
            except Exception as retry_exc:
                failed_count += 1
                logger.warning("Не удалось повторно отправить %s: %s", tg_id, retry_exc)
        except Exception as exc:
            failed_count += 1
            logger.warning("Не удалось отправить общую рассылку %s: %s", tg_id, exc)

    await state.clear()
    await state.set_state(AdminStates.authenticated)
    await mark_admin_authenticated(state)
    await callback.message.answer(
        "Рассылка завершена ✅\n"
        f"Отправлено: {sent_count}\n"
        f"Не доставлено: {failed_count}",
        reply_markup=kb.admin_menu_keyboard(),
    )


@router.callback_query(F.data == "teacher_timetable")
async def teacher_timetable(callback: CallbackQuery, state: FSMContext, db: Session):
    if callback.message.chat.type != "private":
        await callback.answer("❌ Доступно только в личных сообщениях.", show_alert=True)
        return

    await callback.answer()
    await state.clear()
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


@router.callback_query(F.data == "search_teacher")
async def start_teacher_search(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TeacherSearchStates.waiting_for_query)
    await state.update_data(teacher_search_query=None)
    await callback.message.edit_text(
        "Введите часть ФИО преподавателя или название предмета.\n"
        "Например: <code>Иванов</code> или <code>математика</code>.",
        parse_mode="HTML",
        reply_markup=get_teacher_keyboard([], include_search=False),
    )
    await callback.answer()


@router.message(TeacherSearchStates.waiting_for_query, F.text, ~F.text.startswith("/"))
async def search_teacher_by_name_or_subject(message: Message, state: FSMContext, db: Session):
    query = message.text.strip()
    if not query:
        await message.answer("Введите хотя бы один символ ФИО или названия предмета.")
        return

    teachers = find_teachers(db, query)
    if not teachers:
        await message.answer(
            f"По запросу <b>{escape(query)}</b> преподаватели не найдены. "
            "Попробуйте другой запрос.",
            parse_mode="HTML",
            reply_markup=get_teacher_keyboard([], include_search=False),
        )
        return

    await state.update_data(teacher_search_query=query)
    await message.answer(
        f"Найдено преподавателей: <b>{len(teachers)}</b>. Выберите нужного:",
        parse_mode="HTML",
        reply_markup=get_teacher_keyboard(
            teachers,
            page=0,
            include_search=False,
            page_callback_prefix="teacher_search_page",
        ),
    )


@router.callback_query(F.data.startswith("teacher_search_page:"))
async def paginate_teacher_search(callback: CallbackQuery, state: FSMContext, db: Session):
    page = int(callback.data.split(":")[1])
    query = (await state.get_data()).get("teacher_search_query")
    if not query:
        await callback.answer("Поиск устарел. Введите запрос заново.", show_alert=True)
        return

    teachers = find_teachers(db, query)
    max_page = max(0, ceil(len(teachers) / TEACHERS_PER_PAGE) - 1)
    page = min(max(page, 0), max_page)
    await safe_edit_reply_markup(
        callback.message,
        reply_markup=get_teacher_keyboard(
            teachers,
            page=page,
            include_search=False,
            page_callback_prefix="teacher_search_page",
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("teacher_page:"))
async def paginate_teachers(callback: CallbackQuery, db: Session):
    await callback.answer()
    page = int(callback.data.split(":")[1])

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
async def show_teacher_timetable(callback: CallbackQuery, db: Session):
    teacher_id = int(callback.data.split(":")[1])

    teacher = db.query(models.Teacher).filter(models.Teacher.id == teacher_id).first()
    if not teacher:
        await callback.answer("Преподаватель не найден", show_alert=True)
        return

    await callback.answer()
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
    moscow_now = datetime.now(pytz.timezone("Europe/Moscow"))
    current_week_type = week_type_name(moscow_now.isocalendar().week)

    await edit_or_send_long_message(
        callback.message,
        f"<b>{teacher.full_name}</b>\n\n{timetable_text}"
        f"\n\nСейчас: <b>{current_week_type}</b>",
        parse_mode="HTML",
        reply_markup=kb.back_to_main
    )
