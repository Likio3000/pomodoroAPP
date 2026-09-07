import { useI18n } from './i18n/context';
import { useEffect, useState } from 'react';
import { useStore, dispatch, dismissCompletion, dismissError } from './store';
import { Timer } from './components/Timer';
import { Tasks } from './components/Tasks';
import { Metrics, Progress } from './components/Progress';
import { Settings } from './components/Settings';
import { LanguageSwitch } from './components/LanguageSwitch';
import { errorText } from './i18n/messages';
import { Icon } from './components/Icon';
import { clockText, remaining, type Timer as TimerState } from './domain/model';
function DocumentTitle({ timer }: { timer: TimerState }) {
  const { t, language } = useI18n();
  useEffect(() => {
    const update = () => {
      document.title =
        timer.status === 'idle'
          ? `Senda — ${t('title')}`
          : `${clockText(remaining(timer, Date.now()))} · ${t(`mode.${timer.mode}`)} — Senda`;
    };
    update();
    const id = setInterval(update, 1000);
    return () => clearInterval(id);
  }, [timer, language, t]);
  return null;
}
function RunningNotice({ onReturn }: { onReturn: () => void }) {
  const { t } = useI18n();
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
      {state.timer.status === 'paused' ? t('pausedNotice') : t('runningNotice')}
      <Icon name="arrow" size={16} />
    </button>
  );
}
export default function App() {
  const { t, language } = useI18n();
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
        <span className="brand">senda.</span>
        <h1>{error ? t('wait') : t('loadingTitle')}</h1>
        <p>{error ? errorText(language, error) : t('loading')}</p>
        {error ? (
          <>
            <p className="muted">{t('storageHelp')}</p>
            <button className="primary" onClick={() => void dispatch({ type: 'settle' })}>
              {t('tryAgain')}
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
        {t('skip')}
      </a>
      <header className="app-header">
        <a className="brand" href="#enfoque" aria-label={t('home')}>
          senda.
        </a>
        <nav aria-label={t('navigation')}>
          <a href="#enfoque" aria-current={page === 'focus' ? 'page' : undefined}>
            {t('focus')}
          </a>
          <a href="#progreso" aria-current={page === 'progress' ? 'page' : undefined}>
            {t('progress')}
          </a>
        </nav>
        <div className="header-tools">
          <LanguageSwitch />
          <button
            className="settings-button secondary"
            aria-label={t('settings')}
            onClick={() => setSettings(true)}
          >
            <Icon name="settings" size={20} />
            <span>{t('settings')}</span>
          </button>
        </div>
      </header>
      {error ? (
        <div className="error-banner" role="alert">
          <p>{errorText(language, error)}</p>
          <button className="text-button" onClick={() => void dispatch()}>
            {t('retry')}
          </button>
          <button className="icon-button" aria-label={t('closeNotice')} onClick={dismissError}>
            <Icon name="close" />
          </button>
        </div>
      ) : null}
      {completion ? (
        <div className="completion-banner" role="status">
          <Icon name="check" />
          <p>{t(completion)}</p>
          <button
            className="text-button"
            onClick={() => {
              navigate('focus');
              dismissCompletion();
            }}
          >
            {t('backToTimer')}
            <Icon name="arrow" size={17} />
          </button>
          <button
            className="icon-button"
            aria-label={t('closeCompletion')}
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
        <span>{t('footer')}</span>
        <span>
          {t('saved')} <span className="status-dot" aria-hidden="true" />
        </span>
      </footer>
      {settings ? <Settings state={state} onClose={() => setSettings(false)} /> : null}
    </>
  );
}
