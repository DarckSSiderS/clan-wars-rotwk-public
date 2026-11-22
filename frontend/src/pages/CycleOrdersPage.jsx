import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowBack, Refresh, Save, Shield, Groups, PersonRemove, ArrowForward } from '@mui/icons-material';
import { Dialog, DialogActions, DialogContent, DialogTitle } from '@mui/material';
import { PageShell } from '../components/ui';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { clanService } from '../services/clanService';
import { cycleCampaignService as service } from '../services/cycleCampaignService';
import { cycleOperationsService } from '../services/cycleOperationsService';
import { defenceTemplateMessage } from '../i18n/cycleDefenceTemplate';
import { assignPlayer, planCounts, planProblem, planningMessage, routeKey } from '../utils/cyclePlanningView';
import { cyclePhaseLabel } from '../utils/cycleBattleView';
import { formatMoscowDateTime } from '../utils/dateTime';
import { assignSquad, squadGroups, tacticalMessage } from '../utils/cycleTacticalView';
import './CycleOrdersPage.css';

function PlayerOrder({ member, order, data, draft, disabled, readOnly, change, copy, selected, toggle, tactical }) {
  const kind = order?.kind || '';
  const territoryName = id => data.territories.find(t => t.id === id)?.name || `#${id}`;
  const ordinary = [...new Set(draft.filter(o => ['attack', 'defend'].includes(o.kind)).map(o => o.territory_id).filter(Boolean))];
  const destinations = kind === 'defend' ? data.defence_targets : ordinary;
  const warningId = React.useId();
  return <div role="group" aria-label={member.name} className={`co-player${selected ? ' co-player-selected' : ''}`} aria-describedby={member.scouting || !member.eligible || member.reserve_blocked ? warningId : undefined}>
    {!readOnly && <input className="co-select-player" type="checkbox" checked={selected} disabled={disabled || member.scouting || (!member.eligible && !order)} aria-label={`${tactical('select')} ${member.name}`} onChange={toggle} />}
    <h4 className="co-player-name">{member.avatar_url ? <img src={member.avatar_url} alt="" loading="lazy" /> : <Shield aria-hidden="true" />}<span>{member.name}</span></h4>
    {member.scouting && !order ? null : readOnly ? <p className="co-assignment"><strong>{copy(kind || 'none')}</strong>{order?.territory_id && <span>{territoryName(order.territory_id)}
      {kind === 'attack' && ` · ${order.source_id ? territoryName(order.source_id) : copy('landing')} · ${copy(order.route || 'land')}`}</span>}</p> :
    <div className="co-fields"><label>{copy('assignment')}<select disabled={disabled} value={kind} onChange={e => change(member.user_id,
      e.target.value ? { kind: e.target.value } : null)}>
      <option value="">{copy('none')}</option>
      {['attack', 'defend', 'reserve', 'ambush'].map(value => <option key={value} value={value}
        disabled={member.scouting || !member.eligible || (value === 'reserve' && member.reserve_blocked)}>{copy(value)}</option>)}
    </select></label>
    {kind && kind !== 'reserve' && <label>{copy('destination')}<select disabled={disabled} value={kind === 'attack' && order.territory_id ? routeKey(order) : order.territory_id || ''}
      onChange={e => {
        const route = kind === 'attack' ? data.attack_routes.find(r => routeKey(r) === e.target.value) : null;
        change(member.user_id, { kind, ...(route || { territory_id: Number(e.target.value) || null }) });
      }}>
      <option value="">{copy('choose')}</option>
      {kind === 'attack' ? data.attack_routes.map(route => <option key={routeKey(route)} value={routeKey(route)}>
        {territoryName(route.territory_id)} · {route.source_id ? territoryName(route.source_id) : copy('landing')} · {copy(route.route)}
      </option>) : destinations.map(id => <option key={id} value={id}>{territoryName(id)}</option>)}
    </select></label>}</div>}
    {(member.scouting || !member.eligible || member.reserve_blocked) && <p id={warningId} className="co-muted">{copy(member.scouting ? 'scouting' : !member.eligible ? 'noIdentity' : 'blocked')}</p>}
  </div>;
}

function SquadBoard({ members, data, draft, disabled, readOnly, change, changeMany, copy, language }) {
  const tactical = key => tacticalMessage(key, language);
  const [selected, setSelected] = useState([]);
  const [kind, setKind] = useState('attack');
  const [target, setTarget] = useState('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');
  const territoryName = id => data.territories.find(t => t.id === id)?.name || `#${id}`;
  const ordinary = [...new Set(draft.filter(o => ['attack', 'defend'].includes(o.kind)).map(o => o.territory_id).filter(Boolean))];
  const destinations = kind === 'defend' ? data.defence_targets : ordinary;
  const groups = squadGroups(draft);
  const scoutMembers = members.filter(m => m.scouting);
  const freeMembers = members.filter(m => !m.scouting && !draft.some(o => o.user_id === m.user_id));
  const visible = members.filter(m => m.name.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
  function apply() {
    if (disabled || !selected.length) return;
    const route = kind === 'attack' ? data.attack_routes.find(r => routeKey(r) === target) : null;
    const order = !kind ? null : kind === 'reserve' ? { kind } : { kind, ...(route || { territory_id: Number(target) || null }) };
    const next = assignSquad(draft, selected, order);
    const problem = planProblem(next, data);
    if (problem) { setError(problem); return; }
    changeMany(next); setSelected([]); setError('');
  }
  return <div className="co-board">
    <section className="co-roster">
      <div className="co-section-heading"><h3>{tactical('roster')}</h3><span>{members.length}</span></div>
      {!readOnly && <div className="co-composer" role="group" aria-label={tactical('squadAssignment')}>
        <div className="co-composer-heading"><Groups aria-hidden="true" /><strong>{tactical('selected')}: {selected.length}</strong></div>
        <label>{copy('assignment')}<select disabled={disabled} value={kind} onChange={event => { setKind(event.target.value); setTarget(''); setError(''); }}>
          <option value="">{tactical('remove')}</option>{['attack', 'defend', 'reserve', 'ambush'].map(value => <option key={value} value={value}>{copy(value)}</option>)}
        </select></label>
        {kind && kind !== 'reserve' && <label>{copy('destination')}<select value={target} disabled={disabled} onChange={event => { setTarget(event.target.value); setError(''); }}>
          <option value="">{copy('choose')}</option>
          {kind === 'attack' ? data.attack_routes.map(route => <option key={routeKey(route)} value={routeKey(route)}>{territoryName(route.territory_id)} · {route.source_id ? territoryName(route.source_id) : copy('landing')} · {copy(route.route)}</option>) : destinations.map(id => <option key={id} value={id}>{territoryName(id)}</option>)}
        </select></label>}
        <button type="button" className="co-apply" disabled={disabled || !selected.length || Boolean(kind && kind !== 'reserve' && !target)} onClick={apply}><ArrowForward aria-hidden="true" />{tactical('apply')}</button>
        {error && <p role="alert" className="co-error">{copy(error)}</p>}
      </div>}
      <input type="search" className="co-search" aria-label={tactical('search')} placeholder={tactical('search')} value={query} onChange={event => setQuery(event.target.value)}
        onKeyDown={event => { if (event.key === 'Enter') event.preventDefault(); }} />
      {!visible.length && <p className="co-muted">{tactical('noResults')}</p>}
      {visible.map(member => <PlayerOrder key={member.user_id} member={member} order={draft.find(o => o.user_id === member.user_id)} data={data} draft={draft}
        disabled={disabled} readOnly={readOnly} change={change} copy={copy} tactical={tactical} selected={selected.includes(member.user_id)}
        toggle={() => { setSelected(ids => ids.includes(member.user_id) ? ids.filter(id => id !== member.user_id) : [...ids, member.user_id]); setError(''); }} />)}
    </section>
    <aside className="co-squads"><div className="co-section-heading"><h3>{tactical('squads')}</h3><span>{groups.length}</span></div>
      <div className="co-squad-list">{!groups.length && <p className="co-muted">{tactical('emptySquads')}</p>}
        {groups.map(group => <article className={`co-squad co-squad-${group.kind}`} key={group.key}>
          <div className="co-squad-heading"><span>{copy(group.kind)}</span><strong>{group.user_ids.length}</strong></div>
          {group.territory_id && <h4>{territoryName(group.territory_id)}</h4>}
          {group.kind === 'attack' && <p className="co-muted">{group.source_id ? territoryName(group.source_id) : copy('landing')} <ArrowForward aria-hidden="true" /> {copy(group.route || 'land')}</p>}
          <ul>{group.user_ids.map(id => <li key={id}><span>{members.find(m => m.user_id === id)?.name || `#${id}`}</span>
            {!readOnly && <button type="button" disabled={disabled} aria-label={`${tactical('remove')} ${members.find(m => m.user_id === id)?.name || `#${id}`}`} title={tactical('remove')} onClick={() => change(id, null)}><PersonRemove aria-hidden="true" /></button>}</li>)}</ul>
          {!readOnly && <button type="button" disabled={disabled} onClick={() => { setSelected(group.user_ids); setKind(group.kind); setTarget(group.kind === 'attack' ? routeKey(group) : String(group.territory_id || '')); setError(''); }}><Groups aria-hidden="true" />{tactical('selectSquad')}</button>}
        </article>)}
      </div>
      {[['scout', scoutMembers], ['free', freeMembers]].map(([key, rows]) => <section className="co-idle-group" key={key}><h4>{tactical(key)} <span>{rows.length}</span></h4><p>{rows.map(m => m.name).join(' · ') || '—'}</p></section>)}
    </aside>
  </div>;
}

function DefenceTemplate({ data, language, blocked, expired, command }) {
  const incoming = data.defence_template;
  const copy = key => defenceTemplateMessage(key, language);
  const [base, setBase] = useState(incoming);
  const [draft, setDraft] = useState(incoming.assignments);
  const [dirty, setDirty] = useState(false);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirmReload, setConfirmReload] = useState(false);
  const [deadlinePassed, setDeadlinePassed] = useState(false);
  const active = useRef(false);
  const inFlight = useRef(false);
  const headingId = React.useId();
  const dialogId = React.useId();
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => {
    if (inFlight.current || dirty) return;
    setBase(incoming); setDraft(incoming.assignments);
  }, [incoming, dirty]);
  useEffect(() => {
    const remaining = Date.parse(incoming.editable_until) - Date.parse(data.server_time);
    setDeadlinePassed(Boolean(incoming.editable_until) && !(remaining > 0));
    if (!(remaining > 0) || remaining > 2_147_483_647) return;
    const timer = setTimeout(() => setDeadlinePassed(true), remaining);
    return () => clearTimeout(timer);
  }, [incoming.editable_until, data.server_time]);
  const stale = dirty && base.revision !== incoming.revision;
  const disabled = blocked || busy || stale || notice === 'conflict' || !incoming.editable || deadlinePassed
    || (data.phase === 'preparation' && expired);
  const members = [...data.members, ...draft.filter(entry => !data.members.some(m => m.user_id === entry.user_id))
    .map(entry => ({ user_id: entry.user_id, name: `#${entry.user_id}` }))];
  const name = id => incoming.targets.find(t => t.id === id)?.name || `${copy('unavailable')} #${id}`;
  function change(userId, value) {
    if (disabled) return;
    setDraft(rows => [...rows.filter(entry => entry.user_id !== userId),
      ...(value ? [{ user_id: userId, territory_id: Number(value) }] : [])]);
    setDirty(true); setNotice('');
  }
  async function run(reload = false) {
    if (inFlight.current || blocked || (!reload && (disabled || !dirty))) return;
    inFlight.current = true; setBusy(true); setNotice('');
    try {
      const result = await command(reload ? null : { expected_revision: base.revision, assignments: draft });
      if (!active.current) return;
      setBase(result); setDraft(result.assignments); setDirty(false); setNotice(reload ? '' : 'saved');
    } catch (error) {
      if (active.current) setNotice(reload ? 'reloadFailed' : [403, 409].includes(error.response?.status) ? 'conflict' : 'failed');
    } finally { inFlight.current = false; if (active.current) setBusy(false); }
  }
  return <section className="co-template" aria-labelledby={headingId} aria-busy={busy}>
    <div className="co-section-heading"><h3 id={headingId}>{copy('heading')}</h3>
      <button type="button" aria-label={copy('reload')} title={copy('reload')} disabled={blocked || busy}
        onClick={() => dirty ? setConfirmReload(true) : run(true)}><Refresh aria-hidden="true" /></button></div>
    <div className="co-template-rows">{(incoming.editable ? members : members.filter(m => draft.some(entry => entry.user_id === m.user_id))).map(member => {
      const assignment = draft.find(entry => entry.user_id === member.user_id);
      return <div className="co-template-row" key={member.user_id}><span>{member.name}</span>
        {incoming.editable ? <select aria-label={`${copy('assignment')} ${member.name}`} value={assignment?.territory_id || ''}
          disabled={disabled || (!incoming.member_ids.includes(member.user_id) && !assignment)} onChange={event => change(member.user_id, event.target.value)}>
          <option value="">{copy('none')}</option>
          {assignment && !incoming.targets.some(t => t.id === assignment.territory_id) && <option value={assignment.territory_id} disabled>{name(assignment.territory_id)}</option>}
          {incoming.targets.map(target => <option key={target.id} value={target.id} disabled={!incoming.member_ids.includes(member.user_id)}>{target.name || `#${target.id}`}</option>)}
        </select> : <span>{name(assignment.territory_id)}</span>}</div>;
    })}</div>
    {!draft.length && !incoming.editable && <p className="co-muted">{copy('empty')}</p>}
    {(stale || ['conflict', 'failed', 'reloadFailed'].includes(notice)) && <p role="alert" className="co-error">{copy(stale ? 'conflict' : notice)}</p>}
    <div className="co-template-actions"><span role="status">{notice === 'saved' ? copy('saved') : dirty ? copy('dirty') : ''}</span>
      {incoming.editable && <button type="button" disabled={disabled || !dirty} onClick={() => run()}><Save aria-hidden="true" />{copy(busy ? 'saving' : 'save')}</button>}</div>
    <Dialog open={confirmReload} onClose={() => setConfirmReload(false)} aria-labelledby={dialogId}>
      <DialogTitle id={dialogId}>{copy('discard')}</DialogTitle>
      <DialogActions><button className="co-dialog-button" autoFocus onClick={() => setConfirmReload(false)}>{copy('cancel')}</button>
        <button className="co-dialog-button" onClick={() => { setConfirmReload(false); run(true); }}>{copy('refresh')}</button></DialogActions>
    </Dialog>
  </section>;
}

function OrdersContent({ cycleId }) {
  const { language } = useLocalizationContext();
  const copy = key => planningMessage(key, language);
  const [data, setData] = useState(null);
  const [draft, setDraft] = useState([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [clanless, setClanless] = useState(false);
  const [busy, setBusy] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [stale, setStale] = useState(false);
  const [notice, setNotice] = useState('');
  const [confirmReload, setConfirmReload] = useState(false);
  const [expired, setExpired] = useState(false);
  const base = useRef(null);
  const generation = useRef(0);
  const knownMembers = useRef(new Map());
  const ownClan = useRef(null);
  const mounted = useRef(false);
  const pending = useRef(false);
  const writing = useRef(false);
  const dirtyRef = useRef(false);
  const dialogId = React.useId();

  const load = useCallback(async (replace = false) => {
    if (pending.current || writing.current) return;
    pending.current = true;
    if (replace) setReplacing(true);
    const token = generation.current;
    try {
      const clan = await clanService.getMyClan();
      if (!mounted.current || token !== generation.current) return;
      if (clan === null) {
        setData(null); setDraft([]); knownMembers.current.clear(); ownClan.current = null;
        base.current = null; dirtyRef.current = false; setDirty(false); setStale(false);
        setConfirmReload(false); setNotice(''); setClanless(true); setFailed(false);
        return;
      }
      const next = await service.getPlanning(cycleId, clan.id);
      if (!mounted.current || token !== generation.current) return;
      const changedClan = ownClan.current !== next.clan_id;
      if (changedClan) { knownMembers.current.clear(); ownClan.current = next.clan_id; }
      for (const member of next.members) knownMembers.current.set(member.user_id, member);
      if (replace || changedClan || base.current === null || !dirtyRef.current) {
        base.current = next.plan.revision;
        setDraft(next.plan.orders);
        dirtyRef.current = false; setDirty(false); setStale(false);
        if (replace || changedClan) setNotice('');
      } else if (base.current !== next.plan.revision) setStale(true);
      setData(next); setFailed(false); setClanless(false);
    } catch (error) {
      if (mounted.current && token === generation.current) {
        setFailed(true);
        if (error.response?.status === 404) { setClanless(true); setData(null); }
        if ([403, 404].includes(error.response?.status)) {
          setData(null); setDraft([]); knownMembers.current.clear(); ownClan.current = null;
          base.current = null; dirtyRef.current = false; setDirty(false);
        }
      }
    } finally {
      pending.current = false;
      if (mounted.current) { setLoading(false); setReplacing(false); }
    }
  }, [cycleId]);

  useEffect(() => {
    mounted.current = true;
    load();
    const timer = setInterval(() => load(), 30_000);
    return () => { mounted.current = false; clearInterval(timer); };
  }, [load]);
  useEffect(() => {
    if (!data) return;
    const remaining = Date.parse(data.battle_at) - Date.parse(data.server_time);
    setExpired(!(remaining > 0));
    if (!(remaining > 0) || remaining > 2_147_483_647) return;
    const timer = setTimeout(() => setExpired(true), remaining);
    return () => clearTimeout(timer);
  }, [data]);

  const disabled = busy || replacing || failed || stale || !data?.editable || expired;
  const problem = data ? planProblem(draft, data) : null;
  function change(userId, order) {
    if (disabled) return;
    setDraft(rows => assignPlayer(rows, userId, order));
    dirtyRef.current = true; setDirty(true); setNotice('');
  }
  function changeMany(orders) {
    if (disabled) return;
    setDraft(orders); dirtyRef.current = true; setDirty(true); setNotice('');
  }
  async function save(event) {
    event.preventDefault();
    if (disabled || problem || writing.current || !dirty) return;
    // Ignore reads begun before this write, even if their responses arrive last.
    generation.current += 1;
    writing.current = true; setBusy(true); setNotice('');
    try {
      const saved = await service.savePlan(cycleId, data.clan_id, { expected_revision: base.current, orders: draft });
      if (!mounted.current) return;
      base.current = saved.revision;
      setData(old => ({ ...old, plan: saved })); setDraft(saved.orders);
      dirtyRef.current = false; setDirty(false); setNotice('saved');
    } catch (error) {
      if (!mounted.current) return;
      if (error.response?.status === 409 || error.response?.status === 403) { setStale(true); setNotice('conflict'); }
      else setNotice('saveFailed');
    } finally { writing.current = false; if (mounted.current) setBusy(false); }
  }
  async function templateCommand(payload) {
    if (writing.current) throw new Error('Operation in progress');
    generation.current += 1; writing.current = true; setBusy(true);
    try {
      const result = payload === null
        ? await cycleOperationsService.getDefenceTemplate(cycleId, data.clan_id)
        : await cycleOperationsService.saveDefenceTemplate(cycleId, data.clan_id, payload);
      if (mounted.current) setData(old => ({ ...old, defence_template: result }));
      return result;
    } finally { writing.current = false; if (mounted.current) setBusy(false); }
  }
  const counts = planCounts(draft);
  const members = data ? [...data.members, ...draft.filter(order => !data.members.some(m => m.user_id === order.user_id))
    .map(order => ({ ...(knownMembers.current.get(order.user_id) || { user_id: order.user_id, name: `#${order.user_id}` }), eligible: false }))] : [];
  return <PageShell className="cycle-orders" aria-busy={loading || busy || replacing}>
    <header><h1>{copy('ordersTitle')}</h1><button type="button" title={copy('retry')} aria-label={copy('retry')}
      disabled={loading || busy || replacing} onClick={() => dirty ? setConfirmReload(true) : load(true)}><Refresh aria-hidden="true" /></button></header>
    <Link className="co-back" to={`/campaign/cycles/${cycleId}`}><ArrowBack aria-hidden="true" />{copy('battles')}</Link>
    {loading ? <p role="status">{copy('loading')}</p> : clanless ? <p>{copy('clanless')}</p> : <>
      {failed && <p role="alert" className="co-error">{copy('failed')}</p>}
      {data && <>
        <h2>{data.clan_name}</h2>
        <p className="co-muted">{cyclePhaseLabel(data.phase, language)} · {copy('deadline')}: {formatMoscowDateTime(data.battle_at, '-', language)}</p>
        {data.defence_template && <DefenceTemplate key={data.clan_id} data={data} language={language}
          blocked={busy || replacing || failed} expired={expired} command={templateCommand} />}
        {!data.snapshot_ready ? <p>{copy('pending')}</p> : <>
          <dl className="co-counts">{Object.keys(counts).map(key => <div key={key}><dt>{copy(key)}</dt><dd>{counts[key]} / {data.limits[key]}</dd></div>)}</dl>
          {(!data.editable || expired) && <p className="co-muted">{copy('readonly')} {copy('permission')}</p>}
          {data.plan.warnings?.length > 0 && <p className="co-error">{copy('warnings')}</p>}
          {(stale || notice === 'saveFailed') && <p role="alert" className="co-error">{copy(stale ? 'conflict' : notice)}</p>}
          <form onSubmit={save}>
            {!members.length && <p>{copy('noMembers')}</p>}
            <SquadBoard key={data.clan_id} members={members} data={data} draft={draft} disabled={disabled} readOnly={!data.editable} change={change} changeMany={changeMany} copy={copy} language={language} />
            {problem && dirty && <p role="alert" id="co-problem" className="co-error">{copy(problem)}</p>}
            {(data.editable || dirty || notice === 'saved') && <footer><span role="status">{notice === 'saved' ? copy('saved') : dirty ? copy('dirty') : ''}</span>
              {data.editable && <button className="co-save" type="submit" disabled={disabled || !dirty || Boolean(problem)} aria-describedby={problem && dirty ? 'co-problem' : undefined}>
                <Save aria-hidden="true" />{copy(busy ? 'saving' : 'save')}</button>}</footer>}
          </form>
        </>}
      </>}
    </>}
    <Dialog open={confirmReload} onClose={() => setConfirmReload(false)} aria-labelledby={dialogId}>
      <DialogTitle id={dialogId}>{copy('discard')}</DialogTitle><DialogContent>{copy('discardText')}</DialogContent>
      <DialogActions><button className="co-dialog-button" autoFocus onClick={() => setConfirmReload(false)}>{copy('cancel')}</button>
        <button className="co-dialog-button" onClick={() => { setConfirmReload(false); load(true); }}>{copy('retry')}</button></DialogActions>
    </Dialog>
  </PageShell>;
}

export default function CycleOrdersPage() {
  const { cycleId } = useParams();
  const { user } = useAuth();
  return <OrdersContent key={`${user?.id}:${cycleId}`} cycleId={cycleId} />;
}
