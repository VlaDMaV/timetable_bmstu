"use client";
export default function Error({ error }: { error: Error }) {
  return (
    <main className="min-h-screen bg-gray-900 text-gray-100 p-6">
      <div className="max-w-3xl mx-auto">
        <h1 className="text-2xl font-bold mb-3">Ошибка загрузки групп</h1>
        <pre className="text-sm text-red-300">{error.message}</pre>
      </div>
    </main>
  );
}
