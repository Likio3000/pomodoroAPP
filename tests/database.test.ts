import 'fake-indexeddb/auto';
import { afterEach, describe, expect, it } from 'vitest';
import { openDatabase, transaction } from '../src/domain/database';
const connections: IDBDatabase[] = [];
afterEach(() => {
  connections.forEach((db) => db.close());
  connections.length = 0;
});
async function open(name: string) {
  const db = await openDatabase(name);
  connections.push(db);
  return db;
}
describe('transactional persistence', () => {
  it('initializes once and persists across new connections', async () => {
    const name = crypto.randomUUID();
    const first = await open(name);
    await transaction(
      first,
      { type: 'add', title: 'Persistencia', id: 'task-persist' },
      Date.now(),
    );
    const second = await open(name);
    expect((await transaction(second)).state.tasks[0].title).toBe('Persistencia');
  });
  it('serializes concurrent writes without losing tasks', async () => {
    const name = crypto.randomUUID();
    const [a, b] = await Promise.all([open(name), open(name)]);
    await Promise.all([
      transaction(a, { type: 'add', title: 'Desde A', id: 'a' }),
      transaction(b, { type: 'add', title: 'Desde B', id: 'b' }),
    ]);
    expect((await transaction(a)).state.tasks.map((t) => t.title)).toEqual(['Desde A', 'Desde B']);
  });
  it('two tabs completing the same timer create one session and one chime event', async () => {
    const name = crypto.randomUUID();
    const [a, b] = await Promise.all([open(name), open(name)]);
    const started = await transaction(a, { type: 'toggle' }, 100_000);
    const deadline = started.state.timer.endsAt!;
    const results = await Promise.all([
      transaction(a, { type: 'settle' }, deadline),
      transaction(b, { type: 'settle' }, deadline),
    ]);
    expect(results.filter((r) => r.completed)).toHaveLength(1);
    expect((await transaction(a)).state.sessions).toHaveLength(1);
  });
  it('rolls back rejected changes', async () => {
    const db = await open(crypto.randomUUID());
    const original = (await transaction(db)).state;
    await expect(transaction(db, { type: 'add', title: '  ', id: 'bad' })).rejects.toThrow();
    expect((await transaction(db)).state).toEqual(original);
  });
  it('emits one break completion across two tabs without awarding focus time', async () => {
    const name = crypto.randomUUID();
    const [a, b] = await Promise.all([open(name), open(name)]);
    await transaction(a, { type: 'mode', mode: 'short' }, 100_000);
    const started = await transaction(a, { type: 'toggle' }, 100_000);
    const results = await Promise.all([
      transaction(a, { type: 'settle' }, started.state.timer.endsAt!),
      transaction(b, { type: 'settle' }, started.state.timer.endsAt!),
    ]);
    expect(results.filter((r) => r.finished)).toHaveLength(1);
    expect(results.filter((r) => r.completed)).toHaveLength(0);
  });
  it('does not emit a new completion when historical sessions are restored', async () => {
    const db = await open(crypto.randomUUID());
    const original = (await transaction(db)).state;
    const result = await transaction(db, {
      type: 'restore',
      data: {
        ...original,
        sessions: [{ id: 'historical', taskTitle: '', duration: 1_500_000, completedAt: 100_000 }],
      },
    });
    expect(result.state.sessions).toHaveLength(1);
    expect(result.completed).toBe(false);
    expect(result.finished).toBe(false);
  });
});
