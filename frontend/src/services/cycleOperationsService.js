import api from './api';

const templatePath = (cycleId, clanId) => `/campaign/cycles/${encodeURIComponent(cycleId)}/clans/${encodeURIComponent(clanId)}/defence-template`;

export const cycleOperationsService = {
  async getDefenceTemplate(cycleId, clanId) {
    return (await api.get(templatePath(cycleId, clanId))).data;
  },
  async saveDefenceTemplate(cycleId, clanId, payload) {
    return (await api.put(templatePath(cycleId, clanId), payload)).data;
  },
};
