import { describe, expect, it } from 'vitest';
import { csv, dayKey, statistics } from '../src/domain/stats';
import type { Session } from '../src/domain/model';
const session = (at: Date, id = 'one'): Session => ({
  id,
  completedAt: at.getTime(),
  duration: 1_500_000,
  taskTitle: 'Una tarea',
});
describe('honest local-day statistics', () => {
  it('starts empty without fake metrics', () => {
    const stats = statistics([], Date.now());
    expect(stats.minutes).toBe(0);
    expect(stats.streak).toBe(0);
    expect(stats.week).toHaveLength(7);
  });
  it('uses local calendar days, not UTC date slices', () => {
    const now = new Date(2026, 8, 7, 0, 10);
    const stats = statistics(
      [session(new Date(2026, 8, 7, 0, 5)), session(new Date(2026, 8, 6, 23, 55), 'two')],
      now.getTime(),
    );
    expect(stats.today).toHaveLength(1);
    expect(stats.minutes).toBe(25);
    expect(stats.streak).toBe(2);
    expect(dayKey(now.getTime())).toBe('2026-09-07');
  });
  it('keeps yesterday’s streak alive until today ends', () => {
    expect(
      statistics(
        [session(new Date(2026, 8, 6, 12)), session(new Date(2026, 8, 5, 12), 'two')],
        new Date(2026, 8, 7, 12).getTime(),
      ).streak,
    ).toBe(2);
    expect(
      statistics([session(new Date(2026, 8, 5, 12))], new Date(2026, 8, 7, 12).getTime()).streak,
    ).toBe(0);
  });
  it('escapes CSV quotes, newlines and spreadsheet formulas', () => {
    const output = csv([{ ...session(new Date()), taskTitle: '=HYPERLINK("evil")\nnext' }]);
    expect(output).toContain('"\'=HYPERLINK(""evil"")\nnext"');
  });
});
