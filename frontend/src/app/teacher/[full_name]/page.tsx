// src/app/teacher/[full_name]/page.tsx
import { api } from "@/lib/api";
import type { TeacherLessonRow } from "@/types";
import { WEEKDAY_ORDER, WEEKDAYS_RU } from "@/lib/weekdays";
import { getLessonNumber } from "@/lib/lessons";
import { toRu } from "@/lib/groupNames";
import { getCurrentOrd, getISOWeek } from "@/lib/week";
import Link from 'next/link';

// SSR: тянем все занятия преподавателя (обе недели)
async function getTeacherLessons(fullName: string) {
  const safe = encodeURIComponent(fullName);
  return api<TeacherLessonRow[]>(`/dayboard/teacher/${safe}`);
}

// слоты в пределах дня объединяем по ключу (время + предмет + тип + аудитория)
// и перечисляем группы внутри одного блока
function groupBySlot(dayRows: TeacherLessonRow[]) {
  const map = new Map<
    string,
    { slot: TeacherLessonRow; groups: { nameEn: string; pod: number }[] }
  >();

  for (const r of dayRows) {
    const key = `${r.start_time}|${r.end_time}|${r.subject_name}|${r.type}|${r.place}`;
    const rec = map.get(key);
    if (rec) {
      rec.groups.push({ nameEn: r.group, pod: r.podgroup ?? 0 });
    } else {
      map.set(key, {
        slot: r,
        groups: [{ nameEn: r.group, pod: r.podgroup ?? 0 }],
      });
    }
  }

  // сортировка по номеру пары / времени
  return [...map.values()].sort((a, b) => {
    const na = getLessonNumber(a.slot.start_time);
    const nb = getLessonNumber(b.slot.start_time);
    if (na !== nb) return na - nb;
    return a.slot.start_time.localeCompare(b.slot.start_time);
  });
}

export default async function TeacherPage({
  params,
}: {
  params: Promise<{ full_name: string }>; // Next 15: params — Promise
}) {
  const p = await params;
  const fullName = decodeURIComponent(p.full_name);

  // все занятия (и для ord=0, и для ord=1)
  const lessonsAll = await getTeacherLessons(fullName);

  // текущая неделя/ord — только для надписи в шапке
  const currentOrd = getCurrentOrd(); // 0 — Знаменатель, 1 — Числитель
  const currentWeek = Math.max(1, getISOWeek() - 35);
  const currentOrdLabel = currentOrd === 0 ? "Знаменатель" : "Числитель";

  // Разделяем на две выборки: сначала ЧИСЛИТЕЛЬ (1), затем ЗНАМЕНАТЕЛЬ (0)
  const byOrd: Record<0 | 1, TeacherLessonRow[]> = { 0: [], 1: [] };
  for (const r of lessonsAll) {
    const o = (r.ord === 1 ? 1 : 0) as 0 | 1;
    byOrd[o].push(r);
  }

  // Группируем в каждой неделе по дням
  const groupByDay = (rows: TeacherLessonRow[]) => {
    const res: Record<string, TeacherLessonRow[]> = {};
    for (const r of rows) (res[r.day_name] ??= []).push(r);
    return res;
  };

  const byDayOrd1 = groupByDay(byOrd[1]); // Числитель
  const byDayOrd0 = groupByDay(byOrd[0]); // Знаменатель

  return (
    <main className="min-h-screen bg-gray-900 text-gray-100 p-6">
      <div className="max-w-5xl mx-auto">
        {/* Шапка */}
        <header className="mb-6">
          <div className="flex items-center justify-between">
            <Link
              href="/teachers"
              className="px-4 py-2 rounded-xl border border-gray-700 text-gray-300 hover:bg-gray-800 hover:text-white transition w-[230px] text-center"
            >
              ← К списку преподавателей
            </Link>

            <h1 className="text-2xl font-bold text-center flex-1">
              Расписание преподавателя
            </h1>

            <div className="w-[230px]" />
          </div>

          <div className="mt-3 text-sm text-gray-300 text-center">
            Преподаватель: <span className="font-semibold">{fullName}</span> •{" "}
            Сейчас {currentWeek} неделя:{" "}
            <span className="font-semibold">{currentOrdLabel}</span>
          </div>
        </header>

        {/* ====== Блок 1: Числитель (ord=1) ====== */}
        <section className="mb-10">
          <h2 className="text-xl font-bold mb-4">Неделя: Числитель</h2>
          <WeekByDays byDay={byDayOrd1} />
          {Object.keys(byDayOrd1).length === 0 && (
            <div className="text-gray-400">На неделе Числитель занятий не найдено.</div>
          )}
        </section>

        {/* ====== Блок 2: Знаменатель (ord=0) ====== */}
        <section>
          <h2 className="text-xl font-bold mb-4">Неделя: Знаменатель</h2>
          <WeekByDays byDay={byDayOrd0} />
          {Object.keys(byDayOrd0).length === 0 && (
            <div className="text-gray-400">На неделе Знаменатель занятий не найдено.</div>
          )}
        </section>
      </div>
    </main>
  );
}

/** Рендерит неделю: дни в порядке Пн→Вс, внутри дни — слоты, объединённые по времени/предмету/типу/аудитории с перечислением групп */
function WeekByDays({ byDay }: { byDay: Record<string, TeacherLessonRow[]> }) {
  return (
    <div className="space-y-8">
      {WEEKDAY_ORDER.map((day) => {
        const rows = byDay[day];
        if (!rows || rows.length === 0) return null;

        const slots = groupBySlot(rows);

        return (
          <section
            key={day}
            className="rounded-2xl border border-gray-700 bg-gray-800/40 p-4"
          >
            <h3 className="text-lg font-bold mb-4">📅 {WEEKDAYS_RU[day]}</h3>

            <ul className="space-y-4">
              {slots.map(({ slot, groups }) => {
                const n = getLessonNumber(slot.start_time);
                const numLabel = n > 0 ? `${n} пара` : "Пара";
                const groupsText = groups
                  .map((g) => {
                    const ru = toRu(g.nameEn);
                    return g.pod ? `${ru} (подг. ${g.pod})` : ru;
                  })
                  .join("; ");

                return (
                  <li
                    key={`${slot.start_time}-${slot.end_time}-${slot.subject_name}-${slot.type}-${slot.place}`}
                    className="rounded-xl border border-gray-700 bg-gray-900/40 p-3"
                  >
                    <div className="font-semibold">
                      🕒{numLabel} {slot.start_time}–{slot.end_time}
                    </div>
                    <div className="mt-1">
                      {slot.subject_name}{" "}
                      <span className="text-gray-300">({slot.type})</span>
                    </div>
                    <div className="mt-1 text-gray-300">
                      📍Аудитория: {slot.place || "Не указано"}
                    </div>
                    <div className="mt-1 text-gray-300">
                      👥 Группы: {groupsText}
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
