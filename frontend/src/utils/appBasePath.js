const buildBase = import.meta.env?.BASE_URL || '/';

export const appBasePath = buildBase.replace(/\/$/, '') || '/';
export const isAdminPreview = appBasePath === '/admin/preview';

export function withAppBase(path, base = buildBase) {
  const prefix = base.replace(/\/$/, '');
  if (!prefix || !path.startsWith('/') || path.startsWith('//')) return path;
  if (path === prefix || path.startsWith(`${prefix}/`)) return path;
  return `${prefix}${path}`;
}

export function publicAssetCredentials(path, base = buildBase) {
  return base.replace(/\/$/, '') === '/admin/preview'
    && path.startsWith('/') && !path.startsWith('//') ? 'same-origin' : 'omit';
}
