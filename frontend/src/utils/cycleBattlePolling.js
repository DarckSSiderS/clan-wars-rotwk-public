export function startCyclePoll({ load, onData, onError, onBusy = () => {}, interval = 30_000,
  visibility = globalThis.document, schedule = globalThis.setTimeout, cancel = globalThis.clearTimeout }) {
  let stopped = false, inFlight = false, queued = false, timer, controller, generation = 0;
  const visible = () => !visibility?.hidden;
  const clear = () => { cancel(timer); timer = undefined; };
  const refresh = () => {
    if (stopped || !visible()) return;
    clear();
    if (inFlight) { queued = true; return; }
    inFlight = true;
    controller = new AbortController();
    const current = generation;
    onBusy(true);
    let request;
    try { request = load(controller.signal); } catch (error) { request = Promise.reject(error); }
    Promise.resolve(request).then(data => {
      if (!stopped && !controller.signal.aborted && current === generation) onData(data);
    }).catch(error => {
      if (!stopped && !controller.signal.aborted && current === generation) onError(error);
    }).finally(() => {
      inFlight = false;
      if (stopped) return;
      onBusy(false);
      if (queued && visible()) { queued = false; refresh(); }
      else if (visible()) timer = schedule(refresh, interval);
    });
  };
  const onVisibility = () => { if (visible()) refresh(); else clear(); };
  visibility?.addEventListener('visibilitychange', onVisibility);
  refresh();
  return { refresh,
    invalidate() { generation += 1; },
    stop() { stopped = true; clear(); controller?.abort(); visibility?.removeEventListener('visibilitychange', onVisibility); },
  };
}
