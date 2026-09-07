import { createContext, useContext, useEffect, useMemo, type ReactNode } from 'react';
import { useStore } from '../store';
import { translate, type Language, type MessageKey, type Values } from './messages';
function translator(language: Language) {
  return {
    language,
    locale: language === 'es' ? 'es-ES' : 'en-GB',
    t: (key: MessageKey, values?: Values) => translate(language, key, values),
  };
}
const Context = createContext(translator('es'));
export function LanguageProvider({ children }: { children: ReactNode }) {
  const { state } = useStore();
  const language = state?.language ?? 'es';
  const value = useMemo(() => translator(language), [language]);
  useEffect(() => {
    document.documentElement.lang = language;
    document
      .querySelector('meta[name="description"]')
      ?.setAttribute('content', value.t('description'));
    document
      .querySelector('link[rel="manifest"]')
      ?.setAttribute(
        'href',
        language === 'en' ? './manifest.en.webmanifest' : './manifest.webmanifest',
      );
  }, [language, value]);
  return <Context value={value}>{children}</Context>;
}
export function useI18n() {
  return useContext(Context);
}
