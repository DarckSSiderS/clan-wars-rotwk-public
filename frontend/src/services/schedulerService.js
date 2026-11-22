import api from './api';

export const schedulerService = {
  async getAdminOverview(status = '') {
    const response = await api.get('/scheduler/admin-overview', {
      params: { status: status || undefined, limit: 200 },
    });
    return response.data;
  },

  async updateCampaignSettings(settings) {
    const response = await api.put('/scheduler/campaign-settings', settings);
    return response.data;
  },

  async pauseCampaign(reason) {
    const response = await api.post('/scheduler/campaign/pause', { reason });
    return response.data;
  },

  async resumeCampaign(reason) {
    const response = await api.post('/scheduler/campaign/resume', { reason });
    return response.data;
  },

  async fetchMatches(limit = 15) {
    const response = await api.post('/scheduler/fetch-matches', null, {
      params: { limit },
    });
    return response.data;
  },

  async getReplayDetail(replayId) {
    const response = await api.get(`/scheduler/replays/${encodeURIComponent(replayId)}`);
    return response.data;
  },

  async archiveReplay(replayId) {
    const response = await api.post(`/scheduler/replays/${encodeURIComponent(replayId)}/download`);
    return response.data;
  },

  async getReplayFile(replayId) {
    const response = await api.get(
      `/scheduler/replays/${encodeURIComponent(replayId)}/file`,
      { responseType: 'blob' },
    );
    return response.data;
  },
};
