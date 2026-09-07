import { useI18n } from '../i18n/context';
import { dispatch } from '../store';
export function LanguageSwitch() {
  const { language, t } = useI18n();
  return (
    <div className="language-switch" role="group" aria-label={t('language')}>
      <button
        type="button"
        lang="es"
        aria-label="Español"
        aria-pressed={language === 'es'}
        onClick={() => {
          if (language !== 'es') void dispatch({ type: 'language', language: 'es' });
        }}
      >
        ES
      </button>
      <button
        type="button"
        lang="en"
        aria-label="English"
        aria-pressed={language === 'en'}
        onClick={() => {
          if (language !== 'en') void dispatch({ type: 'language', language: 'en' });
        }}
      >
        EN
      </button>
    </div>
  );
}
