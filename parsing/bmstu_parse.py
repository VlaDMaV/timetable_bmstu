import json
from file import your_json_string

# https://lks.bmstu.ru/lks-back/api/v1/schedules/groups/8354bf04-b8ff-11ed-a3ad-272ac9bbc1e7/public

def parse_schedule(data):
    schedule_items = data.get("data", {}).get("schedule", [])
    
    # Списки для уникальных сущностей (справочников)
    teachers = {}   # {full_name: object}
    subjects = {}   # {name: object}
    places = {}     # {name: object}
    types = {}      # {name: object}
    
    # Итоговый массив для Dayboard
    dayboard_entries = []

    for item in schedule_items:

        # 2. Парсим преподавателя (берем первого из списка для простоты)
        t_data = item["teachers"][0] if item["teachers"] else None
        t_name = f"{t_data['lastName']} {t_data['firstName']} {t_data['middleName']}" if t_data else "Неизвестен"
        if t_name not in teachers:
            teachers[t_name] = {"full_name": t_name}

        # 3. Парсим предмет
        sub_name = item["discipline"]["fullName"]
        if sub_name not in subjects:
            subjects[sub_name] = {"name": sub_name}

        # 4. Парсим место (аудиторию)
        p_name = item["audiences"][0]["name"] if item["audiences"] else "НЕТ"
        if p_name not in places:
            places[p_name] = {"name": p_name}

        # 5. Парсим тип занятия (lab, lecture, seminar)
        type_name = item["discipline"].get("actType", "unknown")
        if type_name not in types:
            types[type_name] = {"name": type_name}

        # 6. Определяем числитель/знаменатель (ord)
        # В вашем JSON: "zn" -> 0, "ch" -> 1, "all" -> 2 (или записываем две записи)
        week_type = item["week"]
        ords = [0] if week_type == "zn" else [1] if week_type == "ch" else [0, 1]

        # 7. Подгруппа
        # Извлекаем sub1 из stream, если есть
        podgroup = 0
        if item.get("stream") and item["stream"].get("groups"):
            podgroup = item["stream"]["groups"][0].get("sub1", 0)

        # Собираем данные для Dayboard
        for o in ords:
            dayboard_entries.append({
                "subject": sub_name,
                "teacher": t_name,
                "place": p_name,
                "type": type_name,
                "day_id": item["day"],
                "ord": o,
                "podgroup": podgroup
            })

    return {
        "teachers": list(teachers.values()),
        "subjects": list(subjects.values()),
        "places": list(places.values()),
        "types": list(types.values()),
        "entries": dayboard_entries
    }


# Предположим, ваш JSON лежит в переменной raw_data
raw_data = json.loads(your_json_string)

result = parse_schedule(raw_data)
# print('=========================')
# print(result["teachers"]) # Список всех уникальных учителей
# print('=========================')
# print(result["subjects"])
# print('=========================')
# print(result["places"])
# print('=========================')
# print(result["types"])
# print('=========================')
print(result)