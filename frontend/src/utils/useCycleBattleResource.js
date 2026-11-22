import { useCallback, useEffect, useRef, useState } from 'react';
import { startCyclePoll } from './cycleBattlePolling.js';

export async function readCycleResources(requests) {
  const results = await Promise.allSettled(requests);
  const failed = results.find(row => row.status === 'rejected');
  if (failed) throw failed.reason;
  return results.map(row => row.value);
}

export function useCycleBattleResource(key, load) {
  const loader = useRef(load);
  const poll = useRef(null);
  const [state, setState] = useState({ key: null, data: null, error: null, busy: false });
  useEffect(() => { loader.current = load; });
  useEffect(() => {
    if (key == null) return undefined;
    setState({ key, data: null, error: null, busy: true });
    const instance = startCyclePoll({ load: signal => loader.current(signal),
      onData: data => setState({ key, data, error: null, busy: false }),
      onError: error => setState(previous => ({ ...previous, error })),
      onBusy: busy => setState(previous => ({ ...previous, busy })),
    });
    poll.current = instance;
    return () => { instance.stop(); if (poll.current === instance) poll.current = null; };
  }, [key]);
  const refresh = useCallback(() => poll.current?.refresh(), []);
  const accept = useCallback(next => {
    poll.current?.invalidate();
    setState(previous => ({ ...previous, data: typeof next === 'function' ? next(previous.data) : next, error: null }));
  }, []);
  return { ...(state.key === key ? state : { data: null, error: null, busy: key != null }), refresh, accept };
}
