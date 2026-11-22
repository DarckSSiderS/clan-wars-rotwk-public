import api from './api';

export const diplomacyService = {
  async list(clanId = null, config = {}) {
    const response = await api.get('/clans/diplomacy', {
      ...config,
      params: clanId ? { clan_id: clanId } : undefined,
    });
    return response.data;
  },

  async act(clanId, otherClanId, action, note = '') {
    const response = await api.post(`/clans/${clanId}/diplomacy/${otherClanId}`, {
      action,
      note: note.trim() || null,
    });
    return response.data;
  },
};
