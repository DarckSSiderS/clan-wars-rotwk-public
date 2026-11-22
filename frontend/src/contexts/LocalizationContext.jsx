import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useAuth } from './AuthContext';
import { normalizeLanguage, translate } from '../i18n/messages';
import { apiFetch } from '../services/apiFetch';

const LocalizationContext = createContext(null);

export const useLocalizationContext = () => {
  const context = useContext(LocalizationContext);
  if (!context) {
    throw new Error('useLocalizationContext должен использоваться внутри LocalizationProvider');
  }
  return context;
};

export const LocalizationProvider = ({ children }) => {
  const { user } = useAuth();
  const appliedProfileRef = useRef(null);
  const [language, setLanguage] = useState(() => normalizeLanguage(
    localStorage.getItem('language') || navigator.language || 'ru',
  ));

  const getLocalizedText = useCallback((identifier, fallback = null, params = {}) => (
    translate(identifier, language, fallback, params)
  ), [language]);

  const changeLanguage = useCallback((nextLanguage) => {
    const normalized = normalizeLanguage(nextLanguage);
    setLanguage(normalized);
    localStorage.setItem('language', normalized);

    if (user?.id) {
      apiFetch(`/api/v1/users/${user.id}`, {
        method: 'PUT',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ language: normalized }),
      }).catch(() => {
        // Выбранный язык всё равно остаётся сохранённым в браузере.
      });
    }
  }, [user?.id]);

  useEffect(() => {
    document.documentElement.lang = language;
    document.title = 'ROTWK ClanWars';
  }, [language]);

  useEffect(() => {
    if (!user?.id || appliedProfileRef.current === user.id) return;
    appliedProfileRef.current = user.id;

    const savedLanguage = localStorage.getItem('language');
    const profileLanguage = normalizeLanguage(user.language);
    const selectedLanguage = savedLanguage
      ? normalizeLanguage(savedLanguage)
      : profileLanguage;

    setLanguage(selectedLanguage);
    localStorage.setItem('language', selectedLanguage);
  }, [user?.id, user?.language]);

  const value = useMemo(() => ({
    language,
    texts: {},
    loading: false,
    changeLanguage,
    loadPageTexts: async () => ({}),
    getTextSync: getLocalizedText,
    getLocalizedText,
    t: getLocalizedText,
  }), [language, changeLanguage, getLocalizedText]);

  return (
    <LocalizationContext.Provider value={value}>
      {children}
    </LocalizationContext.Provider>
  );
};
