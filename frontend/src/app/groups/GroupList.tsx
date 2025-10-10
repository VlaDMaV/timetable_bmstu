"use client";

import type { Group } from "@/types";
import { toRu } from "@/lib/groupNames";
import { getCurrentOrd } from "@/lib/week";
import Link from "next/link";

export default function GroupList({ groups }: { groups: Group[] }) {
  // ord: 0 — чётная (Знаменатель), 1 — нечётная (Числитель)
  const ord = getCurrentOrd();
  const ordText = ord === 0 ? "Знаменатель" : "Числитель";

  return (
    <>
      {/* Информация о текущей неделе */}
      <div className="mb-4 text-sm text-gray-300">Сейчас: {ordText}</div>

      {/* Список групп */}
      <ul className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {groups.map((g) => {
          const nameEn = g.name;       // английское имя для API
          const nameRu = toRu(nameEn); // показываем по-русски
          const href = `/schedule?group=${encodeURIComponent(nameEn)}&ord=${ord}`;

          return (
            <li key={g.id}>
              <Link
                href={href}
                className="block p-4 border border-gray-700 bg-gray-800 rounded-xl hover:bg-blue-600 hover:text-white transition text-center"
                title={`Открыть расписание: ${nameRu}`}
              >
                {nameRu}
              </Link>
            </li>
          );
        })}

        {groups.length === 0 && (
          <li className="text-gray-400 text-center col-span-full">
            Нет групп для выбранного направления.
          </li>
        )}
      </ul>
    </>
  );
}
