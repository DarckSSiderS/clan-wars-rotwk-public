import axios from 'axios';
import { announceSessionExpired } from '../utils/authSession';
import { withAppBase } from '../utils/appBasePath';

// Cookie сессии передаются браузером и недоступны JavaScript-коду.
const api = axios.create({
  baseURL: withAppBase('/api/v1'),
  withCredentials: true,
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      announceSessionExpired();
    }
    return Promise.reject(error);
  },
);

export default api;
