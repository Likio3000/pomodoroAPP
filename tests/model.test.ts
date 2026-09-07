import { describe, expect, it } from 'vitest';
import {
  clockText,
  DEFAULT_SETTINGS,
  initialState,
  parseBackup,
  reduce,
  remaining,
  validateSettings,
  type State,
} from '../src/domain/model';
const now = new Date('2026-09-01T02:00:00Z').getTime();
function started() {
  return reduce(initialState(), { type: 'toggle' }, now);
}
function finish(state: State) {
  return reduce(state, { type: 'settle' }, state.timer.endsAt! + 5_000);
}
describe('timer lifecycle', () => {
  it('uses a wall-clock deadline, including after suspension', () => {
    const state = started();
    expect(remaining(state.timer, now + 45_000)).toBe(1_455_000);
    const done = reduce(state, { type: 'settle' }, now + 3_600_000);
    expect(done.sessions).toHaveLength(1);
    expect(done.sessions[0].completedAt).toBe(now + 1_500_000);
    expect(done.timer.mode).toBe('short');
    expect(done.timer.status).toBe('idle');
  });
  it('pauses without consuming time and resumes the exact remainder', () => {
    const paused = reduce(started(), { type: 'toggle' }, now + 23_456);
    expect(paused.timer.status).toBe('paused');
    expect(remaining(paused.timer, now + 500_000)).toBe(1_476_544);
    const resumed = reduce(paused, { type: 'toggle' }, now + 600_000);
    expect(resumed.timer.endsAt).toBe(now + 600_000 + 1_476_544);
    expect(resumed.timer.id).toBe(paused.timer.id);
  });
  it('never creates duplicate sessions on repeated completion', () => {
    const done = finish(started());
    const again = reduce(done, { type: 'settle' }, now + 9_000_000);
    expect(again).toBe(done);
    expect(again.sessions).toHaveLength(1);
  });
  it('does not accidentally start a break on a late pause click', () => {
    const done = reduce(started(), { type: 'toggle' }, now + 1_500_000);
    expect(done.sessions).toHaveLength(1);
    expect(done.timer.status).toBe('idle');
  });
  it('does not award partial or break sessions', () => {
    expect(reduce(started(), { type: 'reset' }, now + 400_000).sessions).toHaveLength(0);
    const rest = reduce(initialState(), { type: 'mode', mode: 'short' }, now);
    const done = finish(reduce(rest, { type: 'toggle' }, now));
    expect(done.sessions).toHaveLength(0);
    expect(done.timer.mode).toBe('focus');
  });
  it('offers a long break after four completed focus sessions', () => {
    let state = initialState();
    let time = now;
    for (let i = 1; i <= 4; i++) {
      state = reduce(state, { type: 'mode', mode: 'focus' }, time);
      state = finish(reduce(state, { type: 'toggle' }, time));
      expect(state.timer.mode).toBe(i === 4 ? 'long' : 'short');
      time += 2_000_000;
    }
    expect(state.sessions).toHaveLength(4);
  });
  it('formats the last fraction of a second without showing zero early', () => {
    expect(clockText(1)).toBe('00:01');
    expect(clockText(60_001)).toBe('01:01');
    expect(clockText(-1)).toBe('00:00');
  });
  it('locks duration changes during an active session', () => {
    expect(() =>
      reduce(started(), { type: 'settings', settings: { ...DEFAULT_SETTINGS, focus: 50 } }, now),
    ).toThrow('Termina');
    expect(
      reduce(started(), { type: 'settings', settings: { ...DEFAULT_SETTINGS, goal: 8 } }, now)
        .settings.goal,
    ).toBe(8);
  });
});
describe('task and session attribution', () => {
  it('keeps the original intention in history after a rename or deletion', () => {
    let state = reduce(
      initialState(),
      { type: 'add', title: 'Planificar entrega', id: 'task-1' },
      now,
    );
    state = reduce(state, { type: 'toggle' }, now);
    state = reduce(state, { type: 'rename', id: 'task-1', title: 'Nuevo título' }, now + 1);
    state = reduce(state, { type: 'delete', id: 'task-1' }, now + 2);
    expect(finish(state).sessions[0].taskTitle).toBe('Planificar entrega');
  });
  it('completes tasks without inventing focus time', () => {
    let state = reduce(initialState(), { type: 'add', title: 'Leer', id: 'task-1' }, now);
    state = reduce(state, { type: 'done', id: 'task-1' }, now);
    expect(state.selectedTask).toBeNull();
    expect(state.sessions).toHaveLength(0);
    expect(state.tasks[0].done).toBe(true);
  });
  it('counts a completed focus for its task', () => {
    const state = reduce(initialState(), { type: 'add', title: 'Leer', id: 'task-1' }, now);
    expect(finish(reduce(state, { type: 'toggle' }, now)).tasks[0].sessions).toBe(1);
  });
  it('rejects blank and excessively long tasks', () => {
    for (const title of ['   ', 'x'.repeat(161)])
      expect(() => reduce(initialState(), { type: 'add', id: 't', title }, now)).toThrow();
  });
});
describe('backup validation', () => {
  it('roundtrips data but restores with an idle timer', () => {
    const data = parseBackup(JSON.stringify(finish(started())));
    const state = reduce(started(), { type: 'restore', data }, now + 2_000_000);
    expect(state.sessions).toEqual(data.sessions);
    expect(state.timer.status).toBe('idle');
  });
  it.each([null, '{}', '{', '{"version":1}', '[]'])('rejects malformed formats: %s', (input) => {
    expect(() => parseBackup(input as string)).toThrow();
  });
  it('rejects duplicate identifiers and invalid durations', () => {
    const state = finish(started());
    expect(() =>
      parseBackup(JSON.stringify({ ...state, sessions: [state.sessions[0], state.sessions[0]] })),
    ).toThrow('identificadores');
    expect(() =>
      parseBackup(JSON.stringify({ ...state, sessions: [{ ...state.sessions[0], duration: -1 }] })),
    ).toThrow('sesión');
  });
  it.each([0, -1, 2.5, Infinity, NaN, 181])('rejects invalid focus duration %s', (focus) => {
    expect(() => validateSettings({ ...DEFAULT_SETTINGS, focus })).toThrow();
  });
  it('rejects oversized files before parsing', () => {
    expect(() => parseBackup(' '.repeat(5_000_001))).toThrow('5 MB');
  });
});
