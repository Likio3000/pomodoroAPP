import { initialState, reduce, type Command, type State } from './model';
export const DATABASE_NAME = 'pomodoro-focus-v2';
export function openDatabase(name = DATABASE_NAME): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(name, 1);
    request.onupgradeneeded = () => request.result.createObjectStore('app');
    request.onsuccess = () => {
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
    request.onerror = () => reject(request.error);
    request.onblocked = () =>
      reject(new Error('Cierra las otras pestañas de Pomodoro y vuelve a intentarlo.'));
  });
}
/** Read/modify/write stays inside a single transaction, including across tabs. */
export function transaction(
  db: IDBDatabase,
  command?: Command,
  now = Date.now(),
): Promise<{ state: State; completed: boolean; finished: boolean }> {
  return new Promise((resolve, reject) => {
    const tx = db.transaction('app', 'readwrite');
    const store = tx.objectStore('app');
    const request = store.get('state');
    let result: { state: State; completed: boolean; finished: boolean };
    let cause: unknown;
    request.onsuccess = () => {
      try {
        const current: State = request.result ?? initialState();
        if (current.version !== 2)
          throw new Error('Esta versión de los datos necesita una versión más reciente de la app.');
        const state = command ? reduce(current, command, now) : current;
        result = {
          state,
          completed: state.sessions.length > current.sessions.length && command?.type !== 'restore',
          finished:
            current.timer.status === 'running' &&
            current.timer.endsAt !== null &&
            now >= current.timer.endsAt &&
            state.timer.id !== current.timer.id,
        };
        if (!request.result || state !== current) store.put(state, 'state');
      } catch (error) {
        cause = error;
        tx.abort();
      }
    };
    tx.oncomplete = () => resolve(result);
    tx.onabort = () =>
      reject(cause ?? tx.error ?? new Error('No se han podido guardar los cambios.'));
    tx.onerror = () => {
      cause ??= tx.error;
    };
  });
}
