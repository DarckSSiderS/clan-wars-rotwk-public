import api from './api';
import { isAdminPreview, withAppBase } from '../utils/appBasePath';

export const authService = {
  async getSession() {
    const response = await api.get('/auth/session');
    return response.data;
  },

  async login(credentials) {
    const response = await api.post('/auth/password-login', {
      nickname: credentials.nickname,
      password: credentials.password,
    });
    return response.data;
  },

  startArenaLogin(returnTo = '/') {
    const safeReturnTo = (
      typeof returnTo === 'string'
      && returnTo.startsWith('/')
      && !returnTo.startsWith('//')
      && !returnTo.includes('\\')
    ) ? returnTo : '/';
    window.location.assign(
      withAppBase(`/api/v1/auth/arena/start?return_to=${encodeURIComponent(safeReturnTo)}`),
    );
  },

  async completeOnboarding(payload) {
    const response = await api.post('/auth/onboarding', payload);
    return response.data;
  },

  async requestPasswordRecovery(email) {
    const response = await api.post('/auth/password-recovery/request', { email });
    return response.data;
  },

  async confirmPasswordRecovery(token, password) {
    const response = await api.post('/auth/password-recovery/confirm', { token, password });
    return response.data;
  },

  async revokeAllSessions() {
    const response = await api.post('/auth/sessions/revoke-all');
    return response.data;
  },

  async impersonateUser(userId) {
    const response = await api.post(`/users/${userId}/impersonate`);
    return response.data;
  },

  async returnFromImpersonation() {
    const response = await api.post('/auth/impersonation/return');
    return response.data;
  },

  async logout() {
    if (isAdminPreview) {
      window.location.assign('/admin');
      return;
    }
    await api.post('/auth/logout');
  },

  // Получение текущего пользователя
  async getCurrentUser() {
    const response = await api.get('/users/me');
    return response.data;
  }
}; 
