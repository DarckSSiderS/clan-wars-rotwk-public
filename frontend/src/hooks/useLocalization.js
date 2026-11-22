import { useCallback } from 'react';
import { useLocalizationContext } from '../contexts/LocalizationContext';

export const useLocalization = () => {
  const {
    language,
    changeLanguage,
    getLocalizedText,
    loadPageTexts,
  } = useLocalizationContext();

  const getText = useCallback(async (identifier, fallback = null, params = {}) => (
    getLocalizedText(identifier, fallback, params)
  ), [getLocalizedText]);

  return {
    texts: {},
    loading: false,
    language,
    getText,
    getTextSync: getLocalizedText,
    changeLanguage,
    loadPageTexts,
  };
};
