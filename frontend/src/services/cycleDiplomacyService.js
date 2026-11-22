import api from './api';

const path = cycleId => `/campaign/cycles/diplomacy/cycles/${encodeURIComponent(cycleId)}`;
export const cycleDiplomacyService = {
  async getClanDirectory(config) {
    const clans = [];
    let page;
    do {
      page = (await api.get('/clans/', { ...config, params: { skip: clans.length, limit: 100 } })).data;
      clans.push(...page);
    } while (page.length === 100);
    return clans;
  },
  async getRelations(cycleId, config) {
    return (await api.get(path(cycleId), config)).data.relations;
  },
  async getOwn(cycleId, clanId, config) {
    return (await api.get(`${path(cycleId)}/clans/${encodeURIComponent(clanId)}`, config)).data;
  },
  async act(cycleId, clanId, payload, config) {
    // Pydantic's integer field accepts decimal strings without JS Number rounding.
    return (await api.post(`${path(cycleId)}/clans/${encodeURIComponent(clanId)}`, payload, config)).data;
  },
};
export default cycleDiplomacyService;
