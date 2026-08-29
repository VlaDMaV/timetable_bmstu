from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


main_menu = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text='📚 Текущая пара', callback_data='current_lesson')],
    [
        InlineKeyboardButton(text='🟢 На сегодня', callback_data='timetable'),
        InlineKeyboardButton(text='🟡 На завтра', callback_data='tomorrow_timetable')
    ],
    [
        InlineKeyboardButton(text='📅 На неделю', callback_data='weekly_timetable'),
        InlineKeyboardButton(text='📖 Настройки', callback_data='help')
    ],
    [InlineKeyboardButton(text='📋 Расписание по преподавателям', callback_data='teacher_timetable')]
])


back_to_main = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
])


podpis_button_off = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🛑 Отписаться", callback_data="unsubscribe"),
        InlineKeyboardButton(text="🔄 Сменить группу", callback_data="change_group")
    ],
    [InlineKeyboardButton(text="⏰ Время оповещения", callback_data="notification_settings")],
    [InlineKeyboardButton(text="💡 Идеи и предложения", callback_data="send_idea")],
    [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
])


podpis_button_on = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🟢 Подписаться", callback_data="subscribe"),
        InlineKeyboardButton(text="🔄 Сменить группу", callback_data="change_group")  
    ],
    [InlineKeyboardButton(text="💡 Идеи и предложения", callback_data="send_idea")],
    [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")],
])


next_week = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📚 На следующую неделю", callback_data="next_week")],
    [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")],
])


prev_week = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📚 На эту неделю", callback_data="weekly_timetable")],
    [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")],
])


def notification_settings_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⏳ За час до первой пары", callback_data="notification_mode:hour_before")
    builder.button(text="🕒 Выбрать время", callback_data="notification_choose_time")
    builder.button(text="⬅️ Назад", callback_data="help")
    builder.adjust(1)
    return builder.as_markup()


def notification_day_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🌙 За день до", callback_data="notification_timing:day_before")
    builder.button(text="☀️ В этот день", callback_data="notification_timing:same_day")
    builder.button(text="⬅️ Назад", callback_data="notification_settings")
    builder.adjust(1)
    return builder.as_markup()


def notification_time_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data="notification_choose_time")
    builder.adjust(1)
    return builder.as_markup()


def idea_input_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад в настройки", callback_data="help")
    builder.adjust(1)
    return builder.as_markup()


def admin_idea_reply_keyboard(user_id: int):
    builder = InlineKeyboardBuilder()
    builder.button(text="↩️ Ответить", callback_data=f"feedback_reply:{user_id}")
    builder.button(text="🔙 В главное меню", callback_data="feedback_main_menu")
    builder.adjust(1)
    return builder.as_markup()


def admin_idea_reply_cancel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отменить ответ", callback_data="feedback_reply_cancel")
    builder.button(text="🔙 В главное меню", callback_data="feedback_main_menu")
    builder.adjust(1)
    return builder.as_markup()


def feedback_main_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 В главное меню", callback_data="feedback_main_menu")
    builder.adjust(1)
    return builder.as_markup()


def admin_menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔎 Проверить расписания", callback_data="admin_check_schedule")
    builder.button(text="📣 Рассылка по группам", callback_data="admin_broadcast")
    builder.button(text="📢 Рассылка всем", callback_data="admin_broadcast_all")
    builder.button(text="🟢 Включить веб-админку", callback_data="admin_container_on")
    builder.button(text="🔴 Выключить веб-админку", callback_data="admin_container_off")
    builder.button(text="🚪 Выйти из админки", callback_data="admin_logout")
    builder.adjust(1)
    return builder.as_markup()


def admin_broadcast_all_confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Отправить всем", callback_data="admin_broadcast_all_confirm")
    builder.button(text="❌ Отменить", callback_data="admin_broadcast_all_cancel")
    builder.adjust(1)
    return builder.as_markup()


def admin_enabled_keyboard(url: str | None = None):
    builder = InlineKeyboardBuilder()
    if url:
        builder.button(text="🌐 Открыть админку", url=url)
    builder.button(text="🔴 Выключить веб-админку", callback_data="admin_container_off")
    builder.button(text="⬅️ В админ-меню", callback_data="admin_menu")
    builder.adjust(1)
    return builder.as_markup()


def admin_back_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ В админ-меню", callback_data="admin_menu")
    builder.button(text="🚪 Выйти из админки", callback_data="admin_logout")
    builder.adjust(1)
    return builder.as_markup()
