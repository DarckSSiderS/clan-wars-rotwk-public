import React, { useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { Dialog, DialogActions, DialogContent, DialogTitle, Button } from '@mui/material';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import api from '../services/api';
import { withAppBase } from '../utils/appBasePath';
import { previewScenarioReturnPath } from '../utils/previewScenarioView';

export default function PreviewScenarioSwitcher() {
  const { t } = useLocalizationContext();
  const location = useLocation();
  const copy = key => t(`admin_preview_scenario_${key}`);
  const [data, setData] = useState(null), [target, setTarget] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const titleId = React.useId();
  useEffect(() => {
    const controller = new AbortController();
    const load = () => api.get('/admin-preview/scenario', { signal: controller.signal }).then(response => { setData(response.data); setError(''); })
      .catch(() => { if (!controller.signal.aborted) setError('unavailable'); });
    load();
    const timer = setInterval(load, 30000);
    return () => { clearInterval(timer); controller.abort(); };
  }, []);
  async function change() {
    if (busy || !target) return;
    setBusy(true); setError('');
    try {
      const { data: next } = await api.post('/admin-preview/scenario', { mode: target, confirm_reset: target === 'preparation' });
      window.location.assign(withAppBase(previewScenarioReturnPath(location.pathname, location.search, next.cycle_id)));
    } catch { setError('failed'); setTarget(null); setBusy(false); }
  }
  return <div className="preview-scenario">
    <div className="preview-scenario__modes" role="group" aria-label={copy('label')}><span>{copy('label')}</span>{['preparation', 'battle'].map(mode => <button key={mode} type="button" disabled={busy || !data || data.mode === mode || (mode === 'battle' && data.can_switch_to_battle === false)} aria-pressed={data?.mode === mode} onClick={() => setTarget(mode)}>{copy(mode)}</button>)}</div>
    {data?.can_switch_to_battle === false && <span role="status">{copy('blocked')}</span>}
    {error && <span role="status">{copy(error)}</span>}
    <Dialog open={target != null} onClose={() => !busy && setTarget(null)} aria-labelledby={titleId}><DialogTitle id={titleId}>{copy('confirm')}</DialogTitle><DialogContent>{copy('description')}</DialogContent><DialogActions><Button disabled={busy} onClick={() => setTarget(null)}>{copy('cancel')}</Button><Button disabled={busy} onClick={change}>{copy('apply')}</Button></DialogActions></Dialog>
  </div>;
}
