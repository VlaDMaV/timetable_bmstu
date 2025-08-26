from collections import defaultdict
import app.text as cs

def format_timetable(data):
    if not data:
        return "Расписание пустое."

    day_lessons = defaultdict(list)
    for lesson in data:
        day = lesson.get('day_name')
        if not day:
            continue
        day_lessons[day].append(lesson)

    text_lines = []

    for day in cs.DAY_ORDER:
        lessons = day_lessons.get(day)
        if not lessons:
            continue

        text_lines.append(f"📅 {cs.WEEKDAYS_RU.get(day, day)}\n")

        lessons.sort(key=lambda x: x.get('start_time', '00:00'))

        for i, l in enumerate(lessons, start=1):
            subject_name = l.get('subject_name', 'Без предмета')
            lesson_type = l.get('type', '')
            start_time = l.get('start_time', '??:??')
            end_time = l.get('end_time', '??:??')
            place = l.get('place', 'Не указано')
            teacher = l.get('teacher_name', 'Не указан')

            text_lines.append(
                f"{i} пара {start_time}–{end_time}\n"
                f"{subject_name}\n"
                f"({lesson_type})\n"
                f"Аудитория: {place}\n"
                f"Преподаватель: {teacher}\n"
            )
        text_lines.append("") 

    return "\n".join(text_lines)