import { apiFetch } from './apiFetch';

// Сервис для проверки статуса стримов
class StreamService {
  // Проверка статуса Twitch стрима
  async checkTwitchStream(channelName) {
    try {
      // Извлекаем имя канала из URL
      const channel = this.extractTwitchChannel(channelName);
      if (!channel) return false;

      // Используем Twitch API через прокси
      const response = await apiFetch(`/api/v1/streams/twitch/${channel}`);

      if (response.ok) {
        const data = await response.json();
        return data.is_live || false;
      }
      return false;
    } catch (error) {
      console.error('Error checking Twitch stream:', error);
      return false;
    }
  }

  // Проверка статуса YouTube стрима
  async checkYouTubeStream(channelUrl) {
    try {
      // Извлекаем ID канала из URL
      const channelId = this.extractYouTubeChannelId(channelUrl);
      if (!channelId) return false;

      // Используем YouTube API через прокси
      const response = await apiFetch(`/api/v1/streams/youtube/${channelId}`);

      if (response.ok) {
        const data = await response.json();
        return data.is_live || false;
      }
      return false;
    } catch (error) {
      console.error('Error checking YouTube stream:', error);
      return false;
    }
  }

  // Извлечение имени канала из Twitch URL
  extractTwitchChannel(url) {
    if (!url) return null;
    
    // Поддерживаемые форматы:
    // https://twitch.tv/username
    // https://www.twitch.tv/username
    // twitch.tv/username
    const match = url.match(/(?:https?:\/\/(?:www\.)?twitch\.tv\/|twitch\.tv\/)([^/?]+)/);
    return match ? match[1] : null;
  }

  // Извлечение ID канала из YouTube URL
  extractYouTubeChannelId(url) {
    if (!url) return null;
    
    // Поддерживаемые форматы:
    // https://youtube.com/@username
    // https://www.youtube.com/@username
    // https://youtube.com/channel/UC...
    // https://www.youtube.com/channel/UC...
    
    // Для @username формата
    const usernameMatch = url.match(/(?:https?:\/\/(?:www\.)?youtube\.com\/@)([^/?]+)/);
    if (usernameMatch) {
      return usernameMatch[1];
    }
    
    // Для channel/UC... формата
    const channelMatch = url.match(/(?:https?:\/\/(?:www\.)?youtube\.com\/channel\/)([^/?]+)/);
    if (channelMatch) {
      return channelMatch[1];
    }
    
    return null;
  }
}

export default new StreamService(); 
