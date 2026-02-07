import os
import json
from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# импортируй свои модели
from models import Group, Teacher, TimeSlot, Day, Subject, Place, Type, Dayboard


# --- helpers ---
DAY_MAP = {
    1: "Monday",
    2: "Tuesday",
    3: "Wednesday",
    4: "Thursday",
    5: "Friday",
    6: "Saturday",
    7: "Sunday",
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


DATABASE_URL = "from .env"

engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_timeout=60,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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


def get_or_create_by(db: Session, model, defaults=None, **kwargs):
    """
    Простая get_or_create. Возвращает (obj, created_bool)
    """
    obj = db.query(model).filter_by(**kwargs).first()
    if obj:
        return obj, False
    params = dict(kwargs)
    if defaults:
        params.update(defaults)
    obj = model(**params)
    db.add(obj)
    db.flush()  # чтобы получить obj.id
    return obj, True


def parse_schedule(data):
    schedule_items = data.get("data", {}).get("schedule", [])

    teachers = set()
    subjects = set()
    places = set()
    types = set()
    entries = []

    for item in schedule_items:
        # teacher
        t_data = item["teachers"][0] if item.get("teachers") else None
        t_name = (
            f"{t_data.get('lastName','').strip()} "
            f"{t_data.get('firstName','').strip()} "
            f"{t_data.get('middleName','').strip()}"
        ).strip() if t_data else "Не указан"

        teachers.add(t_name)

        # subject
        sub_name = item["discipline"]["fullName"]
        subjects.add(sub_name)

        # place
        p_name = item["audiences"][0]["name"] if item.get("audiences") else "Не указана"
        places.add(p_name)

        # type
        raw_type = item["discipline"].get("actType", "").lower()
        type_name = TYPE_MAP.get(raw_type, "Спец. занятие")
        types.add(type_name)

        # week -> ords
        week_type = item.get("week")

        # Вариант для нечётного семестра
        # ords = [0] if week_type == "zn" else [1] if week_type == "ch" else [0, 1]

        # Вариает для чётного семестра
        if week_type == "ch":        # числитель
            ords = [0]
        elif week_type == "zn":      # знаменатель
            ords = [1]
        else:                        # all
            ords = [0, 1]

        # podgroup
        podgroup = 0
        if item.get("stream") and item["stream"].get("groups"):
            podgroup = item["stream"]["groups"][0].get("sub1", 0) or 0

        # time slot (пара) — НУЖНО ИЗ JSON
        # попробуем найти распространённые поля
        pair_number = item.get("time")

        for o in ords:
            entries.append({
                "subject": sub_name,
                "teacher": t_name,
                "place": p_name,
                "type": type_name,
                "day_raw": item.get("day"),   # число из JSON
                "ord": int(o),                # 0/1
                "podgroup": int(podgroup),
                "pair_number": pair_number,   # может быть None
            })

    return {
        "teachers": list(teachers),
        "subjects": list(subjects),
        "places": list(places),
        "types": list(types),
        "entries": entries,
    }


def save_schedule_to_db(
    db: Session,
    parsed: dict,
    group_name: str,
):
    """
    Сохраняет данные в твои таблицы и не создаёт дубликаты.
    group_name — имя группы (нужно для Dayboard.group_id)
    """

    # 0) группа
    group, _ = get_or_create_by(db, Group, name=group_name)

    # 1) справочники
    teachers_map = {}
    for name in parsed["teachers"]:
        # у тебя full_name НЕ unique, поэтому get_or_create_by работает как “не дублировать”
        t, _ = get_or_create_by(db, Teacher, full_name=name)
        teachers_map[name] = t.id

    subjects_map = {}
    for name in parsed["subjects"]:
        s, _ = get_or_create_by(db, Subject, name=name)
        subjects_map[name] = s.id

    places_map = {}
    for name in parsed["places"]:
        p, _ = get_or_create_by(db, Place, name=name)  # тут unique=True уже есть
        places_map[name] = p.id

    types_map = {}
    for name in parsed["types"]:
        tp, _ = get_or_create_by(db, Type, name=name)  # тут unique=True уже есть
        types_map[name] = tp.id

    # 2) days: (name, ord) уникально логически — у тебя нет unique, поэтому тоже get_or_create
    days_map = {}  # (day_name, ord) -> id
    for e in parsed["entries"]:
        day_name = DAY_MAP.get(e["day_raw"], str(e["day_raw"]))
        key = (day_name, e["ord"])
        if key not in days_map:
            d, _ = get_or_create_by(db, Day, name=day_name, ord=e["ord"])
            days_map[key] = d.id

    # 3) timeslots
    # Если у тебя timeslots уже заполнены (id=1..N), мы просто ищем по id.
    # Если нет — можно создавать на лету, но нужны start/end. Поэтому:
    # - если pair_number есть: берём TimeSlot с таким id (или создаём пустышку) — на твой выбор
    # Я сделаю строгий режим: если timeslot не найден — пропустить запись.
    # Если хочешь — скажи, и я сделаю автосоздание по дефолтным временам.
    timeslots_cache = {ts.id: ts.id for ts in db.query(TimeSlot).all()}

    inserted = 0
    skipped_no_time = 0
    skipped_duplicates = 0

    # 4) dayboard entries без дублей: проверяем существование такой же записи перед вставкой
    # Критерий "такая же": все FK + podgroup (можешь расширить/сузить)
    for e in parsed["entries"]:
        pair_number = e["pair_number"]
        if not pair_number:
            skipped_no_time += 1
            continue

        try:
            pair_number_int = int(pair_number)
        except Exception:
            skipped_no_time += 1
            continue

        if pair_number_int not in timeslots_cache:
            skipped_no_time += 1
            continue

        day_name = DAY_MAP.get(e["day_raw"], str(e["day_raw"]))
        day_id = days_map[(day_name, e["ord"])]

        subject_id = subjects_map[e["subject"]]
        teacher_id = teachers_map[e["teacher"]]
        place_id = places_map[e["place"]]
        type_id = types_map[e["type"]]
        time_id = pair_number_int

        exists = db.query(Dayboard.id).filter_by(
            subject_id=subject_id,
            group_id=group.id,
            teacher_id=teacher_id,
            time_id=time_id,
            day_id=day_id,
            place_id=place_id,
            type_id=type_id,
            podgroup=e["podgroup"],
        ).first()

        if exists:
            skipped_duplicates += 1
            continue

        db.add(Dayboard(
            subject_id=subject_id,
            group_id=group.id,
            teacher_id=teacher_id,
            time_id=time_id,
            day_id=day_id,
            place_id=place_id,
            type_id=type_id,
            podgroup=e["podgroup"],
        ))
        inserted += 1

    db.flush()
    return {
        "group_id": group.id,
        "inserted": inserted,
        "skipped_no_time": skipped_no_time,
        "skipped_duplicates": skipped_duplicates,
    }


# -------------------- usage --------------------
if __name__ == "__main__":
    from file import your_json_string
    raw_data = json.loads(your_json_string)
    parsed = parse_schedule(raw_data)

    print('Введите номер группы: ')
    group_name_input=input()
    group_name = group_name_input

    for db in get_db():
        stats = save_schedule_to_db(db, parsed, group_name=group_name)

    print("DONE:", stats)