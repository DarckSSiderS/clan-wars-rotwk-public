export const AUTH_SESSION_EXPIRED_EVENT = 'auth:session-expired';

export const LEGACY_AUTH_STORAGE_KEYS = [
  'token',
  'user',
  'admin_token',
  'original_admin',
];

export const clearLegacyAuthStorage = () => {
  for (const key of LEGACY_AUTH_STORAGE_KEYS) {
    window.localStorage.removeItem(key);
    window.sessionStorage.removeItem(key);
  }
};

export const announceSessionExpired = () => {
  window.dispatchEvent(new Event(AUTH_SESSION_EXPIRED_EVENT));
};
