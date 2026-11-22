import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import { Add, Close, Refresh, Send, SwapHoriz, LocalShipping } from '@mui/icons-material';
import api from '../services/api';
import { clanService } from '../services/clanService';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { costText, economyMessage, resources } from '../utils/cycleEconomyView';
import { formatMoscowDateTime } from '../utils/dateTime';
import { barterFee, rememberBarterCommand, forgetBarterCommand } from '../utils/cycleBarterCommands';
import { barterMessage, cargoFromRows, materials, offerPerspective, validCargoRows } from '../utils/cycleBarterView';
import { CLAN_RESOURCE_BY_KEY } from './clan/clanResources';
import { useAuth } from '../contexts/AuthContext';
import './CycleBarter.css';

export function ResourceAmounts({ cargo, copy }) {
  return <span className="ce-resource-amounts">{resources.filter(key => Number(cargo?.[key]) > 0).map(key => {
    const { Icon } = CLAN_RESOURCE_BY_KEY[key];
    return <span key={key}><Icon aria-hidden="true" /><span>{cargo[key]} {copy(key)}</span></span>;
  })}</span>;
}

function CargoEditor({ rows, onChange, heading, copy, disabled }) {
  return <fieldset disabled={disabled}><legend>{copy(heading)}</legend>
    {rows.map((row, index) => <div className="cb-cargo-row" key={index}>
      <label><span className="cb-sr-only">{`${copy(heading)}: ${copy('material')} ${index + 1}`}</span>
        <select value={row.resource} onChange={e => onChange(rows.map((value, i) => i === index ? { ...row, resource: e.target.value } : value))}>
          {materials.filter(key => key === row.resource || !rows.some(value => value.resource === key)).map(key => <option key={key} value={key}>{copy(key)}</option>)}
        </select></label>
      <label><span className="cb-sr-only">{`${copy(heading)}: ${copy(row.resource)}`}</span><input type="text" inputMode="decimal" required value={row.amount}
        aria-invalid={row.amount !== '' && !validCargoRows([row])} onChange={e => onChange(rows.map((value, i) => i === index ? { ...row, amount: e.target.value } : value))} /></label>
      <button type="button" className="ce-dialog-button" title={`${copy(heading)}: ${copy('remove')}`} aria-label={`${copy(heading)}: ${copy('remove')} ${index + 1}`} disabled={rows.length === 1 || disabled} onClick={() => onChange(rows.filter((_, i) => i !== index))}><Close aria-hidden="true" /></button>
    </div>)}
    {rows.length < materials.length && <button type="button" className="ce-dialog-button cb-add" aria-label={`${copy(heading)}: ${copy('add')}`} onClick={() => onChange([...rows, { resource: materials.find(key => !rows.some(row => row.resource === key)), amount: '' }])}><Add aria-hidden="true" />{copy('resource')}</button>}
  </fieldset>;
}

export default function CycleBarter({ data, refreshWallet, suspended = false }) {
  const { user } = useAuth();
  const { language } = useLocalizationContext(); const copy = key => barterMessage(key, language);
  const base = `/campaign/cycles/market/cycles/${data.cycle_id}`;
  const own = `${base}/clans/${data.clan_id}`;
  const [view, setView] = useState({ offers: [], caravans: [], clans: [] });
  const [loading, setLoading] = useState(true), [busy, setBusy] = useState(false), [error, setError] = useState(false);
  const [offered, setOffered] = useState([{ resource: 'wood', amount: '' }]), [requested, setRequested] = useState([{ resource: 'mithril', amount: '' }]), [target, setTarget] = useState('');
  const [creating, setCreating] = useState(false);
  const [confirmation, setConfirmation] = useState(null);
  const mounted = useRef(false), writing = useRef(false);
  const commandScope = `${user?.id}:${data.season_id}:${data.clan_id}`;
  const dialogId = React.useId();
  const canTrade = data.can_trade && data.lands.length > 0;
  const load = useCallback(async () => {
    try {
      const [publicView, ownView, clans] = await Promise.all([api.get(base), api.get(own), clanService.getClans()]);
      if (mounted.current) {
        const offers = [...new Map([...publicView.data.offers, ...ownView.data.offers].map(offer => [offer.id, offer])).values()];
        setView({ offers, caravans: ownView.data.caravans, clans }); setError(false);
      }
    } catch { if (mounted.current) setError(true); }
    finally { if (mounted.current) setLoading(false); }
  }, [base, own]);
  useEffect(() => { mounted.current = true; load(); return () => { mounted.current = false; }; }, [load]);
  const clanName = id => view.clans.find(c => String(c.id) === String(id))?.name || `#${id}`;
  async function quote(offer) {
    if (writing.current || !canTrade || error || suspended) return;
    writing.current = true; setBusy(true);
    try {
      const { data: quote } = await api.get(`${own}/offers/${offer.id}/quote`);
      if (mounted.current) setConfirmation({ action: `${own}/offers/${offer.id}/accept`, payload: {
        expected_revision: quote.expected_revision, expected_sender_revision: quote.expected_sender_revision,
        expected_wallet_revision: quote.expected_wallet_revision }, quote, offer });
    } catch { if (mounted.current) { await load(); setError(true); } }
    finally { writing.current = false; if (mounted.current) setBusy(false); }
  }
  async function execute() {
    if (writing.current || !confirmation || !canTrade || suspended) return;
    const { action, payload } = confirmation;
    const signature = JSON.stringify([action, payload.offered, payload.requested, payload.target_clan_id]);
    let id;
    try { id = rememberBarterCommand(sessionStorage, commandScope, signature); }
    catch { setError(true); setConfirmation(null); setCreating(false); return; }
    writing.current = true; setBusy(true);
    try {
      await api.post(action, { ...payload, command_id: id });
      try { forgetBarterCommand(sessionStorage, commandScope, signature); } catch { /* Keep an uncertain receipt rather than manufacture a new command. */ }
      if (mounted.current) { await load(); await refreshWallet(); }
    } catch { if (mounted.current) setError(true); }
    finally { writing.current = false; if (mounted.current) { setBusy(false); setConfirmation(null); setCreating(false); } }
  }
  const disabled = loading || busy || suspended;
  const validDraft = validCargoRows(offered) && validCargoRows(requested);
  const pending = view.offers.filter(offer => offer.status === 'pending');
  const history = view.offers.filter(offer => offer.status !== 'pending');
  const confirmationCargo = confirmation?.offer ? offerPerspective(confirmation.offer, data.clan_id)
    : { give: confirmation?.payload.offered, receive: confirmation?.payload.requested };
  const isCancel = confirmation?.action.endsWith('/cancel');
  function closeDialog() { if (!busy) { setCreating(false); setConfirmation(null); } }
  function renderOffer(offer) {
    const perspective = offerPerspective(offer, data.clan_id);
    return <li className="cb-offer" key={offer.id}>
      <div className="cb-offer-clan"><strong>{clanName(offer.sender_clan_id)}</strong><span>{perspective.own ? copy('own') : offer.target_clan_id ? clanName(offer.target_clan_id) : copy('public')}
        {perspective.own && <>{' · '}{offer.accepter_clan_id || offer.target_clan_id ? clanName(offer.accepter_clan_id || offer.target_clan_id) : copy('public')}</>}
      </span><span className={`cb-status cb-status--${offer.status}`}>{copy(offer.status)}</span></div>
      <div className="cb-give"><span>{copy('youGive')}</span><ResourceAmounts cargo={perspective.give} copy={copy} /></div>
      <SwapHoriz className="cb-swap" aria-hidden="true" />
      <div className="cb-receive"><span>{copy('youReceive')}</span><ResourceAmounts cargo={perspective.receive} copy={copy} /></div>
      <div className="cb-offer-action"><span>{copy('fee')}: {barterFee(perspective.receive, data.market_buy)}</span>
        {offer.status === 'pending' && <small>{copy('expires')} {offer.expires_after_cycle}</small>}
        {canTrade && offer.status === 'pending' && (perspective.own
          ? <button disabled={disabled || error} onClick={() => setConfirmation({ action: `${own}/offers/${offer.id}/cancel`, offer, payload: { expected_wallet_revision: data.state.revision, expected_revision: offer.revision } })}>{copy('cancel')}</button>
          : <button className="ce-gold" disabled={disabled || error} onClick={() => quote(offer)}>{copy('accept')}</button>)}
      </div>
    </li>;
  }
  return <div className="cycle-barter" aria-busy={disabled}>
    <div className="cb-heading"><h3>{copy('offers')} <span>{pending.length}</span></h3><div>
      <button disabled={disabled} onClick={load} title={copy('refresh')} aria-label={copy('refresh')}><Refresh aria-hidden="true" /></button>
      {canTrade && <button className="ce-gold" disabled={disabled} onClick={() => setCreating(true)}><Add aria-hidden="true" />{copy('create')}</button>}
    </div></div>
    <p className="cb-terms">{copy('terms')}</p>
    {error && <p role="alert" className="ce-error">{copy('conflict')}</p>}
    {!data.lands.length && <p>{copy('noLand')}</p>}
    {loading && <p role="status">{copy('loading')}</p>}
    {!loading && !pending.length ? <p className="cb-empty">{copy('offersEmpty')}</p> : <ul className="cb-offers">{pending.map(renderOffer)}</ul>}
    <section className="cb-transit"><h3><LocalShipping aria-hidden="true" />{copy('transit')} <span>{view.caravans.filter(c => !c.delivered_at).length}</span></h3>
      {!view.caravans.some(c => !c.delivered_at) && <p className="cb-empty">{copy('transitEmpty')}</p>}
      <ul>{view.caravans.filter(c => !c.delivered_at).map(c => <li className="cb-caravan" key={c.id}><ResourceAmounts cargo={c.cargo} copy={copy} /><span>{copy('travelling')}</span><span>{copy('arrive')}: {formatMoscowDateTime(c.arrives_at, '-', language)}</span>{c.route?.travel_hours != null && <small>{copy('travel')}: {c.route.travel_hours}</small>}</li>)}</ul>
    </section>
    <details className="cb-history"><summary>{copy('history')} · {history.length + view.caravans.filter(c => c.delivered_at).length}</summary><ul>{history.map(renderOffer)}
      {view.caravans.filter(c => c.delivered_at).map(c => <li className="cb-caravan" key={`caravan-${c.id}`}><ResourceAmounts cargo={c.cargo} copy={copy} /><span>{copy('delivered')} · {formatMoscowDateTime(c.delivered_at, '-', language)}</span></li>)}
    </ul></details>
    <Dialog open={creating || Boolean(confirmation)} onClose={closeDialog} aria-labelledby={dialogId} fullWidth maxWidth="sm" className="cb-dialog">
      <DialogTitle id={dialogId}>{copy(confirmation ? isCancel ? 'cancel' : 'confirmOffer' : 'create')}</DialogTitle>
      <DialogContent>
        {!confirmation ? <form id={`${dialogId}-form`} className="cb-create-form" onSubmit={e => { e.preventDefault(); if (validDraft && canTrade) setConfirmation({ action: `${own}/offers`, payload: {
          expected_wallet_revision: data.state.revision, target_clan_id: target ? Number(target) : null,
          offered: cargoFromRows(offered), requested: cargoFromRows(requested) } }); }}>
          <div className="cb-cargo"><CargoEditor rows={offered} onChange={setOffered} heading="give" copy={copy} disabled={disabled} /><CargoEditor rows={requested} onChange={setRequested} heading="receive" copy={copy} disabled={disabled} /></div>
          <label>{copy('target')}<select value={target} disabled={disabled} onChange={e => setTarget(e.target.value)}><option value="">{copy('public')}</option>{view.clans.filter(c => String(c.id) !== String(data.clan_id) && !c.is_deleted).map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          {validCargoRows(requested) && <p>{copy('fee')}: {barterFee(cargoFromRows(requested), data.market_buy)}</p>}
        </form> : isCancel ? <p>{copy('refund')}: {costText(confirmation.offer.offered, copy)}</p> : <>
          <p className="cb-confirm-clan">{confirmation.offer ? clanName(confirmation.offer.sender_clan_id) : target ? clanName(target) : copy('public')}</p>
          <div className="cb-confirm-cargo"><div><span>{copy('youGive')}</span><ResourceAmounts cargo={confirmationCargo.give} copy={copy} /></div><div><span>{copy('youReceive')}</span><ResourceAmounts cargo={confirmationCargo.receive} copy={copy} /></div></div>
          <p>{copy('fee')}: {confirmation.quote?.fee_gold ?? barterFee(confirmation.payload.requested, data.market_buy)}</p>
          {confirmation.quote ? <div className="cb-delivery"><strong>{copy('routeConfirmed')}</strong>{confirmation.quote.travel_hours != null && <p>{copy('travel')}: {confirmation.quote.travel_hours}</p>}<p>{copy('arrive')}: {formatMoscowDateTime(confirmation.quote.arrives_at, '-', language)}</p></div> : <p>{copy('deliveryPending')}</p>}
          <p className="cb-terms">{copy('deliveryNote')}</p>
        </>}
      </DialogContent>
      <DialogActions><button className="ce-dialog-button" autoFocus onClick={closeDialog}>{economyMessage('cancel', language)}</button>
        {confirmation ? <button className="ce-dialog-button ce-gold" disabled={disabled || !canTrade} onClick={execute}>{copy('confirmAction')}</button>
          : <button className="ce-dialog-button ce-gold" type="submit" form={`${dialogId}-form`} disabled={disabled || !validDraft || !canTrade}><Send aria-hidden="true" />{copy('review')}</button>}
      </DialogActions>
    </Dialog>
  </div>;
}
