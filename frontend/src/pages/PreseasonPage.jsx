import React, { useCallback, useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Tooltip } from '@mui/material';
import { Check, Flag, Refresh } from '@mui/icons-material';
import { PageShell } from '../components/ui';
import { CLAN_RESOURCES } from '../components/clan/clanResources';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { clanService } from '../services/clanService';
import { preseasonService as service } from '../services/preseasonService';
import { getRelicArtwork } from '../content/clanRelics';
import { getTerritoryName } from '../i18n/territories';
import './PreseasonPage.css';

function connected(selected, territories) {
  if (selected.length !== 3) return false;
  const world = new Map(territories.map(territory => [territory.id, territory]));
  const reached = new Set([selected[0]]);
  const pending = [selected[0]];
  while (pending.length) {
    const current = pending.pop();
    for (const candidate of selected) {
      if (reached.has(candidate)) continue;
      if (world.get(current)?.neighbours?.includes(candidate) || world.get(candidate)?.neighbours?.includes(current)) {
        reached.add(candidate);
        pending.push(candidate);
      }
    }
  }
  return reached.size === 3;
}
function PreseasonContent() {
  const { t, language } = useLocalizationContext();
  const copy = key => t(`preseason_${key}`);
  const [data, setData] = useState(null), [state, setState] = useState('loading');
  const [lands, setLands] = useState([]), [relics, setRelics] = useState([]), [search, setSearch] = useState('');
  const [confirmation, setConfirmation] = useState(null), [busy, setBusy] = useState(false), [notice, setNotice] = useState('');
  const [errorDetail, setErrorDetail] = useState('');
  const mounted = useRef(false), writing = useRef(false), generation = useRef(0);
  const dialogId = useId();
  const load = useCallback(async () => {
    const token = ++generation.current;
    setState('loading'); setData(null); setConfirmation(null); setLands([]); setRelics([]); setErrorDetail('');
    try {
      const status = await service.getStatus();
      if (!mounted.current || token !== generation.current) return;
      if (status.open !== true) { setState('closed'); return; }
      const clan = await clanService.getMyClan();
      if (!mounted.current || token !== generation.current) return;
      if (!clan?.id) { setState('clanless'); return; }
      const context = await service.getContext(clan.id);
      if (!mounted.current || token !== generation.current) return;
      if (context.open !== true) { setState('closed'); return; }
      setData(context); setLands(context.selected_lands || []); setRelics(context.selected_relics || []); setState('ready');
    } catch (error) {
      if (mounted.current && token === generation.current) { setState('error'); setErrorDetail(error.detail || ''); }
    }
  }, []);
  useEffect(() => { mounted.current = true; load(); return () => { mounted.current = false; }; }, [load]);
  const canLands = data?.open && data.is_head && data.can_choose_lands && !data.selected_lands?.length;
  const canRelics = data?.open && data.is_head && data.can_choose_relics && !data.selected_relics?.length;
  const disabled = busy || state !== 'ready';
  const territoryName = id => getTerritoryName(data?.territories.find(t => t.id === id)?.name || `#${id}`, language);
  const neighbourNames = land => data.territories.filter(other => other.id !== land.id && other.name
    && (land.neighbours?.includes(other.id) || other.neighbours?.includes(land.id)))
    .map(other => getTerritoryName(other.name, language)).join(', ');
  const relicName = key => data?.relics.find(r => r.key === key)?.name || key;
  async function perform(action) {
    if (writing.current || disabled || (action === 'relics' ? !canRelics : !canLands)) return;
    writing.current = true; setBusy(true); setNotice(''); setErrorDetail('');
    try {
      if (action === 'preview') {
        const preview = await service.previewLands(data.clan_id, lands);
        if (mounted.current) setConfirmation({ kind: 'lands', selected: preview.selected, release: preview.release || [], revision: data.revision });
      } else {
        const next = await (action === 'lands' ? service.chooseLands : service.chooseRelics)(data.clan_id, confirmation.selected, confirmation.revision);
        if (mounted.current) {
          setConfirmation(null);
          if (next.open !== true) { setData(null); setState('closed'); }
          else { setData(next); setLands(next.selected_lands || []); setRelics(next.selected_relics || []); }
          setNotice('saved');
        }
      }
    } catch (error) {
      if (mounted.current) {
        await load();
        if (mounted.current) { setErrorDetail(error.detail || ''); setNotice('action_error'); }
      }
    } finally { writing.current = false; if (mounted.current) setBusy(false); }
  }
  const choices = data?.territories.filter(t => !t.has_port && !t.fortress
    && (t.selection_owner_clan_id == null || t.selection_owner_clan_id === data.clan_id)
    && (t.owner_clan_id == null || t.owner_clan_id === data.clan_id)) || [];
  const shown = choices.filter(t => territoryName(t.id).toLocaleLowerCase().includes(search.toLocaleLowerCase()));
  const toggle = (values, value, checked) => checked ? [...values, value] : values.filter(v => v !== value);
  return <PageShell className="preseason-page" aria-busy={busy || state === 'loading'}>
    <header><h1>{copy('title')}</h1><Tooltip title={t('common_refresh')}><span><IconButton aria-label={t('common_refresh')} disabled={busy || state === 'loading'} onClick={() => { setNotice(''); load(); }}><Refresh /></IconButton></span></Tooltip></header>
    <Link to="/map">{t('nav_map')}</Link>
    {state === 'loading' ? <p role="status">{t('common_loading')}</p> : state !== 'ready' ? <Alert severity={state === 'error' ? 'error' : 'info'}>{state === 'error' && errorDetail ? errorDetail : copy(state)}</Alert> : <>
      <h2>{data.clan_name}</h2><p>{copy('open')}</p>
      {notice && <Alert severity={notice === 'saved' ? 'success' : 'warning'} role={notice === 'saved' ? 'status' : 'alert'}>{errorDetail || copy(notice)}</Alert>}
      <section aria-labelledby={`${dialogId}-treasury`}><h2 id={`${dialogId}-treasury`}>{copy('treasury')}</h2><p>{copy('treasury_note')}</p>
        <dl className="preseason-treasury">{CLAN_RESOURCES.filter(r => r.key !== 'territory_points').map(({ key, labelKey, Icon, color }) => <div key={key}><dt><Icon style={{ color }} aria-hidden="true" />{t(labelKey)}</dt><dd>{data.treasury?.[key]}</dd></div>)}</dl>
      </section>
      {!data.is_head && <p>{copy('head_only')}</p>}
      <section aria-labelledby={`${dialogId}-lands`}><h2 id={`${dialogId}-lands`}>{copy('lands')}</h2><p>{copy('lands_rule')}</p><p>{copy('retention_rule')}</p>
        {data.selected_lands?.length > 0 ? <><p className="preseason-confirmed"><Check />{copy('chosen')}</p><ul>{data.selected_lands.map(id => <li key={id}>{territoryName(id)}</li>)}</ul></> : <>
          {data.is_head && !data.can_choose_lands && <p>{copy('ineligible')}</p>}
          <label className="preseason-search">{copy('search')}<input value={search} onChange={e => setSearch(e.target.value)} /></label>
          <fieldset disabled={disabled || !!confirmation}><legend>{copy('selected')}: {lands.length} / 3</legend><div className="preseason-lands">{shown.map(land => <label className="preseason-land" key={land.id}>
            {canLands && <input type="checkbox" aria-label={territoryName(land.id)} checked={lands.includes(land.id)} disabled={!lands.includes(land.id) && lands.length >= 3} onChange={e => setLands(toggle(lands, land.id, e.target.checked))} />}
            <span><strong>{territoryName(land.id)}</strong><small>{copy(land.owner_clan_id === data.clan_id ? 'owned' : land.selection_owner_clan_id === data.clan_id ? 'reserved' : 'available')}</small><small>{copy('neighbours')}: {neighbourNames(land) || copy('no_neighbours')}</small></span>
          </label>)}</div>{!shown.length && <p>{copy('empty')}</p>}</fieldset>
          {canLands && <>{lands.length === 3 && !connected(lands, data.territories) && <p role="status">{copy('connected')}</p>}<Button variant="outlined" startIcon={<Flag />} disabled={disabled || !connected(lands, data.territories)} onClick={() => perform('preview')}>{copy('preview')}</Button></>}
        </>}
      </section>
      <section aria-labelledby={`${dialogId}-relics`}><h2 id={`${dialogId}-relics`}>{copy('relics')}</h2><p>{copy('relics_rule')}</p>
        {data.selected_relics?.length > 0 && <p className="preseason-confirmed"><Check />{copy('chosen')}: {data.selected_relics.map(relicName).join(', ')}</p>}
        <fieldset disabled={disabled || !!confirmation}><legend>{copy('selected')}: {relics.length} / 2</legend><div className="preseason-relics">{data.relics.map(relic => <article className={`preseason-relic${relics.includes(relic.key) ? ' is-selected' : ''}`} key={relic.key}>
          <img src={getRelicArtwork(relic.key)} alt="" /><div><h3>{relic.name}</h3><p>{copy(`effect_${relic.effect}`)}</p><strong>+{relic.effects[0]}% · I</strong>
            {canRelics && <label><input type="checkbox" aria-label={relic.name} checked={relics.includes(relic.key)} disabled={!relics.includes(relic.key) && relics.length >= 2} onChange={e => setRelics(toggle(relics, relic.key, e.target.checked))} />{copy('selected')}</label>}
          </div></article>)}</div></fieldset>
        {canRelics && <Button variant="outlined" startIcon={<Check />} disabled={disabled || relics.length !== 2} onClick={() => setConfirmation({ kind: 'relics', selected: [...relics], revision: data.revision })}>{copy('confirm_relics')}</Button>}
      </section>
    </>}
    <Dialog open={!!confirmation} onClose={() => !busy && setConfirmation(null)} aria-labelledby={`${dialogId}-confirm`} aria-describedby={`${dialogId}-warning`} slotProps={{ paper: { role: 'alertdialog' } }}>
      <DialogTitle id={`${dialogId}-confirm`}>{copy(confirmation?.kind === 'lands' ? 'confirm_lands' : 'confirm_relics')}</DialogTitle><DialogContent>
        <p id={`${dialogId}-warning`}>{copy('irreversible')}</p><ul>{confirmation?.selected.map(value => <li key={value}>{confirmation.kind === 'lands' ? territoryName(value) : relicName(value)}</li>)}</ul>
        {confirmation?.release?.length > 0 && <><h3>{copy('release')}</h3><ul>{confirmation.release.map(id => <li key={id}>{territoryName(id)}</li>)}</ul></>}
      </DialogContent><DialogActions><Button autoFocus disabled={busy} onClick={() => setConfirmation(null)}>{t('common_cancel')}</Button><Button disabled={disabled} onClick={() => perform(confirmation.kind)}>{t('common_confirm')}</Button></DialogActions>
    </Dialog>
  </PageShell>;
}
export default function PreseasonPage() { const { user } = useAuth(); return <PreseasonContent key={user?.id} />; }
