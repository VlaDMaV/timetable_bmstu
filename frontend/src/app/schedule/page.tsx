import { api } from "@/lib/api";
import type { DayboardRow } from "@/types";
import { toRu } from "@/lib/groupNames";
import { getISOWeek, getCurrentOrd } from "@/lib/week";
import { WEEKDAY_ORDER, WEEKDAYS_RU } from "@/lib/weekdays";
import { getLessonNumber } from "@/lib/lessons";

export const dynamic = "force-dynamic";

async function getSchedule(group: string, ord: "0" | "1") {
  const qs = new URLSearchParams({ group, ord }).toString();
  return api<DayboardRow[]>(`/dayboard/filter?${qs}`);
}

type ByPod = Record<number /* podgroup */, DayboardRow[]>;

function sortByLesson(arr: DayboardRow[]) {
  return [...arr].sort((a, b) => {
    const na = getLessonNumber(a.start_time);
    const nb = getLessonNumber(b.start_time);
    if (na !== nb) return na - nb;
    return a.start_time.localeCompare(b.start_time);
  });
}

/** Если в дне есть подгруппа 0 + (1 или 2) — строим два списка:
 *  list1 = 0 ∪ 1, list2 = 0 ∪ 2, оба отсортированы по номеру пары.
 */
function splitOrSingle(byPod: ByPod) {
  const pg0 = byPod[0] ?? [];
  const pg1 = byPod[1] ?? [];
  const pg2 = byPod[2] ?? [];

  if (pg0.length > 0 && (pg1.length > 0 || pg2.length > 0)) {
    return {
      mode: "split" as const,
      list1: sortByLesson([...pg0, ...pg1]),
      list2: sortByLesson([...pg0, ...pg2]),
    };
  }

  if (pg0.length === 0 && (pg1.length > 0 || pg2.length > 0)) {
    if (pg1.length > 0 && pg2.length > 0) {
      return {
        mode: "split" as const,
        list1: sortByLesson([...pg1]),
        list2: sortByLesson([...pg2]),
      };
    }
    const only = pg1.length > 0 ? pg1 : pg2;
    return { mode: "single" as const, list: sortByLesson([...only]) };
  }

  return { mode: "single" as const, list: sortByLesson([...pg0]) };
}

export default async function SchedulePage({
  searchParams,
}: {
  searchParams: { group?: string; ord?: string };
}) {
  const group = searchParams.group;
  const autoOrd = String(getCurrentOrd()) as "0" | "1";
  const ordParam = (searchParams.ord ?? autoOrd) as "0" | "1";

  if (!group) {
    return (
      <main className="min-h-screen bg-gray-900 text-gray-100 p-6">
        <div className="max-w-4xl mx-auto">
          <a
            href="/groups"
            className="inline-block mb-6 px-4 py-2 rounded-xl border border-gray-700 text-gray-300 hover:bg-gray-800 hover:text-white transition"
          >
            ← К выбору группы
          </a>
          <h1 className="text-2xl font-bold">Не выбрана группа</h1>
          <p className="text-gray-400">Перейдите на страницу выбора группы.</p>
        </div>
      </main>
    );
  }

  const rows = await getSchedule(group, ordParam);
  const groupRu = toRu(group);

  // === Номер недели и подписи ===
  const isEven = ordParam === "0"; // 0 — чётная (Знаменатель)
  const baseWeek = getISOWeek() - 35; // смещение на начало семестра
  const isCurrentWeek = ordParam === autoOrd;
  const weekNo = (baseWeek > 0 ? baseWeek : 1) + (isCurrentWeek ? 0 : 1);
  const ordLabel = isEven ? "Знаменатель" : "Числитель";

  // === Параметры правой кнопки ===
  const flippedOrd = ordParam === "0" ? "1" : "0";
  const rightBtnHref = isCurrentWeek
    ? `/schedule?group=${encodeURIComponent(group)}&ord=${flippedOrd}`
    : `/schedule?group=${encodeURIComponent(group)}&ord=${autoOrd}`;
  const rightBtnLabel = isCurrentWeek
    ? "Расписание на следующую неделю →"
    : "Расписание на эту неделю →";
  const rightBtnTitle = isCurrentWeek
    ? "Показать расписание на следующую неделю"
    : "Вернуться к расписанию на текущую неделю";

  // === Группировка: день -> подгруппы ===
  const byDay: Record<string, ByPod> = {};
  for (const r of rows) {
    const day = r.day_name;
    const pg = r.podgroup ?? 0;
    byDay[day] ??= {};
    byDay[day][pg] ??= [];
    byDay[day][pg].push(r);
  }

  return (
    <main className="min-h-screen bg-gray-900 text-gray-100 p-6">
      <div className="max-w-5xl mx-auto">
        {/* ===== Шапка ===== */}
        <header className="mb-6">
          <div className="flex items-center justify-between">
            {/* Левая: назад (фикс. ширина для идеального центрирования заголовка) */}
            <a
              href="/groups"
              className="px-4 py-2 rounded-xl border border-gray-700 text-gray-300 hover:bg-gray-800 hover:text-white transition w-[230px] text-center"
            >
              ← К выбору группы
            </a>

            {/* Центр: заголовок ровно по центру */}
            <h1 className="text-2xl font-bold text-center flex-1">
              Расписание на неделю
            </h1>

            {/* Правая: динамическая кнопка */}
            <a
              href={rightBtnHref}
              className="px-4 py-2 rounded-xl border border-blue-700 bg-blue-600 text-white hover:bg-blue-700 transition w-[230px] text-center"
              title={rightBtnTitle}
            >
              {rightBtnLabel}
            </a>
          </div>

          <div className="mt-3 text-sm text-gray-300 text-center">
            Группа: <span className="font-semibold">{groupRu}</span> • {weekNo} неделя:{" "}
            <span className="font-semibold">{ordLabel}</span>
          </div>
        </header>

        {/* ===== Дни недели по порядку (Пн → Вс) ===== */}
        <div className="space-y-8">
          {WEEKDAY_ORDER.map((day) => {
            const byPod = byDay[day];
            if (!byPod) return null;

            const bucket = splitOrSingle(byPod);

            return (
              <section
                key={day}
                className="rounded-2xl border border-gray-700 bg-gray-800/40 p-4"
              >
                <h2 className="text-xl font-bold mb-4">📅 {WEEKDAYS_RU[day]}</h2>

                {bucket.mode === "single" && <DayLessons list={bucket.list} />}

                {bucket.mode === "split" && (
                  <div className="grid md:grid-cols-2 gap-6">
                    <div>
                      <div className="mb-3 font-semibold">🔹 Подгруппа 1</div>
                      <DayLessons list={bucket.list1} />
                    </div>
                    <div>
                      <div className="mb-3 font-semibold">🔹 Подгруппа 2</div>
                      <DayLessons list={bucket.list2} />
                    </div>
                  </div>
                )}
              </section>
            );
          })}
        </div>

        {rows.length === 0 && (
          <div className="mt-8 text-center text-gray-400">
            Для выбранных параметров пары не найдены.
          </div>
        )}
      </div>
    </main>
  );
}

/** Рендер занятий внутри дня (нумерация по LESSON_NUMBERS) */
function DayLessons({ list }: { list: DayboardRow[] }) {
  return (
    <ul className="space-y-4">
      {list.map((l) => {
        const n = getLessonNumber(l.start_time);
        const numLabel = n > 0 ? `${n} пара` : "Пара";
        return (
          <li
            key={l.id}
            className="rounded-xl border border-gray-700 bg-gray-900/40 p-3"
          >
            <div className="font-semibold">
              🕒{numLabel} {l.start_time}–{l.end_time}
            </div>
            <div className="mt-1">
              {l.subject_name}{" "}
              <span className="text-gray-300">({l.type})</span>
            </div>
            <div className="mt-1 text-gray-300">
              📍Аудитория: {l.place || "Не указано"}
            </div>
            <div className="text-gray-300">
              Преподаватель: {l.teacher_name || "Не указан"}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
