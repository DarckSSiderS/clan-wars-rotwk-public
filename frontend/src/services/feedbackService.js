import api from './api';

export const feedbackService = {
  async create(formData) {
    const response = await api.post('/feedback/tickets', formData);
    return response.data;
  },
  async listMine() {
    const response = await api.get('/feedback/tickets');
    return response.data;
  },
  async getMine(ticketId) {
    const response = await api.get(`/feedback/tickets/${ticketId}`);
    return response.data;
  },
  async reply(ticketId, body) {
    const response = await api.post(`/feedback/tickets/${ticketId}/replies`, { body });
    return response.data;
  },
  async listAdmin(params = {}) {
    const response = await api.get('/admin/feedback/tickets', { params });
    return response.data;
  },
  async getAdmin(ticketId) {
    const response = await api.get(`/admin/feedback/tickets/${ticketId}`);
    return response.data;
  },
  async markAdminRead(ticketId) {
    const response = await api.post(`/admin/feedback/tickets/${ticketId}/read`);
    return response.data;
  },
  async updateAdmin(ticketId, payload) {
    const response = await api.patch(`/admin/feedback/tickets/${ticketId}`, payload);
    return response.data;
  },
  async replyAdmin(ticketId, body) {
    const response = await api.post(`/admin/feedback/tickets/${ticketId}/replies`, { body });
    return response.data;
  },
};
