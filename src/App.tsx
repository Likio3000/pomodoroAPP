import { useEffect, useState } from 'react';
import { useStore, dispatch, dismissCompletion, dismissError } from './store';
import { Timer } from './components/Timer';
import { Tasks } from './components/Tasks';
import { Metrics, Progress } from './components/Progress';
import { Settings } from './components/Settings';
import { Icon } from './components/Icon';
import { clockText, remaining, MODE_LABELS, type Timer as TimerState } from './domain/model';
function DocumentTitle({ timer }: { timer: TimerState }) {
  useEffect(() => {
    const update = () => {
      document.title =
        timer.status === 'idle'
          ? 'pomodoro. — Una cosa a la vez'
          : `${clockText(remaining(timer, Date.now()))} · ${MODE_LABELS[timer.mode]} — pomodoro.`;
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [timer]);
  return null;
}
function RunningNotice({ onReturn }: { onReturn: () => void }) {
  const { state } = useStore();
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  if (!state || state.timer.status === 'idle') return null;
  return (
    <button className="running-notice" onClick={onReturn}>
      <span className="small-dot" />
      {clockText(remaining(state.timer, now))} ·{' '}
      {state.timer.status === 'paused' ? 'Sesión pausada' : 'Tu sesión sigue en marcha'}
      <Icon name="arrow" size={16} />
    </button>
  );
}
export default function App() {
  const { state, error, completion } = useStore();
  const [page, setPage] = useState<'focus' | 'progress'>(
    location.hash === '#progreso' ? 'progress' : 'focus',
  );
  const [settings, setSettings] = useState(false);
  useEffect(() => {
    const sync = () => setPage(location.hash === '#progreso' ? 'progress' : 'focus');
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);
  const navigate = (next: 'focus' | 'progress') => {
    location.hash = next === 'focus' ? 'enfoque' : 'progreso';
    setPage(next);
  };
  if (!state)
    return (
      <main className="loading-state">
        <span className="brand">pomodoro.</span>
        <h1>{error ? 'Un momento.' : 'Haciendo espacio…'}</h1>
        <p>{error ?? 'Preparando tu espacio de enfoque.'}</p>
        {error ? (
          <>
            <p className="muted">
              Necesitamos almacenamiento local para guardar tus sesiones. Revisa los permisos del
              navegador o el espacio disponible.
            </p>
            <button className="primary" onClick={() => void dispatch({ type: 'settle' })}>
              Volver a intentar
            </button>
          </>
        ) : null}
      </main>
    );
  return (
    <>
      <DocumentTitle timer={state.timer} />
      <a
        className="skip-link"
        href="#main-content"
        onClick={(e) => {
          e.preventDefault();
          const main = document.getElementById('main-content');
          main?.setAttribute('tabindex', '-1');
          main?.focus();
        }}
      >
        Saltar al contenido
      </a>
      <header className="app-header">
        <a className="brand" href="#enfoque" aria-label="Pomodoro, inicio">
          pomodoro.
        </a>
        <nav aria-label="Navegación principal">
          <a href="#enfoque" aria-current={page === 'focus' ? 'page' : undefined}>
            Enfoque
          </a>
          <a href="#progreso" aria-current={page === 'progress' ? 'page' : undefined}>
            Progreso
          </a>
        </nav>
        <button
          className="settings-button secondary"
          aria-label="Ajustes"
          onClick={() => setSettings(true)}
        >
          <Icon name="settings" size={20} />
          <span>Ajustes</span>
        </button>
      </header>
      {error ? (
        <div className="error-banner" role="alert">
          <p>{error}</p>
          <button className="text-button" onClick={() => void dispatch()}>
            Reintentar
          </button>
          <button className="icon-button" aria-label="Cerrar aviso" onClick={dismissError}>
            <Icon name="close" />
          </button>
        </div>
      ) : null}
      {completion ? (
        <div className="completion-banner" role="status">
          <Icon name="check" />
          <p>{completion}</p>
          <button
            className="text-button"
            onClick={() => {
              navigate('focus');
              dismissCompletion();
            }}
          >
            Volver al reloj
            <Icon name="arrow" size={17} />
          </button>
          <button
            className="icon-button"
            aria-label="Cerrar aviso de sesión"
            onClick={dismissCompletion}
          >
            <Icon name="close" />
          </button>
        </div>
      ) : null}
      {page === 'focus' ? (
        <>
          <main className="focus-layout" id="main-content">
            <Timer state={state} />
            <Tasks state={state} />
          </main>
          <Metrics state={state} />
        </>
      ) : (
        <>
          <RunningNotice onReturn={() => navigate('focus')} />
          <Progress state={state} />
        </>
      )}
      <footer className="app-footer">
        <span>Menos ruido. Más espacio.</span>
        <span>
          Guardado en este dispositivo <span className="status-dot" aria-hidden="true" />
        </span>
      </footer>
      {settings ? <Settings state={state} onClose={() => setSettings(false)} /> : null}
    </>
  );
}
