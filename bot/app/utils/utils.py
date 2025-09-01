from collections import defaultdict
import app.text as cs

def format_timetable(data):
    if not data:
        return "Расписание пустое."

    day_lessons = defaultdict(list)
    day_lessons_by_subgroup = defaultdict(lambda: {"1": [], "2": []})

    for lesson in data:
        day = lesson.get('day_name')
        if not day:
            continue
        
        podgroup = lesson.get('podgroup', 0)
        
        if podgroup == 0:
            day_lessons[day].append(lesson)
            day_lessons_by_subgroup[day]["1"].append(lesson)
            day_lessons_by_subgroup[day]["2"].append(lesson)
        elif podgroup in (1, 2):
            day_lessons_by_subgroup[day][str(podgroup)].append(lesson)

    text_lines = []

    for day in cs.DAY_ORDER:
        lessons_all = day_lessons.get(day, [])
        lessons_subgroup = day_lessons_by_subgroup.get(day, {"1": [], "2": []})

        if not lessons_all and not (lessons_subgroup["1"] or lessons_subgroup["2"]):
            continue

        text_lines.append(f"📅 {cs.WEEKDAYS_RU.get(day, day)}\n")

        if lessons_all and not any(len(v) > 0 for v in lessons_subgroup.values() if v != lessons_all):
            lessons_all.sort(key=lambda x: x.get('start_time', '00:00'))
            for i, l in enumerate(lessons_all, start=1):
                subject_name = l.get('subject_name', 'Без предмета')
                lesson_type = l.get('type', '')
                start_time = l.get('start_time', '??:??')
                end_time = l.get('end_time', '??:??')
                place = l.get('place', 'Не указано')
                teacher = l.get('teacher_name', 'Не указан')

                text_lines.append(
                    f"🕒{i} пара {start_time}–{end_time}\n"
                    f"<b>{subject_name}</b> <i>({lesson_type})</i>\n"
                    f"📍Аудитория: {place}\n"
                    f"Преподаватель: {teacher}\n"
                )
        else:
            for subgroup in ("1", "2"):
                lessons_sub = lessons_subgroup[subgroup]
                if not lessons_sub:
                    continue

                text_lines.append(f"🔹 Подгруппа {subgroup}:\n")
                lessons_sub.sort(key=lambda x: x.get('start_time', '00:00'))
                for i, l in enumerate(lessons_sub, start=1):
                    subject_name = l.get('subject_name', 'Без предмета')
                    lesson_type = l.get('type', '')
                    start_time = l.get('start_time', '??:??')
                    end_time = l.get('end_time', '??:??')
                    place = l.get('place', 'Не указано')
                    teacher = l.get('teacher_name', 'Не указан')

                    text_lines.append(
                        f"🕒{i} пара {start_time}–{end_time}\n"
                        f"<b>{subject_name}</b> <i>({lesson_type})</i>\n"
                        f"📍Аудитория: {place}\n"
                        f"Преподаватель: {teacher}\n"
                    )

        text_lines.append("")

    return "\n".join(text_lines)
