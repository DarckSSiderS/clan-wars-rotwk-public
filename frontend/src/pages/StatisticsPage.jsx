import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { usePatch } from '../contexts/PatchContext';
import { apiFetch } from '../services/apiFetch';
import PlayerIdentity from '../components/PlayerIdentity';
import './StatisticsPage.css';

const PERIODS = [
  { value: '30d', labelKey: 'statistics_period_30d' },
  { value: 'season', labelKey: 'statistics_period_season' },
  { value: 'all', labelKey: 'statistics_period_all' },
];

const CONTROL_COLORS = ['#8c8f88', '#87453c', '#6f815c', '#564b6d', '#6f6045'];

const makePolyline = (values) => {
  const normalized = values.length > 1 ? values : [0, 0];
  const max = Math.max(1, ...normalized);
  return normalized.map((value, index) => {
    const x = (index / Math.max(1, normalized.length - 1)) * 600;
    const y = 158 - (Number(value || 0) / max) * 126;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
};

const StatisticsPage = () => {
  const { getLocalizedText, loadPageTexts, language } = useLocalizationContext();
  const { selectedPatch, selectedPatchData } = usePatch();
  const [period, setPeriod] = useState('30d');
  const [stats, setStats] = useState(null);
  const [world, setWorld] = useState(null);
  const [players, setPlayers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const numberFormatter = useMemo(() => new Intl.NumberFormat(language), [language]);

  useEffect(() => {
    loadPageTexts('statistics', language);
  }, [language, loadPageTexts]);

  useEffect(() => {
    const controller = new AbortController();
    const loadStatistics = async () => {
      setLoading(true);
      setError('');
      try {
        const [overallResponse, worldResponse, playersResponse] = await Promise.all([
          apiFetch(`/api/v1/statistics/overall?period=${period}`, { signal: controller.signal }),
          apiFetch('/api/v1/statistics/home', { signal: controller.signal }),
          apiFetch(`/api/v1/statistics/players?patch=${selectedPatch}&sort=elo_desc&limit=25`, { signal: controller.signal }),
        ]);

        if (!overallResponse.ok) {
          throw new Error(getLocalizedText('statistics_load_error', 'Не удалось загрузить статистику'));
        }

        setStats(await overallResponse.json());
        setWorld(worldResponse.ok ? await worldResponse.json() : null);
        setPlayers(playersResponse.ok ? (await playersResponse.json()).players || [] : []);
      } catch (requestError) {
        if (requestError.name !== 'AbortError') setError(requestError.message);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };

    loadStatistics();
    return () => controller.abort();
  }, [getLocalizedText, period, selectedPatch]);

  const dailyActivity = useMemo(() => stats?.daily_activity || [], [stats]);
  const activityPolyline = useMemo(
    () => makePolyline(dailyActivity.map((item) => item.matches)),
    [dailyActivity],
  );
  const activeWars = world?.active_wars || [];

  const territoryControl = useMemo(() => {
    const total = Number(stats?.territories?.total || world?.territories?.total || 0);
    const leaders = (stats?.territory_control || []).slice(0, 4).map((item, index) => ({
      ...item,
      color: item.map_color || CONTROL_COLORS[index],
      percent: total ? Math.round((Number(item.territories || 0) / total) * 100) : 0,
    }));
    const controlled = leaders.reduce((sum, item) => sum + Number(item.territories || 0), 0);
    const other = Math.max(0, total - controlled);
    return {
      total,
      items: [
        ...leaders,
        {
          clan_id: 'other',
          clan_name: getLocalizedText('statistics_other_clans', 'Прочие и свободные'),
          territories: other,
          percent: total ? Math.round((other / total) * 100) : 0,
          color: CONTROL_COLORS[4],
        },
      ],
    };
  }, [getLocalizedText, stats, world]);

  const donutBackground = useMemo(() => {
    if (!territoryControl.total) {
      return 'radial-gradient(circle at center,#131613 0 48%,transparent 49%),conic-gradient(#353a35 0 100%)';
    }
    let cursor = 0;
    const stops = territoryControl.items.map((item) => {
      const start = cursor;
      cursor = Math.min(100, cursor + item.percent);
      return `${item.color} ${start}% ${cursor}%`;
    });
    if (cursor < 100) stops.push(`#272b27 ${cursor}% 100%`);
    return `radial-gradient(circle at center,#131613 0 48%,transparent 49%),conic-gradient(${stops.join(',')})`;
  }, [territoryControl]);

  const bestMetrics = useMemo(() => {
    if (!players.length) return [];
    const bestWinrate = [...players].filter((player) => player.matches > 0)
      .sort((left, right) => right.win_rate - left.win_rate)[0];
    const mostWins = [...players].sort((left, right) => right.wins - left.wins)[0];
    const mostMatches = [...players].sort((left, right) => right.matches - left.matches)[0];
    return [
      { label: getLocalizedText('statistics_best_elo', null, { patch: selectedPatchData.label }), player: players[0], value: numberFormatter.format(players[0].elo || 0) },
      bestWinrate && { label: getLocalizedText('statistics_best_winrate'), player: bestWinrate, value: `${bestWinrate.win_rate}%` },
      mostWins && { label: getLocalizedText('statistics_most_wins'), player: mostWins, value: numberFormatter.format(mostWins.wins || 0) },
      mostMatches && { label: getLocalizedText('statistics_most_matches'), player: mostMatches, value: numberFormatter.format(mostMatches.matches || 0) },
      players[1] && { label: getLocalizedText('statistics_second_elo', null, { patch: selectedPatchData.label }), player: players[1], value: numberFormatter.format(players[1].elo || 0) },
    ].filter(Boolean);
  }, [getLocalizedText, numberFormatter, players, selectedPatchData.label]);

  const selectedPeriod = PERIODS.find((item) => item.value === period) || PERIODS[0];
  const selectedPeriodLabel = getLocalizedText(selectedPeriod.labelKey);

  return (
    <main className="prototype-exact-page statistics-exact-page">
      <header className="page-title">
        <div>
          <div className="eyebrow">{getLocalizedText('statistics_world_analytics', 'Аналитика мира')}</div>
          <h1 className="serif">{getLocalizedText('statistics_title_short', 'Статистика')}</h1>
          <p className="subtitle">
            {getLocalizedText('statistics_prototype_subtitle', 'Динамика сезона, активность игроков и распределение территорий.')}
          </p>
        </div>
        <select
          className="input select-small"
          value={period}
          onChange={(event) => setPeriod(event.target.value)}
          aria-label={getLocalizedText('statistics_period', 'Период статистики')}
        >
          {PERIODS.map((item) => (
            <option key={item.value} value={item.value}>{getLocalizedText(item.labelKey)}</option>
          ))}
        </select>
      </header>

      {loading ? (
        <section className="card panel statistics-exact-state" aria-live="polite">
          <span className="statistics-exact-loader" />
          {getLocalizedText('statistics_loading', 'Загружаем статистику')}
        </section>
      ) : error ? (
        <section className="card panel statistics-exact-state statistics-exact-state--error">{error}</section>
      ) : (
        <>
          <section className="grid g4 statistics-kpis" data-section="kpis">
            <article className="card kpi"><strong>{numberFormatter.format(stats?.total_matches || 0)}</strong><small>{getLocalizedText('statistics_kpi_matches')}</small><span className="delta">{selectedPeriodLabel}</span></article>
            <article className="card kpi"><strong>{numberFormatter.format(activeWars.length)}</strong><small>{getLocalizedText('statistics_kpi_battles_now')}</small><span className="delta">{getLocalizedText('statistics_kpi_active_clan_wars')}</span></article>
            <article className="card kpi"><strong>{numberFormatter.format(stats?.total_players || 0)}</strong><small>{getLocalizedText('statistics_kpi_players')}</small><span className="delta">{getLocalizedText('statistics_kpi_registered')}</span></article>
            <article className="card kpi"><strong>{numberFormatter.format(stats?.total_clans || 0)}</strong><small>{getLocalizedText('statistics_kpi_clans')}</small><span className="delta">{getLocalizedText('statistics_kpi_in_campaign')}</span></article>
          </section>

          <section className="section grid g2 statistics-chart-grid">
            <article className="card panel" data-section="match-chart">
              <div className="section-head">
                <div><div className="eyebrow">{getLocalizedText('statistics_activity')}</div><h2>{getLocalizedText('statistics_matches_30d')}</h2></div>
                <b className="delta">{numberFormatter.format(dailyActivity.reduce((sum, item) => sum + item.matches, 0))}</b>
              </div>
              <div className="linechart">
                <svg viewBox="0 0 600 180" preserveAspectRatio="none" role="img" aria-label={getLocalizedText('statistics_matches_trend')}>
                  <g opacity=".5">
                    <line className="gridline" x1="0" y1="30" x2="600" y2="30" />
                    <line className="gridline" x1="0" y1="90" x2="600" y2="90" />
                    <line className="gridline" x1="0" y1="150" x2="600" y2="150" />
                  </g>
                  <polyline points={activityPolyline} />
                </svg>
              </div>
            </article>

            <article className="card panel" data-section="active-war-fronts">
              <div className="section-head">
                <div><div className="eyebrow">{getLocalizedText('statistics_war_front')}</div><h2>{getLocalizedText('statistics_kpi_battles_now')}</h2></div>
                <b className="delta">{numberFormatter.format(activeWars.length)}</b>
              </div>
              <div className="statistics-war-fronts">
                {activeWars.slice(0, 4).map((war) => (
                  <Link to={`/battles/${war.id}`} key={war.id}>
                    <span>{war.territory_name || getLocalizedText('common_unknown_territory')}</span>
                    <b>{war.attacking_clan?.name || getLocalizedText('statistics_attacking_clan')} → {war.defending_clan?.name || getLocalizedText('homepage_neutral_lands')}</b>
                  </Link>
                ))}
                {!activeWars.length && <p>{getLocalizedText('statistics_no_active_battles')}</p>}
              </div>
            </article>
          </section>

          <section className="section grid g2 statistics-detail-grid">
            <article className="card panel" data-section="territory-control">
              <div className="section-head"><h2>{getLocalizedText('statistics_map_control')}</h2></div>
              <div className="donut-wrap">
                <div className="donut" style={{ background: donutBackground }}>
                  <b>{numberFormatter.format(territoryControl.total)}</b><span>{getLocalizedText('statistics_territories_lower')}</span>
                </div>
                <div className="legend wide">
                  {territoryControl.items.map((item) => (
                    <div key={item.clan_id}>
                      <span><i className="swatch" style={{ background: item.color }} />{item.clan_name}</span>
                      <b>{item.territories} · {item.percent}%</b>
                    </div>
                  ))}
                </div>
              </div>
            </article>

            <article className="card panel">
              <div className="section-head"><h2>{getLocalizedText('statistics_best_metrics')}</h2></div>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>{getLocalizedText('statistics_metric')}</th><th>{getLocalizedText('common_player')}</th><th>{getLocalizedText('statistics_value')}</th></tr></thead>
                  <tbody>
                    {bestMetrics.length ? bestMetrics.map((metric) => (
                      <tr key={metric.label}>
                        <td>{metric.label}</td>
                        <td><PlayerIdentity username={metric.player.username} /></td>
                        <td>{metric.value}</td>
                      </tr>
                    )) : <tr><td colSpan="3" className="statistics-empty-cell">{getLocalizedText('statistics_no_ranking_data')}</td></tr>}
                  </tbody>
                </table>
              </div>
            </article>
          </section>

        </>
      )}
    </main>
  );
};

export default StatisticsPage;
