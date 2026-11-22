import React, { useEffect, useRef, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { Refresh, ArrowBack, Shield, Save, Edit, Preview, Check, ExpandMore } from '@mui/icons-material';
import { PageShell } from '../components/ui';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { cycleCampaignService } from '../services/cycleCampaignService';
import { cycleInterceptionReviewService as reviewService } from '../services/cycleInterceptionReviewService';
import { cycleMessage, cycleReasonLabel, formatScore, groupContributions, reviewCounted } from '../utils/cycleBattleView';
import {
  interceptionMessage, interceptionReviewMessage as reviewCopy, canRestoreInterceptionContribution,
  canChangeInterceptionOutcome, canConfirmInterceptionOutcome, createInterceptionCommandStore,
} from '../utils/cycleInterceptionView';
import { getPlayerDisplayName } from '../utils/playerIdentity';
import { formatMoscowDateTime } from '../utils/dateTime';
import './CycleBattlesPage.css';
import './CycleBattleScreen.css';
import './CycleInterceptionPage.css';

function useReviewCommand({ cycleId, dispatchId, actorId, onReload }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const inFlight = useRef(false);
  async function run(action, payload) {
    if (inFlight.current) return null;
    inFlight.current = true;
    setBusy(true); setError(''); setSaved(false);
    let commands;
    try {
      commands = createInterceptionCommandStore(window.sessionStorage, `${actorId}:${cycleId}:${dispatchId}`);
      const command = commands.prepare(action, payload);
      const result = await reviewService[action](cycleId, dispatchId, command);
      commands.settle(action, payload);
      setSaved(true);
      if (action !== 'preview') onReload();
      return result;
    } catch (failure) {
      if (failure.response?.status === 409) {
        try { commands?.settle(action, payload); } catch { /* Повтор останется в хранилище до успешного ответа. */ }
      }
      const detail = failure.response?.data?.detail;
      setError(typeof detail === 'string' && /[А-Яа-яЁё]/.test(detail) ? detail : reviewCopy('error'));
      return null;
    } finally { inFlight.current = false; setBusy(false); }
  }
  return { run, busy, error, saved };
}

export function InterceptionReviewForm({ data, row, ...context }) {
  const [reason, setReason] = useState('');
  const [amount, setAmount] = useState('');
  const [sideId, setSideId] = useState(String(data.sides[0]?.clan_id || ''));
  const [confirmedVersion, setConfirmedVersion] = useState(null);
  const [countedDraft, setCountedDraft] = useState(null);
  const { run, busy, error, saved } = useReviewCommand(context);
  const errorId = React.useId();
  const mayRestore = canRestoreInterceptionContribution(row);
  const reviewVersion = JSON.stringify([data.revision, row?.replay_id, row?.user_id,
    Boolean(row?.counted), row?.reason, row?.calculation?.historical_elo]);
  const confirmed = confirmedVersion === reviewVersion;
  const counted = reviewCounted(row, countedDraft?.version === reviewVersion ? countedDraft : null);
  async function submit(event) {
    event.preventDefault();
    if (!confirmed || !reason.trim() || busy || (row && counted === row.counted)) return;
    const payload = { expected_revision: data.revision, reason: reason.trim(), ...(row
      ? { replay_id: row.replay_id, user_id: row.user_id, counted }
      : { side_clan_id: Number(sideId), amount: amount.trim() }) };
    const result = await run(row ? 'review' : 'adjust', payload);
    setConfirmedVersion(null);
    if (result) { setReason(''); setAmount(''); setCountedDraft(null); }
  }
  const missingElo = row && row.calculation?.historical_elo == null;
  return <form className="ci-review-form" onSubmit={submit} aria-busy={busy}>
    <fieldset disabled={busy || data.revision == null}>
      <legend>{reviewCopy(row ? 'review' : 'adjust')}</legend>
      {row ? <>
        {missingElo && <p>{reviewCopy('missing_elo')}</p>}
        <label className="ci-check"><input type="checkbox" checked={counted} disabled={!row.counted && !mayRestore}
          onChange={e => { setCountedDraft({ original: Boolean(row.counted), value: e.target.checked, version: reviewVersion }); setConfirmedVersion(null); }} />{reviewCopy('counted')}</label>
      </> : <div className="ci-adjust-inputs">
        <label>{reviewCopy('side')}<select required value={sideId} onChange={e => { setSideId(e.target.value); setConfirmedVersion(null); }}>
          {data.sides.map(side => <option key={side.clan_id} value={side.clan_id}>{side.clan_name || `#${side.clan_id}`}</option>)}
        </select></label>
        <label>{reviewCopy('amount')}<input required type="text" inputMode="decimal" pattern="-?[0-9]{1,16}(\.[0-9]{1,12})?"
          value={amount} onChange={e => { setAmount(e.target.value); setConfirmedVersion(null); }} aria-describedby={error ? errorId : undefined} /></label>
      </div>}
      <label>{reviewCopy('reason')}<textarea required maxLength={500} value={reason}
        onChange={e => { setReason(e.target.value); setConfirmedVersion(null); }} aria-describedby={error ? errorId : undefined} /></label>
      <label className="ci-check"><input required type="checkbox" checked={confirmed} onChange={e => setConfirmedVersion(e.target.checked ? reviewVersion : null)} />{reviewCopy('confirm_edit')}</label>
      <button type="submit" disabled={!confirmed || !reason.trim() || (row ? counted === row.counted : !amount.trim())}>
        <Save aria-hidden="true" />{reviewCopy(busy ? 'saving' : 'save')}</button>
    </fieldset>
    {error && <p id={errorId} role="alert" className="cycle-error">{error}</p>}
    {saved && <p role="status">{reviewCopy('saved')}</p>}
  </form>;
}

export function InterceptionOutcomeReview({ data, ...context }) {
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const { run, busy, error } = useReviewCommand(context);
  const errorId = React.useId();
  const elapsed = data.receivedAt == null ? 0 : Math.max(0, Date.now() - data.receivedAt);
  const open = canChangeInterceptionOutcome(data, elapsed);
  const valid = canConfirmInterceptionOutcome(data, preview, elapsed);
  async function loadPreview(event) {
    event.preventDefault();
    if (!reason.trim() || busy) return;
    const result = await run('preview', { expected_revision: data.revision, reason: reason.trim() });
    setPreview(result); setConfirmed(false);
  }
  async function confirm() {
    if (!confirmed || !valid || busy) return;
    const result = await run('confirm', { expected_revision: preview.revision,
      preview_command_id: preview.preview_command_id, reason: reason.trim() });
    setConfirmed(false);
    if (result) { setPreview(null); setReason(''); }
  }
  const arrived = Date.parse(data.server_time) + elapsed >= Date.parse(data.arrives_at);
  return <section className="ci-outcome-review" aria-busy={busy}>
    <h2>{reviewCopy('outcome')}</h2>
    {!open ? <p>{reviewCopy(arrived ? 'arrival_locked' : 'pending_window')}</p> : <>
      <form onSubmit={loadPreview}>
        <fieldset disabled={busy}>
          <label>{reviewCopy('reason')}<textarea required maxLength={500} value={reason}
            onChange={e => { setReason(e.target.value); setPreview(null); setConfirmed(false); }}
            aria-describedby={error ? errorId : undefined} /></label>
          <button type="submit" disabled={!reason.trim()}><Preview aria-hidden="true" />{reviewCopy('preview')}</button>
        </fieldset>
      </form>
      {preview && <div className="ci-outcome-preview">
        <h3>{reviewCopy('proposed')}</h3>
        <p>{interceptionMessage(preview.proposed_result.outcome, 'ru')}</p>
        <dl className="ci-preview-scores">{data.sides.map(side => <div key={side.clan_id}><dt>{side.clan_name || `#${side.clan_id}`}</dt>
          <dd>{formatScore(side.role === 'help' ? preview.proposed_result.help_score : preview.proposed_result.ambush_scores[String(side.clan_id)])}</dd></div>)}</dl>
        {!valid && <p role="alert" className="cycle-error">{reviewCopy('stale')}</p>}
        <label className="ci-check"><input type="checkbox" checked={confirmed} disabled={busy || !valid}
          onChange={e => setConfirmed(e.target.checked)} />{reviewCopy('confirm_outcome')}</label>
        <button type="button" disabled={busy || !valid || !confirmed} onClick={confirm}><Check aria-hidden="true" />{reviewCopy(busy ? 'saving' : 'confirm')}</button>
      </div>}
    </>}
    {error && <p id={errorId} role="alert" className="cycle-error">{error}</p>}
  </section>;
}

function InterceptionAudit({ data, time }) {
  return <details className="ci-audit"><summary>{reviewCopy('audit')}</summary>
    {!data.audit?.length && <p>{reviewCopy('no_audit')}</p>}
    <ol>{data.audit?.map(entry => <li key={entry.command_id}>
      <strong>{reviewCopy(`${entry.action}_action`)}</strong><time>{time(entry.created_at)}</time>
      <p>{reviewCopy('actor')} #{entry.actor_user_id} · {reviewCopy('revision')} {entry.expected_revision}</p>
      <p>{entry.reason}</p><code>{entry.command_id}</code>
    </li>)}</ol>
  </details>;
}

function InterceptionContent({ cycleId, dispatchId, admin, actorId }) {
  const { language } = useLocalizationContext();
  const copy = key => interceptionMessage(key, language);
  const common = key => cycleMessage(key, language);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    const read = admin ? reviewService.read : cycleCampaignService.getInterception;
    read(cycleId, dispatchId, { signal: controller.signal }).then(next => {
      if (!controller.signal.aborted) { setData({ ...next, receivedAt: Date.now() }); setFailed(false); }
    }).catch(() => {
      if (!controller.signal.aborted) setFailed(true);
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [cycleId, dispatchId, attempt, admin]);
  useEffect(() => {
    const timer = window.setInterval(() => setAttempt(value => value + 1), 15000);
    return () => window.clearInterval(timer);
  }, []);
  const clanName = side => side.clan_name || `${common('common_clan')} #${side.clan_id}`;
  const playerName = id => getPlayerDisplayName(data?.sides.flatMap(s => s.members).find(m => m.user_id === id), `${common('cycle_player')} #${id}`);
  const time = value => formatMoscowDateTime(value, '-', language);
  const reviewContext = { cycleId, dispatchId, actorId, onReload: () => setAttempt(value => value + 1) };
  return <PageShell className="cycle-battles cycle-battle-screen cycle-interception" aria-busy={loading}>
    <header className="cycle-heading"><div className="cycle-heading-identity"><div>
      <span className="cycle-eyebrow">{common('cycle_campaign')}<span aria-hidden="true"> / </span>{common('cycle_number')} {cycleId}</span>
      <h1>{copy('screen')}</h1>
    </div></div><button className="cycle-icon-button" disabled={loading} title={common('common_refresh')} aria-label={common('common_refresh')} onClick={() => setAttempt(value => value + 1)}><Refresh aria-hidden="true" /></button></header>
    <nav className="ci-navigation cycle-breadcrumbs"><Link to={`/campaign/cycles/${cycleId}/reinforcements`}><ArrowBack aria-hidden="true" />{common('cycle_reinforcements')}</Link>
      {data && <Link to={`/campaign/cycles/${cycleId}?territory=${data.territory_id}`}>{copy('territory')}</Link>}</nav>
    {failed && <p role="alert" className="cycle-error">{common('cycle_request_failed')}</p>}
    {!data && loading && <p role="status">{common('common_loading')}</p>}
    {data && <>
      <div className="ci-territory-heading"><h2>{data.territory_name || `#${data.territory_id}`}</h2>
        <p className="ci-phase cycle-phase-badge"><span aria-hidden="true" />{copy(data.phase)}</p></div>
      <p className={`ci-result ci-result-${data.outcome}`}><strong>{reviewCopy('applied')}: </strong>{copy(data.outcome)}</p>
      {data.original_applied_result && <p className="ci-original"><strong>{reviewCopy('original')}: </strong>{copy(data.original_applied_result.outcome)}</p>}
      <dl className="cycle-times">{[['start', data.starts_at], ['end', data.ends_at], ['deadline', data.replay_deadline], ['arrival', data.arrives_at]].map(([key, value]) => <div key={key}><dt>{copy(key)}</dt><dd>{time(value)}</dd></div>)}</dl>
      <h2 className="ci-section-title">{reviewCopy('history')}</h2>
      <ul className="ci-sides">{data.sides.map(side => <li key={side.clan_id}>
        <div className="ci-side-heading"><Shield aria-hidden="true" /><div><h3>{clanName(side)}</h3><small>{copy(side.role)}</small></div>
          <b className={String(side.score).startsWith('-') ? 'ci-side-score cycle-negative' : 'ci-side-score'}>{formatScore(side.score)}</b></div>
        <ul className="ci-members">{side.members.map(m => <li key={m.user_id}><strong>{getPlayerDisplayName(m, `${common('cycle_player')} #${m.user_id}`)}</strong>
          <dl>{[['positive', 'positive_points'], ['negative', 'negative_points'], ['total', 'total_points']].map(([label, field]) => <div key={field}><dt>{copy(label)}</dt><dd>{formatScore(m[field])}</dd></div>)}</dl>
        </li>)}</ul>
      </li>)}</ul>
      <h2 className="ci-section-title">{common('cycle_matches')}</h2>
      {!data.contributions.length && <p className="ci-no-matches">{common('cycle_no_matches')}</p>}
      {groupContributions(data.contributions).map(match => <details className="cycle-match" key={match.replay_id}>
        <summary><span className="ci-match-title">{common('cycle_replay')} {match.replay_id}</span>
          <span className="cycle-badge">{match.contributions.length} {common('cycle_contributions')}</span><ExpandMore className="cycle-disclosure-icon" aria-hidden="true" /></summary>
        <div className="cycle-match-body">{match.contributions.map(row => <section className="cycle-contribution" key={row.user_id}>
          <div className="cycle-contribution-heading"><h3>{playerName(row.user_id)}</h3><div className="cycle-contribution-score">
            <strong className={String(row.points).startsWith('-') ? 'cycle-negative' : 'cycle-positive'}>{formatScore(row.points)}</strong>
            <small>{common(row.counted ? 'cycle_counted' : 'cycle_excluded')}</small></div></div>
          <p className="cycle-contribution-reason">{cycleReasonLabel(row.reason, language)}</p>
          {row.reviewed && <p>{reviewCopy('reviewed')}</p>}
          <dl className="cycle-calculation">{[['cycle_historical_elo', 'historical_elo'], ['cycle_base_points', 'base_points'],
            ['cycle_victory_bonus', 'victory_bonus_percent'], ['cycle_direct_multiplier', 'direct_multiplier']].map(([label, field]) => <div key={field}><dt>{common(label)}</dt><dd>{row.calculation?.[field] != null && field === 'direct_multiplier' ? 'x' : ''}{formatScore(row.calculation?.[field])}{row.calculation?.[field] != null && field === 'victory_bonus_percent' ? '%' : ''}</dd></div>)}</dl>
          {admin && <details className="ci-contribution-review"><summary><Edit aria-hidden="true" />{reviewCopy('review')}</summary>
            <InterceptionReviewForm data={data} row={row} {...reviewContext} />
          </details>}
        </section>)}</div>
      </details>)}
      {!!data.adjustments?.length && <section className="ci-adjustments"><h2>{reviewCopy('manual')}</h2>
        <ul>{data.adjustments.map(item => <li key={item.id}><strong>{clanName(data.sides.find(side => side.clan_id === item.clan_id) || { clan_id: item.clan_id })}</strong>
          <b>{formatScore(item.points)}</b><p>{item.reason}</p><time>{time(item.created_at)}</time></li>)}</ul>
      </section>}
      {admin && <section className="ci-admin">
        <InterceptionReviewForm data={data} {...reviewContext} />
        <InterceptionOutcomeReview data={data} {...reviewContext} />
        <InterceptionAudit data={data} time={time} />
      </section>}
    </>}
  </PageShell>;
}

export default function CycleInterceptionPage() {
  const { cycleId } = useParams();
  const [params] = useSearchParams();
  const { user } = useAuth();
  const dispatchId = params.get('dispatch') || '';
  return <InterceptionContent key={`${user?.id}:${cycleId}:${dispatchId}`} cycleId={cycleId} dispatchId={dispatchId}
    actorId={user?.id} admin={user?.role?.name === 'admin'} />;
}
