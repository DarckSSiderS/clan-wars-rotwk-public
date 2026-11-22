import api from './api';

export const messagingService = {
  async list() {
    const response = await api.get('/messages/conversations');
    return response.data;
  },

  async open(username) {
    const response = await api.post(`/messages/conversations/${encodeURIComponent(username)}`);
    return response.data;
  },

  async getMessages(conversationId) {
    const response = await api.get(`/messages/conversations/${conversationId}/messages`);
    return response.data;
  },

  async send(conversationId, body) {
    const response = await api.post(`/messages/conversations/${conversationId}/messages`, { body });
    return response.data;
  },

  async block(username) {
    await api.put(`/messages/blocks/${encodeURIComponent(username)}`);
  },

  async report(messageId, reason) {
    await api.post(`/messages/${messageId}/report`, { reason });
  },
};
