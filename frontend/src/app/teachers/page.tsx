import { api } from "@/lib/api";
import type { Teacher } from "@/types";
import Link from "next/link";

export const dynamic = "force-dynamic";

async function getTeachers(q?: string) {
  const qs = new URLSearchParams();
  if (q) qs.set("q", q);
  // исключаем "Не указан" по умолчанию, берем побольше лимит
  qs.set("include_unknown", "false");
  qs.set("limit", "500");
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return api<Teacher[]>(`/teachers${suffix}`);
}

export default async function TeachersPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const sp = await searchParams;
  const q = sp?.q?.trim() || undefined;
  const teachers = await getTeachers(q);

  return (
    <main className="min-h-screen bg-gray-900 text-gray-100 p-6">
      <div className="max-w-4xl mx-auto">
        {/* Шапка */}
        <header className="flex items-center justify-between mb-6">
          <Link 
            href="/"
            className="px-4 py-2 rounded-xl border border-gray-700 text-gray-300 hover:bg-gray-800 hover:text-white transition"
          >
            ← На главную
          </Link>
          <h1 className="text-2xl font-bold text-center flex-1">Преподаватели</h1>
          <div className="w-[140px]" />
        </header>

        {/* Поиск */}
        <form className="mb-6 flex gap-2" action="/teachers" method="get">
          <input
            type="text"
            name="q"
            defaultValue={q || ""}
            placeholder="Поиск по ФИО..."
            className="flex-1 px-3 py-2 rounded-xl border border-gray-700 bg-gray-800 text-gray-100 placeholder-gray-400"
          />
          <button className="px-4 py-2 rounded-xl bg-blue-600 text-white hover:bg-blue-700 transition">
            Найти
          </button>
          <Link
            href="/teachers"
            className="px-4 py-2 rounded-xl border border-gray-700 text-gray-300 hover:bg-gray-800 transition"
          >
            Сброс
          </Link>
        </form>

        {/* Список */}
        <ul className="grid sm:grid-cols-2 gap-3">
          {teachers.map((t) => (
            <li key={t.id}>
              <Link
                href={`/teacher/${encodeURIComponent(t.full_name)}`}
                className="block p-4 border border-gray-700 bg-gray-800 rounded-xl hover:bg-blue-600 hover:text-white transition"
                title={`Расписание: ${t.full_name}`}
              >
                {t.full_name}
              </Link>
            </li>
          ))}
        </ul>

        {teachers.length === 0 && (
          <div className="mt-8 text-center text-gray-400">
            Преподаватели не найдены.
          </div>
        )}
      </div>
    </main>
  );
}
