// ===== Группы =====
export type Group = {
  id: number;
  name: string; // англ. код группы (например: "uik2-52b", "mk3-51b")
};

// ===== Преподаватели (список) =====
export type Teacher = {
  id: number;
  full_name: string;
};

// ===== Ряд расписания группы (ответ /dayboard/filter) =====
// Соответствует вашему DayboardWithAll (бек)
export type DayboardRow = {
  id: number;
  subject_name: string;
  group_name: string;
  teacher_name: string;
  day_name:
    | "Monday"
    | "Tuesday"
    | "Wednesday"
    | "Thursday"
    | "Friday"
    | "Saturday"
    | "Sunday";
  ord: 0 | 1; // 0 — Знаменатель, 1 — Числитель
  start_time: string; // "08:30"
  end_time: string; // "10:05"
  place: string; // аудитория
  type: string; // тип занятия (Лекция/Семинар/Лаб.)
  podgroup: number; // 0 — общая, 1/2 — подгруппы
};

// ===== Ряд расписания преподавателя (ответ /dayboard/teacher/{full_name}) =====
export type TeacherLessonRow = {
  day_name:
    | "Monday"
    | "Tuesday"
    | "Wednesday"
    | "Thursday"
    | "Friday"
    | "Saturday"
    | "Sunday";
  ord: 0 | 1;
  start_time: string;
  end_time: string;
  subject_name: string;
  type: string;
  place: string;
  teacher_name: string;
  group: string; // англ. код группы
  podgroup: number; // 0/1/2
};