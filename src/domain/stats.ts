import type { Session } from './model';
export function dayKey(time: number): string {
  const d = new Date(time);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
export function daysBefore(now: number, n: number): Date {
  const d = new Date(now);
  d.setHours(12, 0, 0, 0);
  d.setDate(d.getDate() - n);
  return d;
}
export function statistics(sessions: Session[], now: number) {
  const today = sessions.filter((s) => dayKey(s.completedAt) === dayKey(now));
  const active = new Set(sessions.map((s) => dayKey(s.completedAt)));
  let streak = 0;
  let offset = active.has(dayKey(now)) ? 0 : 1;
  while (active.has(dayKey(daysBefore(now, offset).getTime()))) {
    streak++;
    offset++;
  }
  const week = Array.from({ length: 7 }, (_, i) => {
    const date = daysBefore(now, 6 - i);
    const key = dayKey(date.getTime());
    return {
      key,
      label: date.toLocaleDateString('es', { weekday: 'short' }).replace('.', ''),
      minutes: sessions
        .filter((s) => dayKey(s.completedAt) === key)
        .reduce((sum, s) => sum + s.duration / 60_000, 0),
      today: i === 6,
    };
  });
  return {
    today,
    minutes: today.reduce((sum, s) => sum + s.duration / 60_000, 0),
    streak,
    week,
    totalMinutes: sessions.reduce((sum, s) => sum + s.duration / 60_000, 0),
  };
}
export function csv(sessions: Session[]): string {
  const safe = (text: string) =>
    `"${(/^[\s]*[=+@\-\t\r]/.test(text) ? "'" + text : text).replaceAll('"', '""')}"`;
  return (
    '\uFEFFfecha_iso,tarea,minutos\r\n' +
    sessions
      .map(
        (s) =>
          `${new Date(s.completedAt).toISOString()},${safe(s.taskTitle)},${s.duration / 60_000}`,
      )
      .join('\r\n')
  );
}
