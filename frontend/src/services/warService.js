import api from './api';

export const warService = {
  async getWars() {
    const response = await api.get('/wars/', { params: { limit: 500 } });
    return response.data;
  },

  async getActiveWars() {
    const response = await api.get('/wars/active/');
    return response.data;
  },

  async getClanWars(clanId) {
    const response = await api.get(`/wars/clan/${clanId}`);
    return response.data;
  },

  async getWar(warId) {
    const response = await api.get(`/wars/${warId}`);
    return response.data;
  },

  async getWarReadiness(clanId) {
    const response = await api.get(`/clans/${clanId}/war-readiness`);
    return response.data;
  },

  async createWar({
    territoryId,
    sourceTerritoryId = null,
    squadMemberIds,
    warlordUserId,
    expectedRuleVersion,
  }) {
    const response = await api.post('/wars/', {
      territory_id: territoryId,
      source_territory_id: sourceTerritoryId,
      squad_member_ids: squadMemberIds,
      warlord_user_id: warlordUserId,
      expected_rule_version: expectedRuleVersion,
    });
    return response.data;
  },

  async getAdminWar(warId) {
    const response = await api.get(`/admin/clan-warfare/wars/${warId}`);
    return response.data;
  },
};
