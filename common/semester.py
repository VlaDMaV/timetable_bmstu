import os


# Единственная настройка семестра:
# true — нечётный семестр (-35 и совпадение чётности),
# false — чётный семестр (-6 и противоположная чётность).
_semester_value = os.getenv("SEMESTER_IS_ODD", "true").strip().lower()
if _semester_value in {"1", "true", "yes", "on"}:
    SEMESTER_IS_ODD = True
elif _semester_value in {"0", "false", "no", "off"}:
    SEMESTER_IS_ODD = False
else:
    raise RuntimeError("SEMESTER_IS_ODD должен быть true или false")


def academic_week_number(calendar_week: int, is_odd_semester: bool = SEMESTER_IS_ODD) -> int:
    """Преобразует номер недели года в номер учебной недели семестра."""
    return calendar_week - (35 if is_odd_semester else 6)


def schedule_ord_for_week(calendar_week: int, is_odd_semester: bool = SEMESTER_IS_ODD) -> int:
    """Возвращает ord расписания: 0 — знаменатель, 1 — числитель."""
    academic_week_parity = academic_week_number(calendar_week, is_odd_semester) % 2
    if is_odd_semester:
        return academic_week_parity
    return 1 - academic_week_parity


def week_type_name(calendar_week: int, is_odd_semester: bool = SEMESTER_IS_ODD) -> str:
    return "Знаменатель" if schedule_ord_for_week(calendar_week, is_odd_semester) == 0 else "Числитель"
