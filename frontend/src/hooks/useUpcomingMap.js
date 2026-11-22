import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../services/apiFetch';

export default function useUpcomingMap(enabled) {
  const [state, setState] = useState({ data: null, error: false });
  const [attempt, setAttempt] = useState(0);
  const refresh = useCallback(() => setAttempt(value => value + 1), []);
  useEffect(() => {
    if (!enabled) return undefined;
    const controller = new AbortController();
    setState({ data: null, error: false });
    apiFetch('/api/v1/campaign/map/preparation', { signal: controller.signal })
      .then(async response => {
        if (!response.ok) throw Error('Map unavailable');
        const data = await response.json();
        if (data.upcoming !== true || !Array.isArray(data.territories)) throw Error('Invalid map');
        if (!controller.signal.aborted) setState({ data, error: false });
      }).catch(() => { if (!controller.signal.aborted) setState({ data: null, error: true }); });
    return () => controller.abort();
  }, [enabled, attempt]);
  return { ...state, refresh };
}
