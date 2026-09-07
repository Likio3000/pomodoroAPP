import { StrictMode, Component, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { LanguageProvider, useI18n } from './i18n/context';
import './styles.css';
function FailureScreen() {
  const { t } = useI18n();
  return (
    <main className="loading-state">
      <span className="brand">senda.</span>
      <h1>{t('failedTitle')}</h1>
      <p>{t('dataSafe')}</p>
      <button className="primary" onClick={() => location.reload()}>
        {t('reopen')}
      </button>
    </main>
  );
}
class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <FailureScreen /> : this.props.children;
  }
}
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LanguageProvider>
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </LanguageProvider>
  </StrictMode>,
);
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    void navigator.serviceWorker.register('./sw.js').catch(() => {
      /* Online app remains usable if offline installation is unavailable. */
    });
  });
}
