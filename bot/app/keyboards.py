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
    [InlineKeyboardButton(text='📋 Расписание по преподователям', callback_data='teacher_timetable')]
])


back_to_main = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
])


podpis_button_off = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🛑 Отписаться", callback_data="unsubscribe"),
        InlineKeyboardButton(text="🔄 Сменить группу", callback_data="change_group")
    ],
    [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
])


podpis_button_on = InlineKeyboardMarkup(inline_keyboard=[
    [
        InlineKeyboardButton(text="🟢 Подписаться", callback_data="subscribe"),
        InlineKeyboardButton(text="🔄 Сменить группу", callback_data="change_group")  
    ],
    [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")],
])
