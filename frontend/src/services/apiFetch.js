import { announceSessionExpired } from '../utils/authSession';
import { withAppBase, publicAssetCredentials } from '../utils/appBasePath';

const API_PREFIX = '/api/v1/';

export const apiFetch = async (input, init = {}) => {
  if (typeof input !== 'string' || !input.startsWith(API_PREFIX)) {
    throw new TypeError('apiFetch принимает только внутренние API URL');
  }

  const headers = new Headers(init.headers);
  if (headers.has('Authorization')) {
    throw new TypeError('Authorization header запрещен для cookie-сессии');
  }

  const response = await fetch(withAppBase(input), {
    ...init,
    headers,
    credentials: 'include',
  });
  if (response.status === 401) {
    announceSessionExpired();
  }
  return response;
};

export const publicFetch = (input, init = {}) => fetch(withAppBase(input), {
  ...init,
  credentials: publicAssetCredentials(input),
});

export const encyclopediaAssetFetch = (input, init = {}) => {
  if (typeof input !== 'string' || !/^\/encyclopedia\/ennorath\/(?:catalog\.json|models\/[a-zA-Z0-9_-]+\.glb)$/.test(input)) {
    throw new TypeError('Invalid encyclopedia asset URL');
  }
  return publicFetch(input, { signal: init.signal });
};
