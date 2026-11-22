import { apiFetch } from './apiFetch';

const base = '/api/v1/campaign/preseason';
async function request(path, payload, signal) {
  const response = await apiFetch(`${base}${path}`, {
    method: payload === undefined ? 'GET' : 'POST', signal,
    ...(payload === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const error = new Error('Preseason request failed');
    error.status = response.status;
    if (typeof body?.detail === 'string' && body.detail.trim()) error.detail = body.detail;
    throw error;
  }
  return response.json();
}
const clanPath = id => `/clans/${encodeURIComponent(id)}`;
export const preseasonService = {
  getStatus: signal => request('/status', undefined, signal),
  getContext: (id, signal) => request(clanPath(id), undefined, signal),
  previewLands: (id, selected) => request(`${clanPath(id)}/lands/preview`, { selected }),
  chooseLands: (id, selected, revision) => request(`${clanPath(id)}/lands`, { selected, expected_revision: revision }),
  chooseRelics: (id, selected, revision) => request(`${clanPath(id)}/relics`, { selected, expected_revision: revision }),
};
