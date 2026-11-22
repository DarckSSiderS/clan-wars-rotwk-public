import { publicFetch } from './apiFetch';
import { archiveEndpoint, archiveMapUrl, archiveViewBox } from '../utils/seasonArchive.js';

async function readArchive(seasonId, signal) {
  const response = await publicFetch(archiveEndpoint(seasonId), { method: 'GET', signal });
  if (!response.ok) {
    const error = new Error('Archive unavailable');
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export async function listSeasonArchives(signal) {
  const data = await readArchive(undefined, signal);
  if (!Array.isArray(data?.seasons)) throw new TypeError('Invalid archive list');
  return data.seasons;
}

export async function getSeasonArchive(seasonId, signal) {
  const data = await readArchive(seasonId, signal);
  if (String(data?.season?.id) !== String(seasonId) || !Array.isArray(data?.territories)
      || !Array.isArray(data?.clans) || data.schema_version !== 1
      || !archiveMapUrl(data.map_image_url, seasonId)) throw new TypeError('Invalid archive payload');
  archiveViewBox(data.view_box);
  return data;
}
