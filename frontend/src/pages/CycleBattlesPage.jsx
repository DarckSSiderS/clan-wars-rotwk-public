import React, { useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { Refresh, Shield, ArrowBack, Save, ArrowForward, MilitaryTech, MapOutlined, Schedule, ExpandMore, Groups, Search, Close, GridView, Public, EmojiEvents, SettingsOutlined, History, OpenInNew, EditOutlined } from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { PageShell } from '../components/ui';
import { Tabs, Tab } from '@mui/material';
import MatchDetailsDialog from '../components/MatchDetailsDialog';
import CycleMatchSummary from '../components/CycleMatchSummary';
import { cycleCampaignService as service } from '../services/cycleCampaignService';
import { cycleEconomyService } from '../services/cycleEconomyService';
import { useCycleBattleResource, readCycleResources } from '../utils/useCycleBattleResource';
import { cycleReadiness, readinessMessage } from '../utils/cycleReadiness';
import { createAdjustmentCommand, cycleMessage, cyclePhaseLabel, cycleReasonLabel, reviewCounted, selectTerritoryBattle, formatScore, groupClanBattles } from '../utils/cycleBattleView';
import { getPlayerDisplayName } from '../utils/playerIdentity';
import { formatMoscowDateTime } from '../utils/dateTime';
import { nextCycleDeadline, cycleSchedule, filterBattleList, summarizeClanBattles } from '../utils/cycleBattlePresentation';
import './CycleBattlesPage.css';
import './CycleBattleScreen.css';
import '../components/CycleMatchFeed.css';
import { territoryMatchFeed, matchFeedCounts, matchMessage, battleKind } from '../utils/cycleMatchPresentation';

const errorText = error => {
  const detail = error.response?.data?.detail;
  return typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : error.message || String(error);
};
const clanName = (side, copy) => side?.clan_name || `${copy('common_clan')} #${side?.clan_id}`;

function ErrorNotice({ error, copy, id }) {
  return <div id={id} role="alert" className="cycle-error">
    <p>{copy('cycle_request_failed')}</p>
    <details><summary>{copy('cycle_error_details')}</summary><p>{error}</p></details>
  </div>;
}

function ClanAvatar({ side }) {
  return side.avatar_url ? <img className="cycle-avatar" src={side.avatar_url} alt="" />
    : <Shield className="cycle-avatar" aria-hidden="true" />;
}

function LateReplayDecision({ battleId, item, copy, onDecided }) {
  const [preview, setPreview] = useState(null);
  const [counted, setCounted] = useState(true);
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef(null);
  const command = useRef(null);
  const errorId = React.useId();
  if (!command.current) command.current = createAdjustmentCommand();
  useEffect(() => () => request.current?.abort(), []);
  async function load() {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller; setBusy(true); setError(''); setConfirmed(false);
    try {
      const result = await service.previewLateReplay(battleId, item.match_id, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setPreview(result); setCounted(result.can_accept); command.current.reset();
    } catch (failure) { if (!controller.signal.aborted) setError(errorText(failure)); }
    finally {
      if (request.current === controller) {
        request.current = null;
        if (!controller.signal.aborted) setBusy(false);
      }
    }
  }
  async function submit(event) {
    event.preventDefault();
    if (request.current || !preview || !confirmed || !reason.trim() || (counted && !preview.can_accept)) return;
    const payload = { preview_token: preview.preview_token, counted, reason: reason.trim() };
    const controller = new AbortController();
    request.current = controller; setBusy(true); setError('');
    try {
      const updated = await service.decideLateReplay(battleId, item.match_id,
        { ...payload, command_id: command.current.get(payload) }, { signal: controller.signal });
      if (!controller.signal.aborted) onDecided(item.match_id, updated);
    } catch (failure) { if (!controller.signal.aborted) setError(errorText(failure)); }
    finally {
      if (request.current === controller) {
        request.current = null;
        if (!controller.signal.aborted) setBusy(false);
      }
    }
  }
  return <div className="cycle-late-decision" aria-busy={busy}>
    {!preview && !item.historical_elo_available && <p>{copy('cycle_late_missing_elo')}</p>}
    <button type="button" disabled={busy} onClick={load}><Refresh aria-hidden="true" />
      {copy(preview ? 'cycle_late_preview_refresh' : 'cycle_late_review')}
    </button>
    {preview && <form onSubmit={submit}>
      <fieldset disabled={busy}>
        <legend>{copy('cycle_late_preview')}</legend>
        {preview.players.map(player => <section key={player.user_id}>
          <h4>{getPlayerDisplayName(player, `${copy('cycle_player')} #${player.user_id}`)} · {formatScore(player.points)}</h4>
          <p>{cycleReasonLabel(player.reason, copy.language)}</p>
          <dl className="cycle-calculation">{[['cycle_historical_elo', 'historical_elo'], ['cycle_base_points', 'base_points'],
            ['cycle_victory_bonus', 'victory_bonus_percent'], ['cycle_direct_multiplier', 'direct_multiplier'],
            ['cycle_exhaustion_multiplier', 'exhaustion_multiplier']].map(([label, field]) => <div key={field}>
              <dt>{copy(label)}</dt><dd>{formatScore(player.calculation?.[field])}</dd>
            </div>)}</dl>
        </section>)}
        {!preview.can_accept && <p>{copy('cycle_late_unavailable')}</p>}
        <label>{copy('cycle_late_action')}<select value={String(counted)} onChange={e => { setCounted(e.target.value === 'true'); setConfirmed(false); }}>
          <option value="true" disabled={!preview.can_accept}>{copy('cycle_late_accept')}</option>
          <option value="false">{copy('cycle_late_reject')}</option>
        </select></label>
        <label>{copy('cycle_late_reason')}<textarea required maxLength={500} value={reason} aria-describedby={error ? errorId : undefined}
          onChange={e => { setReason(e.target.value); setConfirmed(false); }} /></label>
        <label className="cycle-check"><input type="checkbox" required checked={confirmed}
          onChange={e => setConfirmed(e.target.checked)} />{copy('cycle_late_confirm')}</label>
        <button className="cycle-gold" type="submit" disabled={!confirmed || !reason.trim() || (counted && !preview.can_accept)}>
          <Save aria-hidden="true" />{copy('cycle_late_submit')}
        </button>
      </fieldset>
    </form>}
    {error && <ErrorNotice id={errorId} error={error} copy={copy} />}
  </div>;
}

function LateReplays({ battleId, copy, onUpdate }) {
  const [items, setItems] = useState([]);
  const [checked, setChecked] = useState(false);
  const [nextAfter, setNextAfter] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const request = useRef(null);
  const titleId = React.useId();
  useEffect(() => () => request.current?.abort(), []);
  const decided = (matchId, updated) => {
    setItems(previous => previous.filter(item => item.match_id !== matchId));
    onUpdate(updated);
  };
  async function load(restart = false) {
    if (request.current) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError('');
    try {
      const result = await service.getLateReplays(battleId, restart ? 0 : nextAfter ?? 0,
        { signal: controller.signal });
      if (controller.signal.aborted) return;
      setItems(previous => [...new Map((restart ? result.items : [...previous, ...result.items])
        .map(item => [item.match_id, item])).values()]);
      setNextAfter(result.next_after_id); setChecked(true);
    } catch (failure) {
      if (!controller.signal.aborted) setError(errorText(failure));
    } finally {
      if (request.current === controller) {
        request.current = null;
        if (!controller.signal.aborted) setBusy(false);
      }
    }
  }
  return <section className="cycle-late-replays" role="region" aria-labelledby={titleId} aria-busy={busy}>
    <h3 id={titleId}>{copy('cycle_late_title')}</h3>
    {checked && (items.length ? <>
      <p>{copy('cycle_late_warning')}</p>
      <ul>{items.map(item => <li key={item.match_id}>
        <strong>{item.players.map(player => getPlayerDisplayName(player, `${copy('cycle_player')} #${player.user_id}`)).join(', ')}</strong>
        <p>{formatMoscowDateTime(item.started_at, '-', copy.language)}</p>
        {item.players.filter(player => player.reason).map(player => <p key={player.user_id}>
          {getPlayerDisplayName(player)}: {cycleReasonLabel(player.reason, copy.language)}
        </p>)}
        <a href={`https://bfmeladder.com/replay/${encodeURIComponent(item.source_replay_id)}`} target="_blank" rel="noreferrer">{copy('cycle_late_open')}</a>
        <LateReplayDecision key={item.match_id} battleId={battleId} item={item} copy={copy} onDecided={decided} />
      </li>)}</ul>
    </> : nextAfter === null ? <p role="status">{copy('cycle_late_empty')}</p> : null)}
    {checked && nextAfter !== null && <p role="status">{copy('cycle_late_partial')}</p>}
    {error && <ErrorNotice error={error} copy={copy} />}
    <div className="cycle-late-actions">
      <button type="button" disabled={busy} onClick={() => load(checked && nextAfter === null)}><Refresh aria-hidden="true" />
        {!checked ? copy('cycle_late_scan') : nextAfter !== null ? copy('cycle_late_more') : copy('cycle_late_restart')}
      </button>
      {checked && nextAfter !== null && <button type="button" disabled={busy} onClick={() => load(true)}>{copy('cycle_late_restart')}</button>}
    </div>
  </section>;
}

function AdminForm({ battle, contribution, onUpdate, copy }) {
  const [reason, setReason] = useState('');
  const [amount, setAmount] = useState('');
  const [clanId, setClanId] = useState(battle.sides[0]?.clan_id ?? '');
  const [countedDraft, setCountedDraft] = useState(null);
  const counted = reviewCounted(contribution, countedDraft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const command = useRef(null);
  if (!command.current) command.current = createAdjustmentCommand();
  const errorId = React.useId();
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    setBusy(true); setError(''); setSaved(false);
    try {
      let updated;
      if (contribution) {
        updated = await service.review(battle.id, {
          replay_id: contribution.replay_id, user_id: contribution.user_id, counted, reason: reason.trim(),
        });
      } else {
        const payload = { clan_id: Number(clanId), amount: amount.trim(), reason: reason.trim() };
        updated = await service.adjust(battle.id, { ...payload, command_id: command.current.get(payload) });
        command.current.reset();
        setAmount('');
      }
      onUpdate(updated); setCountedDraft(null); setReason(''); setSaved(true);
    } catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  }
  return <form className="cycle-admin" onSubmit={submit} aria-busy={busy}>
    <fieldset disabled={busy}>
      <legend>{contribution ? copy('cycle_review') : copy('cycle_adjust')}</legend>
      {contribution ? <label className="cycle-check"><input type="checkbox" checked={counted} onChange={e => setCountedDraft({ original: Boolean(contribution.counted), value: e.target.checked })} />{copy('cycle_counted')}</label>
        : <><label>{copy('common_clan')}<select required value={clanId} onChange={e => setClanId(e.target.value)}>{battle.sides.map(side => <option key={side.clan_id} value={side.clan_id}>{clanName(side, copy)}</option>)}</select></label>
          <label>{copy('cycle_amount')}<input required type="text" inputMode="decimal" pattern="-?[0-9]{1,16}(\.[0-9]{1,12})?" value={amount} onChange={e => setAmount(e.target.value)} aria-describedby={error ? errorId : undefined} /></label></>}
      <label>{copy('cycle_reason')}<textarea required maxLength={500} value={reason} onChange={e => setReason(e.target.value)} aria-describedby={error ? errorId : undefined} /></label>
      <button type="submit" disabled={!reason.trim() || (!contribution && (!amount.trim() || !clanId))}><Save aria-hidden="true" />{busy ? copy('common_saving') : copy('common_save')}</button>
    </fieldset>
    {error && <ErrorNotice id={errorId} error={error} copy={copy} />}
    {saved && <p role="status">{copy('common_saved')}</p>}
  </form>;
}

function OwnershipForm({ battle, onUpdate, copy }) {
  const [preview, setPreview] = useState(null);
  const [owner, setOwner] = useState('');
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const command = useRef(null);
  if (!command.current) command.current = createAdjustmentCommand();
  const descriptionId = React.useId();
  const errorId = React.useId();
  const ownerId = React.useId();
  async function loadPreview() {
    if (busy) return;
    setBusy(true); setError(''); setSaved(false); setConfirmed(false);
    try {
      const next = await service.previewOwnership(battle.id);
      setPreview(next);
      const proposed = battle.recalculated_winner_clan_id;
      setOwner(next.choices.some(row => row.clan_id === proposed) ? String(proposed ?? '') : '');
      command.current.reset();
    } catch (failure) { setError(errorText(failure)); }
    finally { setBusy(false); }
  }
  async function submit(event) {
    event.preventDefault();
    if (busy || !confirmed || !preview) return;
    setBusy(true); setError(''); setSaved(false);
    const payload = { new_owner_clan_id: owner === '' ? null : Number(owner),
      preview_token: preview.preview_token, reason: reason.trim() };
    try {
      const updated = await service.correctOwnership(battle.id, { ...payload, command_id: command.current.get(payload) });
      onUpdate(updated); setPreview(null); setReason(''); setConfirmed(false); setSaved(true);
      command.current.reset();
    } catch (failure) { setError(errorText(failure)); setConfirmed(false); }
    finally { setBusy(false); }
  }
  const sameOwner = preview && (owner === '' ? null : Number(owner)) === preview.current_owner_clan_id;
  return <div className="cycle-ownership" aria-busy={busy}>
    {!preview ? <>
      <button type="button" className="cycle-gold" disabled={busy} onClick={loadPreview}><Shield aria-hidden="true" />{copy('cycle_ownership_open')}</button>
      {error && <ErrorNotice error={error} copy={copy} />}
    </> : <form onSubmit={submit} aria-label={copy('cycle_ownership_title')}>
      <fieldset disabled={busy}>
        <legend>{copy('cycle_ownership_title')}</legend>
        <p>{copy('cycle_ownership_current')}: {preview.current_owner_name || (preview.current_owner_clan_id == null ? copy('cycle_ownership_neutral') : `${copy('common_clan')} #${preview.current_owner_clan_id}`)}</p>
        <div><label htmlFor={ownerId}>{copy('cycle_ownership_new')}</label><select id={ownerId} value={owner} onChange={event => { setOwner(event.target.value); setConfirmed(false); }}>
          {preview.choices.map(row => <option key={row.clan_id ?? 'neutral'} value={row.clan_id ?? ''}>{row.clan_name || copy('cycle_ownership_neutral')}</option>)}
        </select></div>
        <label>{copy('cycle_reason')}<textarea required maxLength={500} value={reason} onChange={event => setReason(event.target.value)} aria-describedby={error ? errorId : undefined} /></label>
        <p id={descriptionId}>{copy('cycle_ownership_warning')}</p>
        <label className="cycle-check"><input required type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} aria-describedby={descriptionId} />{copy('cycle_ownership_confirm')}</label>
        <button type="submit" className="cycle-gold" disabled={!confirmed || !reason.trim() || sameOwner}><Save aria-hidden="true" />{busy ? copy('common_saving') : copy('cycle_ownership_submit')}</button>
        <button type="button" onClick={loadPreview}><Refresh aria-hidden="true" />{copy('cycle_ownership_refresh')}</button>
      </fieldset>
      {error && <ErrorNotice id={errorId} error={error} copy={copy} />}
    </form>}
    {saved && <p role="status">{copy('common_saved')}</p>}
  </div>;
}

function BattleDetail({ battleId, admin, onUpdate, copy, refreshRef }) {
  const resource = useCycleBattleResource(`battle:${battleId}`, signal => service.getBattle(battleId, { signal }));
  const battle = resource.data;
  const [section, setSection] = useState('matches');
  const [adminVisited, setAdminVisited] = useState(false);
  const [matchRef, setMatchRef] = useState(null);
  const [filter, setFilter] = useState('all');
  const panelId = React.useId();
  useEffect(() => {
    refreshRef.current = resource.refresh;
    return () => { refreshRef.current = null; };
  }, [refreshRef, resource.refresh]);
  const update = next => { resource.accept(next); onUpdate(next); };
  if (!battle && resource.error) return <div><ErrorNotice error={errorText(resource.error)} copy={copy} /><button onClick={resource.refresh}><Refresh aria-hidden="true" />{copy('common_retry')}</button></div>;
  if (!battle) return <p role="status">{copy('common_loading')}</p>;
  const memberName = userId => {
    const member = battle.sides.flatMap(side => side.members || []).find(row => row.user_id === userId);
    return getPlayerDisplayName(member, `${copy('cycle_player')} #${userId}`);
  };
  const winnerName = id => id == null ? copy('cycle_no_winner') : clanName(battle.sides.find(side => side.clan_id === id) || { clan_id: id }, copy);
  const matches = territoryMatchFeed(battle);
  const counts = matchFeedCounts(matches);
  const matchCopy = key => matchMessage(key, copy.language);
  const visibleMatches = matches.filter(match => filter === 'all' || (filter === 'counted' ? match.status !== 'rejected' : match.status === 'rejected'));
  const tabs = [['matches', `${copy('cycle_matches')} · ${matches.length}`], ['roster', copy('cycle_roster')], ['history', copy('cycle_history')], ...(admin ? [['admin', copy('cycle_admin_tools')]] : [])];
  return <div className="cycle-detail">
    {resource.error && <p role="alert" className="cycle-refresh-warning">{readinessMessage('refreshFailed', copy.language)}</p>}
    {battle.ownership_applied_at && <p className="cycle-ownership-current"><Shield aria-hidden="true" />
      <span>{copy('cycle_ownership_current')}: <strong>{battle.current_owner_name || (battle.current_owner_clan_id == null ? copy('cycle_ownership_neutral') : `${copy('common_clan')} #${battle.current_owner_clan_id}`)}</strong></span>
    </p>}
    <Tabs className="cycle-detail-tabs" value={section} onChange={(_event, value) => { setSection(value); if (value === 'admin') setAdminVisited(true); }} variant="fullWidth" aria-label={copy('cycle_details')}>
      {tabs.map(([key, label]) => <Tab key={key} value={key} label={label} id={`${panelId}-${key}`} aria-controls={`${panelId}-panel-${key}`} />)}
    </Tabs>
    <div className="cycle-detail-panel" hidden={section !== 'matches'} role="tabpanel" id={`${panelId}-panel-matches`} aria-labelledby={`${panelId}-matches`}>
        <div className="cm-feed-filters"><div>{[['all', 'all'], ['counted', 'onlyCounted'], ['rejected', 'onlyRejected']].map(([key, label]) => <button key={key} type="button" aria-pressed={filter === key} aria-label={matchCopy(label)} onClick={() => setFilter(key)}>{matchCopy(label)} <span>{counts[key]}</span></button>)}</div><span className="cm-feed-count">{matchCopy('matches')}: {matches.length}</span></div>
        {!matches.length && <div className="cycle-empty-inline"><MilitaryTech aria-hidden="true" /><p>{copy('cycle_no_matches')}</p></div>}
        {!!matches.length && !visibleMatches.length && <p className="cycle-muted">{matchCopy('feedEmpty')}</p>}
        {visibleMatches.map((match, index) => {
          return <details className="cycle-match" key={match.replay_id}>
            <CycleMatchSummary match={match} index={index} language={copy.language} memberName={memberName} clanLabel={id => clanName({ clan_id: id }, copy)} />
            <div className="cycle-match-body"><div className="cycle-match-toolbar"><span>{copy('cycle_match')} {String(index + 1).padStart(2, '0')}</span>
              <button type="button" onClick={() => setMatchRef(String(match.replay_id).replace(/^bfmeladder:/, ''))}><OpenInNew aria-hidden="true" />{copy('cycle_match_info')}</button>
            </div>
            <h3 className="cm-contributions-heading">{matchCopy('playerScores')}</h3>
            {match.contributions.map(row => <section className="cycle-contribution" key={`${row.replay_id}-${row.user_id}`}>
              <div className="cycle-contribution-heading"><div><h3>{memberName(row.user_id)}</h3><span>{clanName(battle.sides.find(side => side.clan_id === row.clan_id) || row, copy)}</span></div>
                <div className="cycle-contribution-score"><strong className={String(row.points).startsWith('-') ? 'cycle-negative' : 'cycle-positive'}>{formatScore(row.points)}</strong><small>{row.counted ? copy('cycle_counted') : copy('cycle_excluded')}</small></div>
              </div>
              {(!row.counted || row.reason !== 'counted') && <p className="cycle-contribution-reason">{cycleReasonLabel(row.reason, copy.language)}</p>}
              {row.review_reason && <p>{copy('cycle_review_reason')}: {cycleReasonLabel(row.review_reason, copy.language)}</p>}
              {row.calculation && <details className="cycle-math"><summary>{copy('cycle_calculation')}<ExpandMore aria-hidden="true" /></summary><dl className="cycle-calculation">
                <div><dt>{copy('cycle_historical_elo')}</dt><dd>{formatScore(row.calculation.historical_elo)}</dd></div>
                <div><dt>{copy('cycle_base_points')}</dt><dd>{formatScore(row.calculation.base_points)}</dd></div>
                <div><dt>{copy('cycle_victory_bonus')}</dt><dd>{formatScore(row.calculation.victory_bonus_percent)}%</dd></div>
                <div><dt>{copy('cycle_direct_multiplier')}</dt><dd>x{formatScore(row.calculation.direct_multiplier)}</dd></div>
                <div><dt>{copy('cycle_exhaustion_multiplier')}</dt><dd>x{formatScore(row.calculation.exhaustion_multiplier)}</dd></div>
              </dl></details>}
              {admin && <details className="cycle-match-review"><summary><EditOutlined aria-hidden="true" />{copy('cycle_change_decision')}</summary><AdminForm battle={battle} contribution={row} onUpdate={update} copy={copy} /></details>}
            </section>)}
            </div>
          </details>;
        })}
    </div>
    <div className="cycle-detail-panel" hidden={section !== 'roster'} role="tabpanel" id={`${panelId}-panel-roster`} aria-labelledby={`${panelId}-roster`}>
      {section === 'roster' && <ul className="cycle-lineups">{battle.sides.map(side => <li key={side.clan_id}>
        <div className="cycle-lineup-heading"><ClanAvatar side={side} /><div><h3>{clanName(side, copy)}</h3><small>{side.role === 'defense' ? copy('cycle_defense') : copy('cycle_attack')}</small></div><strong>{formatScore(side.score)}</strong></div>
        {side.members?.length ? <ul className="cycle-player-list">{side.members.map(member => <li key={member.user_id}><span className="cycle-player-mark" aria-hidden="true">{getPlayerDisplayName(member, '?').slice(0, 1)}</span>{getPlayerDisplayName(member, `${copy('cycle_player')} #${member.user_id}`)}</li>)}</ul> : <p>{copy('cycle_no_members')}</p>}
      </li>)}</ul>}
    </div>
    <div className="cycle-detail-panel" hidden={section !== 'history'} role="tabpanel" id={`${panelId}-panel-history`} aria-labelledby={`${panelId}-history`}>
        <dl className="cycle-results"><div><dt>{copy('cycle_confirmed_winner')}</dt><dd>{winnerName(battle.winner_clan_id)}</dd></div><div><dt>{copy('cycle_recalculated_winner')}</dt><dd>{winnerName(battle.recalculated_winner_clan_id)}</dd></div></dl>
        {!!battle.ownership_corrections?.length && <section className="cycle-ownership-history"><h3>{copy('cycle_ownership_history')}</h3><ul className="cycle-event-list">{battle.ownership_corrections.map(row => <li key={row.id}><History aria-hidden="true" /><div><strong>{row.new_owner_clan_id == null ? copy('cycle_ownership_neutral') : winnerName(row.new_owner_clan_id)}</strong><p>{row.reason}</p><time>{formatMoscowDateTime(row.applied_at, '-', copy.language)}</time></div></li>)}</ul></section>}
        <h3>{copy('cycle_adjustments')}</h3>
        {battle.adjustments?.length ? <ul className="cycle-event-list">{battle.adjustments.map(row => <li key={row.id}><SettingsOutlined aria-hidden="true" /><div><strong>{clanName(battle.sides.find(side => side.clan_id === row.clan_id) || row, copy)} · {formatScore(row.points)}</strong><p>{cycleReasonLabel(row.reason, copy.language)}</p></div></li>)}</ul> : <p className="cycle-muted">{copy('cycle_no_adjustments')}</p>}
    </div>
    {admin && adminVisited && <div className="cycle-detail-panel" hidden={section !== 'admin'} role="tabpanel" id={`${panelId}-panel-admin`} aria-labelledby={`${panelId}-admin`}><div className="cycle-admin-tools">
        <section><h3>{copy('cycle_adjust')}</h3><AdminForm battle={battle} onUpdate={update} copy={copy} /></section>
        {battle.ownership_applied_at && <section><OwnershipForm battle={battle} onUpdate={update} copy={copy} /></section>}
        {battle.completed_at && <LateReplays key={battle.id} battleId={battle.id} copy={copy} onUpdate={update} />}
      </div></div>}
    <MatchDetailsDialog open={matchRef != null} matchRef={matchRef} onClose={() => setMatchRef(null)} />
  </div>;
}

function BattleSides({ battle, copy, expanded = false }) {
  return <ul className={`cycle-sides${expanded ? ' cycle-sides--expanded' : ''}`}>{battle.sides.map(side => {
    const winner = battle.completed_at && battle.winner_clan_id != null && String(battle.winner_clan_id) === String(side.clan_id);
    return <li key={side.clan_id} className={winner ? 'cycle-side-winner' : ''}>
      <ClanAvatar side={side} /><span className="cycle-side-name"><strong>{clanName(side, copy)}</strong><small>{side.role === 'defense' ? copy('cycle_defense') : copy('cycle_attack')}{winner && <> · <EmojiEvents aria-hidden="true" />{copy('cycle_winner')}</>}</small></span>
      <span className="cycle-side-score"><b className={String(side.score).startsWith('-') ? 'cycle-negative' : ''}>{formatScore(side.score)}</b>{expanded && <small>{matchMessage('score', copy.language)}</small>}</span>
    </li>;
  })}</ul>;
}

function BattleCard({ battle, copy, onOpen, phase }) {
  const matchCopy = key => matchMessage(key, copy.language);
  return <article className="cycle-battle">
    <div className="cycle-territory-heading"><span className="cycle-territory-symbol"><Public aria-hidden="true" /></span><div><small>{copy('cycle_territory')}</small><h3>{battle.territory_name || `#${battle.territory_id}`}</h3></div>
      <span className={`cycle-badge ${battle.completed_at ? '' : 'cycle-badge--active'}`}>{matchCopy(battle.completed_at ? 'settled' : phase === 'battle' ? 'active' : 'pending')}</span>
    </div>
    <p className="cycle-land-context"><span>{matchCopy(battleKind(battle))}</span><span>{matchCopy('owner')}: <strong>{battle.owner_clan_id != null ? battle.owner_clan_name || clanName({ clan_id: battle.owner_clan_id }, copy) : battle.sides.find(side => side.role === 'defense')?.clan_name || matchCopy('neutral')}</strong></span></p>
    <BattleSides battle={battle} copy={copy} />
    <div className="cycle-land-meta"><span><Groups aria-hidden="true" />{matchCopy('involved')}: {battle.sides.reduce((total, side) => total + (side.members?.length || 0), 0)}</span><span>{matchCopy('matches')}: {new Set((battle.contributions || []).map(row => row.replay_id)).size}</span></div>
    <button className="cycle-battle-open" onClick={() => onOpen(battle)}>{copy('cycle_details')}<ArrowForward aria-hidden="true" /></button>
  </article>;
}

function OwnReadiness({ cycle, language, refreshRef }) {
  const resource = useCycleBattleResource(`readiness:${cycle.id}:${cycle.season_id}`, async signal => {
    let own;
    try { own = await service.getOwnClan({ signal }); }
    catch (error) { if (error.response?.status === 404) return null; throw error; }
    if (!own?.id || signal.aborted) return null;
    const [planning, preparation, economy] = await readCycleResources([
      service.getPlanning(cycle.id, own.id, { signal }),
      service.getPreparation(cycle.id, own.id, { signal }),
      cycleEconomyService.context(cycle.season_id, own.id, { signal }),
    ]);
    return { clan_name: own.name, summary: cycleReadiness(planning, preparation, economy) };
  });
  useEffect(() => {
    refreshRef.current = resource.refresh;
    return () => { refreshRef.current = null; };
  }, [refreshRef, resource.refresh]);
  const text = key => readinessMessage(key, language);
  if (!resource.data?.summary) return resource.error ? <p className="cycle-refresh-warning" role="status">{text('unavailable')}</p> : null;
  const summary = resource.data.summary;
  return <section className="cycle-readiness" aria-label={text('screen')}>
    <h2>{text('screen')} <small>{resource.data.clan_name}</small></h2>
    <dl>{['free', 'uncovered', 'reserve', 'scout', 'relics'].map(key => <div key={key}><dt>{text(key)}</dt><dd>{summary[key] == null ? '—' : key === 'scout' ? text(summary[key]) : summary[key]}</dd></div>)}</dl>
    {resource.error && <p role="status" className="cycle-refresh-warning">{text('refreshFailed')}</p>}
  </section>;
}

function CycleBattlesContent({ cycleId }) {
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const { language } = useLocalizationContext();
  const copy = Object.assign(key => cycleMessage(key, language), { language });
  const resource = useCycleBattleResource(`cycle:${cycleId}`, async signal => {
    const [cycle, battles] = await readCycleResources([
      service.getCycle(cycleId, { signal }), service.getBattles(cycleId, { signal }),
    ]);
    return { cycle, battles };
  });
  const cycle = resource.data?.cycle;
  const battles = resource.data?.battles || [];
  const detailRefresh = useRef(null);
  const readinessRefresh = useRef(null);
  const [view, setView] = useState('clans');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const loading = !resource.data && !resource.error;
  const refresh = () => { resource.refresh(); detailRefresh.current?.(); readinessRefresh.current?.(); };
  const clans = groupClanBattles(battles);
  const clan = clans.find(row => String(row.clan_id) === searchParams.get('clan'));
  const territoryView = selectTerritoryBattle(battles, searchParams.get('territory'), user);
  const territoryClan = clans.find(row => row.clan_id === territoryView?.clan_id);
  const showAllClans = () => {
    const next = new URLSearchParams(searchParams);
    next.delete('territory'); next.delete('clan');
    setSearchParams(next); setQuery(''); setStatus('all');
  };
  const selectClan = id => {
    const next = new URLSearchParams(searchParams);
    next.set('clan', String(id)); next.delete('territory');
    setSearchParams(next); setQuery(''); setStatus('all');
  };
  const openBattle = battle => {
    const next = new URLSearchParams(searchParams);
    next.set('territory', String(battle.territory_id));
    setSearchParams(next);
  };
  const update = next => resource.accept(previous => ({ ...previous, battles: previous.battles.map(row => row.id === next.id ? next : row) }));
  const deadline = nextCycleDeadline(cycle);
  const scheduleLabel = key => copy(key).replace('{number}', String((cycle?.number ?? Number(cycleId)) + 1));
  const currentClan = clan || territoryClan;
  const visibleBattles = filterBattleList(clan?.battles || battles, status, query);
  const visibleClans = clans.filter(row => row.battles.some(battle => (
    (status === 'all' || Boolean(battle.completed_at) === (status === 'completed'))
    && (!query.trim() || `${row.clan_name} ${battle.territory_name}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))
  )));
  const heading = territoryView ? territoryView.battle.territory_name || `${copy('cycle_territory')} #${territoryView.battle.territory_id}` : clan ? clanName(clan, copy) : copy('cycle_entry_title');
  const showTerritories = clan || view === 'territories';
  return <PageShell className="cycle-battles cycle-battle-screen" aria-busy={loading}>
    <header className="cycle-heading"><div className="cycle-heading-identity">{clan && !territoryView && <ClanAvatar side={clan} />}
      <div><span className="cycle-eyebrow">{copy('cycle_campaign')}<span aria-hidden="true"> / </span>{copy('cycle_number')} {cycle?.number ?? cycleId}</span><h1>{heading}</h1></div>
    </div><div className="cycle-heading-actions"><Link className="cycle-map-link" to="/map"><MapOutlined aria-hidden="true" />{copy('cycle_map')}</Link><button className="cycle-icon-button" onClick={refresh} disabled={resource.busy} title={copy('common_refresh')} aria-label={copy('common_refresh')}><Refresh aria-hidden="true" /></button></div></header>
    {loading ? <div className="cycle-loading" role="status"><span className="cycle-loading-mark"><MilitaryTech aria-hidden="true" /></span>{copy('common_loading')}</div> : !resource.data ? <div className="cycle-state"><ErrorNotice error={errorText(resource.error)} copy={copy} /><button onClick={refresh}>{copy('common_retry')}</button></div> : <>
      {resource.error && <p role="alert" className="cycle-refresh-warning">{readinessMessage('refreshFailed', language)}</p>}
      <section className="cycle-status-strip" aria-label={copy('cycle_phase')}><span className={`cycle-phase-badge cycle-phase-badge--${cycle.phase}`}><span aria-hidden="true" />{cyclePhaseLabel(cycle.phase, language)}</span>
        {deadline && <div className="cycle-deadline"><Schedule aria-hidden="true" /><span>{scheduleLabel(deadline.key)}<strong>{formatMoscowDateTime(deadline.value, '-', language)}</strong></span></div>}
        <button className="cycle-schedule-toggle" aria-expanded={scheduleOpen} aria-controls="cycle-schedule" onClick={() => setScheduleOpen(value => !value)}>{copy('cycle_schedule')}<ExpandMore aria-hidden="true" /></button>
      </section>
      {cycle.season_id && user && <OwnReadiness cycle={cycle} language={language} refreshRef={readinessRefresh} />}
      {scheduleOpen && <dl className="cycle-times" id="cycle-schedule">{cycleSchedule(cycle).map(step => <div
        key={step.key} className={step.next ? 'cycle-schedule-next' : undefined} aria-current={step.current ? 'step' : undefined}>
        <dt>{scheduleLabel(step.key)}{step.current && <small>{copy('cycle_current_stage')}</small>}</dt>
        <dd>{step.value ? <time dateTime={step.value}>{formatMoscowDateTime(step.value, '-', language)}</time>
          : copy(step.next ? 'cycle_next_cycle_pending' : 'cycle_settlement_pending')}</dd>
      </div>)}</dl>}
      {(clan || territoryView) && <nav className="cycle-breadcrumbs" aria-label={copy('cycle_clan_battles')}><button onClick={showAllClans}><ArrowBack aria-hidden="true" />{copy('cycle_all_clans')}</button>{territoryView && currentClan && <><span aria-hidden="true">/</span><button onClick={() => selectClan(currentClan.clan_id)}>{clanName(currentClan, copy)}</button></>}{territoryView && <><span aria-hidden="true">/</span><span>{heading}</span></>}</nav>}
      {territoryView ? <section className="cycle-battle cycle-battle--opened" aria-label={copy('cycle_details')}>
        <div className="cycle-land-banner"><span><Public aria-hidden="true" /><span>{matchMessage(battleKind(territoryView.battle), language)}<small>{matchMessage('owner', language)}: {territoryView.battle.owner_clan_name || territoryView.battle.sides.find(side => side.role === 'defense')?.clan_name || (territoryView.battle.owner_clan_id != null ? clanName({ clan_id: territoryView.battle.owner_clan_id }, copy) : matchMessage('neutral', language))}</small></span></span><span className="cycle-badge cycle-badge--active">{matchMessage(territoryView.battle.completed_at ? 'settled' : cycle.phase === 'battle' ? 'active' : 'pending', language)}</span></div>
        <BattleSides battle={territoryView.battle} copy={copy} expanded />
        <BattleDetail key={territoryView.battle.id} battleId={territoryView.battle.id} admin={user?.role?.name === 'admin'} onUpdate={update} copy={copy} refreshRef={detailRefresh} />
      </section> : !clans.length ? <div className="cycle-empty"><span className="cycle-empty-symbol"><MilitaryTech aria-hidden="true" /></span><h2>{copy('cycle_empty')}</h2><Link className="cycle-gold-link" to="/map"><MapOutlined aria-hidden="true" />{copy('cycle_map')}</Link></div> : <section className="cycle-overview">
        <dl className="cycle-overview-stats">{clan ? (() => {
          const counts = summarizeClanBattles(clan.battles, clan.clan_id);
          return [[copy('cycle_territories_count'), counts.total], [copy('cycle_attack_count'), counts.attacks], [copy('cycle_defense_count'), counts.defenses], [copy('cycle_wins_count'), counts.won]];
        })().map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>) : [[copy('cycle_territories_count'), battles.length], [copy('cycle_clans_count'), clans.length], [copy('cycle_finished_count'), battles.filter(battle => battle.completed_at).length]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
        <div className="cycle-overview-heading"><div><span className="cycle-eyebrow">{clan ? copy('cycle_clan_battles') : copy('cycle_number') + ' ' + cycle.number}</span><h2>{copy(showTerritories ? 'cycle_territories_heading' : 'cycle_clans_heading')}</h2></div>
          {!clan && <div className="cycle-view-switch" role="group" aria-label={copy('cycle_view')}><button aria-pressed={view === 'clans'} onClick={() => setView('clans')}><Groups aria-hidden="true" />{copy('cycle_view_clans')}</button><button aria-pressed={view === 'territories'} onClick={() => setView('territories')}><GridView aria-hidden="true" />{copy('cycle_view_territories')}</button></div>}
        </div>
        <div className="cycle-filters"><div className="cycle-filter-tabs" role="group" aria-label={copy('cycle_phase')}>{['all', 'active', 'completed'].map(value => <button key={value} aria-pressed={status === value} onClick={() => setStatus(value)}>{copy(`cycle_filter_${value}`)}</button>)}</div>
          <div className="cycle-search"><Search aria-hidden="true" /><input type="search" aria-label={copy('cycle_search')} placeholder={copy('cycle_search')} value={query} onChange={event => setQuery(event.target.value)} />{query && <button aria-label={copy('cycle_clear_search')} title={copy('cycle_clear_search')} onClick={() => setQuery('')}><Close aria-hidden="true" /></button>}</div>
        </div>
        {showTerritories ? <div className="cycle-battle-grid">{visibleBattles.map(battle => <BattleCard key={battle.id} battle={battle} copy={copy} phase={cycle.phase} onOpen={openBattle} />)}</div> : <ul className="cycle-clans">{visibleClans.map(row => {
          const counts = summarizeClanBattles(row.battles, row.clan_id);
          return <li key={row.clan_id}><button className="cycle-clan-card" onClick={() => selectClan(row.clan_id)}>
            <div className="cycle-clan-card-heading"><span className="cycle-clan-emblem"><ClanAvatar side={row} /></span><span><small>{copy('common_clan')}</small><strong>{clanName(row, copy)}</strong></span><ArrowForward className="cycle-card-arrow" aria-hidden="true" /></div>
            <div className="cycle-clan-lands">{row.battles.map(battle => battle.territory_name || `#${battle.territory_id}`).join(' · ')}</div>
            <div className="cycle-clan-card-meta"><span><Public aria-hidden="true" />{copy('cycle_territories_count')}: <b>{counts.total}</b></span><span><Shield aria-hidden="true" />{copy('cycle_defense_count')}: <b>{counts.defenses}</b></span><span><MilitaryTech aria-hidden="true" />{copy('cycle_attack_count')}: <b>{counts.attacks}</b></span><span><EmojiEvents aria-hidden="true" />{copy('cycle_wins_count')}: <b>{counts.won}</b></span></div>
          </button></li>;
        })}</ul>}
        {!(showTerritories ? visibleBattles.length : visibleClans.length) && <div className="cycle-empty"><Search aria-hidden="true" /><h3>{copy('cycle_no_results')}</h3><button onClick={() => { setQuery(''); setStatus('all'); }}>{copy('cycle_reset_filters')}</button></div>}
      </section>}
    </>}
  </PageShell>;
}

export default function CycleBattlesPage() {
  const { cycleId } = useParams();
  return <CycleBattlesContent key={cycleId} cycleId={cycleId} />;
}
