from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy.orm import Session, joinedload

from common.database import models


DAY_MAP = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
}

DAY_NAMES_RU = {
    "Monday": "Понедельник",
    "Tuesday": "Вторник",
    "Wednesday": "Среда",
    "Thursday": "Четверг",
    "Friday": "Пятница",
    "Saturday": "Суббота",
    "Sunday": "Воскресенье",
}

TYPE_MAP = {
    "lecture": "Лекция",
    "lab": "Лабораторная работа",
    "laboratory": "Лабораторная работа",
    "seminar": "Семинар",
    "practice": "Практика",
    "exam": "Экзамен",
    "consultation": "Консультация",
    "unknown": "Спец. занятие",
}


@dataclass(frozen=True, order=True)
class LessonKey:
    day_name: str
    ord: int
    time_id: int
    subject: str
    teacher: str
    place: str
    lesson_type: str
    podgroup: int

    def as_dict(self) -> dict:
        return {
            "day_name": self.day_name,
            "ord": self.ord,
            "time_id": self.time_id,
            "subject": self.subject,
            "teacher": self.teacher,
            "place": self.place,
            "lesson_type": self.lesson_type,
            "podgroup": self.podgroup,
        }


def normalize_group_name(value: str) -> str:
    """Приводит русское или латинское название группы к виду uik1-11b/mk1-11b."""
    normalized = (value or "").lower().strip().replace(" ", "")
    normalized = normalized.replace("—", "-").replace("–", "-")
    if normalized.startswith("иук"):
        normalized = "uik" + normalized[3:]
    elif normalized.startswith("уик"):
        normalized = "uik" + normalized[3:]
    elif normalized.startswith("мк"):
        normalized = "mk" + normalized[2:]
    return normalized.translate(str.maketrans({"б": "b", "м": "m", "а": "a"}))


def display_group_name(value: str) -> str:
    normalized = normalize_group_name(value)
    if normalized.startswith("uik"):
        normalized = "ИУК" + normalized[3:]
    elif normalized.startswith("mk"):
        normalized = "МК" + normalized[2:]
    return normalized.translate(str.maketrans({"b": "Б", "m": "М", "a": "А"}))


def _clean(value: object, fallback: str) -> str:
    cleaned = str(value or "").strip()
    return cleaned or fallback


def parse_source_schedule(payload: dict) -> tuple[list[LessonKey], list[str]]:
    """Преобразует ответ BMSTU в канонические занятия, как текущий parsing/parse.py."""
    data = payload.get("data") or {}
    raw_schedule = data.get("schedule")
    if not isinstance(raw_schedule, list):
        return [], ["В ответе BMSTU отсутствует массив data.schedule"]

    group_uuid = data.get("uuid")
    lessons: list[LessonKey] = []
    errors: list[str] = []

    for index, item in enumerate(raw_schedule, start=1):
        if not isinstance(item, dict):
            errors.append(f"Запись {index}: ожидался объект")
            continue

        discipline = item.get("discipline") or {}
        subject = _clean(discipline.get("fullName"), "")
        if not subject:
            errors.append(f"Запись {index}: не указана дисциплина")
            continue

        teacher_names: list[str] = []
        for teacher in item.get("teachers") or []:
            name = " ".join(
                part
                for part in (
                    _clean(teacher.get("lastName"), ""),
                    _clean(teacher.get("firstName"), ""),
                    _clean(teacher.get("middleName"), ""),
                )
                if part
            )
            if name and name not in teacher_names:
                teacher_names.append(name)
        teacher_name = ", ".join(teacher_names) or "Не указан"

        audience_names: list[str] = []
        for audience in item.get("audiences") or []:
            name = _clean(audience.get("name"), "")
            if name and name not in audience_names:
                audience_names.append(name)
        place_name = ", ".join(audience_names) or "Не указана"

        raw_type = _clean(discipline.get("actType"), "unknown").lower()
        lesson_type = TYPE_MAP.get(raw_type, "Спец. занятие")

        day_name = DAY_MAP.get(item.get("day"))
        if day_name is None:
            errors.append(f"Запись {index}: неизвестный день {item.get('day')!r}")
            continue

        try:
            time_id = int(item.get("time"))
        except (TypeError, ValueError):
            errors.append(f"Запись {index}: некорректный номер пары {item.get('time')!r}")
            continue
        if time_id <= 0:
            errors.append(f"Запись {index}: номер пары должен быть положительным")
            continue

        week_type = item.get("week")
        if week_type == "ch":
            ords = (1,)
        elif week_type == "zn":
            ords = (0,)
        else:
            ords = (0, 1)

        podgroup = 0
        stream_groups = (item.get("stream") or {}).get("groups") or []
        if stream_groups:
            selected = next(
                (group for group in stream_groups if group.get("groupUuid") == group_uuid),
                stream_groups[0],
            )
            try:
                podgroup = int(selected.get("sub1") or 0)
            except (TypeError, ValueError):
                errors.append(f"Запись {index}: некорректная подгруппа")
                continue

        for ord_value in ords:
            lessons.append(
                LessonKey(
                    day_name=day_name,
                    ord=ord_value,
                    time_id=time_id,
                    subject=subject,
                    teacher=teacher_name,
                    place=place_name,
                    lesson_type=lesson_type,
                    podgroup=podgroup,
                )
            )

    # В БД одна логическая запись должна существовать один раз.
    return sorted(set(lessons)), errors


def load_db_schedule(db: Session, group: models.Group | None) -> list[LessonKey]:
    if group is None:
        return []

    rows = (
        db.query(models.Dayboard)
        .options(
            joinedload(models.Dayboard.subject_rel),
            joinedload(models.Dayboard.teacher_rel),
            joinedload(models.Dayboard.time_rel),
            joinedload(models.Dayboard.day_rel),
            joinedload(models.Dayboard.place_rel),
            joinedload(models.Dayboard.type_rel),
        )
        .filter(models.Dayboard.group_id == group.id)
        .all()
    )
    return sorted(
        LessonKey(
            day_name=row.day_rel.name,
            ord=int(row.day_rel.ord),
            time_id=int(row.time_id),
            subject=row.subject_rel.name.strip(),
            teacher=row.teacher_rel.full_name.strip(),
            place=row.place_rel.name.strip(),
            lesson_type=row.type_rel.name.strip(),
            podgroup=int(row.podgroup or 0),
        )
        for row in rows
    )


def diff_lessons(
    current: Sequence[LessonKey],
    proposed: Sequence[LessonKey],
) -> tuple[list[LessonKey], list[LessonKey]]:
    current_counter = Counter(current)
    proposed_counter = Counter(proposed)
    added = sorted((proposed_counter - current_counter).elements())
    removed = sorted((current_counter - proposed_counter).elements())
    return added, removed


def format_lesson(lesson: LessonKey) -> str:
    week = "числитель" if lesson.ord == 1 else "знаменатель"
    subgroup = "вся группа" if lesson.podgroup == 0 else f"подгруппа {lesson.podgroup}"
    return (
        f"{DAY_NAMES_RU.get(lesson.day_name, lesson.day_name)} | {week} | "
        f"{lesson.time_id} пара | {lesson.subject} | {lesson.teacher} | "
        f"{lesson.place} | {lesson.lesson_type} | {subgroup}"
    )


def _get_or_create(db: Session, model, **kwargs):
    instance = db.query(model).filter_by(**kwargs).first()
    if instance is None:
        instance = model(**kwargs)
        db.add(instance)
        db.flush()
    return instance


def validate_source_for_apply(
    db: Session,
    group_name: str,
    payload: dict,
) -> list[LessonKey]:
    payload_group = normalize_group_name((payload.get("data") or {}).get("title", ""))
    if payload_group != normalize_group_name(group_name):
        raise ValueError(
            f"Название группы в снимке ({payload_group or 'не указано'}) "
            f"не совпадает с {group_name}"
        )

    lessons, errors = parse_source_schedule(payload)
    if errors:
        raise ValueError("; ".join(errors[:5]))
    if not lessons:
        raise ValueError("BMSTU вернул пустое расписание; автоматическая очистка запрещена")

    known_time_ids = {row_id for (row_id,) in db.query(models.TimeSlot.id).all()}
    missing_time_ids = sorted({lesson.time_id for lesson in lessons} - known_time_ids)
    if missing_time_ids:
        raise ValueError(f"В БД отсутствуют номера пар: {missing_time_ids}")
    return lessons


def replace_group_schedule(
    db: Session,
    group_name: str,
    payload: dict,
) -> tuple[int, int, int]:
    """Заменяет расписание одной группы внутри транзакции вызывающей стороны."""
    normalized_group = normalize_group_name(group_name)
    lessons = validate_source_for_apply(db, normalized_group, payload)

    group = db.query(models.Group).filter(models.Group.name == normalized_group).first()
    created_group = group is None
    if group is None:
        group = models.Group(name=normalized_group)
        db.add(group)
        db.flush()

    old_count = (
        db.query(models.Dayboard)
        .filter(models.Dayboard.group_id == group.id)
        .count()
    )

    subjects = {
        name: _get_or_create(db, models.Subject, name=name)
        for name in {lesson.subject for lesson in lessons}
    }
    teachers = {
        name: _get_or_create(db, models.Teacher, full_name=name)
        for name in {lesson.teacher for lesson in lessons}
    }
    places = {
        name: _get_or_create(db, models.Place, name=name)
        for name in {lesson.place for lesson in lessons}
    }
    lesson_types = {
        name: _get_or_create(db, models.Type, name=name)
        for name in {lesson.lesson_type for lesson in lessons}
    }
    days = {
        (lesson.day_name, lesson.ord): _get_or_create(
            db,
            models.Day,
            name=lesson.day_name,
            ord=lesson.ord,
        )
        for lesson in lessons
    }

    db.query(models.Dayboard).filter(
        models.Dayboard.group_id == group.id
    ).delete(synchronize_session=False)

    for lesson in lessons:
        db.add(
            models.Dayboard(
                subject_id=subjects[lesson.subject].id,
                group_id=group.id,
                teacher_id=teachers[lesson.teacher].id,
                time_id=lesson.time_id,
                day_id=days[(lesson.day_name, lesson.ord)].id,
                place_id=places[lesson.place].id,
                type_id=lesson_types[lesson.lesson_type].id,
                podgroup=lesson.podgroup,
            )
        )

    db.flush()
    return old_count, len(lessons), int(created_group)


def parse_admin_group_selection(text: str) -> tuple[str, list[str]]:
    cleaned = (text or "").strip().lower()
    if cleaned in {"все", "all"}:
        return "all", []
    if cleaned in {"отмена", "отменить", "cancel", "нет"}:
        return "cancel", []

    names = []
    for token in re.split(r"[,;\s]+", cleaned):
        normalized = normalize_group_name(token)
        if normalized and normalized not in names:
            names.append(normalized)
    return "groups", names


def dump_payload(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def load_payload(value: str) -> dict:
    payload = json.loads(value)
    if not isinstance(payload, dict):
        raise ValueError("Сохранённый снимок расписания имеет неверный формат")
    return payload
