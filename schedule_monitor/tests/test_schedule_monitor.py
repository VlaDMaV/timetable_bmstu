import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from common.database import models
from common.schedule_sync import (
    LessonKey,
    diff_lessons,
    normalize_group_name,
    parse_admin_group_selection,
    parse_source_schedule,
    replace_group_schedule,
)
from schedule_monitor.config import MonitorConfig
from schedule_monitor.main import (
    claim_manual_run,
    finish_manual_run,
    next_sunday_run,
    recover_interrupted_manual_runs,
)
from schedule_monitor.monitor import describe_exception, discover_groups


def schedule_payload(title="МК1-11Б", uuid="group-uuid", subject="Новый предмет"):
    return {
        "data": {
            "title": title,
            "uuid": uuid,
            "schedule": [
                {
                    "day": 1,
                    "time": 1,
                    "week": "all",
                    "discipline": {"fullName": subject, "actType": "lecture"},
                    "teachers": [
                        {"lastName": "Иванов", "firstName": "Иван", "middleName": "Иванович"}
                    ],
                    "audiences": [{"name": "101"}],
                    "stream": {"groups": [{"groupUuid": uuid, "sub1": 2}]},
                }
            ],
        }
    }


class ScheduleNormalizationTests(unittest.TestCase):
    def test_nested_network_error_is_described(self):
        try:
            try:
                raise OSError("TLS connection closed")
            except OSError as exc:
                raise RuntimeError() from exc
        except RuntimeError as exc:
            description = describe_exception(exc)

        self.assertIn("RuntimeError", description)
        self.assertIn("OSError: TLS connection closed", description)

    def test_group_names_accept_russian_and_latin(self):
        self.assertEqual(normalize_group_name("МК2-72Б"), "mk2-72b")
        self.assertEqual(normalize_group_name("ИУК6-11/5"), "uik6-11/5")

    def test_source_schedule_expands_all_weeks_and_selects_group_subgroup(self):
        lessons, errors = parse_source_schedule(schedule_payload())

        self.assertEqual(errors, [])
        self.assertEqual(len(lessons), 2)
        self.assertEqual({lesson.ord for lesson in lessons}, {0, 1})
        self.assertEqual({lesson.podgroup for lesson in lessons}, {2})
        self.assertEqual({lesson.teacher for lesson in lessons}, {"Иванов Иван Иванович"})

    def test_diff_reports_additions_and_removals(self):
        old = LessonKey("Monday", 0, 1, "Старый", "А", "1", "Лекция", 0)
        new = LessonKey("Monday", 0, 1, "Новый", "А", "1", "Лекция", 0)

        added, removed = diff_lessons([old], [new])

        self.assertEqual(added, [new])
        self.assertEqual(removed, [old])

    def test_admin_selection(self):
        self.assertEqual(parse_admin_group_selection("все"), ("all", []))
        self.assertEqual(parse_admin_group_selection("отмена"), ("cancel", []))
        self.assertEqual(
            parse_admin_group_selection("МК2-72Б, uik3-52b\nmk2-72b"),
            ("groups", ["mk2-72b", "uik3-52b"]),
        )


class DiscoveryTests(unittest.TestCase):
    def test_discovers_only_selected_faculties_and_excludes_aspirants(self):
        config = MonitorConfig(
            database_url="sqlite://",
            bot_token="1:test",
            admin_id=1,
            faculty_uuids=("faculty-uik", "faculty-mk"),
        )
        structure = {
            "data": {
                "children": [
                    {
                        "uuid": "faculty-uik",
                        "children": [
                            {"nodeType": "group", "uuid": "1", "abbr": "ИУК1-11Б"},
                            {"nodeType": "group", "uuid": "2", "abbr": "ИУК1-11А"},
                        ],
                    },
                    {
                        "uuid": "other",
                        "children": [
                            {"nodeType": "group", "uuid": "3", "abbr": "РК1-11Б"},
                        ],
                    },
                ]
            }
        }

        groups = discover_groups(structure, config)

        self.assertEqual([group.group_name for group in groups], ["uik1-11b"])


class AtomicReplacementTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)

    def test_replacement_preserves_group_and_user_link(self):
        with self.Session() as db:
            group = models.Group(name="mk1-11b")
            db.add_all(
                [
                    group,
                    models.TimeSlot(id=1, start_time="08:30", end_time="10:05"),
                ]
            )
            db.flush()
            original_group_id = group.id
            db.add(
                models.User(
                    tg_id=123,
                    username="admin",
                    title="private",
                    group_id=group.id,
                    is_active=1,
                )
            )
            db.commit()

            old_count, new_count, created = replace_group_schedule(
                db,
                "mk1-11b",
                schedule_payload(),
            )
            db.commit()

            self.assertEqual(old_count, 0)
            self.assertEqual(new_count, 2)
            self.assertEqual(created, 0)
            self.assertEqual(db.query(models.Group).filter_by(name="mk1-11b").one().id, original_group_id)
            self.assertEqual(db.query(models.User).filter_by(tg_id=123).one().group_id, original_group_id)
            self.assertEqual(db.query(models.Dayboard).filter_by(group_id=original_group_id).count(), 2)

    def test_empty_source_is_rejected_before_deletion(self):
        payload = schedule_payload()
        payload["data"]["schedule"] = []
        with self.Session() as db:
            db.add_all(
                [
                    models.Group(name="mk1-11b"),
                    models.TimeSlot(id=1, start_time="08:30", end_time="10:05"),
                ]
            )
            db.commit()
            with self.assertRaisesRegex(ValueError, "пустое расписание"):
                replace_group_schedule(db, "mk1-11b", payload)


class SchedulerTests(unittest.TestCase):
    def test_sunday_before_run_uses_same_day(self):
        timezone = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 8, 30, 8, 0, tzinfo=timezone)
        self.assertEqual(
            next_sunday_run(now, 9, 0),
            datetime(2026, 8, 30, 9, 0, tzinfo=timezone),
        )

    def test_sunday_after_run_uses_next_week(self):
        timezone = ZoneInfo("Europe/Moscow")
        now = datetime(2026, 8, 30, 10, 0, tzinfo=timezone)
        self.assertEqual(
            next_sunday_run(now, 9, 0),
            datetime(2026, 9, 6, 9, 0, tzinfo=timezone),
        )


class ManualRunQueueTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        models.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, autoflush=False)

    def test_claim_and_finish_manual_run(self):
        with self.Session() as db:
            db.add(models.ScheduleMonitorRun(requested_by=123, status="queued"))
            db.commit()

        run_id = claim_manual_run(self.Session)
        self.assertIsNotNone(run_id)
        self.assertIsNone(claim_manual_run(self.Session))

        finish_manual_run(self.Session, run_id)
        with self.Session() as db:
            run = db.get(models.ScheduleMonitorRun, run_id)
            self.assertEqual(run.status, "completed")
            self.assertIsNotNone(run.started_at)
            self.assertIsNotNone(run.finished_at)

    def test_interrupted_run_is_marked_failed(self):
        with self.Session() as db:
            run = models.ScheduleMonitorRun(requested_by=123, status="running")
            db.add(run)
            db.commit()
            run_id = run.id

        recover_interrupted_manual_runs(self.Session)
        with self.Session() as db:
            run = db.get(models.ScheduleMonitorRun, run_id)
            self.assertEqual(run.status, "failed")
            self.assertIn("перезапущен", run.error)


if __name__ == "__main__":
    unittest.main()
