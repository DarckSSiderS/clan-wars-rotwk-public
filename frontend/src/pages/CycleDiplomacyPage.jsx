import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Check, Close, Gavel, Handshake, LinkOff, Refresh, Search, Send, Shield } from '@mui/icons-material';
import { Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material';
import { PageShell } from '../components/ui';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { clanService } from '../services/clanService';
import { cycleCampaignService } from '../services/cycleCampaignService';
import { cycleDiplomacyService as service } from '../services/cycleDiplomacyService';
import { cyclePhaseLabel } from '../utils/cycleBattleView';
import { formatMoscowDateTime } from '../utils/dateTime';
import { buildDiplomacyAction, diplomacyEditable, diplomacyLabel, diplomacyMessage,
  filterRelations, isDiplomacyHead, parseWarDuration, relationForClan } from '../utils/cycleDiplomacyView';
import './CycleDiplomacyPage.css';

function ClanLink({ clan, id, copy }) {
  return <Link className="cd-clan" to={`/clans/${id}`}>
    {clan?.avatar_url ? <img src={clan.avatar_url} alt="" loading="lazy" /> : <Shield aria-hidden="true" />}
    <span>{clan?.name || `${copy('deleted')} #${id}`}</span>
  </Link>;
}

function Relation({ row, copy, language }) {
  const label = value => diplomacyLabel(value, language);
  return <li className="cd-relation">
    <div className="cd-pair"><ClanLink clan={row.clan_low} id={row.clan_low_id} copy={copy} />
      <span className="cd-status">{row.status === 'allied' ? <Handshake aria-hidden="true" /> : row.status === 'hostile' ? <Gavel aria-hidden="true" /> : <Shield aria-hidden="true" />}{label(row.status)}</span>
      <ClanLink clan={row.clan_high} id={row.clan_high_id} copy={copy} /></div>
    {row.allied_at && <p className="cd-muted">{copy('since')}: {formatMoscowDateTime(row.allied_at, '-', language)}</p>}
    {Object.entries(row.declarations || {}).length > 0 && <ul className="cd-terms">{Object.entries(row.declarations).map(([id, term]) => <li key={id}>
      <strong>{Number(id) === row.clan_low_id ? row.clan_low?.name || `${copy('clan')} #${id}` : row.clan_high?.name || `${copy('clan')} #${id}`}</strong>
      <span>{label(term.source)}</span>
      <span>{term.remaining_cycles == null ? copy('indefinite') : `${copy('remaining')}: ${term.remaining_cycles}`}</span>
      {term.last_cycle != null && <span>{copy('ends')}: {term.last_cycle}</span>}
      <span className="cd-muted">{copy('declared')}: {formatMoscowDateTime(term.declared_at, '-', language)}</span>
    </li>)}</ul>}
  </li>;
}

function HeadControls({ data, busy, submit, copy, language }) {
  const [target, setTarget] = useState('');
  const [duration, setDuration] = useState('');
  const [indefinite, setIndefinite] = useState(false);
  const [invalid, setInvalid] = useState(false);
  const [confirmation, setConfirmation] = useState(null);
  const errorId = React.useId();
  const phaseId = React.useId();
  const dialogId = React.useId();
  const otherId = Number(target);
  const options = data.clans.filter(clan => clan.id !== data.clan.id && !clan.is_deleted);
  const validTarget = options.some(clan => clan.id === otherId);
  const relation = relationForClan(data.relations, data.clan.id, otherId);
  const editable = diplomacyEditable(data.cycle.phase);
  const disabled = busy || !editable;
  const status = relation?.status || 'neutral';
  const name = id => data.clans.find(clan => clan.id === id)?.name || `${copy('clan')} #${id}`;
  function command(action) {
    let term;
    if (action === 'declare_war') {
      try { term = parseWarDuration(duration, indefinite); setInvalid(false); }
      catch { setInvalid(true); return; }
    }
    const payload = buildDiplomacyAction({ action, otherClanId: otherId, own: data.own, duration: term });
    if (action === 'declare_war' || action === 'break_alliance') setConfirmation(payload);
    else submit(payload);
  }
  return <section className="cd-management" aria-labelledby="cd-management-heading">
    <h2 id="cd-management-heading">{copy('management')}</h2>
    {!editable && <p id={phaseId} className="cd-muted">{copy('blocked')}</p>}
    <fieldset disabled={disabled} aria-describedby={!editable ? phaseId : undefined}>
      <legend className="cd-sr-only">{copy('management')}</legend>
      <label className="cd-target">{copy('target')}<select value={target} onChange={e => { setTarget(e.target.value); setInvalid(false); }}>
        <option value="">{copy('choose')}</option>{options.map(clan => <option key={clan.id} value={clan.id}>{clan.name}</option>)}
      </select></label>
      {validTarget && <p className="cd-muted">{name(otherId)}: {diplomacyLabel(status, language)}</p>}
      <div className="cd-actions">
        <button disabled={!validTarget || status !== 'neutral'} onClick={() => command('offer_alliance')}><Handshake aria-hidden="true" />{copy('offerAlliance')}</button>
        <button disabled={!validTarget || status !== 'hostile'} onClick={() => command('offer_peace')}><Send aria-hidden="true" />{copy('offerPeace')}</button>
        <button disabled={!validTarget || status !== 'allied'} onClick={() => command('break_alliance')}><LinkOff aria-hidden="true" />{copy('break')}</button>
      </div>
      <form noValidate onSubmit={e => { e.preventDefault(); command('declare_war'); }}>
        <fieldset disabled={!validTarget || status === 'allied'}>
          <legend>{copy('war')}</legend>
          <div className="cd-war-fields"><label>{copy('durationMode')}<select value={indefinite ? 'indefinite' : 'finite'} onChange={e => { setIndefinite(e.target.value === 'indefinite'); setInvalid(false); }}>
            <option value="finite">{copy('finite')}</option><option value="indefinite">{copy('indefinite')}</option>
          </select></label>
          {!indefinite && <label>{copy('duration')}<input type="text" inputMode="numeric" pattern="[0-9]+" required value={duration}
            onChange={e => { setDuration(e.target.value); setInvalid(false); }} aria-invalid={invalid} aria-describedby={invalid ? errorId : undefined} /></label>}
          <button type="submit"><Gavel aria-hidden="true" />{copy('war')}</button></div>
          {invalid && <p id={errorId} role="alert" className="cd-error">{copy('durationError')}</p>}
        </fieldset>
      </form>
    </fieldset>
    <h3>{copy('proposals')}</h3>
    {!data.own.proposals.length ? <p className="cd-muted">{copy('noProposals')}</p> : <ul className="cd-proposals">{data.own.proposals.map(proposal => {
      const outgoing = proposal.sender_clan_id === data.clan.id;
      const current = relationForClan(data.relations, data.clan.id, proposal.other_clan_id);
      const cannotAccept = proposal.kind === 'alliance' && ['hostile', 'allied'].includes(current?.status);
      return <li key={proposal.id}>
        <div><strong>{diplomacyLabel(proposal.kind, language)} · {outgoing ? copy('outgoing') : copy('incoming')}</strong>
          <Link to={`/clans/${proposal.other_clan_id}`}>{name(proposal.other_clan_id)}</Link>
          <p>{diplomacyLabel(proposal.status, language)} · {copy('expires')}: {proposal.expires_after_cycle}</p>
          <small>{copy('created')}: {formatMoscowDateTime(proposal.created_at, '-', language)}</small></div>
        {proposal.status === 'pending' && <button disabled={disabled || (!outgoing && cannotAccept)} aria-describedby={!editable ? phaseId : undefined}
          onClick={() => submit(buildDiplomacyAction({ action: outgoing ? 'revoke' : 'accept', otherClanId: proposal.other_clan_id, own: data.own, proposalId: proposal.id }))}>
          {outgoing ? <Close aria-hidden="true" /> : <Check aria-hidden="true" />}{outgoing ? copy('revoke') : copy('accept')}
        </button>}
      </li>;
    })}</ul>}
    <Dialog className="cd-confirm" open={Boolean(confirmation)} onClose={() => setConfirmation(null)} aria-labelledby={dialogId} PaperProps={{ role: 'alertdialog' }}>
      <DialogTitle id={dialogId}>{copy(confirmation?.action === 'declare_war' ? 'confirmWar' : 'confirmBreak')}</DialogTitle>
      <DialogContent>{name(confirmation?.other_clan_id)}{confirmation?.action === 'declare_war' && <p>{confirmation.duration == null ? copy('indefinite') : `${copy('duration')}: ${confirmation.duration}`}</p>}</DialogContent>
      <DialogActions><button className="cd-dialog-button" autoFocus onClick={() => setConfirmation(null)}>{copy('cancel')}</button>
        <button className="cd-dialog-button" disabled={disabled} onClick={() => { const payload = confirmation; setConfirmation(null); submit(payload); }}><Check aria-hidden="true" />{copy('confirm')}</button></DialogActions>
    </Dialog>
  </section>;
}

function DiplomacyContent({ cycleId, user }) {
  const { language } = useLocalizationContext();
  const copy = key => diplomacyMessage(key, language);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const request = useRef(0);
  const mounted = useRef(false);
  const writing = useRef(false);
  const load = useCallback(async () => {
    const token = ++request.current;
    setLoading(true); setError(false);
    try {
      const [cycle, relations] = await Promise.all([cycleCampaignService.getCycle(cycleId), service.getRelations(cycleId)]);
      let clan = null, own = null, clans = [], privateError = false;
      try {
        clan = await clanService.getMyClan();
        if (isDiplomacyHead(user, clan)) [own, clans] = await Promise.all([service.getOwn(cycleId, clan.id), service.getClanDirectory()]);
      } catch (failure) { privateError = failure.response?.status !== 404; }
      if (mounted.current && token === request.current) setData({ cycle, relations, clan, own, clans, privateError });
      return true;
    } catch {
      if (mounted.current && token === request.current) setError(true);
      return false;
    } finally { if (mounted.current && token === request.current) setLoading(false); }
  }, [cycleId, user]);
  useEffect(() => {
    mounted.current = true;
    load();
    return () => { mounted.current = false; request.current += 1; };
  }, [load]);
  async function submit(payload) {
    if (writing.current || loading || error || !data?.own || !isDiplomacyHead(user, data.clan) || !diplomacyEditable(data.cycle.phase)) return;
    writing.current = true; setBusy(true); setNotice('');
    try {
      await service.act(cycleId, data.clan.id, payload);
      if (mounted.current) { await load(); if (mounted.current) setNotice('saved'); }
    } catch (failure) {
      if (mounted.current) {
        const refreshed = await load();
        if (mounted.current) setNotice(failure.response?.status === 409 && refreshed ? 'conflict' : 'actionFailed');
      }
    } finally { writing.current = false; if (mounted.current) setBusy(false); }
  }
  const rows = filterRelations(data?.relations, search, status);
  const sections = [['allied', 'allies'], ['hostile', 'enemies'], ['neutral', 'neutrals']];
  return <PageShell className="cycle-diplomacy" aria-busy={loading || busy}>
    <header className="cd-header"><div><h1>{copy('diplomacy_title')}</h1>{data && <p>{copy('cycle')} {data.cycle.number} · {copy('phase')}: {cyclePhaseLabel(data.cycle.phase, language)}</p>}</div>
      <button onClick={load} disabled={loading || busy} title={copy('refresh')} aria-label={copy('refresh')}><Refresh aria-hidden="true" /></button></header>
    {notice && <p role={notice === 'saved' ? 'status' : 'alert'} className={notice === 'saved' ? 'cd-muted' : 'cd-error'}>{copy(notice)}</p>}
    {loading && <p role="status">{copy('loading')}</p>}
    {error && <div role="alert"><p>{copy('failed')}</p><button onClick={load}><Refresh aria-hidden="true" />{copy('refresh')}</button></div>}
    {data && !error && <>
      <div className="cd-filters"><label><span><Search aria-hidden="true" />{copy('search')}</span><input type="search" value={search} onChange={e => setSearch(e.target.value)} /></label>
        <label>{copy('filter')}<select value={status} onChange={e => setStatus(e.target.value)}><option value="all">{copy('all')}</option>{sections.map(([value, key]) => <option key={value} value={value}>{copy(key)}</option>)}</select></label></div>
      {!rows.length ? <div className="cd-empty"><p role="status">{copy('relations_empty')}</p><button onClick={() => { setSearch(''); setStatus('all'); }} disabled={!search && status === 'all'}>{copy('clear')}</button></div> : sections.map(([value, key]) => {
        const group = rows.filter(row => row.status === value);
        return group.length > 0 && <section className="cd-public-section" key={value} aria-labelledby={`cd-${value}`}><h2 id={`cd-${value}`}>{copy(key)} <span className="cd-muted">{group.length}</span></h2>
          <ul className="cd-relations">{group.map(row => <Relation key={`${row.clan_low_id}-${row.clan_high_id}`} row={row} copy={copy} language={language} />)}</ul></section>;
      })}
      {data.privateError && <p role="alert" className="cd-error">{copy('privateFailed')}</p>}
      {!data.privateError && data.own && isDiplomacyHead(user, data.clan) && <HeadControls data={data} busy={busy || loading} submit={submit} copy={copy} language={language} />}
    </>}
  </PageShell>;
}

export default function CycleDiplomacyPage() {
  const { cycleId } = useParams();
  const { user } = useAuth();
  return <DiplomacyContent key={`${cycleId}-${user?.id}`} cycleId={cycleId} user={user} />;
}
