import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Send, SupportAgent, Groups, Search, Shield, ArrowForward } from '@mui/icons-material';
import CycleMapCommands from './CycleMapCommands';
import { mapCommandMessage, mapReinforcementTarget } from '../../utils/cycleMapCommandView';
import { cycleCampaignService } from '../../services/cycleCampaignService';
import { reinforcementMessage, dispatchState, dispatchRouteDrawing } from '../../utils/cycleReinforcementView';
import { formatScore } from '../../utils/cycleBattleView';
import { formatMoscowDateTime } from '../../utils/dateTime';
import { interceptionMessage, interceptionPath } from '../../utils/cycleInterceptionView';
import { costText, economyMessage } from '../../utils/cycleEconomyView';
import { cycleMessage } from '../../utils/cycleBattleView';
import { attackDrawing, battleStatus, tacticalMessage, visibleHelpRequests, placeMapLabel } from '../../utils/cycleTacticalView';
import { planningMessage } from '../../utils/cyclePlanningView';
import './CycleMap.css';

function drawGeographicRoute(group, route, markerRadius) {
  const ns = 'http://www.w3.org/2000/svg';
  const boxes = new Map();
  for (const node of route.nodes || []) {
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', node.svg_path_data); path.classList.add('cycle-route-land');
    const title = document.createElementNS(ns, 'title'); title.textContent = node.name;
    path.appendChild(title); group.appendChild(path);
    boxes.set(node.territory_id, path.getBBox());
  }
  const drawing = dispatchRouteDrawing(route, boxes);
  if (!drawing) return null;
  if (drawing.points.length > 1) {
    const line = document.createElementNS(ns, 'polyline');
    line.setAttribute('points', drawing.points.map(point => point.join(',')).join(' '));
    line.classList.add('cycle-route-line'); group.appendChild(line);
  }
  const radius = markerRadius || Math.max(drawing.viewBox[2], drawing.viewBox[3]) / 60;
  for (const [point, kind] of [[drawing.origin, 'origin'], [drawing.target, 'target']]) {
    if (!point) continue;
    const marker = document.createElementNS(ns, 'circle');
    marker.setAttribute('cx', point[0]); marker.setAttribute('cy', point[1]); marker.setAttribute('r', radius);
    marker.classList.add('cycle-route-point', `cycle-route-${kind}`); group.appendChild(marker);
  }
  return drawing;
}

export function CycleDispatchRouteMap({ route, language }) {
  const svgRef = useRef(null);
  const titleId = React.useId();
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg || !route) return;
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    svg.appendChild(group);
    const drawing = drawGeographicRoute(group, route);
    if (drawing) {
      svg.setAttribute('viewBox', drawing.viewBox.join(' '));
      svg.setAttribute('data-route-drawn', 'true');
    }
    return () => { group.remove(); svg.removeAttribute('data-route-drawn'); };
  }, [route]);
  const copy = key => reinforcementMessage(key, language);
  if (!route) return <p className="cr-muted">{copy('routeLegacy')}</p>;
  return <figure className="cycle-dispatch-route">
    <svg ref={svgRef} role="img" aria-labelledby={titleId} preserveAspectRatio="xMidYMid meet">
      <title id={titleId}>{copy('route')}: {route.nodes.map(node => node.name).join(' → ')}</title>
    </svg>
    <p className="cycle-route-missing">{copy('routeGeometry')}</p>
    <figcaption>
      {route.status === 'mapped' ? <ol aria-label={copy('route')}>{route.nodes.map(node => <li key={node.territory_id}>{node.name}</li>)}</ol>
        : <p>{copy(route.status === 'no_origin' ? 'routeLandless' : 'routeUnreachable')}</p>}
    </figcaption>
  </figure>;
}

export function CycleMapTerritorySummary({ data, territoryId, cycleId, language, hasPort, influence }) {
  const copy = key => economyMessage(key, language);
  const territory = data?.territories?.find(item => item.territory_id === territoryId);
  const branches = ['gold', territory?.profile_material === 'mithril' ? 'mithril' : 'profile', 'fortification', 'offense', ...(hasPort ? ['naval'] : [])];
  const names = { gold: 'goldBranch', mithril: 'mithrilBranch', profile: 'profile' };
  return <section className="territory-summary cycle-map-economy">
    {territory ? <>
      <h3>{cycleMessage('cycle_map_income', language)}</h3>
      <p>{costText(territory.daily_income, copy)} · {copy('daily')}</p>
      <small>{cycleMessage('cycle_map_without_relics', language)}</small>
      <p>{cycleMessage('cycle_map_land_influence', language)}: {influence ?? '—'}</p>
      <h3>{cycleMessage('cycle_map_development', language)}</h3>
      <dl>{branches.map(branch => <div key={branch}><dt>{copy(names[branch] || branch)}</dt>
        <dd>{territory.levels[branch] || 0}/{territory.max_level}</dd></div>)}</dl>
    </> : <p>{copy(data ? 'unavailable' : 'loading')}</p>}
    {cycleId && data?.clan_id && <Link className="cycle-map-action" to={`/clans/${data.clan_id}?tab=development`}>{copy('lands')}</Link>}
  </section>;
}

export function CycleMapLegend({ data, enabled, language }) {
  const copy = key => tacticalMessage(key, language);
  if (!data || !enabled) return null;
  return <div className="cycle-map-legend">
    {data.ready ? <><span className="cycle-map-legend-attack"><ArrowForward aria-hidden="true" />{copy('attacker')}</span>
      <span><Shield aria-hidden="true" />{copy('defender')}</span>
      <span className="cycle-map-legend-help"><SupportAgent aria-hidden="true" />{copy('help')}</span>
      <span className="cycle-map-legend-help"><Send aria-hidden="true" />{copy('moving')}</span></>
      : data.phase === 'preparation' ? <span>{copy('preparation')}</span> : null}
  </div>;
}

export function CycleMapLayer({ svgRef, svgContent, fullscreen, data, territories, enabled, language }) {
  useEffect(() => {
    let layer;
    const draw = () => {
    const svg = svgRef.current?.querySelector('svg');
    if (!svg) return;
    svg.querySelector('#cycle-map-layer')?.remove();
    if (!enabled || !data?.ready) return;
    const ns = 'http://www.w3.org/2000/svg';
    layer = document.createElementNS(ns, 'g');
    layer.id = 'cycle-map-layer'; layer.style.pointerEvents = 'none';
    svg.appendChild(layer);
    const copy = key => tacticalMessage(key, language);
    const boxes = new Map();
    const paths = [...svg.querySelectorAll('path.interactive-region')];
    for (const territory of territories) {
      const path = paths.find(p => p.getAttribute('data-name') === territory.name || (territory.svg_path_data && p.getAttribute('d') === territory.svg_path_data));
      if (path) boxes.set(territory.id, path.getBBox());
    }
    const occupied = (data.battles || []).flatMap(battle => {
      const box = boxes.get(battle.territory_id);
      return box ? [{ x: box.x + box.width / 2 - 160, y: box.y + box.height / 2 - 120, width: 320, height: 250 }] : [];
    });
    function svgText(group, x, y, text, className) {
      const label = document.createElementNS(ns, 'text');
      label.setAttribute('x', x); label.setAttribute('y', y); label.setAttribute('text-anchor', 'middle');
      label.classList.add(className); label.textContent = text; group.appendChild(label);
      return label;
    }
    for (const route of data.attack_routes || []) {
      const drawing = attackDrawing(route, boxes);
      if (!drawing) continue;
      const group = document.createElementNS(ns, 'g');
      group.classList.add('cycle-map-attack'); group.setAttribute('data-clan-id', route.clan_id);
      const title = document.createElementNS(ns, 'title');
      title.textContent = `${route.clan_name || `#${route.clan_id}`} → ${territories.find(t => t.id === route.target_territory_id)?.name || route.target_territory_id} · ${copy('players')}: ${route.player_count}`;
      group.appendChild(title);
      const line = document.createElementNS(ns, 'line');
      for (const [key, value] of Object.entries({ x1: drawing.start[0], y1: drawing.start[1], x2: drawing.end[0], y2: drawing.end[1] })) line.setAttribute(key, value);
      if (route.route === 'sea') line.classList.add('cycle-map-sea-attack');
      group.appendChild(line);
      const head = document.createElementNS(ns, 'path');
      head.setAttribute('d', 'M -26 -16 L 0 0 L -26 16 Z');
      head.setAttribute('transform', `translate(${drawing.end.join(' ')}) rotate(${drawing.angle})`); group.appendChild(head);
      const name = route.clan_name || `#${route.clan_id}`;
      const text = name.length > 22 ? `${name.slice(0, 21)}…` : name;
      const position = placeMapLabel(drawing.middle, text, occupied);
      const leader = document.createElementNS(ns, 'line'); leader.classList.add('cycle-map-label-leader');
      for (const [key, value] of Object.entries({ x1: drawing.middle[0], y1: drawing.middle[1], x2: position.x, y2: position.y - 12 })) leader.setAttribute(key, value);
      group.appendChild(leader);
      svgText(group, position.x, position.y, text, 'cycle-map-route-label');
      layer.appendChild(group);
    }
    for (const dispatch of data.dispatches) {
      if (!dispatch.route) continue;
      const group = document.createElementNS(ns, 'g');
      group.classList.add('cycle-map-geographic-route');
      group.setAttribute('data-state', dispatchState(dispatch, Date.parse(data.server_time)));
      group.setAttribute('data-dispatch-id', dispatch.id); layer.appendChild(group);
      const drawing = drawGeographicRoute(group, dispatch.route, 12);
      if (drawing?.points.length > 1) {
        const end = drawing.points.at(-1), before = drawing.points.at(-2);
        const dx = end[0] - before[0], dy = end[1] - before[1];
        const arrow = document.createElementNS(ns, 'path'); arrow.classList.add('cycle-route-arrow');
        arrow.setAttribute('d', 'M -26 -16 L 0 0 L -26 16 Z');
        arrow.setAttribute('transform', `translate(${before[0] + dx * .75} ${before[1] + dy * .75}) rotate(${Math.atan2(dy, dx) * 180 / Math.PI})`);
        group.appendChild(arrow);
      }
    }
    for (const battle of data.battles) {
      const box = boxes.get(battle.territory_id);
      if (!box) continue;
      const status = battleStatus(battle);
      const group = document.createElementNS(ns, 'g');
      group.classList.add('cycle-map-marker');
      group.classList.add(`cycle-map-${status}`);
      group.setAttribute('transform', `translate(${box.x + box.width / 2} ${box.y + box.height / 2})`);
      const title = document.createElementNS(ns, 'title');
      title.textContent = `${copy(status)} · ${battle.sides.map(s => `${s.clan_name || `#${s.clan_id}`}: ${s.score}`).join(' · ')}`;
      group.appendChild(title);
      const circle = document.createElementNS(ns, 'circle'); circle.setAttribute('r', '42'); group.appendChild(circle);
      const label = document.createElementNS(ns, 'text'); label.setAttribute('text-anchor', 'middle'); label.setAttribute('dominant-baseline', 'central'); label.textContent = status === 'defense' ? '◇' : String(battle.sides.length); group.appendChild(label);
      svgText(group, 0, -65, copy(status === 'contested' ? 'attacker' : status === 'defense' ? 'defender' : status), 'cycle-map-status-label');
      const moving = data.dispatches.filter(d => d.territory_id === battle.territory_id && ['travelling', 'pending'].includes(dispatchState(d, Date.parse(data.server_time))));
      if (moving.length) {
        const badge = document.createElementNS(ns, 'text'); badge.classList.add('cycle-map-movement');
        badge.setAttribute('y', '87'); badge.setAttribute('text-anchor', 'middle');
        badge.textContent = `${copy('moving')} +${moving.length}`;
        const hint = document.createElementNS(ns, 'title'); hint.textContent = reinforcementMessage('movements', language); badge.appendChild(hint); group.appendChild(badge);
      }
      if (data.ambushes.some(a => a.territory_id === battle.territory_id && a.dispatch_id)) {
        const alert = document.createElementNS(ns, 'text'); alert.classList.add('cycle-map-interception');
        alert.setAttribute('x', '40'); alert.textContent = '!'; group.appendChild(alert);
      }
      layer.appendChild(group);
    }
    const helpByLand = new Map();
    for (const request of visibleHelpRequests(data)) {
      if (!helpByLand.has(request.territory_id)) helpByLand.set(request.territory_id, []);
      helpByLand.get(request.territory_id).push(request);
    }
    for (const [id, requests] of helpByLand) {
      const box = boxes.get(id);
      if (!box) continue;
      const group = document.createElementNS(ns, 'g'); group.classList.add('cycle-map-help');
      const title = document.createElementNS(ns, 'title'); title.textContent = requests.map(q => `${copy('help')}: ${q.clan_name || `#${q.recipient_clan_id}`}`).join(' · '); group.appendChild(title);
      const moving = data.dispatches.some(d => d.territory_id === id && ['travelling', 'pending'].includes(dispatchState(d, Date.parse(data.server_time))));
      svgText(group, box.x + box.width / 2, box.y + box.height / 2 + (moving ? 146 : 87), `${copy('help')} +${requests.length}`, 'cycle-map-help-label');
      layer.appendChild(group);
    }
    svg.appendChild(layer);
    };
    const timer = setTimeout(draw, 250);
    return () => { clearTimeout(timer); layer?.remove(); };
  }, [svgRef, svgContent, fullscreen, data, territories, enabled, language]);
  return null;
}

export function CycleMapPanel({ data, loading, error, refresh, territoryId, territoryName, cycleId, language }) {
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [sent, setSent] = useState(false);
  const [action, setAction] = useState(null);
  const [reinforcement, setReinforcement] = useState(null);
  const [clock, setClock] = useState(Date.now);
  const contextGeneration = useRef(0);
  const command = useRef(null);
  const scope = useRef(0);
  const copy = key => reinforcementMessage(key, language);
  const tactical = key => tacticalMessage(key, language);
  useEffect(() => {
    setBusy(false); setNotice(''); setSent(false); setAction(null); command.current = null;
    // Ответ относится только к текущей территории, клану и циклу этой панели.
    return () => { scope.current += 1; };
  }, [territoryId, cycleId, data?.clan_id]);
  useEffect(() => {
    const controller = new AbortController();
    setReinforcement(null);
    if (!cycleId || !data?.clan_id || data.cycle_id !== cycleId || loading || error) return;
    async function load() {
      const token = ++contextGeneration.current;
      try {
        const next = await cycleCampaignService.getReinforcements(cycleId, data.clan_id, { signal: controller.signal });
        if (controller.signal.aborted || token !== contextGeneration.current) return;
        if (next.cycle_id !== cycleId || next.clan_id !== data.clan_id) { setReinforcement(null); return; }
        setReinforcement({ data: next, mapData: data, territoryId, receivedAt: Date.now() });
      } catch {
        if (!controller.signal.aborted && token === contextGeneration.current) setReinforcement(null);
      }
    }
    load();
    const poll = setInterval(load, 15000);
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => { controller.abort(); clearInterval(poll); clearInterval(timer); };
  }, [cycleId, territoryId, data, loading, error]);
  if (!cycleId) return null;
  const context = !loading && !error && reinforcement?.mapData === data && reinforcement.territoryId === territoryId ? reinforcement.data : null;
  const now = context ? Date.parse(context.server_time) + Math.max(0, clock - reinforcement.receivedAt) : NaN;
  const reinforcementTarget = mapReinforcementTarget(context, territoryId, now);
  const battle = data?.battles.find(b => b.territory_id === territoryId);
  const requests = reinforcementTarget ? context.allied_targets?.filter(t => t.territory_id === territoryId) || [] : [];
  const dispatches = data?.dispatches.filter(d => d.territory_id === territoryId) || [];
  const helpRequests = visibleHelpRequests(data).filter(q => q.territory_id === territoryId);
  const attacks = data?.attack_routes?.filter(route => route.target_territory_id === territoryId) || [];
  const clanName = id => data?.clans?.find(c => c.id === id)?.name || data?.battles?.flatMap(b => b.sides).find(s => s.clan_id === id)?.clan_name || `#${id}`;
  async function help() {
    if (busy || loading || sent || !data?.can_command || !data.help_targets.includes(territoryId)) return;
    const id = command.current || crypto.randomUUID(); command.current = id;
    const requestScope = scope.current;
    setBusy(true); setNotice('');
    try {
      await cycleCampaignService.requestHelp(cycleId, data.clan_id, { territory_id: territoryId, request_id: id, expected_revision: data.revision });
      if (scope.current !== requestScope) return;
      setSent(true); setNotice('requested'); refresh();
    } catch {
      if (scope.current !== requestScope) return;
      setNotice('conflict'); refresh();
    } finally { if (scope.current === requestScope) setBusy(false); }
  }
  return <section className="cycle-map-panel" aria-busy={busy || loading}>
    {error && <><p role="alert">{copy('loadFailed')}</p><button onClick={refresh}>{copy('refresh')}</button></>}
    {data && !data.ready && data.phase === 'preparation' && <p className="cycle-map-phase">{tactical('preparation')}</p>}
    {battle && <>
      <div className="cycle-map-battle-heading"><Shield aria-hidden="true" /><div><strong>{tactical(battleStatus(battle))}</strong><span>{battle.territory_name || territoryName}</span></div></div>
      <p className="cycle-map-owner">{tactical('owner')}: <strong>{battle.owner_clan_id == null ? tactical('neutral') : battle.owner_clan_name || clanName(battle.owner_clan_id)}</strong></p>
      <ul className="cycle-map-scores">{battle.sides.map(s => <li key={s.clan_id}>
        <div><span className="cycle-map-role">{tactical(s.role === 'defender' || s.role === 'defense' || s.clan_id === battle.owner_clan_id ? 'defender' : 'attacker')}</span>
          <strong>{s.clan_name || `#${s.clan_id}`}</strong>{s.player_count != null && <small>{tactical('players')}: {s.player_count}</small>}</div>
        <strong className="cycle-map-score">{formatScore(s.score)}</strong></li>)}</ul>
      {attacks.map((route, index) => <p className="cycle-map-attack-detail" key={`${route.clan_id}:${index}`}>
        <ArrowForward aria-hidden="true" /><span><strong>{route.clan_name || clanName(route.clan_id)}</strong><br />
          {route.source_territory_id ? route.source_territory_name || `#${route.source_territory_id}` : planningMessage('landing', language)} → {battle.territory_name || territoryName}<br />
          {planningMessage(route.route || 'land', language)} · {tactical('players')}: {route.player_count}</span></p>)}
    </>}
    {helpRequests.map(q => <div className="cycle-map-help-request" key={q.id}><SupportAgent aria-hidden="true" /><span><strong>{tactical('help')}</strong><br />{q.clan_name || clanName(q.recipient_clan_id)}</span></div>)}
    {notice && <p role={notice === 'requested' ? 'status' : 'alert'}>{copy(notice)}</p>}
    {data?.can_command && data.help_targets.includes(territoryId) && <button disabled={busy || loading || sent} onClick={help}><SupportAgent aria-hidden="true" />{copy('request')}</button>}
    {requests.map(q => <button className="cycle-map-action" key={q.request_id} disabled={busy} onClick={() => setAction({ kind: 'reinforcements', recipient: q.recipient_clan_id, request: q.request_id })}><Send aria-hidden="true" />{copy('allied')} {clanName(q.recipient_clan_id)}</button>)}
    {dispatches.map(d => <div className="cycle-map-dispatch" key={d.id}><p><Send aria-hidden="true" /><strong>{copy(dispatchState(d, Date.parse(data.server_time)))}</strong></p>
      <p>{d.sender_clan_name || clanName(d.sender_clan_id)} <ArrowForward aria-hidden="true" /> {d.recipient_clan_name || clanName(d.recipient_clan_id)}</p>
      {d.player_count != null && <p>{tactical('players')}: {d.player_count}</p>}
      {copy('arrival')}: {formatMoscowDateTime(d.arrives_at, '-', language)}
      {d.interception_at && Date.parse(data.server_time) >= Date.parse(d.interception_at) && <><br /><Link to={interceptionPath(cycleId, d.id)}>{interceptionMessage('open', language)}</Link></>}
    </div>)}
    {data?.clan_id && <div className="cycle-map-command-buttons">
      <button disabled={loading || error} onClick={() => setAction({ kind: 'orders' })}><Groups aria-hidden="true" />{mapCommandMessage('orders', language)}</button>
      {reinforcementTarget && <button disabled={busy} onClick={() => setAction({ kind: 'reinforcements', recipient: reinforcementTarget.recipient_clan_id, request: reinforcementTarget.request_id })}><Send aria-hidden="true" />{mapCommandMessage('reinforcements', language)}</button>}
      <button disabled={loading || error} onClick={() => setAction({ kind: 'scout' })}><Search aria-hidden="true" />{mapCommandMessage('scout', language)}</button>
    </div>}
    {action && <CycleMapCommands key={`${cycleId}:${territoryId}:${data?.clan_id}`} action={action} onClose={() => setAction(null)} cycleId={cycleId} territoryId={territoryId} territoryName={territoryName} onUpdate={refresh} />}
  </section>;
}
