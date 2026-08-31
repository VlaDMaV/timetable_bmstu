import unittest
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import handlers
from common.database import models
from common.database.base import Base
from test_stability import FakeState


def message(chat_id=-100, actor_id=10, chat_type="supergroup", value="21:45"):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type=chat_type, title="Test group"),
        from_user=SimpleNamespace(id=actor_id, is_bot=False, username="renamed_owner"),
        sender_chat=None,
        text=value,
        answer=AsyncMock(),
        edit_text=AsyncMock(),
    )


def callback(actor_id=10, data="notification_settings", chat_id=-100, chat_type="supergroup"):
    msg = message(chat_id, actor_id, chat_type)
    return SimpleNamespace(message=msg, from_user=msg.from_user, data=data, answer=AsyncMock())


class GroupSettingsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([
            models.Group(id=1, name="uik6-11b"),
            models.Group(id=2, name="uik6-31b"),
            models.User(tg_id=-100, username="old_owner_name", title="Test group",
                        settings_owner_tg_id=10, group_id=1, is_active=1,
                        last_notification_date=date(2026, 8, 31)),
            models.User(tg_id=10, username="old_owner_name", title="private", group_id=1,
                        is_active=1),
        ])
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def group(self):
        return self.db.query(models.User).filter_by(tg_id=-100).one()

    async def test_non_owner_cannot_use_settings_or_old_selection_buttons(self):
        cases = [
            (handlers.subscribe_user, "subscribe", False),
            (handlers.unsubscribe_user, "unsubscribe", False),
            (handlers.change_group, "change_group", True),
            (handlers.choose_group, "choose_group:2", True),
            (handlers.notification_settings, "notification_settings", True),
            (handlers.notification_choose_time, "notification_choose_time", True),
            (handlers.notification_hour_before, "notification_mode:hour_before", True),
            (handlers.notification_timing, "notification_timing:day_before", True),
            (handlers.start_group_search, "search_group", True),
            (handlers.choose_faculty, "choose_faculty:uik", True),
        ]
        for handler, data, needs_state in cases:
            with self.subTest(handler=handler.__name__):
                event = callback(actor_id=20, data=data)
                kwargs = {"state": FakeState()} if needs_state else {}
                await handler(event, db=self.db, **kwargs)
                event.answer.assert_awaited_once_with(handlers.GROUP_SETTINGS_DENIED, show_alert=True)
                event.message.edit_text.assert_not_awaited()
                self.assertEqual(self.group().group_id, 1)
                self.assertEqual(self.group().is_active, 1)
                self.assertEqual(self.group().notification_mode, "same_day")

    async def test_owner_can_unsubscribe_and_resubscribe_in_both_group_types(self):
        for chat_type in ("group", "supergroup"):
            event = callback(chat_type=chat_type)
            await handlers.unsubscribe_user(event, self.db)
            self.assertEqual(self.group().is_active, 0)
            await handlers.subscribe_user(event, self.db)
            self.assertEqual(self.group().is_active, 1)

    async def test_owner_changes_group_without_changing_personal_settings(self):
        await handlers.change_group(callback(), FakeState(), self.db)
        await handlers.choose_group(callback(data="choose_group:2"), FakeState(), self.db)
        self.assertEqual(self.group().group_id, 2)
        self.assertEqual(self.db.query(models.User).filter_by(tg_id=10).one().group_id, 1)

    async def test_owner_can_save_hour_before_and_explicit_time(self):
        await handlers.notification_hour_before(callback(), FakeState(), self.db)
        self.assertEqual(self.group().notification_mode, "hour_before")
        self.assertIsNone(self.group().last_notification_date)
        await handlers.notification_time_input(
            message(), FakeState({"notification_mode": "day_before"}), self.db,
        )
        self.assertEqual(self.group().notification_mode, "day_before")
        self.assertEqual(self.group().notification_time, time(21, 45))
        self.assertEqual(self.db.query(models.User).filter_by(tg_id=10).one().notification_mode, "same_day")

    async def test_group_time_prompt_uses_force_reply(self):
        event = callback(data="notification_timing:day_before")
        state = FakeState()
        await handlers.notification_timing(event, state, self.db)
        self.assertEqual(state.state, handlers.NotificationStates.waiting_for_time)
        markup = event.message.answer.call_args.kwargs["reply_markup"]
        self.assertTrue(markup.force_reply)
        self.assertIn("tg://user?id=10", event.message.answer.call_args.args[0])

    async def test_time_input_checks_owner_again_after_prompt(self):
        for actor_id in (20, 10):
            with self.subTest(actor_id=actor_id):
                self.group().settings_owner_tg_id = 30
                self.db.commit()
                msg = message(actor_id=actor_id)
                state = FakeState({"notification_mode": "day_before"})
                await handlers.notification_time_input(msg, state, self.db)
                msg.answer.assert_awaited_once_with(handlers.GROUP_SETTINGS_DENIED)
                self.assertEqual(self.group().notification_mode, "same_day")

    async def test_anonymous_sender_is_denied(self):
        msg = message()
        msg.sender_chat = msg.chat
        await handlers.notification_time_input(msg, FakeState(), self.db)
        msg.answer.assert_awaited_once_with(handlers.GROUP_SETTINGS_DENIED)

    async def test_unknown_owner_cannot_be_claimed_by_start_or_username(self):
        self.group().settings_owner_tg_id = None
        self.db.commit()
        await handlers.start(message(), FakeState(), self.db)
        event = callback()
        await handlers.unsubscribe_user(event, self.db)
        self.assertIsNone(self.group().settings_owner_tg_id)
        self.assertIn("Владелец старой привязки не определён", event.answer.call_args.args[0])

    async def test_private_chat_keeps_existing_settings_behavior(self):
        event = callback(chat_id=10, chat_type="private")
        await handlers.unsubscribe_user(event, self.db)
        self.assertEqual(self.db.query(models.User).filter_by(tg_id=10).one().is_active, 0)
        self.assertEqual(self.group().is_active, 1)

    async def test_membership_event_records_adder_but_promotion_does_not_transfer(self):
        event = SimpleNamespace(
            chat=message(chat_id=-200).chat,
            from_user=message().from_user,
            old_chat_member=SimpleNamespace(status="left"),
            new_chat_member=SimpleNamespace(status="member"),
        )
        await handlers.bot_added_to_group(event, self.db)
        group = self.db.query(models.User).filter_by(tg_id=-200).one()
        self.assertEqual(group.settings_owner_tg_id, 10)
        event.from_user = message(actor_id=20).from_user
        event.old_chat_member.status = "member"
        event.new_chat_member.status = "administrator"
        await handlers.bot_added_to_group(event, self.db)
        await handlers.start(message(chat_id=-200, actor_id=20), FakeState(), self.db)
        self.assertEqual(group.settings_owner_tg_id, 10)

