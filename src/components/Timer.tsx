import { useEffect, useState } from 'react';
import { clockText, MODE_LABELS, remaining, type Mode, type State } from '../domain/model';
import { dispatch, dismissCompletion } from '../store';
import { unlockSound } from '../sound';
import { Icon } from './Icon';
import { Dialog } from './Dialog';
const ticks = Array.from({ length: 60 }, (_, index) => (
  <line
    key={index}
    x1="180"
    y1="19"
    x2="180"
    y2={index % 5 === 0 ? '34' : '27'}
    transform={`rotate(${index * 6} 180 180)`}
    className={index % 5 === 0 ? 'major-tick' : ''}
  />
));
export function Timer({ state }: { state: State }) {
  const [now, setNow] = useState(Date.now);
  const [confirm, setConfirm] = useState<Mode | 'reset' | null>(null);
  const timer = state.timer;
  const left = remaining(timer, now);
  const toggle = () => {
    unlockSound();
    dismissCompletion();
    void dispatch({ type: 'toggle' });
  };
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(id);
  }, []);
  useEffect(() => {
    const handle = (event: KeyboardEvent) => {
      if (
        event.code !== 'Space' ||
        event.repeat ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey ||
        document.querySelector('dialog[open]')
      )
        return;
      if (
        (event.target as HTMLElement)?.closest(
          'input, textarea, button, select, a, [contenteditable="true"]',
        )
      )
        return;
      event.preventDefault();
      unlockSound();
      dismissCompletion();
      void dispatch({ type: 'toggle' });
    };
    window.addEventListener('keydown', handle);
    return () => window.removeEventListener('keydown', handle);
  }, []);
  const choose = (mode: Mode) => {
    if (mode === timer.mode) return;
    if (timer.status !== 'idle') setConfirm(mode);
    else {
      dismissCompletion();
      void dispatch({ type: 'mode', mode });
    }
  };
  const activeTask =
    timer.status !== 'idle'
      ? timer.taskTitle
      : state.tasks.find((t) => t.id === state.selectedTask && !t.done)?.title;
  return (
    <section className={`focus-canvas mode-${timer.mode}`} aria-labelledby="focus-title">
      <header className="focus-heading">
        <h1 id="focus-title">
          {timer.mode === 'focus' ? 'Una cosa a la vez.' : 'También cuenta parar.'}
        </h1>
        <p>
          {timer.mode === 'focus'
            ? 'Haz espacio para lo importante.'
            : 'Suelta la pantalla. Respira. Vuelve a tu ritmo.'}
        </p>
      </header>
      <div className="mode-switch" role="group" aria-label="Tipo de sesión">
        {(Object.keys(MODE_LABELS) as Mode[]).map((mode) => (
          <button key={mode} aria-pressed={timer.mode === mode} onClick={() => choose(mode)}>
            {MODE_LABELS[mode]}
          </button>
        ))}
      </div>
      <div className={`dial ${timer.status === 'running' ? 'running' : ''}`}>
        <svg className="dial-art" viewBox="0 0 360 360" aria-hidden="true">
          <circle className="dial-track" cx="180" cy="180" r="176" />
          <circle
            className="dial-progress"
            cx="180"
            cy="180"
            r="176"
            pathLength="100"
            strokeDasharray="100"
            strokeDashoffset={100 - (left / timer.duration) * 100}
            transform="rotate(-90 180 180)"
          />
          <g className="dial-ticks">{ticks}</g>
        </svg>
        <div className="dial-content">
          <span
            className="timer-value"
            role="timer"
            aria-label={`${MODE_LABELS[timer.mode]}: ${clockText(left)}`}
            aria-live="off"
          >
            {clockText(left)}
          </span>
          <span className="timer-caption">
            {timer.status === 'paused'
              ? 'A TU RITMO'
              : timer.status === 'running'
                ? timer.mode === 'focus'
                  ? 'ESTÁS AQUÍ. ES SUFICIENTE.'
                  : 'RECARGANDO ENERGÍA'
                : 'TODO EMPIEZA AQUÍ'}
          </span>
        </div>
      </div>
      {activeTask ? (
        <p className="current-task">
          <span className="small-dot" />
          {activeTask}
        </p>
      ) : null}
      <div className="timer-controls">
        <button className="primary start-button" onClick={toggle}>
          <Icon name={timer.status === 'running' ? 'pause' : 'play'} size={23} />
          {timer.status === 'running'
            ? 'Pausar'
            : timer.status === 'paused'
              ? 'Continuar'
              : 'Comenzar'}
        </button>
        <button
          className="reset-button icon-button"
          aria-label="Reiniciar temporizador"
          disabled={timer.status === 'idle'}
          onClick={() => setConfirm('reset')}
        >
          <Icon name="reset" size={24} />
        </button>
      </div>
      <p className="keyboard-tip">
        <kbd>Espacio</kbd> para empezar o pausar
      </p>
      {confirm ? (
        <Dialog title="¿Empezamos de nuevo?" onClose={() => setConfirm(null)}>
          <p className="dialog-copy">
            Esta sesión está en marcha. Si{' '}
            {confirm === 'reset' ? 'la reinicias' : 'cambias de modo'}, su tiempo no se añadirá al
            historial. Tus sesiones completadas se conservan.
          </p>
          <div className="dialog-actions">
            <button className="secondary" onClick={() => setConfirm(null)}>
              Seguir aquí
            </button>
            <button
              className="primary"
              onClick={() => {
                void dispatch(
                  confirm === 'reset' ? { type: 'reset' } : { type: 'mode', mode: confirm },
                );
                setConfirm(null);
              }}
            >
              {' '}
              {confirm === 'reset' ? 'Reiniciar' : 'Cambiar de modo'}
            </button>
          </div>
        </Dialog>
      ) : null}
    </section>
  );
}
