from datetime import date

from sqlalchemy.orm import Session

from common.database import models


def is_day_off(db: Session, target_date: date) -> bool:
    return (
        db.query(models.DayOff.id)
        .filter(models.DayOff.date == target_date)
        .first()
        is not None
    )


def get_days_off(db: Session, start_date: date, end_date: date) -> set[date]:
    if end_date < start_date:
        return set()

    rows = (
        db.query(models.DayOff.date)
        .filter(
            models.DayOff.date >= start_date,
            models.DayOff.date <= end_date,
        )
        .all()
    )
    return {row[0] for row in rows}
