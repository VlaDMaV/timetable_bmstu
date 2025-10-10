// Соответствие "время начала" -> "номер пары"
export const LESSON_NUMBERS: Record<string, number> = {
  "08:30": 1,
  "10:20": 2,
  "12:10": 3,
  "14:15": 4,
  "16:05": 5,
  "17:55": 6,
};

export function getLessonNumber(startTime: string): number {
  // берём только HH:MM (на случай если придёт "08:30:00")
  const key = (startTime || "").slice(0, 5);
  return LESSON_NUMBERS[key] ?? 0; // 0 если неизвестно
}
