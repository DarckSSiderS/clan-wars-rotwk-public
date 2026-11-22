import api from './api';

export const statisticsService = {
  async getHomeSummary() {
    const response = await api.get('/statistics/home');
    return response.data;
  },
};
