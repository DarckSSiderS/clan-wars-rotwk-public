import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Alert, Button, IconButton, Tooltip } from '@mui/material';
import { ArrowBackRounded, ArrowForwardRounded, HistoryRounded, RestartAltRounded, ZoomInRounded, ZoomOutRounded } from '@mui/icons-material';
import { PageShell } from '../components/ui';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { getSeasonArchive, listSeasonArchives } from '../services/seasonArchiveService';
import { archiveAwardUrl, archiveClanColor, archiveClans, archiveViewBox } from '../utils/seasonArchive';
import { withAppBase } from '../utils/appBasePath';
import './SeasonArchivePage.css';

const TERRITORY_METRICS = [
  ['stronghold_power', 'season_archive_stronghold'],
  ['fortifications', 'season_archive_fortifications'],
  ['offense_level', 'season_archive_offense'],
  ['gold_level', 'season_archive_gold_level'],
  ['resource_level', 'season_archive_resource_level'],
  ['port_level', 'season_archive_port_level'],
  ['fleet_level', 'season_archive_fleet_level'],
  ['development_level', 'season_archive_development'],
  ['influence_value', 'season_archive_influence'],
];

function AwardList({ awards = [], t, compact = false }) {
  if (!awards.length) return compact ? null : <p className="season-archive-muted">{t('season_archive_no_awards')}</p>;
  return <ul className={`season-archive-awards${compact ? ' is-compact' : ''}`}>
    {awards.map(award => {
      const image = archiveAwardUrl(award.image);
      const label = t(award.label_key, award.key);
      return <li key={award.key}>
        {image && <img src={withAppBase(image)} alt={compact ? label : ''} title={label} width="48" height="48" loading="lazy" />}
        {(!compact || !image) && <div><strong>{label}</strong>{!compact && <p>{t(award.description_key, '')}</p>}</div>}
      </li>;
    })}
  </ul>;
}

const Swatch = ({ clan }) => <i className="season-archive-swatch" style={{ backgroundColor: archiveClanColor(clan) }} aria-hidden="true" />;

function FrozenMap({ archive, clans, selectedId, selectedClanId, onSelect, t }) {
  const bounds = useMemo(() => archiveViewBox(archive.view_box), [archive.view_box]);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [imageFailed, setImageFailed] = useState(false);
  const drag = useRef(null);
  const wasDragged = useRef(false);
  const width = bounds.width / zoom;
  const height = bounds.height / zoom;
  const x = bounds.x + (bounds.width - width) / 2 + offset.x;
  const y = bounds.y + (bounds.height - height) / 2 + offset.y;
  const move = (dx, dy) => setOffset(previous => ({
    x: Math.max(-(bounds.width - width) / 2, Math.min((bounds.width - width) / 2, previous.x + dx)),
    y: Math.max(-(bounds.height - height) / 2, Math.min((bounds.height - height) / 2, previous.y + dy)),
  }));
  const changeZoom = value => { setZoom(Math.max(1, Math.min(4, value))); setOffset({ x: 0, y: 0 }); };
  const clanById = new Map(clans.map(clan => [String(clan.clan_id), clan]));
  return <div className="season-archive-map-shell">
    <div className="season-archive-map-toolbar">
      <h2>{t('season_archive_map')}</h2>
      <div className="season-archive-map-tools">
        <Tooltip title={t('season_archive_zoom_out')}><span><IconButton aria-label={t('season_archive_zoom_out')} disabled={zoom === 1} onClick={() => changeZoom(zoom - 0.5)}><ZoomOutRounded /></IconButton></span></Tooltip>
        <output>{Math.round(zoom * 100)}%</output>
        <Tooltip title={t('season_archive_zoom_in')}><span><IconButton aria-label={t('season_archive_zoom_in')} disabled={zoom === 4} onClick={() => changeZoom(zoom + 0.5)}><ZoomInRounded /></IconButton></span></Tooltip>
        <Tooltip title={t('season_archive_reset')}><IconButton aria-label={t('season_archive_reset')} onClick={() => changeZoom(1)}><RestartAltRounded /></IconButton></Tooltip>
      </div>
    </div>
    {imageFailed && <Alert severity="warning">{t('season_archive_image_error')}</Alert>}
    <svg className="season-archive-map" viewBox={zoom === 1 ? archive.view_box : `${x} ${y} ${width} ${height}`}
      aria-label={t('season_archive_map')} role="group" tabIndex={0}
      style={{ aspectRatio: `${bounds.width} / ${bounds.height}`, cursor: zoom > 1 ? 'grab' : 'default' }}
      onPointerDown={event => {
        wasDragged.current = false;
        if (zoom <= 1 || event.button !== 0) return;
        const rect = event.currentTarget.getBoundingClientRect();
        drag.current = { x: event.clientX, y: event.clientY, scale: Math.max(width / rect.width, height / rect.height) };
      }}
      onPointerMove={event => {
        if (!drag.current) return;
        const dx = drag.current.x - event.clientX;
        const dy = drag.current.y - event.clientY;
        if (!wasDragged.current && Math.abs(dx) + Math.abs(dy) < 4) return;
        wasDragged.current = true;
        event.currentTarget.setPointerCapture(event.pointerId);
        move(dx * drag.current.scale, dy * drag.current.scale);
        drag.current = { ...drag.current, x: event.clientX, y: event.clientY };
      }}
      onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
      onKeyDown={event => {
        const directions = { ArrowLeft: [-width / 10, 0], ArrowRight: [width / 10, 0], ArrowUp: [0, -height / 10], ArrowDown: [0, height / 10] };
        if (zoom > 1 && directions[event.key]) { event.preventDefault(); move(...directions[event.key]); }
      }}>
      <image href={withAppBase(archive.map_image_url)} x={bounds.x} y={bounds.y} width={bounds.width} height={bounds.height}
        preserveAspectRatio="xMidYMid meet" onError={() => setImageFailed(true)} pointerEvents="none" />
      {archive.territories.map(territory => {
        const clan = clanById.get(String(territory.owner_clan_id));
        const selected = String(selectedId) === String(territory.id);
        const related = selectedClanId != null && String(selectedClanId) === String(territory.owner_clan_id);
        return <path key={territory.id} d={territory.svg_path_data} role="button" tabIndex={0}
          aria-label={territory.name} aria-pressed={selected}
          className={`season-archive-territory${selected ? ' is-selected' : ''}${related ? ' is-related' : ''}`}
          fill={archiveClanColor(clan)} fillOpacity={clan ? 0.42 : territory.is_playable === false ? 0.08 : 0.16}
          onClick={() => { if (!wasDragged.current) onSelect(territory); }}
          onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); onSelect(territory); } }}>
          <title>{territory.name}</title>
        </path>;
      })}
    </svg>
    {!archive.territories.length && <p className="season-archive-muted">{t('season_archive_no_lands')}</p>}
  </div>;
}

function ArchiveDetail({ archive, t, language, date }) {
  const clans = useMemo(() => archiveClans(archive.clans), [archive.clans]);
  const [territoryId, setTerritoryId] = useState(null);
  const [clanId, setClanId] = useState(null);
  const territory = archive.territories.find(item => String(item.id) === String(territoryId));
  const clan = clans.find(item => String(item.clan_id) === String(clanId));
  const formatNumber = value => value == null ? '\u2014' : new Intl.NumberFormat(language).format(Number(value));
  const selectTerritory = item => { setTerritoryId(item?.id ?? null); setClanId(item?.owner_clan_id ?? null); };
  const selectClan = id => { setClanId(id); setTerritoryId(null); };
  return <>
    <header className="season-archive-heading">
      <div>
        <Link className="season-archive-back" to="/seasons"><ArrowBackRounded fontSize="small" />{t('season_archive_back')}</Link>
        <div className="season-archive-eyebrow">{t('season_archive_number', null, { number: archive.season.number })} · {t('seasons_status_completed')}</div>
        <h1>{archive.season.name}</h1>
        <p className="season-archive-muted">{date(archive.season.starts_at)} — {date(archive.season.ends_at)}</p>
      </div>
      <p className="season-archive-captured"><HistoryRounded fontSize="small" />{t('season_archive_captured', null, { date: date(archive.captured_at, true) })}</p>
    </header>
    <div className="season-archive-workspace">
      <div className="season-archive-map-column">
        <FrozenMap archive={archive} clans={clans} selectedId={territoryId} selectedClanId={clanId} onSelect={selectTerritory} t={t} />
        <nav className="season-archive-legend" aria-label={t('season_archive_legend')}>
          <button type="button" aria-pressed={clanId == null && territoryId == null} onClick={() => selectClan(null)}>{t('season_archive_all')}</button>
          {clans.map(item => <button type="button" key={item.clan_id} aria-pressed={String(item.clan_id) === String(clanId)} onClick={() => selectClan(item.clan_id)}><Swatch clan={item} />{item.clan_name}</button>)}
          <span><Swatch />{t('season_archive_neutral')}</span>
        </nav>
      </div>
      <aside className="season-archive-sidebar" aria-label={t('season_archive_details')}>
        <div className="season-archive-field"><label htmlFor="archive-territory">{t('season_archive_territory')}</label>
          <select id="archive-territory" value={territoryId ?? ''} onChange={event => selectTerritory(archive.territories.find(item => String(item.id) === event.target.value))}>
            <option value="">{t('season_archive_no_territory')}</option>
            {archive.territories.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </div>
        <section aria-live="polite">
          <h2>{territory?.name || t('season_archive_no_territory')}</h2>
          {territory && <>
            <dl className="season-archive-metrics">
              <div><dt>{t('season_archive_region')}</dt><dd>{territory.region || '\u2014'}</dd></div>
              <div><dt>{t('season_archive_port')}</dt><dd>{t(territory.has_port ? 'common_yes' : 'common_no')}</dd></div>
              {TERRITORY_METRICS.filter(([key]) => territory[key] != null).map(([key, label]) => <div key={key}><dt>{t(label)}</dt><dd>{formatNumber(territory[key])}</dd></div>)}
            </dl>
            {territory.is_playable === false && <p className="season-archive-muted">{t('season_archive_unavailable')}</p>}
            {!territory.owner_clan_id && <p className="season-archive-muted">{t('season_archive_neutral')}</p>}
          </>}
        </section>
        <div className="season-archive-field"><label htmlFor="archive-clan">{t('season_archive_clan')}</label>
          <select id="archive-clan" value={clanId ?? ''} onChange={event => selectClan(event.target.value || null)}>
            <option value="">{t('season_archive_no_clan')}</option>
            {clans.map(item => <option key={item.clan_id} value={item.clan_id}>{item.clan_name}</option>)}
          </select>
        </div>
        <section aria-live="polite">
          <h2 className="season-archive-clan-name">{clan && <Swatch clan={clan} />}{clan?.clan_name || t('season_archive_no_clan')}</h2>
          {clan && <>
            <dl className="season-archive-metrics">
              {['rank', 'influence', 'territory_count', 'wars_won'].map((key, index) => <div key={key}><dt>{t(['season_archive_rank', 'season_archive_influence', 'season_archive_lands', 'season_archive_wins'][index])}</dt><dd>{formatNumber(clan[key])}</dd></div>)}
            </dl>
            <h3>{t('season_archive_awards')}</h3>
            <AwardList awards={clan.awards} t={t} />
          </>}
        </section>
      </aside>
    </div>
    <section className="season-archive-results" aria-labelledby="season-archive-results-title">
      <h2 id="season-archive-results-title">{t('season_archive_standings')}</h2>
      {!clans.length ? <p className="season-archive-muted">{t('season_archive_no_clans')}</p> : <div className="season-archive-table-scroll" tabIndex={0} role="region" aria-label={t('season_archive_standings')}>
        <table className="season-archive-table">
          <thead><tr>{['rank', 'clan', 'influence', 'lands', 'wins', 'defenses', 'losses', 'awards'].map(key => <th scope="col" key={key}>{t(`season_archive_${key}`)}</th>)}</tr></thead>
          <tbody>{clans.map(item => <tr key={item.clan_id} className={String(clanId) === String(item.clan_id) ? 'is-selected' : ''}>
            <td>{formatNumber(item.rank)}</td>
            <th scope="row"><button type="button" onClick={() => selectClan(item.clan_id)} aria-pressed={String(clanId) === String(item.clan_id)}><Swatch clan={item} />{item.clan_name}</button></th>
            {['influence', 'territory_count', 'wars_won', 'defenses_won', 'wars_lost'].map(key => <td key={key}>{formatNumber(item[key])}</td>)}
            <td><AwardList awards={item.awards} t={t} compact /></td>
          </tr>)}</tbody>
        </table>
      </div>}
    </section>
  </>;
}

export default function SeasonArchivePage() {
  const { seasonId } = useParams();
  const { t, language } = useLocalizationContext();
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState({ key: null, loading: true });
  const key = seasonId || 'list';
  useEffect(() => {
    const controller = new AbortController();
    setState({ key, loading: true });
    const request = seasonId ? getSeasonArchive(seasonId, controller.signal) : listSeasonArchives(controller.signal);
    request.then(data => { if (!controller.signal.aborted) setState({ key, data }); })
      .catch(error => { if (!controller.signal.aborted) setState({ key, error: error.status === 404 ? 'season_archive_missing' : 'season_archive_error' }); });
    return () => controller.abort();
  }, [key, seasonId, attempt]);
  const date = (value, includeTime = false) => {
    const parsed = new Date(value);
    return value && Number.isFinite(parsed.getTime()) ? new Intl.DateTimeFormat(language, {
      dateStyle: 'medium', ...(includeTime ? { timeStyle: 'short' } : {}), timeZone: 'Europe/Moscow',
    }).format(parsed) : '\u2014';
  };
  const loading = state.key !== key || state.loading;
  return <PageShell className="season-archive-page">
    {(!seasonId || loading || state.error) && <header className="season-archive-heading"><div><h1>{t('season_archive_title')}</h1></div></header>}
    {loading ? <div className="season-archive-state" role="status">{t('common_loading')}</div> : state.error ? <div className="season-archive-state">
      <Alert severity="error">{t(state.error)}</Alert>
      <Button startIcon={<RestartAltRounded />} onClick={() => setAttempt(value => value + 1)}>{t('season_archive_retry')}</Button>
      {seasonId && <Link to="/seasons">{t('season_archive_back')}</Link>}
    </div> : seasonId ? <ArchiveDetail key={seasonId} archive={state.data} t={t} language={language} date={date} /> : (
      !state.data.length ? <p className="season-archive-state">{t('season_archive_empty')}</p> : <ul className="season-archive-season-list">
        {state.data.map(season => <li key={season.id}><Link to={`/seasons/${season.id}`}>
          <HistoryRounded className="season-archive-season-icon" aria-hidden="true" />
          <div><span className="season-archive-eyebrow">{t('season_archive_number', null, { number: season.number })} · {t('seasons_status_completed')}</span><h2>{season.name}</h2><p>{date(season.starts_at)} — {date(season.ends_at)}</p></div>
          <ArrowForwardRounded aria-hidden="true" />
        </Link></li>)}
      </ul>
    )}
  </PageShell>;
}
