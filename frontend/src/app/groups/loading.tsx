export default function Loading() {
  return (
    <main className="min-h-screen bg-gray-900 text-gray-100 p-6">
      <div className="max-w-3xl mx-auto animate-pulse">
        <div className="h-8 w-56 bg-gray-800 rounded mb-6" />
        <div className="grid sm:grid-cols-2 gap-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-14 bg-gray-800 rounded-xl" />
          ))}
        </div>
      </div>
    </main>
  );
}
