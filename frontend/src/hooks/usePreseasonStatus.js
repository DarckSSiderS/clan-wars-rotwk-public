import { useCallback, useEffect, useState } from 'react';
import { preseasonService } from '../services/preseasonService';

export default function usePreseasonStatus() {
  const [status, setStatus] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const refresh = useCallback(() => setAttempt(value => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    setStatus(null);
    preseasonService.getStatus(controller.signal).then(next => { if (!controller.signal.aborted) setStatus(next); }).catch(() => {});
    return () => controller.abort();
  }, [attempt]);
  return { open: status?.open === true, resolved: status !== null, refresh };
}
