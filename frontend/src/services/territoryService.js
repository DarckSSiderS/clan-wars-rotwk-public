import api from './api';
import { apiFetch } from './apiFetch';

const API_BASE_URL = '/api/v1/territories';
const fetchFresh = (url) => apiFetch(url, { cache: 'no-store' });

export const territoryService = {
  // Получить все территории
  async getAllTerritories() {
    try {
      const response = await fetchFresh(`${API_BASE_URL}/`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching territories:', error);
      return [];
    }
  },

  // Получить территорию по ID
  async getTerritoryById(id) {
    try {
      const response = await fetchFresh(`${API_BASE_URL}/${id}`);
      if (!response.ok) {
        if (response.status === 404) {
          return null;
        }
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching territory by ID:', error);
      return null;
    }
  },

  // Получить территорию по имени
  async getTerritoryByName(name) {
    try {
      const response = await fetchFresh(`${API_BASE_URL}/by-name/${encodeURIComponent(name)}`);
      if (!response.ok) {
        if (response.status === 404) {
          return null;
        }
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching territory by name:', error);
      return null;
    }
  },

  // Получить территорию по SVG path data
  async getTerritoryByPathData(pathData) {
    try {
      const response = await fetchFresh(`${API_BASE_URL}/by-path-data/${encodeURIComponent(pathData)}`);
      if (!response.ok) {
        if (response.status === 404) {
          return null;
        }
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching territory by path data:', error);
      return null;
    }
  },

  // Получить территории по региону
  async getTerritoriesByRegion(region) {
    try {
      const response = await fetchFresh(`${API_BASE_URL}/region/${encodeURIComponent(region)}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching territories by region:', error);
      return [];
    }
  },

  // Получить территории по статусу
  async getTerritoriesByStatus(status) {
    try {
      const response = await fetchFresh(`${API_BASE_URL}/status/${encodeURIComponent(status)}`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching territories by status:', error);
      return [];
    }
  },

  // Получить статистику территорий
  async getTerritoryStats() {
    try {
      const response = await fetchFresh(`${API_BASE_URL}/stats`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error fetching territory stats:', error);
      return {
        total: 0,
        contested: 0,
        neutral: 0,
        active: 0,
        contested_percentage: 0,
        neutral_percentage: 0,
        active_percentage: 0
      };
    }
  },

  async getTerritoryEconomy(id) {
    const response = await fetchFresh(`${API_BASE_URL}/${id}/economy`);
    if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
    return response.json();
  },

  async upgradeTerritory(id, upgradeType, fallbackMessage) {
    const response = await apiFetch(`${API_BASE_URL}/${id}/upgrade`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ upgrade_type: upgradeType, levels: 1 }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || fallbackMessage);
    }
    return response.json();
  },

  // Создать новую территорию
  async createTerritory(territoryData) {
    try {
      const response = await api.post('/territories/', territoryData);
      return response.data;
    } catch (error) {
      console.error('Error creating territory:', error);
      throw error;
    }
  },

  // Обновить территорию
  async updateTerritory(id, territoryData, fallbackMessage) {
    try {
      const response = await api.put(`/territories/${id}`, territoryData);
      return response.data;
    } catch (error) {
      console.error('Error updating territory:', error);
      throw new Error(
        error.response?.data?.detail || fallbackMessage
      );
    }
  },

  // Добавить атакующий клан
  async addAttackingClan(territoryId, clanId) {
    try {
      const response = await apiFetch(`${API_BASE_URL}/${territoryId}/attacking-clans/${clanId}`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error adding attacking clan:', error);
      throw error;
    }
  },

  // Добавить защищающий клан
  async addDefendingClan(territoryId, clanId) {
    try {
      const response = await apiFetch(`${API_BASE_URL}/${territoryId}/defending-clans/${clanId}`, {
        method: 'POST',
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error adding defending clan:', error);
      throw error;
    }
  },

  // Удалить клан с территории
  async removeClanFromTerritory(territoryId, clanId) {
    try {
      const response = await apiFetch(`${API_BASE_URL}/${territoryId}/clans/${clanId}`, {
        method: 'DELETE',
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      return await response.json();
    } catch (error) {
      console.error('Error removing clan from territory:', error);
      throw error;
    }
  }
}; 
