import Image from "next/image";

export default function HomePage() {
  return (
    <main className="flex flex-col items-center min-h-screen bg-gray-900 text-gray-100">
      {/* ===== Верхний блок: логотип + название ===== */}
      <header className="flex items-center justify-center gap-4 mt-10 mb-6">
        <Image
          src="/bmstu.png"
          alt="BMSTU"
          width={64}
          height={64}
          priority
          className="rounded-full"
        />
        <h1 className="text-4xl md:text-5xl font-extrabold tracking-tight text-white drop-shadow-lg">
          TimeTable BMSTU
        </h1>
      </header>

      {/* ===== Большое фото под заголовком ===== */}
      <div className="relative w-full h-[500px] md:h-[650px] overflow-hidden mb-10">
        {/* Фоновое фото */}
        <Image
          src="/campus.jpg" // поменяй на свой файл
          alt="BMSTU Campus"
          fill
          className="object-cover opacity-70"
          priority
        />
        {/* затемняющий градиент снизу для контраста */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-black/30 to-black/70"></div>
        {/* Текст поверх фото */}
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center px-4">
          <h2 className="text-3xl md:text-4xl font-bold text-white drop-shadow-2xl mb-4">
            Расписание занятий КФ МГТУ им. Баумана
          </h2>
          <p className="text-lg text-gray-200 max-w-2xl">
            Узнай своё расписание по преподавателю или группе —
            быстро и удобно
          </p>
        </div>
      </div>

      {/* ===== Центральная часть: выбор направления ===== */}
      <section className="flex flex-col items-center justify-center flex-grow p-6">
        <h3 className="text-2xl font-semibold mb-8 text-gray-300">
          Выберите направление
        </h3>

        <div className="grid sm:grid-cols-2 gap-4">
          <a
            href="/groups?kind=mk"
            className="p-6 border border-gray-700 bg-gray-800 rounded-xl text-center text-lg font-semibold hover:bg-blue-600 hover:text-white transition"
          >
            МК
          </a>
          <a
            href="/groups?kind=uik"
            className="p-6 border border-gray-700 bg-gray-800 rounded-xl text-center text-lg font-semibold hover:bg-blue-600 hover:text-white transition"
          >
            ИУК
          </a>
        </div>
        <div className="mt-6">
          <a
            href="/teachers"
            className="inline-block p-4 border border-gray-700 bg-gray-800 rounded-xl text-center text-lg font-semibold hover:bg-blue-600 hover:text-white transition"
          >
            Расписание по преподавателям
          </a>
        </div>
      </section>

      {/* ===== Подвал ===== */}
      <footer className="text-sm text-gray-500 mt-12 mb-6">
        © {new Date().getFullYear()} BMSTU
      </footer>
    </main>
  );
}
