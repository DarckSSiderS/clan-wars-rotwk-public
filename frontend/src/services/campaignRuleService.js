import api from './api';

export const campaignRuleService = {
  async getPublic(seasonId) {
    const response = await api.get('/campaign/rules/public', {
      params: seasonId ? { season_id: seasonId } : undefined,
    });
    return response.data;
  },
  getCurrent: () => api.get('/admin/campaign-rules'),
  getHistory: () => api.get('/admin/campaign-rules/history'),
  update: (payload) => api.put('/admin/campaign-rules', payload),
  restore: (version, payload) => (
    api.post(`/admin/campaign-rules/${version}/restore`, payload)
  ),
};

export default campaignRuleService;
