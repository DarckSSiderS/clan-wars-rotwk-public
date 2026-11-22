import api from './api';

export const clanService = {
  // Получение списка всех кланов
  async getClans() {
    const response = await api.get('/clans/');
    return response.data;
  },

  async getMapColorState(clanId = null) {
    const response = await api.get('/clans/map-colors', {
      params: clanId ? { clan_id: clanId } : undefined,
    });
    return response.data;
  },

  // Получение информации о клане
  async getClan(clanId) {
    const response = await api.get(`/clans/${clanId}`);
    return response.data;
  },

  // Получение клана текущего пользователя
  async getMyClan() {
    const response = await api.get('/clans/my');
    return response.data;
  },

  // Создание клана
  async createClan(clanData) {
    const response = await api.post('/clans/', clanData);
    return response.data;
  },

  async createClanWithAssets(clanData, avatar, mapEmblem) {
    const formData = new FormData();
    Object.entries(clanData).forEach(([key, value]) => {
      formData.append(key, value ?? '');
    });
    if (avatar) formData.append('avatar', avatar);
    if (mapEmblem) formData.append('map_emblem', mapEmblem);
    const response = await api.post('/clans/with-assets', formData);
    return response.data;
  },

  // Обновление клана
  async updateClan(clanId, clanData) {
    const response = await api.put(`/clans/${clanId}`, clanData);
    return response.data;
  },

  // Получение участников клана
  async getClanMembers(clanId) {
    const response = await api.get(`/clans/${clanId}/members`);
    return response.data;
  },

  async getClanAssets(clanId) {
    const response = await api.get(`/clans/${clanId}/assets`);
    return response.data;
  },

  async purchaseClanAsset(clanId, assetId) {
    const response = await api.post(`/clans/${clanId}/assets/purchase`, { asset_id: assetId });
    return response.data;
  },

  async updateRelicLoadout(clanId, assetIds) {
    const response = await api.put(`/clans/${clanId}/assets/loadout`, {
      asset_ids: assetIds,
    });
    return response.data;
  },

  async getAdminClanAssets() {
    const response = await api.get('/clans/assets/admin');
    return response.data;
  },

  async createClanAsset(assetData) {
    const response = await api.post('/clans/assets/admin', assetData);
    return response.data;
  },

  async updateClanAsset(assetId, assetData) {
    const response = await api.put(`/clans/assets/admin/${assetId}`, assetData);
    return response.data;
  },

  async disableClanAsset(assetId) {
    const response = await api.delete(`/clans/assets/admin/${assetId}`);
    return response.data;
  },

  async setTrader(clanId, userId, isTrader) {
    const response = await api.put(`/clans/${clanId}/members/${userId}/trader`, { is_trader: isTrader });
    return response.data;
  },

  async setMemberRole(clanId, userId, role) {
    const response = await api.put(
      `/clans/${clanId}/members/${userId}/role`,
      { role },
    );
    return response.data;
  },

  async setMemberWarlord(clanId, userId, isWarlord) {
    const response = await api.put(
      `/clans/${clanId}/members/${userId}/warlord`,
      { is_warlord: isWarlord },
    );
    return response.data;
  },

  async getMarket(clanId) {
    const response = await api.get('/clans/market/offers', {
      params: clanId ? { clan_id: clanId } : {},
    });
    return response.data;
  },

  async createMarketOffer(offer) {
    const response = await api.post('/clans/market/offers', offer);
    return response.data;
  },

  async acceptMarketOffer(offerId, accepterClanId) {
    const response = await api.post(`/clans/market/offers/${offerId}/accept`, {
      accepter_clan_id: accepterClanId,
    });
    return response.data;
  },

  async cancelMarketOffer(offerId) {
    const response = await api.post(`/clans/market/offers/${offerId}/cancel`);
    return response.data;
  },

  async getClanEconomy(clanId) {
    const response = await api.get(`/clans/${clanId}/economy`);
    return response.data;
  },

  // Приглашение пользователя в клан
  async inviteUser(clanId, userId) {
    const response = await api.post(`/clans/${clanId}/invite`, { invitee_id: userId });
    return response.data;
  },

  async appointAdminClanMember(clanId, userId) {
    const response = await api.post(`/clans/${clanId}/admin-members/${userId}`);
    return response.data;
  },

  async removeAdminClanMember(clanId, userId) {
    const response = await api.delete(`/clans/${clanId}/admin-members/${userId}`);
    return response.data;
  },

  async resetAdminClanSandbox(clanId) {
    const response = await api.post(`/clans/${clanId}/admin-sandbox/reset`);
    return response.data;
  },

  // Получение приглашений пользователя
  async getInvites() {
    const response = await api.get('/clans/invites/');
    return response.data;
  },

  // Ответ на приглашение
  async respondToInvite(inviteId, status) {
    const apiResponse = await api.put(`/clans/invites/${inviteId}?status=${status}`);
    return apiResponse.data;
  },

  // Получение заявок в клан
  async getApplications(clanId) {
    const response = await api.get(`/clans/${clanId}/applications`);
    return response.data;
  },

  // Загрузить аватар клана
  async uploadAvatar(clanId, formData) {
    const response = await api.post(`/clans/${clanId}/avatar`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // Исключить участника из клана
  async kickMember(clanId, userId) {
    const response = await api.delete(`/clans/${clanId}/members/${userId}`);
    return response.data;
  },

  // Подача заявки в клан
  async applyToClan(clanId, message) {
    const response = await api.post(`/clans/${clanId}/applications`, { message });
    return response.data;
  },

  // Удаление клана
  async deleteClan(clanId) {
    const response = await api.delete(`/clans/${clanId}`);
    return response.data;
  },

  // Выход из клана
  async leaveClan(clanId) {
    const response = await api.post(`/clans/${clanId}/leave`);
    return response.data;
  },

  // Назначение лидера клана
  async transferLeadership(clanId, userId) {
    const response = await api.post(`/clans/${clanId}/transfer-leadership`, { user_id: userId });
    return response.data;
  },

  // Загрузка аватара клана
  async uploadClanAvatar(clanId, file) {
    const formData = new FormData();
    formData.append('avatar', file);

    const response = await api.post(`/clans/${clanId}/avatar`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  // Ответ на заявку в клан
  async respondToApplication(applicationId, status) {
    const response = await api.put(`/clans/applications/${applicationId}?status=${status}`);
    return response.data;
  }
}; 
