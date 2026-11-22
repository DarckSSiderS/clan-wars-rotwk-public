import api from './api';

export const userService = {
  // Получение текущего пользователя
  async getCurrentUser() {
    const response = await api.get('/users/me');
    return response.data;
  },

  // Обновление профиля пользователя
  async updateProfile(userId, userData) {
    const response = await api.put(`/users/${userId}`, userData);
    return response.data;
  },

  // Обновление баланса пользователя
  async updateBalance(userId, amount) {
    const response = await api.put(`/users/${userId}/balance`, { amount });
    return response.data;
  },

  // Загрузка аватара пользователя
  async uploadAvatar(userId, file, cropData = null) {
    const formData = new FormData();
    formData.append('avatar', file);
    
    if (cropData) {
      formData.append('crop_x', cropData.x);
      formData.append('crop_y', cropData.y);
      formData.append('crop_width', cropData.width);
      formData.append('crop_height', cropData.height);
    }

    const response = await api.post(`/users/${userId}/avatar`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // Получение списка пользователей
  async getUsers(skip = 0, limit = 100) {
    const response = await api.get(`/users/?skip=${skip}&limit=${limit}`);
    return response.data;
  },

  // Получение пользователя по ID
  async getUser(userId) {
    const response = await api.get(`/users/${userId}`);
    return response.data;
  },

  // Поиск пользователей по имени
  async searchUsersByUsername(username) {
    const response = await api.get(`/users/search/${username}`);
    return response.data;
  },

  // Получение статистики пользователя
  async getUserStats(userId, clanId = null) {
    const response = await api.get(`/users/${userId}/stats`, {
      params: clanId ? { clan_id: clanId } : undefined,
    });
    return response.data;
  },

  // Поиск пользователей без клана
  async searchUsersWithoutClan(username) {
    const response = await api.get(`/users/search/clanless/${username}`);
    return response.data;
  }
};
