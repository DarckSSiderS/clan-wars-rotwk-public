import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { ArrowBack, Refresh, Send, SupportAgent } from '@mui/icons-material';
import { Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material';
import { PageShell } from '../components/ui';
import { CycleDispatchRouteMap } from '../components/map/CycleMap';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { clanService } from '../services/clanService';
import { cycleCampaignService as service } from '../services/cycleCampaignService';
import { dispatchState, dispatchTargetKey, dispatchCountdown, reinforcementCommand, reinforcementMessage } from '../utils/cycleReinforcementView';
import { formatMoscowDateTime } from '../utils/dateTime';
import { interceptionMessage, interceptionPath } from '../utils/cycleInterceptionView';
import './CycleReinforcementsPage.css';

export function ReinforcementsContent({ cycleId, targetTerritoryId, targetRecipientId, targetRequestId, embedded = false, onUpdate, onBusyChange }) {
  const [searchParams] = useSearchParams();
  const initialTerritory = targetTerritoryId ?? Number(searchParams.get('territory'));
  const initialRecipient = targetRecipientId ?? Number(searchParams.get('recipient'));
  const initialRequest = targetRequestId ?? searchParams.get('request');
  const { language } = useLocalizationContext();
  const copy = key => reinforcementMessage(key, language);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [clanless, setClanless] = useState(false);
  const [busy, setBusy] = useState(false);
  const [targetKey, setTargetKey] = useState('');
  const [originId, setOriginId] = useState(null);
  const [picked, setPicked] = useState([]);
  const [confirmation, setConfirmation] = useState(null);
  const [notice, setNotice] = useState('');
  const [clock, setClock] = useState(Date.now);
  const mounted = useRef(false);
  const reading = useRef(null);
  const writing = useRef(false);
  const generation = useRef(0);
  const ownClan = useRef(null);
  const commands = useRef(new Map());
  const selection = useRef({ key: '', ids: [], origin: null });
  const dialog = useRef(null);
  const dialogId = React.useId();
  const selectId = React.useId();
  const originSelectId = React.useId();
  useEffect(() => { onBusyChange?.(busy); return () => onBusyChange?.(false); }, [busy, onBusyChange]);
  function chooseTarget(value) { selection.current.key = value; setTargetKey(value); }
  function chooseOrigin(value) { selection.current.origin = value; setOriginId(value); }
  function choosePlayers(ids) { selection.current.ids = ids; setPicked(ids); }
  function closeConfirmation() { dialog.current = null; setConfirmation(null); }

  const load = useCallback(async (force = false) => {
    if (writing.current || (reading.current !== null && !force)) return;
    const token = ++generation.current;
    reading.current = token;
    try {
      const clan = await clanService.getMyClan();
      if (!mounted.current || token !== generation.current) return;
      if (clan === null) {
        setData(null); choosePlayers([]); chooseTarget(''); chooseOrigin(null); closeConfirmation();
        commands.current.clear(); ownClan.current = null; setNotice('');
        setClanless(true); setFailed(false);
        return;
      }
      const next = await service.getReinforcements(cycleId, clan.id);
      if (!mounted.current || token !== generation.current) return;
      if (ownClan.current !== next.clan_id) {
        ownClan.current = next.clan_id; commands.current.clear();
        chooseTarget(''); choosePlayers([]); chooseOrigin(null); closeConfirmation();
        const options = [...next.own_targets.map(t => ({ ...t, recipient_clan_id: next.clan_id, request_id: null })), ...next.allied_targets];
        const match = options.find(t => t.territory_id === initialTerritory
          && t.recipient_clan_id === (initialRecipient || next.clan_id) && (t.request_id || null) === initialRequest);
        if (match) chooseTarget(dispatchTargetKey(match));
      }
      if (dialog.current && (!next.can_command || dialog.current.revision !== next.state?.revision)) {
        closeConfirmation(); setNotice('conflict');
      }
      if (selection.current.origin !== null && !(next.origins || []).some(t => t.territory_id === selection.current.origin)) {
        chooseOrigin(null); closeConfirmation(); setNotice('conflict');
      }
      for (const command of commands.current.values()) {
        const done = command.action === 'dispatch' ? next.state?.dispatches.some(d => d.id === command.id)
          : next.state?.requests.some(q => q.id === command.id);
        if (!done) continue;
        commands.current.delete(command.signature);
        if (command.action === 'dispatch') {
          if (selection.current.key === command.key && selection.current.origin === command.origin
            && JSON.stringify([...selection.current.ids].sort((a, b) => a - b)) === JSON.stringify(command.players)) {
            choosePlayers([]); chooseTarget('');
          }
          setNotice('sent');
        } else setNotice('requested');
      }
      setData({ ...next, receivedAt: Date.now() }); setFailed(false); setClanless(false);
    } catch (error) {
      if (!mounted.current || token !== generation.current) return;
      setFailed(true); closeConfirmation();
      if ([403, 404].includes(error.response?.status)) {
        setData(null); choosePlayers([]); chooseTarget(''); chooseOrigin(null); commands.current.clear(); ownClan.current = null;
        setClanless(error.response.status === 404);
      }
    } finally {
      if (reading.current === token) reading.current = null;
      if (mounted.current && token === generation.current) setLoading(false);
    }
  }, [cycleId, initialTerritory, initialRecipient, initialRequest]);
  useEffect(() => {
    mounted.current = true; load();
    const poll = setInterval(() => load(), 15_000);
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => { mounted.current = false; clearInterval(poll); clearInterval(timer); };
  }, [load]);
  const now = data ? Date.parse(data.server_time) + Math.max(0, clock - data.receivedAt) : 0;
  const expired = !data || now >= Date.parse(data.command_deadline);
  const disabled = busy || failed || !data?.can_command || expired;
  const targets = data ? [...data.own_targets.map(t => ({ ...t, recipient_clan_id: data.clan_id, request_id: null })), ...data.allied_targets]
    .filter(target => targetTerritoryId == null || target.territory_id === targetTerritoryId) : [];
  const target = targets.find(t => dispatchTargetKey(t) === targetKey);
  const origins = data?.origins || [];
  const validOrigin = origins.length ? origins.some(t => t.territory_id === originId) : originId === null;
  const routePreview = validOrigin && target ? data?.route_previews?.find(route => route.origin_territory_id === originId && route.target_territory_id === target.territory_id) : null;
  const validPlayers = picked.length > 0 && picked.every(id => data?.players.some(p => p.user_id === id && p.available));
  const territory = id => data?.territories.find(t => t.id === id)?.name || `#${id}`;
  const clanName = id => data?.clans.find(c => c.id === id)?.name || `${copy('unavailableClan')} #${id}`;
  const playerName = id => data?.names.find(p => p.user_id === id)?.name || data?.players.find(p => p.user_id === id)?.name || `#${id}`;
  const time = value => formatMoscowDateTime(value, '-', language);
  useEffect(() => {
    if (expired && dialog.current) { dialog.current = null; setConfirmation(null); }
  }, [expired]);

  function confirmSend(event) {
    event.preventDefault();
    if (disabled || !target || !validPlayers || !validOrigin) return;
    const draft = { target: { ...target, origin_territory_id: originId }, route: routePreview,
      players: [...picked].sort((a, b) => a - b), revision: data.state.revision, clanId: data.clan_id };
    dialog.current = draft; setConfirmation(draft);
  }
  async function execute(action, destination, ids = [], confirmedRevision = null) {
    if (disabled || writing.current || !data?.state) return;
    if (confirmedRevision !== null && confirmedRevision !== data.state.revision) { closeConfirmation(); setNotice('conflict'); return; }
    const candidate = reinforcementCommand(null, action, destination, ids);
    const command = commands.current.get(candidate.signature) || { ...candidate, key: dispatchTargetKey(destination),
      origin: destination.origin_territory_id ?? null, players: [...ids].sort((a, b) => a - b) };
    commands.current.set(command.signature, command);
    generation.current += 1; writing.current = true; setBusy(true); setNotice(''); closeConfirmation();
    try {
      const payload = { territory_id: destination.territory_id, expected_revision: data.state.revision };
      if (action === 'dispatch') await service.dispatch(cycleId, data.clan_id, { ...payload, dispatch_id: command.id,
        origin_territory_id: command.origin,
        recipient_clan_id: destination.recipient_clan_id, request_id: destination.request_id || null, player_user_ids: command.players });
      else await service.requestHelp(cycleId, data.clan_id, { ...payload, request_id: command.id });
      if (!mounted.current) return;
      setNotice(action === 'dispatch' ? 'sent' : 'requested');
      if (action === 'dispatch') { choosePlayers([]); chooseTarget(''); }
      commands.current.delete(command.signature);
      writing.current = false;
      await load(true);
      onUpdate?.();
    } catch (error) {
      if (!mounted.current) return;
      writing.current = false;
      setNotice([403, 409].includes(error.response?.status) ? 'conflict' : 'failed');
      if ([403, 409].includes(error.response?.status)) await load(true);
    } finally { writing.current = false; if (mounted.current) setBusy(false); }
  }
  const movements = data?.state?.dispatches.filter(d => d.sender_clan_id === data.clan_id || d.recipient_clan_id === data.clan_id) || [];
  const ownTargets = data?.own_targets.filter(target => targetTerritoryId == null || target.territory_id === targetTerritoryId) || [];
  return <PageShell as={embedded ? 'section' : 'main'} className="cycle-reinforcements" aria-busy={loading || busy}>
    {!embedded && <><header><h1>{copy('screen')}</h1><button type="button" disabled={loading || busy} title={copy('refresh')} aria-label={copy('refresh')} onClick={() => load(true)}><Refresh aria-hidden="true" /></button></header>
    <Link className="cr-back" to={`/campaign/cycles/${cycleId}`}><ArrowBack aria-hidden="true" />{copy('battles')}</Link></>}
    {loading ? <p role="status">{copy('loading')}</p> : clanless ? <p>{copy('clanless')}</p> : <>
      {failed && <p role="alert" className="cr-error">{copy('loadFailed')}</p>}
      {data && <><h2>{data.clan_name}</h2>
        <p className="cr-muted">{copy('deadline')}: {time(data.command_deadline)}</p>
        {!data.ready ? <p>{copy('notReady')}</p> : <>
          {(!data.can_command || expired) && <p className="cr-muted">{copy('readonly')}</p>}
          {['conflict', 'failed'].includes(notice) ? <p role="alert" className="cr-error">{copy(notice)}</p> : <p role="status">{notice ? copy(notice) : ''}</p>}
          <section className="cr-section" aria-labelledby="cr-help-heading"><h2 id="cr-help-heading">{copy('assistance')}</h2>
            {!ownTargets.length ? <p className="cr-muted">{copy('noBattles')}</p> : <ul className="cr-help-list">{ownTargets.map(t => {
              const waiting = data.state.requests.some(q => q.recipient_clan_id === data.clan_id && q.territory_id === t.territory_id && !q.dispatch_id);
              const incoming = data.state.dispatches.some(d => d.recipient_clan_id === data.clan_id && d.territory_id === t.territory_id && d.sender_clan_id !== data.clan_id);
              return <li key={t.territory_id}><div><Link to={`/campaign/cycles/${cycleId}?territory=${t.territory_id}`}>{territory(t.territory_id)}</Link>
                {waiting && <small>{copy('waiting')}</small>}{incoming && <small>{copy('incoming')}</small>}</div>
                {data.can_command && <button type="button" disabled={disabled || !data.help_targets.includes(t.territory_id)}
                  onClick={() => execute('request', { territory_id: t.territory_id, recipient_clan_id: data.clan_id })}><SupportAgent aria-hidden="true" />{copy('request')}</button>}</li>;
            })}</ul>}
          </section>
          <section className="cr-section" aria-labelledby="cr-reserve-heading"><h2 id="cr-reserve-heading">{copy('reserve')}</h2>
            <form onSubmit={confirmSend}>
              {!data.players.length ? <p className="cr-muted">{copy('noReserve')}</p> : <ul className="cr-players">{data.players.map(player => <li key={player.user_id}>
                <label><input type="checkbox" checked={picked.includes(player.user_id)} disabled={disabled || (!player.available && !picked.includes(player.user_id))}
                  onChange={event => choosePlayers(event.target.checked ? [...picked, player.user_id] : picked.filter(id => id !== player.user_id))} />
                  {player.avatar_url && <img src={player.avatar_url} alt="" loading="lazy" />}<span>{player.name || `#${player.user_id}`}</span></label>
                {player.unavailable_reason && <small>{copy(player.unavailable_reason)}</small>}</li>)}</ul>}
              {data.can_command && <><label htmlFor={selectId}>{copy('target')}</label><select id={selectId} value={targetKey} disabled={disabled} onChange={event => chooseTarget(event.target.value)}>
                <option value="">{copy('choose')}</option><optgroup label={copy('own')}>{targets.filter(t => !t.request_id).map(t => <option key={dispatchTargetKey(t)} value={dispatchTargetKey(t)}>{territory(t.territory_id)}</option>)}</optgroup>
                <optgroup label={copy('allied')}>{targets.filter(t => t.request_id).map(t => <option key={dispatchTargetKey(t)} value={dispatchTargetKey(t)}>{clanName(t.recipient_clan_id)} · {territory(t.territory_id)}</option>)}</optgroup>
              </select>
              {origins.length > 0 ? <><label htmlFor={originSelectId}>{copy('origin')}</label>
                <select id={originSelectId} value={originId ?? ''} required disabled={disabled}
                  onChange={event => chooseOrigin(event.target.value ? Number(event.target.value) : null)}>
                  <option value="">{copy('chooseOrigin')}</option>
                  {origins.map(origin => <option key={origin.territory_id} value={origin.territory_id}>{origin.name}</option>)}
                </select></> : <p className="cr-muted">{copy('routeLandless')}</p>}
              {target && validOrigin && routePreview && <CycleDispatchRouteMap route={routePreview} language={language} />}
              {!data.allied_targets.length && <p className="cr-muted">{copy('noAllied')}</p>}
              <button className="cr-gold" type="submit" disabled={disabled || !target || !validPlayers || !validOrigin}><Send aria-hidden="true" />{copy('send')}</button></>}
            </form>
          </section>
          <section className="cr-section" aria-labelledby="cr-movements-heading"><h2 id="cr-movements-heading">{copy('movements')}</h2>
            {!movements.length ? <p className="cr-muted">{copy('noMovements')}</p> : <ul className="cr-movements">{movements.map(d => <li className="cr-dispatch" key={d.id}>
              <h3>{clanName(d.sender_clan_id)} → {clanName(d.recipient_clan_id)}</h3>
              <Link to={`/campaign/cycles/${cycleId}?territory=${d.territory_id}`}>{territory(d.territory_id)}</Link>
              <p className={`cr-route-status cr-route-${d.outcome}`}>{copy(dispatchState(d, now))}</p>
              {d.interception_at && now >= Date.parse(d.interception_at) && <Link to={interceptionPath(cycleId, d.id)}>{interceptionMessage('open', language)}</Link>}
              <p>{d.player_user_ids.map(playerName).join(', ')}</p>
              <CycleDispatchRouteMap route={d.route} language={language} />
              {now < Date.parse(d.arrives_at) && <p className="cr-countdown">{copy('remaining')}: <time>{dispatchCountdown(d, now)}</time></p>}
              <dl>{[['sentAt', d.sent_at], ['arrival', d.arrives_at], ...(d.interception_at ? [['interception', d.interception_at], ['interceptionEnd', d.interception_ends_at]] : [])].map(([key, value]) => <div key={key}><dt>{copy(key)}</dt><dd>{time(value)}</dd></div>)}</dl>
            </li>)}</ul>}
          </section>
        </>}
      </>}
    </>}
    <Dialog open={Boolean(confirmation)} onClose={closeConfirmation} aria-labelledby={dialogId}>
      <DialogTitle id={dialogId}>{copy('confirmHeading')}</DialogTitle><DialogContent>
        <p>{confirmation && `${clanName(confirmation.target.recipient_clan_id)} · ${territory(confirmation.target.territory_id)}`}</p>
        {confirmation?.target.origin_territory_id && <p>{copy('origin')}: {origins.find(t => t.territory_id === confirmation.target.origin_territory_id)?.name}</p>}
        {confirmation?.route && <CycleDispatchRouteMap route={confirmation.route} language={language} />}
        <p>{copy('selected')}: {confirmation?.players.map(playerName).join(', ')}</p><p>{copy('confirmText')}</p>
      </DialogContent><DialogActions><button className="cr-dialog-button" autoFocus onClick={closeConfirmation}>{copy('cancel')}</button>
        <button className="cr-dialog-button cr-gold" disabled={disabled || !confirmation || !validPlayers || !target || !validOrigin}
          onClick={() => execute('dispatch', confirmation.target, confirmation.players, confirmation.revision)}><Send aria-hidden="true" />{copy('confirm')}</button></DialogActions>
    </Dialog>
  </PageShell>;
}

export default function CycleReinforcementsPage() {
  const { cycleId } = useParams();
  const { user } = useAuth();
  const [params] = useSearchParams();
  return <ReinforcementsContent key={`${user?.id}:${cycleId}:${params.toString()}`} cycleId={cycleId} />;
}
