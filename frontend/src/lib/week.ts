// ISO week number (1..53), локальное время клиента не важно — берём UTC,
// чтобы не было скачков при смене часовых поясов.
export function getISOWeek(date = new Date()): number {
  const d = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  // четверг - "якорный" день ISO-недели
  const day = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7);
  return weekNo;
}

// ord: 0 — чётная неделя, 1 — нечётная
export function getCurrentOrd(date = new Date()): 0 | 1 {
  return ((getISOWeek(date)+1) % 2 === 0 ? 0 : 1);
}
