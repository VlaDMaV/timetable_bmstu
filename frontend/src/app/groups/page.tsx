import { api } from "@/lib/api";
import type { Group } from "@/types";
import Image from "next/image";
import GroupList from "./GroupList";
import Link from 'next/link';

async function getGroups(kind?: "mk" | "uik") {
  const qs = kind ? `?kind=${kind}` : "";
  return api<Group[]>(`/groups${qs}`);
}

export default async function GroupsPage({
  searchParams,
}: {
  searchParams: Promise<{ kind?: string }>; // <-- ВАЖНО: Promise
}) {
  const sp = await searchParams;            // <-- ВАЖНО: await
  const rawKind = sp?.kind;
  const kind = rawKind === "mk" || rawKind === "uik" ? (rawKind as "mk" | "uik") : undefined;

  const groups = await getGroups(kind);

  return (
    <main className="min-h-screen bg-gray-900 text-gray-100 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Шапка */}
        <header className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <Image
              src="/bmstu.png"
              alt="BMSTU"
              width={56}
              height={56}
              priority
              className="rounded-full"
            />
            <h1 className="text-2xl font-bold">TimeTable BMSTU</h1>
          </div>
          <Link
            href="/"
            className="px-4 py-2 rounded-xl border border-gray-700 text-gray-300 hover:bg-gray-800 hover:text-white transition"
          >
            ← Назад
          </Link>
        </header>

        {/* Заголовок и фильтры */}
        <div className="flex flex-wrap items-center justify-between mb-6 gap-3">
          <h2 className="text-3xl font-semibold mb-3 sm:mb-0">
            {kind === "mk" ? "Группы МК" : kind === "uik" ? "Группы ИУК" : "Все группы"}
          </h2>

          <div className="flex items-center gap-2">
            <nav className="flex gap-2">
              <Link
                href="/groups"
                className={`px-3 py-1 rounded-xl border border-gray-700 ${
                  !kind ? "bg-gray-800 text-white" : "bg-gray-900 text-gray-400"
                }`}
              >
                Все
              </Link>
              <Link
                href="/groups?kind=mk"
                className={`px-3 py-1 rounded-xl border border-gray-700 ${
                  kind === "mk" ? "bg-gray-800 text-white" : "bg-gray-900 text-gray-400"
                }`}
              >
                МК
              </Link>
              <Link
                href="/groups?kind=uik"
                className={`px-3 py-1 rounded-xl border border-gray-700 ${
                  kind === "uik" ? "bg-gray-800 text-white" : "bg-gray-900 text-gray-400"
                }`}
              >
                ИУК
              </Link>
            </nav>

            {/* Кнопка на преподавателей */}
            <Link
              href="/teachers"
              className="px-3 py-1 rounded-xl border border-gray-700 bg-gray-800 hover:bg-blue-600 hover:text-white transition"
              title="Перейти к расписанию по преподавателям"
            >
              Расписание по преподавателям
            </Link>
          </div>
        </div>

        {/* Список групп */}
        <GroupList groups={groups} />
      </div>
    </main>
  );
}
