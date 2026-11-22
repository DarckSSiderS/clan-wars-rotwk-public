import api from './api';

class LocalizationService {
  constructor() {
    this.cache = new Map(); // Кэш для хранения переводов
    this.currentLanguage = localStorage.getItem('language') || 'ru';
  }

  // Установить язык
  setLanguage(language) {
    this.currentLanguage = language;
    localStorage.setItem('language', language);
    this.cache.clear(); // Очищаем кэш при смене языка
  }

  // Получить текущий язык
  getLanguage() {
    return this.currentLanguage;
  }

  // Получить текст по идентификатору
  async getText(identifier, language = null) {
    const lang = language || this.currentLanguage;
    
    // Проверяем кэш
    const cacheKey = `${identifier}_${lang}`;
    if (this.cache.has(cacheKey)) {
      return this.cache.get(cacheKey);
    }

    try {
      const response = await api.get(`/localization/text/${identifier}`, {
        params: { language: lang }
      });
      
      const text = response.data.text;
      this.cache.set(cacheKey, text);
      return text;
    } catch (error) {
      console.error(`Ошибка получения текста для ${identifier}:`, error);
      return identifier; // Возвращаем идентификатор как fallback
    }
  }

  // Получить все тексты для страницы
  async getPageTexts(webpage, language = null) {
    const lang = language || this.currentLanguage;
    
    // Проверяем кэш
    const cacheKey = `${webpage}_${lang}`;
    if (this.cache.has(cacheKey)) {
      const cachedTexts = this.cache.get(cacheKey);
      return cachedTexts;
    }

    try {
      const response = await api.get(`/localization/webpage/${webpage}/texts`, {
        params: { language: lang }
      });
      
      const texts = response.data.texts;
      this.cache.set(cacheKey, texts);
      
      // Также кэшируем отдельные тексты
      Object.entries(texts).forEach(([identifier, text]) => {
        const textCacheKey = `${identifier}_${lang}`;
        this.cache.set(textCacheKey, text);
      });
      
      return texts;
    } catch (error) {
      console.error(`Ошибка получения текстов для страницы ${webpage}:`, error);
      return {};
    }
  }

  // Получить все записи локализации
  async getAllLocalizations() {
    try {
      const response = await api.get('/localization/');
      return response.data;
    } catch (error) {
      console.error('Ошибка получения всех записей локализации:', error);
      return [];
    }
  }

  // Получить записи локализации для страницы
  async getLocalizationsByWebpage(webpage) {
    try {
      const response = await api.get(`/localization/webpage/${webpage}`);
      return response.data;
    } catch (error) {
      console.error(`Ошибка получения локализации для страницы ${webpage}:`, error);
      return [];
    }
  }

  // Создать новую запись локализации
  async createLocalization(localization) {
    try {
      const response = await api.post('/localization/', localization);
      return response.data;
    } catch (error) {
      console.error('Ошибка создания записи локализации:', error);
      throw error;
    }
  }

  // Обновить запись локализации
  async updateLocalization(identifier, updates) {
    try {
      const response = await api.put(`/localization/${identifier}`, updates);
      return response.data;
    } catch (error) {
      console.error(`Ошибка обновления записи локализации ${identifier}:`, error);
      throw error;
    }
  }

  // Удалить запись локализации
  async deleteLocalization(identifier) {
    try {
      const response = await api.delete(`/localization/${identifier}`);
      return response.data;
    } catch (error) {
      console.error(`Ошибка удаления записи локализации ${identifier}:`, error);
      throw error;
    }
  }

  // Утилита для быстрого получения текста (синхронная версия из кэша)
  getTextSync(identifier, language = null) {
    const lang = language || this.currentLanguage;
    const cacheKey = `${identifier}_${lang}`;
    const cachedText = this.cache.get(cacheKey);
    return cachedText || identifier;
  }

  // Утилита для получения текстов страницы (синхронная версия из кэша)
  getPageTextsSync(webpage, language = null) {
    const lang = language || this.currentLanguage;
    const cacheKey = `${webpage}_${lang}`;
    return this.cache.get(cacheKey) || {};
  }
}

export const localizationService = new LocalizationService();
