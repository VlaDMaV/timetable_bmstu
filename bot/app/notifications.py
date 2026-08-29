from datetime import date, datetime, time, timedelta
import re

from sqlalchemy.orm import Session

import app.text as cs
from common.calendar_days import is_day_off
from common.database import models
from common.semester import schedule_ord_for_week


NOTIFICATION_MODES = {"hour_before", "same_day", "day_before"}
NOTIFICATION_MODE_LABELS = {
    "hour_before": "за час до первой пары",
    "same_day": "в день занятий",
    "day_before": "за день до занятий",
}
NOTIFICATION_GRACE = timedelta(minutes=10)


def notification_mode_label(mode: str) -> str:
    return NOTIFICATION_MODE_LABELS.get(mode, "в день занятий")


def parse_notification_time(value: str) -> time | None:
    value = (value or "").strip()
    if not re.fullmatch(r"\d{2}:\d{2}", value):
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def first_lesson_time(db: Session, group_id: int, target_date: date) -> time | None:
    day_name = cs.WEEKDAYS.get(target_date.isoweekday())
    week_ord = schedule_ord_for_week(target_date.isocalendar()[1])
    row = (
        db.query(models.TimeSlot.start_time)
        .join(models.Dayboard, models.Dayboard.time_id == models.TimeSlot.id)
        .join(models.Day, models.Dayboard.day_id == models.Day.id)
        .filter(
            models.Dayboard.group_id == group_id,
            models.Day.name == day_name,
            models.Day.ord == week_ord,
        )
        .order_by(models.TimeSlot.start_time)
        .first()
    )
    if not row:
        return None
    try:
        return datetime.strptime(row[0], "%H:%M").time()
    except (TypeError, ValueError):
        return None


def due_notification_target(
    db: Session,
    user: models.User,
    now: datetime,
    grace: timedelta = NOTIFICATION_GRACE,
) -> date | None:
    """Возвращает дату расписания, если уведомление нужно отправить сейчас."""
    if not user.is_active or not user.group_id:
        return None

    mode = user.notification_mode or "same_day"
    if mode not in NOTIFICATION_MODES:
        return None

    if mode == "day_before":
        target_date = now.date() + timedelta(days=1)
        due_date = now.date()
        due_time = user.notification_time
    elif mode == "same_day":
        target_date = now.date()
        due_date = target_date
        due_time = user.notification_time
    else:
        target_date = now.date()
        due_date = target_date
        first_time = first_lesson_time(db, user.group_id, target_date)
        if first_time is None:
            return None
        first_lesson_at = datetime.combine(target_date, first_time, tzinfo=now.tzinfo)
        due_at = first_lesson_at - timedelta(hours=1)
        due_date = due_at.date()
        due_time = due_at.time().replace(tzinfo=None)

    if target_date.isoweekday() == 7 or is_day_off(db, target_date):
        return None
    if user.last_notification_date == target_date:
        return None
    if due_time is None:
        return None

    due_at = datetime.combine(due_date, due_time, tzinfo=now.tzinfo)
    if due_at <= now < due_at + grace:
        return target_date
    return None
