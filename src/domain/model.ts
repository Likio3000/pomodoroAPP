export type Mode = 'focus' | 'short' | 'long';
export type Settings = { focus: number; short: number; long: number; goal: number; sound: boolean };
export type Task = {
  id: string;
  title: string;
  done: boolean;
  createdAt: number;
  sessions: number;
};
export type Session = { id: string; taskTitle: string; duration: number; completedAt: number };
export type Timer = {
  id: string;
  mode: Mode;
  status: 'idle' | 'running' | 'paused';
  duration: number;
  remaining: number;
  endsAt: number | null;
  taskId: string | null;
  taskTitle: string;
};
export type State = {
  version: 2;
  revision: number;
  settings: Settings;
  tasks: Task[];
  sessions: Session[];
  selectedTask: string | null;
  timer: Timer;
  cycle: number;
};
export const DEFAULT_SETTINGS: Settings = { focus: 25, short: 5, long: 15, goal: 4, sound: true };
export const MODE_LABELS: Record<Mode, string> = {
  focus: 'Enfoque',
  short: 'Pausa corta',
  long: 'Pausa larga',
};
export function freshTimer(mode: Mode, settings: Settings, id = crypto.randomUUID()): Timer {
  return {
    id,
    mode,
    status: 'idle',
    duration: settings[mode] * 60_000,
    remaining: settings[mode] * 60_000,
    endsAt: null,
    taskId: null,
    taskTitle: '',
  };
}
export function initialState(): State {
  return {
    version: 2,
    revision: 0,
    settings: { ...DEFAULT_SETTINGS },
    tasks: [],
    sessions: [],
    selectedTask: null,
    timer: freshTimer('focus', DEFAULT_SETTINGS),
    cycle: 0,
  };
}
export function remaining(timer: Timer, now: number): number {
  return Math.max(
    0,
    Math.min(
      timer.duration,
      timer.status === 'running' && timer.endsAt !== null ? timer.endsAt - now : timer.remaining,
    ),
  );
}
export function clockText(milliseconds: number): string {
  const seconds = Math.max(0, Math.ceil(milliseconds / 1000));
  return `${Math.floor(seconds / 60)
    .toString()
    .padStart(2, '0')}:${(seconds % 60).toString().padStart(2, '0')}`;
}
export type Command =
  | { type: 'toggle' }
  | { type: 'settle' }
  | { type: 'reset' }
  | { type: 'mode'; mode: Mode }
  | { type: 'select'; id: string | null }
  | { type: 'add'; title: string; id: string }
  | { type: 'done'; id: string }
  | { type: 'delete'; id: string }
  | { type: 'rename'; id: string; title: string }
  | { type: 'settings'; settings: Settings }
  | { type: 'restore'; data: Backup };

function title(value: string): string {
  const clean = value.trim();
  if (!clean || clean.length > 160)
    throw new Error('Escribe una tarea de entre 1 y 160 caracteres.');
  return clean;
}
export function validateSettings(input: unknown): Settings {
  if (!input || typeof input !== 'object') throw new Error('Ajustes no válidos.');
  const s = input as Settings;
  for (const [key, max] of [
    ['focus', 180],
    ['short', 60],
    ['long', 90],
    ['goal', 16],
  ] as const) {
    if (!Number.isInteger(s[key]) || s[key] < 1 || s[key] > max)
      throw new Error(`Revisa ${key}: debe estar entre 1 y ${max}.`);
  }
  if (typeof s.sound !== 'boolean') throw new Error('Ajustes de sonido no válidos.');
  return { focus: s.focus, short: s.short, long: s.long, goal: s.goal, sound: s.sound };
}

/** Pure transition. All callers persist through one IndexedDB read/write transaction. */
export function reduce(state: State, command: Command, now: number): State {
  const oldTimer = state.timer;
  if (oldTimer.status === 'running' && oldTimer.endsAt !== null && now >= oldTimer.endsAt) {
    const isFocus = oldTimer.mode === 'focus';
    const cycle = state.cycle + (isFocus ? 1 : 0);
    const next: Mode = isFocus ? (cycle % 4 === 0 ? 'long' : 'short') : 'focus';
    const session: Session = {
      id: oldTimer.id,
      taskTitle: oldTimer.taskTitle,
      duration: oldTimer.duration,
      completedAt: oldTimer.endsAt,
    };
    state = {
      ...state,
      revision: state.revision + 1,
      cycle,
      sessions:
        isFocus && !state.sessions.some((s) => s.id === session.id)
          ? [...state.sessions, session]
          : state.sessions,
      tasks: isFocus
        ? state.tasks.map((t) =>
            t.id === oldTimer.taskId ? { ...t, sessions: t.sessions + 1 } : t,
          )
        : state.tasks,
      timer: freshTimer(next, state.settings),
    };
    // A late click at the boundary must never start the next session accidentally.
    if (command.type === 'toggle' || command.type === 'settle') return state;
  }
  if (command.type === 'settle') return state;
  let next = { ...state, revision: state.revision + 1 };
  switch (command.type) {
    case 'toggle': {
      const t = state.timer;
      if (t.status === 'running')
        next.timer = { ...t, status: 'paused', remaining: remaining(t, now), endsAt: null };
      else {
        const task = state.tasks.find((x) => x.id === state.selectedTask && !x.done);
        next.timer = {
          ...t,
          status: 'running',
          endsAt: now + t.remaining,
          taskId: t.status === 'idle' ? (task?.id ?? null) : t.taskId,
          taskTitle: t.status === 'idle' ? (task?.title ?? '') : t.taskTitle,
        };
      }
      break;
    }
    case 'reset':
      next.timer = freshTimer(state.timer.mode, state.settings);
      break;
    case 'mode':
      next.timer = freshTimer(command.mode, state.settings);
      break;
    case 'select':
      if (command.id && !state.tasks.some((t) => t.id === command.id && !t.done))
        throw new Error('Esta tarea ya no está disponible.');
      next.selectedTask = command.id;
      break;
    case 'add':
      if (state.tasks.length >= 500)
        throw new Error('Has llegado a 500 tareas. Elimina alguna para añadir otra.');
      next.tasks = [
        ...state.tasks,
        { id: command.id, title: title(command.title), done: false, sessions: 0, createdAt: now },
      ];
      next.selectedTask = state.selectedTask ?? command.id;
      break;
    case 'done':
      next.tasks = state.tasks.map((t) => (t.id === command.id ? { ...t, done: !t.done } : t));
      if (next.tasks.find((t) => t.id === state.selectedTask)?.done) next.selectedTask = null;
      break;
    case 'delete':
      next.tasks = state.tasks.filter((t) => t.id !== command.id);
      if (state.selectedTask === command.id) next.selectedTask = null;
      break;
    case 'rename':
      next.tasks = state.tasks.map((t) =>
        t.id === command.id ? { ...t, title: title(command.title) } : t,
      );
      break;
    case 'settings': {
      const settings = validateSettings(command.settings);
      if (
        state.timer.status !== 'idle' &&
        ['focus', 'short', 'long'].some((k) => settings[k as Mode] !== state.settings[k as Mode])
      )
        throw new Error('Termina o reinicia la sesión antes de cambiar su duración.');
      next.settings = settings;
      if (state.timer.status === 'idle') next.timer = freshTimer(state.timer.mode, settings);
      break;
    }
    case 'restore':
      next = {
        ...initialState(),
        revision: next.revision,
        settings: command.data.settings,
        tasks: command.data.tasks,
        sessions: command.data.sessions,
        cycle: command.data.sessions.length,
        timer: freshTimer('focus', command.data.settings),
      };
      break;
  }
  return next;
}

export type Backup = { version: 2; settings: Settings; tasks: Task[]; sessions: Session[] };
export function parseBackup(text: string): Backup {
  if (text.length > 5_000_000) throw new Error('La copia supera el límite de 5 MB.');
  let data: Backup;
  try {
    data = JSON.parse(text);
  } catch {
    throw new Error('El archivo no contiene JSON válido.');
  }
  if (!data || data.version !== 2 || !Array.isArray(data.tasks) || !Array.isArray(data.sessions))
    throw new Error('No es una copia de Pomodoro versión 2.');
  if (data.tasks.length > 500 || data.sessions.length > 25_000)
    throw new Error('La copia contiene demasiados registros.');
  const settings = validateSettings(data.settings);
  const unique = new Set<string>();
  const validId = (id: unknown) => {
    if (typeof id !== 'string' || !/^[\w-]{1,80}$/.test(id) || unique.has(id))
      throw new Error('La copia contiene identificadores repetidos o no válidos.');
    unique.add(id);
    return id;
  };
  const validTime = (n: unknown): n is number =>
    typeof n === 'number' && Number.isSafeInteger(n) && n > 0 && n <= Date.now() + 60_000;
  const tasks = data.tasks.map((t) => {
    if (
      !t ||
      typeof t.title !== 'string' ||
      typeof t.done !== 'boolean' ||
      !validTime(t.createdAt) ||
      !Number.isSafeInteger(t.sessions) ||
      t.sessions < 0
    )
      throw new Error('La copia contiene una tarea no válida.');
    return {
      id: validId(t.id),
      title: title(t.title),
      done: t.done,
      createdAt: t.createdAt,
      sessions: t.sessions,
    };
  });
  const sessions = data.sessions.map((s) => {
    if (
      !s ||
      typeof s.taskTitle !== 'string' ||
      s.taskTitle.length > 160 ||
      !validTime(s.completedAt) ||
      !Number.isSafeInteger(s.duration) ||
      s.duration < 60_000 ||
      s.duration > 180 * 60_000 ||
      s.duration % 60_000 !== 0
    )
      throw new Error('La copia contiene una sesión no válida.');
    return {
      id: validId(s.id),
      taskTitle: s.taskTitle,
      completedAt: s.completedAt,
      duration: s.duration,
    };
  });
  return { version: 2, settings, tasks, sessions };
}
