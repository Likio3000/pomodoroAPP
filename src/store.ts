import { translate, UserError } from './i18n/messages';
import { useSyncExternalStore } from 'react';
import { openDatabase, transaction } from './domain/database';
import type { Command, State } from './domain/model';
import { chime } from './sound';
import { dayKey } from './domain/stats';

type Snapshot = {
  state: State | null;
  error: UserError | null;
  completion: 'focusComplete' | 'breakComplete' | null;
};
let snapshot: Snapshot = { state: null, error: null, completion: null };
const listeners = new Set<() => void>();
let database: Promise<IDBDatabase> | null = null;
const channel =
  typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel('pomodoro-focus-v2') : null;
function emit(patch: Partial<Snapshot>) {
  snapshot = { ...snapshot, ...patch };
  listeners.forEach((fn) => fn());
}
function getDatabase() {
  return (database ??= openDatabase().catch((error) => {
    database = null;
    throw error;
  }));
}
export async function dispatch(command?: Command): Promise<boolean> {
  try {
    const result = await transaction(await getDatabase(), command);
    if (!snapshot.state || result.state.revision >= snapshot.state.revision)
      emit({ state: result.state, error: null });
    if (command?.type === 'restore' || command?.type === 'reset') emit({ completion: null });
    if (result.completed) {
      emit({ completion: 'focusComplete' });
      if (result.state.settings.sound) chime();
      if (document.hidden && 'Notification' in window && Notification.permission === 'granted') {
        try {
          new Notification(translate(result.state.language ?? 'es', 'notificationTitle'), {
            body: translate(result.state.language ?? 'es', 'notificationBody'),
            tag: 'pomodoro-complete',
          });
        } catch {
          /* Mobile notification support varies. */
        }
      }
    } else if (result.finished) {
      emit({ completion: 'breakComplete' });
      if (result.state.settings.sound) chime();
    }
    if (command) channel?.postMessage(result.state.revision);
    return true;
  } catch (error) {
    emit({
      error: error instanceof UserError ? error : new UserError('storageError'),
    });
    return false;
  }
}
export function dismissCompletion() {
  emit({ completion: null });
}
export function dismissError() {
  emit({ error: null });
}
channel?.addEventListener('message', () => {
  void dispatch();
});
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) void dispatch({ type: 'settle' });
});
window.addEventListener('focus', () => {
  void dispatch({ type: 'settle' });
});
export function useStore() {
  return useSyncExternalStore(
    (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
    () => snapshot,
  );
}
void dispatch({ type: 'settle' });
let calendarDay = dayKey(Date.now());
setInterval(() => {
  const day = dayKey(Date.now());
  if (day !== calendarDay) {
    calendarDay = day;
    emit({});
  }
  const timer = snapshot.state?.timer;
  if (timer?.status === 'running' && timer.endsAt !== null && timer.endsAt <= Date.now())
    void dispatch({ type: 'settle' });
}, 500);
