import { useCallback, useEffect, useState } from 'react';
import { cycleCampaignService } from '../services/cycleCampaignService';

export default function useCycleMap(cycleId, userId) {
  const [state, setState] = useState({ data: null, loading: false, error: false });
  const [attempt, setAttempt] = useState(0);
  const refresh = useCallback(() => setAttempt(n => n + 1), []);
  useEffect(() => {
    if (!cycleId || !userId) { setState({ data: null, loading: false, error: false }); return; }
    const controller = new AbortController();
    setState(old => ({ ...old, loading: true }));
    cycleCampaignService.getMap(cycleId, { signal: controller.signal }).then(data => {
      if (data.cycle_id !== cycleId || !Array.isArray(data.dispatches) || !Array.isArray(data.battles)) throw new Error('Invalid cycle map');
      if (!controller.signal.aborted) setState({ data, userId, loading: false, error: false });
    }).catch(() => { if (!controller.signal.aborted) setState({ data: null, loading: false, error: true }); });
    return () => controller.abort();
  }, [cycleId, userId, attempt]);
  useEffect(() => {
    if (!cycleId) return;
    const timer = setInterval(refresh, 15_000);
    return () => clearInterval(timer);
  }, [cycleId, refresh]);
  return { ...state, data: state.data?.cycle_id === cycleId && state.userId === userId ? state.data : null, refresh };
}
