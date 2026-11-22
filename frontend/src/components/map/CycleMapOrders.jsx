import React, { useEffect, useRef, useState } from 'react';
import { Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material';
import { Refresh, Shield } from '@mui/icons-material';
import { useLocalizationContext } from '../../contexts/LocalizationContext';
import { clanService } from '../../services/clanService';
import { cycleCampaignService as service } from '../../services/cycleCampaignService';
import { assignPlayer, planningMessage, planProblem, routeKey } from '../../utils/cyclePlanningView';
import { mapAttackUnavailableReason, mapCommandMessage } from '../../utils/cycleMapCommandView';

export default function CycleMapOrders({ cycleId, territoryId, onUpdate, onBusyChange }) {
  const { language } = useLocalizationContext();
  const copy = key => planningMessage(key, language);
  const label = key => mapCommandMessage(key, language);
  const [data, setData] = useState(null), [failed, setFailed] = useState(false), [clanless, setClanless] = useState(false);
  const [busy, setBusy] = useState(false), [kind, setKind] = useState(''), [route, setRoute] = useState('');
  const [players, setPlayers] = useState([]), [confirmation, setConfirmation] = useState(null), [notice, setNotice] = useState('');
  const [attempt, setAttempt] = useState(0), [clock, setClock] = useState(Date.now);
  const [attackTarget, setAttackTarget] = useState(territoryId);
  const mounted = useRef(false);
  const generation = useRef(0), writing = useRef(false);
  const dialogId = React.useId();
  useEffect(() => {
    mounted.current = true;
    const token = ++generation.current;
    const controller = new AbortController();
    setData(null); setFailed(false); setClanless(false); setConfirmation(null); setPlayers([]);
    clanService.getMyClan().then(async clan => {
      if (controller.signal.aborted || token !== generation.current) return;
      if (!clan) { setClanless(true); return; }
      const next = await service.getPlanning(cycleId, clan.id, { signal: controller.signal });
      if (!controller.signal.aborted && token === generation.current) { setData({ ...next, receivedAt: Date.now() }); setFailed(false); }
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => { mounted.current = false; controller.abort(); };
  }, [cycleId, attempt]);
  useEffect(() => { const timer = setInterval(() => setClock(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const routes = data?.attack_routes.filter(item => item.territory_id === attackTarget) || [];
  const destinations = [...new Set(data?.attack_routes.map(item => item.territory_id) || [])];
  const selectedTerritoryAttackable = data?.attack_routes.some(item => item.territory_id === territoryId);
  const kinds = [
    ...(routes.length ? ['attack'] : []),
    ...(data?.defence_targets.includes(territoryId) ? ['defend'] : []),
    ...(data?.plan.orders.some(item => ['attack', 'defend'].includes(item.kind) && item.territory_id === territoryId) ? ['ambush'] : []),
  ];
  const selectedKind = kinds.includes(kind) ? kind : kinds[0];
  const selectedRoute = routes.find(item => routeKey(item) === route) || routes[0];
  const now = data ? Date.parse(data.server_time) + Math.max(0, clock - data.receivedAt) : 0;
  const editable = data?.editable && data.snapshot_ready && now < Date.parse(data.battle_at);
  const disabled = busy || failed || !editable;
  const assignment = selectedKind === 'attack' ? { ...selectedRoute, kind: selectedKind } : { kind: selectedKind, territory_id: territoryId };
  const draft = data ? players.reduce((orders, userId) => assignPlayer(orders, userId, assignment), data.plan.orders) : [];
  const problem = data && players.length ? planProblem(draft, data) : null;
  const name = id => data?.territories.find(item => item.id === id)?.name || `#${id}`;
  async function save() {
    if (disabled || writing.current || !confirmation || confirmation.revision !== data.plan.revision) return;
    const token = generation.current;
    writing.current = true;
    setBusy(true); onBusyChange(true); setNotice('');
    try {
      const plan = await service.savePlan(cycleId, data.clan_id, { expected_revision: confirmation.revision, orders: confirmation.orders });
      if (!mounted.current || token !== generation.current) return;
      setData(old => ({ ...old, plan })); setPlayers([]); setNotice('saved'); onUpdate();
    } catch { if (mounted.current && token === generation.current) { setFailed(true); setNotice('conflict'); } }
    finally { writing.current = false; if (mounted.current && token === generation.current) { setBusy(false); setConfirmation(null); } onBusyChange(false); }
  }
  if (clanless) return <p>{copy('clanless')}</p>;
  if (!data) return <div><p role={failed ? 'alert' : 'status'}>{copy(failed ? 'failed' : 'loading')}</p>{failed && <button onClick={() => setAttempt(value => value + 1)}><Refresh aria-hidden="true" />{copy('retry')}</button>}</div>;
  return <div className="cycle-map-orders">
    {!editable && <p>{copy('readonly')} {copy('permission')}</p>}
    {notice && <p role={notice === 'saved' ? 'status' : 'alert'}>{copy(notice)}</p>}
    {failed && <button disabled={busy} onClick={() => { setConfirmation(null); setAttempt(value => value + 1); }}><Refresh aria-hidden="true" />{copy('retry')}</button>}
    {!selectedTerritoryAttackable && <p role="status">{name(territoryId)}: {label(mapAttackUnavailableReason(data, territoryId))}</p>}
    {destinations.length ? <label>{label('attackDestination')}<select disabled={disabled} value={destinations.includes(attackTarget) ? attackTarget : ''}
      onChange={event => { setAttackTarget(Number(event.target.value)); setKind('attack'); setRoute(''); setPlayers([]); setConfirmation(null); }}>
      <option value="" disabled>{label('chooseAttack')}</option>
      {destinations.map(id => <option key={id} value={id}>{name(id)}</option>)}
    </select></label> : <p>{label('noAttackDestinations')}</p>}
    {kinds.length ? <form onSubmit={event => { event.preventDefault(); if (!disabled && players.length && !problem) setConfirmation({ revision: data.plan.revision, orders: draft }); }}>
      <label>{label('action')}<select disabled={disabled} value={selectedKind} onChange={event => { setKind(event.target.value); setConfirmation(null); }}>{kinds.map(value => <option key={value} value={value}>{copy(value)}</option>)}</select></label>
      {selectedKind === 'attack' && <label>{label('attackSource')}<select disabled={disabled} value={selectedRoute ? routeKey(selectedRoute) : ''} onChange={event => { setRoute(event.target.value); setConfirmation(null); }}>{routes.map(item => <option key={routeKey(item)} value={routeKey(item)}>{item.source_id ? name(item.source_id) : copy('landing')} · {copy(item.route)}</option>)}</select></label>}
      <fieldset disabled={disabled}><legend>{label('players')}</legend><ul>{data.members.map(member => {
        const order = data.plan.orders.find(item => item.user_id === member.user_id);
        return <li key={member.user_id}><label><input type="checkbox" checked={players.includes(member.user_id)} disabled={!member.eligible || member.scouting} onChange={event => setPlayers(event.target.checked ? [...players, member.user_id] : players.filter(id => id !== member.user_id))} /><Shield aria-hidden="true" /><span>{member.name}</span></label>
          <small>{label('current')}: {copy(member.scouting ? 'scouting' : order?.kind || 'none')}{!member.scouting && order?.territory_id && ` · ${name(order.territory_id)}`}</small></li>;
      })}</ul></fieldset>
      {problem && <p role="alert">{copy(problem)}</p>}
      <button className="cycle-map-command-primary" disabled={disabled || !players.length || Boolean(problem)}>{label('review')}</button>
    </form> : null}
    <Dialog open={Boolean(confirmation)} onClose={() => !busy && setConfirmation(null)} aria-labelledby={dialogId}>
      <DialogTitle id={dialogId}>{label('confirmOrder')}</DialogTitle><DialogContent><h3>{name(selectedKind === 'attack' ? attackTarget : territoryId)} · {copy(selectedKind)}</h3><p>{players.map(id => data.members.find(member => member.user_id === id)?.name || `#${id}`).join(', ')}</p><p>{label('reassignment')}</p></DialogContent>
      <DialogActions className="cycle-map-dialog-actions"><button disabled={busy} onClick={() => setConfirmation(null)}>{label('cancel')}</button><button disabled={disabled} onClick={save}>{label('confirm')}</button></DialogActions>
    </Dialog>
  </div>;
}
