import api from './api';

const base = '/campaign/cycles';
export const cycleCampaignService = {
  async getOwnClan(config) {
    return (await api.get('/clans/my', config)).data;
  },
  async getCurrent(config) {
    return (await api.get(`${base}/current`, config)).data;
  },
  async getCycle(cycleId, config) {
    return (await api.get(`${base}/${encodeURIComponent(cycleId)}`, config)).data;
  },
  async getMap(cycleId, config) {
    return (await api.get(`${base}/${encodeURIComponent(cycleId)}/map`, config)).data;
  },
  async getInterception(cycleId, dispatchId, config) {
    return (await api.get(`${base}/${encodeURIComponent(cycleId)}/interception`, {
      ...config, params: { ...config?.params, dispatch_id: dispatchId },
    })).data;
  },
  async getClanHistory(clanId, config) {
    return (await api.get(`${base}/clans/${encodeURIComponent(clanId)}/history`, config)).data;
  },
  async getPreparation(cycleId, clanId, config) {
    return (await api.get(`${base}/${encodeURIComponent(cycleId)}/clans/${encodeURIComponent(clanId)}/preparation`, config)).data;
  },
  async preparationCommand(cycleId, clanId, action, payload) {
    return (await api.post(`${base}/${encodeURIComponent(cycleId)}/clans/${encodeURIComponent(clanId)}/${action}`, payload)).data;
  },
  async getPlanning(cycleId, clanId, config) {
    return (await api.get(`${base}/${encodeURIComponent(cycleId)}/clans/${encodeURIComponent(clanId)}/planning`, config)).data;
  },
  async savePlan(cycleId, clanId, payload) {
    return (await api.put(`${base}/${encodeURIComponent(cycleId)}/clans/${encodeURIComponent(clanId)}/plan`, payload)).data;
  },
  async getReinforcements(cycleId, clanId, config) {
    return (await api.get(`${base}/${encodeURIComponent(cycleId)}/clans/${encodeURIComponent(clanId)}/reinforcements/context`, config)).data;
  },
  async requestHelp(cycleId, clanId, payload) {
    return (await api.post(`${base}/${encodeURIComponent(cycleId)}/clans/${encodeURIComponent(clanId)}/reinforcements/requests`, payload)).data;
  },
  async dispatch(cycleId, clanId, payload) {
    return (await api.post(`${base}/${encodeURIComponent(cycleId)}/clans/${encodeURIComponent(clanId)}/reinforcements/dispatches`, payload)).data;
  },
  async getBattles(cycleId, config) {
    return (await api.get(`${base}/${encodeURIComponent(cycleId)}/battles`, config)).data.battles;
  },
  async getBattle(battleId, config) {
    return (await api.get(`${base}/battles/${encodeURIComponent(battleId)}`, config)).data;
  },
  async getLateReplays(battleId, afterId = 0, config) {
    return (await api.get(`${base}/battles/${encodeURIComponent(battleId)}/late-replays`, {
      ...config, params: { ...config?.params, after_id: afterId },
    })).data;
  },
  async previewLateReplay(battleId, matchId, config) {
    return (await api.get(`${base}/battles/${encodeURIComponent(battleId)}/late-replays/${encodeURIComponent(matchId)}`, config)).data;
  },
  async decideLateReplay(battleId, matchId, payload, config) {
    return (await api.post(`${base}/battles/${encodeURIComponent(battleId)}/late-replays/${encodeURIComponent(matchId)}`, payload, config)).data;
  },
  async review(battleId, payload) {
    return (await api.post(`${base}/battles/${encodeURIComponent(battleId)}/review`, payload)).data;
  },
  async adjust(battleId, payload) {
    return (await api.post(`${base}/battles/${encodeURIComponent(battleId)}/adjustments`, payload)).data;
  },
  async previewOwnership(battleId) {
    return (await api.get(`${base}/battles/${encodeURIComponent(battleId)}/ownership`)).data;
  },
  async correctOwnership(battleId, payload) {
    return (await api.post(`${base}/battles/${encodeURIComponent(battleId)}/ownership`, payload)).data;
  },
};

export default cycleCampaignService;
