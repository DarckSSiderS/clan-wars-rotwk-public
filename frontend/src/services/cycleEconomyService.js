import api from './api';
const base = (season, clan) => `/campaign/cycles/economy/seasons/${encodeURIComponent(season)}/clans/${encodeURIComponent(clan)}`;
export const cycleEconomyService = {
  async context(season, clan, config) { return (await api.get(`${base(season, clan)}/context`, config)).data; },
  async command(season, clan, action, payload) {
    const url = `${base(season, clan)}/${action}`;
    return (await (action === 'active-relics' ? api.put(url, payload) : api.post(url, payload))).data;
  },
};
