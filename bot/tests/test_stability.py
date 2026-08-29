import unittest
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock, patch
from types import SimpleNamespace

from aiogram.exceptions import TelegramBadRequest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.utils.utils import format_teacher_timetable_simple, format_timetable
from app.utils.telegram import (
    edit_or_send_long_message,
    safe_edit_reply_markup,
    safe_edit_text,
    split_message_text,
)
from app.handlers import (
    AdminStates,
    BroadcastAllStates,
    FeedbackReplyStates,
    FeedbackStates,
    _format_idea_for_admin,
    admin_login,
    admin_password_input,
    find_teachers,
    get_broadcast_all_message,
    get_broadcast_all_user_ids,
    get_faculty_keyboard,
    get_teacher_keyboard,
    notification_time_input,
    start_feedback_reply,
    submit_feedback_reply,
    submit_idea,
)
from config import config
from app import keyboards as bot_keyboards
from app import text as bot_text
from app.notifications import due_notification_target, parse_notification_time
from app.admin_auth import (
    ADMIN_AUTH_DATA_KEY,
    is_admin_authenticated,
    password_matches,
)
from common.calendar_days import get_days_off, is_day_off
from common.database import models
from common.database.base import Base
from common.semester import academic_week_number, schedule_ord_for_week, week_type_name
from run import (
    DatabaseSessionMiddleware,
    process_due_notifications,
    send_daily_timetable,
    send_user_schedule_notification,
)


class FakeMessage:
    def __init__(self, edit_error=None):
        self.edit_error = edit_error
        self.edited = []
        self.sent = []

    async def edit_text(self, text, **kwargs):
        if self.edit_error:
            raise self.edit_error
        self.edited.append((text, kwargs))

    async def edit_reply_markup(self, **kwargs):
        if self.edit_error:
            raise self.edit_error
        self.edited.append((None, kwargs))

    async def answer(self, text, **kwargs):
        self.sent.append((text, kwargs))


class FakeSession:
    def __init__(self):
        self.closed = False
        self.rolled_back = False

    def close(self):
        self.closed = True

    def rollback(self):
        self.rolled_back = True


class FakeState:
    def __init__(self, data=None):
        self.data = data or {}
        self.cleared = False
        self.state = None

    async def get_data(self):
        return self.data

    async def clear(self):
        self.data = {}
        self.state = None
        self.cleared = True

    async def set_state(self, state):
        self.state = state

    async def update_data(self, **kwargs):
        self.data.update(kwargs)


class FakeTextMessage:
    def __init__(self, tg_id, text):
        self.chat = SimpleNamespace(id=tg_id)
        self.text = text
        self.sent = []

    async def answer(self, text, **kwargs):
        self.sent.append((text, kwargs))


class FakeAdminMessage:
    def __init__(self, user_id, text="/admin", chat_type="private"):
        self.from_user = SimpleNamespace(id=user_id)
        self.chat = SimpleNamespace(type=chat_type)
        self.text = text
        self.sent = []
        self.deleted = False

    async def answer(self, text, **kwargs):
        self.sent.append((text, kwargs))

    async def delete(self):
        self.deleted = True


class FakeIdeaMessage:
    def __init__(self, text, user_id=321, username="idea_author"):
        self.from_user = SimpleNamespace(
            id=user_id,
            username=username,
            full_name="Иван <Иванов>",
        )
        self.chat = SimpleNamespace(id=user_id, type="private")
        self.text = text
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.sent = []

    async def answer(self, text, **kwargs):
        self.sent.append((text, kwargs))


class FakeIdeaCallback:
    def __init__(self, user_id, recipient_id):
        self.from_user = SimpleNamespace(id=user_id)
        self.data = f"feedback_reply:{recipient_id}"
        self.message = SimpleNamespace(answer=AsyncMock())
        self.answer = AsyncMock()


class TelegramUtilityTests(unittest.IsolatedAsyncioTestCase):
    def test_support_message_is_in_settings_and_footer_has_two_line_breaks(self):
        self.assertIn(bot_text.SUPPORT_CARD_NUMBER, bot_text.help_text)
        self.assertEqual(
            bot_text.append_support_footer(
                "Расписание",
                trailing_text="0 неделя: Знаменатель",
            ),
            f"Расписание\n\n{bot_text.SUPPORT_MESSAGE}\n\n0 неделя: Знаменатель",
        )

    def test_split_message_keeps_chunks_under_limit(self):
        text = ("Строка <b>предмет</b> <i>лекция</i>\n" * 500).strip()
        chunks = split_message_text(text)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 4000 for chunk in chunks))
        for chunk in chunks:
            self.assertEqual(chunk.count("<b>"), chunk.count("</b>"))
            self.assertEqual(chunk.count("<i>"), chunk.count("</i>"))

    async def test_not_modified_is_ignored(self):
        error = TelegramBadRequest(method=None, message="Bad Request: message is not modified")
        message = FakeMessage(edit_error=error)

        self.assertFalse(await safe_edit_text(message, "Без изменений"))
        self.assertFalse(await safe_edit_reply_markup(message, reply_markup=None))

    async def test_long_message_places_keyboard_on_last_chunk(self):
        message = FakeMessage()
        await edit_or_send_long_message(
            message,
            ("Строка расписания\n" * 500).strip(),
            parse_mode="HTML",
            reply_markup="keyboard",
        )

        self.assertEqual(len(message.edited), 1)
        self.assertGreater(len(message.sent), 0)
        self.assertIsNone(message.edited[0][1]["reply_markup"])
        self.assertEqual(message.sent[-1][1]["reply_markup"], "keyboard")


class AdminAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    def test_password_comparison_is_exact(self):
        self.assertTrue(password_matches("strong-password", "strong-password"))
        self.assertFalse(password_matches("strong-password ", "strong-password"))
        self.assertFalse(password_matches("", ""))

    async def test_admin_session_requires_id_and_authenticated_flag(self):
        state = FakeState({ADMIN_AUTH_DATA_KEY: True})
        self.assertTrue(await is_admin_authenticated(state, 100, 100))
        self.assertFalse(await is_admin_authenticated(state, 101, 100))
        self.assertFalse(await is_admin_authenticated(FakeState(), 100, 100))

    def test_admin_menu_contains_only_admin_actions_and_logout(self):
        callbacks = {
            button.callback_data
            for row in bot_keyboards.admin_menu_keyboard().inline_keyboard
            for button in row
        }
        self.assertEqual(
            callbacks,
            {
                "admin_check_schedule",
                "admin_broadcast",
                "admin_broadcast_all",
                "admin_container_on",
                "admin_container_off",
                "admin_logout",
            },
        )

    def test_broadcast_all_confirmation_keyboard_has_send_and_cancel(self):
        callbacks = {
            button.callback_data
            for row in bot_keyboards.admin_broadcast_all_confirm_keyboard().inline_keyboard
            for button in row
        }
        self.assertEqual(
            callbacks,
            {"admin_broadcast_all_confirm", "admin_broadcast_all_cancel"},
        )

    def test_admin_enabled_keyboard_has_visible_url_and_navigation(self):
        url = "https://example.com/secret/admin/"
        markup = bot_keyboards.admin_enabled_keyboard(url)
        buttons = [button for row in markup.inline_keyboard for button in row]

        self.assertEqual(buttons[0].url, url)
        self.assertEqual(buttons[0].text, "🌐 Открыть админку")
        self.assertEqual(
            {button.callback_data for button in buttons if button.callback_data},
            {"admin_container_off", "admin_menu"},
        )

    def test_admin_enabled_keyboard_can_omit_unsupported_local_url(self):
        markup = bot_keyboards.admin_enabled_keyboard()
        buttons = [button for row in markup.inline_keyboard for button in row]

        self.assertTrue(all(button.url is None for button in buttons))
        self.assertEqual(
            {button.callback_data for button in buttons},
            {"admin_container_off", "admin_menu"},
        )

    async def test_admin_command_requests_password_and_opens_menu(self):
        state = FakeState()
        command = FakeAdminMessage(config.admin_id)
        await admin_login(command, state)

        self.assertEqual(state.state, AdminStates.waiting_for_password)
        self.assertIn("Введите пароль", command.sent[-1][0])

        password_message = FakeAdminMessage(
            config.admin_id,
            text=config.admin_password.get_secret_value(),
        )
        await admin_password_input(password_message, state)

        self.assertTrue(password_message.deleted)
        self.assertEqual(state.state, AdminStates.authenticated)
        self.assertTrue(state.data[ADMIN_AUTH_DATA_KEY])
        self.assertIn("Админ-меню", password_message.sent[-1][0])

    async def test_three_wrong_passwords_cancel_login(self):
        state = FakeState()
        await admin_login(FakeAdminMessage(config.admin_id), state)

        last_message = None
        for _ in range(3):
            last_message = FakeAdminMessage(config.admin_id, text="wrong-password")
            await admin_password_input(last_message, state)

        self.assertIsNone(state.state)
        self.assertNotIn(ADMIN_AUTH_DATA_KEY, state.data)
        self.assertIn("трёх попыток", last_message.sent[-1][0])

    async def test_broadcast_all_message_is_previewed_as_html(self):
        state = FakeState({ADMIN_AUTH_DATA_KEY: True})
        message = FakeAdminMessage(config.admin_id, text="<b>Новость</b>")

        await get_broadcast_all_message(message, state)

        self.assertEqual(state.state, BroadcastAllStates.waiting_for_confirmation)
        self.assertEqual(state.data["broadcast_all_text"], "<b>Новость</b>")
        self.assertEqual(message.sent[1][0], "<b>Новость</b>")
        self.assertEqual(message.sent[1][1]["parse_mode"], "HTML")


class BroadcastAllRecipientsTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_includes_all_private_users_but_not_group_chats(self):
        with self.session_factory() as db:
            db.add_all([
                models.User(
                    tg_id=101,
                    username="active",
                    title="private",
                    is_active=1,
                ),
                models.User(
                    tg_id=102,
                    username="inactive",
                    title="private",
                    is_active=0,
                ),
                models.User(
                    tg_id=-103,
                    username="group",
                    title="supergroup",
                    is_active=1,
                ),
            ])
            db.commit()

            self.assertEqual(get_broadcast_all_user_ids(db), [101, 102])


class DatabaseSessionMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_is_closed_after_success(self):
        session = FakeSession()
        middleware = DatabaseSessionMiddleware(lambda: session)

        async def handler(event, data):
            self.assertIs(data["db"], session)
            return "ok"

        result = await middleware(handler, object(), {})

        self.assertEqual(result, "ok")
        self.assertTrue(session.closed)
        self.assertFalse(session.rolled_back)

    async def test_session_is_rolled_back_and_closed_after_error(self):
        session = FakeSession()
        middleware = DatabaseSessionMiddleware(lambda: session)

        async def handler(event, data):
            raise RuntimeError("test error")

        with self.assertRaisesRegex(RuntimeError, "test error"):
            await middleware(handler, object(), {})

        self.assertTrue(session.rolled_back)
        self.assertTrue(session.closed)


class GroupSelectionKeyboardTests(unittest.TestCase):
    @staticmethod
    def _callbacks(markup):
        return {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        }

    def test_search_button_is_hidden_while_bot_waits_for_group_name(self):
        regular_callbacks = self._callbacks(get_faculty_keyboard())
        waiting_callbacks = self._callbacks(
            get_faculty_keyboard(include_group_search=False)
        )

        self.assertIn("search_group", regular_callbacks)
        self.assertNotIn("search_group", waiting_callbacks)
        self.assertEqual(
            waiting_callbacks,
            {"choose_faculty:uik", "choose_faculty:mk", "back_to_main"},
        )

    def test_time_input_keyboard_contains_only_back_button(self):
        callbacks = self._callbacks(bot_keyboards.notification_time_keyboard())
        self.assertEqual(callbacks, {"notification_choose_time"})

    def test_idea_button_is_available_in_both_settings_variants(self):
        for markup in (bot_keyboards.podpis_button_off, bot_keyboards.podpis_button_on):
            self.assertIn("send_idea", self._callbacks(markup))

        active_rows = bot_keyboards.podpis_button_off.inline_keyboard
        notification_row = next(
            index
            for index, row in enumerate(active_rows)
            if row[0].callback_data == "notification_settings"
        )
        self.assertEqual(
            active_rows[notification_row + 1][0].callback_data,
            "send_idea",
        )

    def test_teacher_list_has_search_and_search_pagination_keeps_its_query(self):
        teachers = [SimpleNamespace(id=index, full_name=f"Преподаватель {index}") for index in range(7)]

        regular_callbacks = self._callbacks(get_teacher_keyboard(teachers))
        search_callbacks = self._callbacks(get_teacher_keyboard(
            teachers,
            include_search=False,
            page_callback_prefix="teacher_search_page",
        ))

        self.assertIn("search_teacher", regular_callbacks)
        self.assertIn("teacher_search_page:1", search_callbacks)
        self.assertNotIn("search_teacher", search_callbacks)
        self.assertIn("teacher_timetable", search_callbacks)


class FeedbackTests(unittest.IsolatedAsyncioTestCase):
    def test_admin_message_has_profile_link_and_escaped_text(self):
        message = FakeIdeaMessage("Добавьте <b>кнопку</b> & поиск")

        formatted = _format_idea_for_admin(message)

        self.assertIn('href="tg://user?id=321"', formatted)
        self.assertIn("Иван &lt;Иванов&gt;", formatted)
        self.assertIn("Добавьте &lt;b&gt;кнопку&lt;/b&gt; &amp; поиск", formatted)

    def test_feedback_admin_keyboards_have_main_menu_navigation(self):
        incoming_callbacks = {
            button.callback_data
            for row in bot_keyboards.admin_idea_reply_keyboard(321).inline_keyboard
            for button in row
        }
        waiting_callbacks = {
            button.callback_data
            for row in bot_keyboards.admin_idea_reply_cancel_keyboard().inline_keyboard
            for button in row
        }
        done_callbacks = {
            button.callback_data
            for row in bot_keyboards.feedback_main_menu_keyboard().inline_keyboard
            for button in row
        }

        self.assertEqual(incoming_callbacks, {"feedback_reply:321", "feedback_main_menu"})
        self.assertEqual(waiting_callbacks, {"feedback_reply_cancel", "feedback_main_menu"})
        self.assertEqual(done_callbacks, {"feedback_main_menu"})

    async def test_idea_is_sent_to_admin_and_state_is_cleared(self):
        state = FakeState()
        await state.set_state(FeedbackStates.waiting_for_text)
        message = FakeIdeaMessage("Улучшить поиск")

        await submit_idea(message, state)

        message.bot.send_message.assert_awaited_once()
        call = message.bot.send_message.await_args
        self.assertEqual(call.args[0], config.admin_id)
        self.assertEqual(call.kwargs["parse_mode"], "HTML")
        reply_button = call.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(reply_button.callback_data, "feedback_reply:321")
        self.assertIsNone(state.state)
        self.assertIn("Идея отправлена", message.sent[-1][0])

    async def test_admin_can_reply_to_idea_author(self):
        state = FakeState()
        callback = FakeIdeaCallback(config.admin_id, recipient_id=321)

        await start_feedback_reply(callback, state)

        self.assertEqual(state.state, FeedbackReplyStates.waiting_for_text)
        self.assertEqual(state.data["feedback_recipient_id"], 321)

        message = FakeIdeaMessage("Спасибо за идею", user_id=config.admin_id)
        await submit_feedback_reply(message, state)

        message.bot.send_message.assert_awaited_once()
        call = message.bot.send_message.await_args
        self.assertEqual(call.args[:2], (
            321,
            "💬 Ответ администратора на вашу идею:\n\nСпасибо за идею",
        ))
        recipient_button = call.kwargs["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(recipient_button.callback_data, "feedback_main_menu")
        self.assertIsNone(state.state)
        self.assertIn("Ответ отправлен", message.sent[-1][0])
        done_button = message.sent[-1][1]["reply_markup"].inline_keyboard[0][0]
        self.assertEqual(done_button.callback_data, "feedback_main_menu")

    async def test_non_admin_cannot_start_feedback_reply(self):
        state = FakeState()
        callback = FakeIdeaCallback(config.admin_id + 1, recipient_id=321)

        await start_feedback_reply(callback, state)

        self.assertIsNone(state.state)
        callback.answer.assert_awaited_once_with(
            "У вас нет прав администратора.",
            show_alert=True,
        )

class TeacherSearchTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_finds_teacher_by_full_name_or_subject(self):
        with self.session_factory() as db:
            group = models.Group(name="TEST-TEACHER-SEARCH")
            subject = models.Subject(name="Высшая математика")
            teacher = models.Teacher(full_name="Иванов Иван Иванович")
            place = models.Place(name="Аудитория поиска")
            lesson_type = models.Type(name="Лекция поиска")
            slot = models.TimeSlot(start_time="08:30", end_time="10:05")
            day = models.Day(name="Monday", ord=0)
            db.add_all([group, subject, teacher, place, lesson_type, slot, day])
            db.flush()
            db.add(models.Dayboard(
                subject_id=subject.id,
                group_id=group.id,
                teacher_id=teacher.id,
                time_id=slot.id,
                day_id=day.id,
                place_id=place.id,
                type_id=lesson_type.id,
                podgroup=0,
            ))
            db.commit()

            self.assertEqual(find_teachers(db, "Иванов"), [teacher])
            self.assertEqual(find_teachers(db, "математика"), [teacher])
            self.assertEqual(find_teachers(db, "химия"), [])

    def test_teacher_schedule_labels_match_current_week_logic(self):
        timetable = format_teacher_timetable_simple([
            {
                "ord": 0,
                "day_name": "Monday",
                "start_time": "08:30",
                "end_time": "10:05",
                "subject_name": "Математика",
                "place": "101",
                "group": "uik1-11b",
            },
            {
                "ord": 1,
                "day_name": "Tuesday",
                "start_time": "10:15",
                "end_time": "11:50",
                "subject_name": "Физика",
                "place": "102",
                "group": "uik1-11b",
            },
        ])

        self.assertLess(timetable.index("Знаменатель"), timetable.index("Числитель"))
        self.assertEqual(academic_week_number(36, is_odd_semester=True), 1)
        self.assertEqual(schedule_ord_for_week(36, is_odd_semester=True), 1)
        self.assertEqual(week_type_name(36, is_odd_semester=True), "Числитель")

        self.assertEqual(academic_week_number(7, is_odd_semester=False), 1)
        self.assertEqual(schedule_ord_for_week(7, is_odd_semester=False), 0)
        self.assertEqual(week_type_name(7, is_odd_semester=False), "Знаменатель")


class DayOffCalendarTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_date_is_saved_and_loaded_by_range(self):
        with self.session_factory() as db:
            db.add(models.DayOff(date=date(2026, 9, 1)))
            db.commit()

            self.assertTrue(is_day_off(db, date(2026, 9, 1)))
            self.assertFalse(is_day_off(db, date(2026, 9, 2)))
            self.assertEqual(
                get_days_off(db, date(2026, 8, 31), date(2026, 9, 6)),
                {date(2026, 9, 1)},
            )

    def test_formatter_replaces_lessons_with_explicit_day_off(self):
        lessons = [{
            "day_name": "Tuesday",
            "podgroup": 0,
            "subject_name": "Математика",
            "start_time": "08:30",
            "end_time": "10:05",
        }]
        target_date = date(2026, 9, 1)

        result = format_timetable(
            lessons,
            include_empty_days=True,
            day_dates={"Tuesday": target_date},
            days=["Tuesday"],
            day_off_dates={target_date},
        )

        self.assertIn("🎉 <b>Выходной</b>", result)
        self.assertNotIn("Математика", result)

    async def test_daily_broadcast_sends_nothing_on_saved_day_off(self):
        today = datetime.now(ZoneInfo("Europe/Moscow")).date()
        with self.session_factory() as db:
            db.add(models.DayOff(date=today))
            db.commit()

        class BotThatMustNotSend:
            async def send_message(self, *args, **kwargs):
                raise AssertionError("Рассылка не должна отправляться в выходной")

        with patch("run.SessionLocal", self.session_factory):
            result = await send_daily_timetable(BotThatMustNotSend())

        self.assertEqual(result, 0)


class PersonalizedNotificationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session_factory = sessionmaker(bind=self.engine)
        self.target_date = date(2026, 9, 7)  # понедельник

    def tearDown(self):
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _add_group_schedule(self, db, group_name, first_lesson_start):
        group = models.Group(name=group_name)
        subject = models.Subject(name=f"Предмет {group_name}")
        teacher = models.Teacher(full_name=f"Преподаватель {group_name}")
        place = models.Place(name=f"Аудитория {group_name}")
        lesson_type = models.Type(name=f"Тип {group_name}")
        slot = models.TimeSlot(start_time=first_lesson_start, end_time="12:00")
        week_ord = schedule_ord_for_week(self.target_date.isocalendar()[1])
        day = models.Day(name="Monday", ord=week_ord)
        db.add_all([group, subject, teacher, place, lesson_type, slot, day])
        db.flush()
        db.add(models.Dayboard(
            subject_id=subject.id,
            group_id=group.id,
            teacher_id=teacher.id,
            time_id=slot.id,
            day_id=day.id,
            place_id=place.id,
            type_id=lesson_type.id,
            podgroup=0,
        ))
        db.flush()
        return group

    def test_time_parser_requires_strict_valid_24_hour_time(self):
        self.assertEqual(parse_notification_time("08:30"), time(8, 30))
        for invalid in ("8:30", "24:00", "12:60", "утром", ""):
            with self.subTest(invalid=invalid):
                self.assertIsNone(parse_notification_time(invalid))

    def test_hour_before_depends_on_each_users_group_first_lesson(self):
        with self.session_factory() as db:
            early_group = self._add_group_schedule(db, "TEST-EARLY", "08:30")
            late_group = self._add_group_schedule(db, "TEST-LATE", "10:20")
            early_user = models.User(
                tg_id=101,
                username="early",
                title="private",
                group_id=early_group.id,
                is_active=1,
                notification_mode="hour_before",
            )
            late_user = models.User(
                tg_id=102,
                username="late",
                title="private",
                group_id=late_group.id,
                is_active=1,
                notification_mode="hour_before",
            )
            db.add_all([early_user, late_user])
            db.commit()

            at_0730 = datetime(2026, 9, 7, 7, 30, tzinfo=ZoneInfo("Europe/Moscow"))
            at_0920 = datetime(2026, 9, 7, 9, 20, tzinfo=ZoneInfo("Europe/Moscow"))
            self.assertEqual(
                due_notification_target(db, early_user, at_0730),
                self.target_date,
            )
            self.assertIsNone(due_notification_target(db, late_user, at_0730))
            self.assertIsNone(due_notification_target(db, early_user, at_0920))
            self.assertEqual(
                due_notification_target(db, late_user, at_0920),
                self.target_date,
            )

    def test_day_before_targets_tomorrow_and_respects_day_off(self):
        with self.session_factory() as db:
            group = models.Group(name="TEST-DAY-BEFORE")
            user = models.User(
                tg_id=106,
                username="day_before",
                title="private",
                group_rel=group,
                is_active=1,
                notification_mode="day_before",
                notification_time=time(20, 0),
            )
            db.add(user)
            db.commit()

            now = datetime(2026, 9, 7, 20, 0, tzinfo=ZoneInfo("Europe/Moscow"))
            tomorrow = date(2026, 9, 8)
            self.assertEqual(due_notification_target(db, user, now), tomorrow)

            db.add(models.DayOff(date=tomorrow))
            db.commit()
            self.assertIsNone(due_notification_target(db, user, now))

    async def test_scheduler_marks_target_date_and_does_not_send_twice(self):
        with self.session_factory() as db:
            group = self._add_group_schedule(db, "TEST-SAME-DAY", "10:20")
            db.add(models.User(
                tg_id=103,
                username="same_day",
                title="private",
                group_id=group.id,
                is_active=1,
                notification_mode="same_day",
                notification_time=time(8, 0),
            ))
            db.commit()

        now = datetime(2026, 9, 7, 8, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        sender = AsyncMock(return_value=True)
        with patch("run.SessionLocal", self.session_factory), patch(
            "run.send_user_schedule_notification", sender
        ):
            self.assertEqual(await process_due_notifications(object(), now), 1)
            self.assertEqual(await process_due_notifications(object(), now), 0)

        self.assertEqual(sender.await_count, 1)
        with self.session_factory() as db:
            user = db.query(models.User).filter_by(tg_id=103).one()
            self.assertEqual(user.last_notification_date, self.target_date)

    async def test_empty_schedule_is_not_sent(self):
        class EmptyResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return []

        class EmptyScheduleClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return False

            async def get(self, *args, **kwargs):
                return EmptyResponse()

        class BotThatMustNotSend:
            async def send_message(self, *args, **kwargs):
                raise AssertionError("При пустом расписании отправки быть не должно")

        with self.session_factory() as db:
            group = models.Group(name="TEST-EMPTY")
            user = models.User(
                tg_id=107,
                username="empty",
                title="private",
                group_rel=group,
                is_active=1,
            )
            db.add(user)
            db.commit()

            with patch("run.httpx.AsyncClient", return_value=EmptyScheduleClient()):
                result = await send_user_schedule_notification(
                    BotThatMustNotSend(), user, self.target_date
                )

        self.assertFalse(result)

    async def test_empty_schedule_is_marked_handled_and_not_checked_twice(self):
        with self.session_factory() as db:
            group = models.Group(name="TEST-EMPTY-HANDLED")
            db.add(group)
            db.flush()
            db.add(models.User(
                tg_id=108,
                username="empty_handled",
                title="private",
                group_id=group.id,
                is_active=1,
                notification_mode="same_day",
                notification_time=time(8, 0),
            ))
            db.commit()

        now = datetime(2026, 9, 7, 8, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        sender = AsyncMock(return_value=False)
        with patch("run.SessionLocal", self.session_factory), patch(
            "run.send_user_schedule_notification", sender
        ):
            self.assertEqual(await process_due_notifications(object(), now), 0)
            self.assertEqual(await process_due_notifications(object(), now), 0)

        self.assertEqual(sender.await_count, 1)
        with self.session_factory() as db:
            user = db.query(models.User).filter_by(tg_id=108).one()
            self.assertEqual(user.last_notification_date, self.target_date)

    async def test_invalid_time_is_requested_again_without_enter_button(self):
        message = FakeTextMessage(104, "25:70")
        state = FakeState({"notification_mode": "same_day"})
        with self.session_factory() as db:
            await notification_time_input(message, state, db)

        self.assertFalse(state.cleared)
        self.assertIn("Некорректное время", message.sent[-1][0])
        callbacks = GroupSelectionKeyboardTests._callbacks(
            message.sent[-1][1]["reply_markup"]
        )
        self.assertEqual(callbacks, {"notification_choose_time"})

    async def test_valid_time_is_saved_for_subscribed_user(self):
        with self.session_factory() as db:
            group = models.Group(name="TEST-INPUT")
            db.add(group)
            db.flush()
            db.add(models.User(
                tg_id=105,
                username="input",
                title="private",
                group_id=group.id,
                is_active=1,
            ))
            db.commit()

            message = FakeTextMessage(105, "21:45")
            state = FakeState({"notification_mode": "day_before"})
            await notification_time_input(message, state, db)

            user = db.query(models.User).filter_by(tg_id=105).one()
            self.assertEqual(user.notification_mode, "day_before")
            self.assertEqual(user.notification_time, time(21, 45))

        self.assertTrue(state.cleared)
        self.assertIn("Настройка сохранена", message.sent[-1][0])


if __name__ == "__main__":
    unittest.main()
