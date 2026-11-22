import { useCallback, useEffect, useState } from 'react';
import { cycleCampaignService } from '../services/cycleCampaignService';
import { resolveCampaignNavigation } from '../utils/campaignNavigation';

export default function useCampaignNavigation(pollInterval = 0) {
  const [state, setState] = useState({ navigation: null, loading: true, error: false });
  const [attempt, setAttempt] = useState(0);
  const refresh = useCallback(() => setAttempt(value => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    setState(previous => ({ ...previous, loading: true, error: false }));
    cycleCampaignService.getCurrent({ signal: controller.signal })
      .then(data => {
        if (!controller.signal.aborted) setState({ navigation: resolveCampaignNavigation(data), loading: false, error: false });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ navigation: null, loading: false, error: true });
      });
    return () => controller.abort();
  }, [attempt]);
  useEffect(() => {
    if (!pollInterval) return undefined;
    const timer = window.setInterval(refresh, pollInterval);
    return () => window.clearInterval(timer);
  }, [pollInterval, refresh]);
  return { ...state, refresh };
}
