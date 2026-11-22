import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Refresh, Flag } from '@mui/icons-material';
import { Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import { PageShell } from '../components/ui';
import CycleScouting from '../components/campaign/CycleScouting';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { clanService } from '../services/clanService';
import { cycleCampaignService as service } from '../services/cycleCampaignService';
import { cycleMessage } from '../utils/cycleBattleView';
import { preparationMessage, scoutOrderAvailable } from '../utils/cyclePreparationView';
import { formatMoscowDateTime } from '../utils/dateTime';
import './CyclePreparationPage.css';

function PreparationContent({ cycleId }) {
  const { language, t } = useLocalizationContext(); const copy = key => preparationMessage(key, language);
  const [data, setData] = useState(null), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false), [clanless, setClanless] = useState(false), [notice, setNotice] = useState('');
  const [selected, setSelected] = useState([]), [search, setSearch] = useState('');
  const [confirmation, setConfirmation] = useState(null);
  const mounted = useRef(false), generation = useRef(0), writing = useRef(false);
  const dialogId = React.useId();
  const load = useCallback(async () => {
    setLoading(true); setConfirmation(null);
    const token = ++generation.current;
    try {
      const clan = await clanService.getMyClan();
      if (!mounted.current || token !== generation.current) return;
      if (!clan) { setData(null); setClanless(true); setConfirmation(null); setSelected([]); return; }
      const next = await service.getPreparation(cycleId, clan.id);
      if (mounted.current && token === generation.current) { setData(next); setFailed(false); setClanless(false); }
    } catch { if (mounted.current && token === generation.current) { setData(null); setFailed(true); setConfirmation(null); } }
    finally { if (mounted.current && token === generation.current) setLoading(false); }
  }, [cycleId]);
  useEffect(() => { mounted.current = true; load(); return () => { mounted.current = false; }; }, [load]);
  async function command(action, payload, preview = false) {
    if (writing.current || failed || loading || !data || (action === 'scout' && !scoutOrderAvailable(data, payload))) return;
    writing.current = true; setBusy(true); setNotice(''); generation.current += 1;
    try {
      const response = await service.preparationCommand(cycleId, data.clan_id, action, payload);
      if (!mounted.current) return;
      if (preview) setConfirmation({ action: 'startup/claim', payload: { selected: response.selected, expected_revision: data.startup.revision }, preview: response });
      else { setConfirmation(null); await load(); setNotice('saved'); }
    } catch { if (mounted.current) { setConfirmation(null); await load(); setNotice('failed'); } }
    finally { writing.current = false; if (mounted.current) setBusy(false); }
  }
  const disabled = busy || failed || loading;
  const name = id => data?.territories.find(t => t.id === id)?.name || `#${id}`;
  const choices = data?.territories.filter(land => {
    const owner = land.selection_owner_clan_id === undefined ? land.owner_clan_id : land.selection_owner_clan_id;
    return !land.port && !land.has_port && !land.fortress && (owner === null || owner === data.clan_id)
      && (!search || land.name.toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  }) || [];
  return <PageShell className="cycle-preparation" aria-busy={busy || loading}>
    <header><h1>{copy('screen')}</h1><button disabled={busy} title={copy('refresh')} aria-label={copy('refresh')} onClick={load}><Refresh aria-hidden="true" /></button></header>
    <Link to={`/campaign/cycles/${cycleId}`}>{cycleMessage('cycle_battles_title', language)}</Link>
    {loading ? <p role="status">{copy('loading')}</p> : clanless ? <p>{copy('clanless')}</p> : <>
      {failed && <p role="alert">{copy('failed')}</p>}{notice && <p role={notice === 'saved' ? 'status' : 'alert'}>{copy(notice)}</p>}
      {data && <><h2>{data.clan_name}</h2>
        <CycleScouting data={data} disabled={disabled || Boolean(confirmation)} onOrder={(territoryId, scoutUserId) => setConfirmation({ action: 'scout',
          scoutName: data.scout.players.find(player => player.user_id === scoutUserId)?.name,
          payload: { territory_id: territoryId, scout_user_id: scoutUserId, expected_revision: data.scout.wallet_revision },
        })} />
        <section><h2>{copy('startup')}</h2>{!data.startup.ready ? <p>{copy('pendingInit')}</p> : <>
          <p>{copy('deadline')}: {formatMoscowDateTime(data.startup.deadline, '-', language)}</p>
          {data.startup.selected_lands?.length > 0 && <ul>{data.startup.selected_lands.map(id => <li key={id}>{name(id)}</li>)}</ul>}
          {data.startup.can_claim ? <><p>{copy('landsRule')}</p><label>{copy('search')}<input value={search} onChange={e => setSearch(e.target.value)} /></label>
            <fieldset disabled={disabled}><legend>{copy('selected')}: {selected.length} / 3</legend><ul className="cp-choices">{choices.map(land => <li key={land.id}><label><input type="checkbox" aria-label={land.name} checked={selected.includes(land.id)} disabled={!selected.includes(land.id) && selected.length >= 3}
              onChange={e => setSelected(e.target.checked ? [...selected, land.id] : selected.filter(id => id !== land.id))} />{land.name}{land.owner_clan_id == null && land.selection_owner_clan_id === data.clan_id && <small>{t('preseason_reserved')}</small>}</label></li>)}</ul></fieldset>
            <button disabled={disabled || selected.length !== 3} onClick={() => command('startup/preview', { selected }, true)}><Flag aria-hidden="true" />{copy('preview')}</button></> : <p>{copy('closed')}</p>}
        </>}</section>
      </>}
    </>}
    <Dialog open={Boolean(confirmation)} onClose={() => !busy && setConfirmation(null)} aria-labelledby={dialogId}><DialogTitle id={dialogId}>{copy(confirmation?.action === 'scout' ? 'order' : 'claim')}</DialogTitle><DialogContent>
      {confirmation?.action === 'scout' ? <><p>{name(confirmation.payload.territory_id)}</p><p>{copy('scoutPlayer')}: {confirmation.scoutName}</p><p>{copy('scoutLock')}</p><p>{copy('paid')}</p></> : <><h3>{copy('selected')}</h3><p>{confirmation?.preview.selected.map(name).join(', ')}</p>{confirmation?.preview.release.length > 0 && <><h3>{copy('release')}</h3><p>{confirmation.preview.release.map(name).join(', ')}</p></>}</>}
    </DialogContent><DialogActions><button className="cp-dialog-button" autoFocus disabled={busy} onClick={() => setConfirmation(null)}>{copy('cancel')}</button><button className="cp-dialog-button" disabled={disabled || (confirmation?.action === 'scout' && !scoutOrderAvailable(data, confirmation.payload))} onClick={() => command(confirmation.action, confirmation.payload)}>{copy('confirm')}</button></DialogActions></Dialog>
  </PageShell>;
}
export default function CyclePreparationPage() { const { cycleId } = useParams(); const { user } = useAuth(); return <PreparationContent key={`${user?.id}:${cycleId}`} cycleId={cycleId} />; }
