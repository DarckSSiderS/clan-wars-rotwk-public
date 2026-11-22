import api from './api';

export const presenceService = {
  async getMany(userIds) {
    const params = new URLSearchParams();
    [...new Set(userIds.map(Number).filter(Number.isInteger))]
      .slice(0, 100)
      .forEach((userId) => params.append('user_ids', String(userId)));
    if (!params.size) return [];
    const response = await api.get(`/presence?${params.toString()}`);
    return response.data.items || [];
  },

  async requestOnline(userId) {
    const response = await api.post(`/presence/${userId}/online-request`);
    return response.data;
  },
};
