import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { HistoryRounded, MilitaryTechRounded } from '@mui/icons-material';
import { PageShell, Surface } from '../components/ui';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { useAuth } from '../contexts/AuthContext';
import { usePatch } from '../contexts/PatchContext';
import { apiFetch } from '../services/apiFetch';
import PlayerIdentity from '../components/PlayerIdentity';
import './PrototypeFeaturePages.css';

const ROMAN_NUMERALS = [
  [1000, 'M'],
  [900, 'CM'],
  [500, 'D'],
  [400, 'CD'],
  [100, 'C'],
  [90, 'XC'],
  [50, 'L'],
  [40, 'XL'],
  [10, 'X'],
  [9, 'IX'],
  [5, 'V'],
  [4, 'IV'],
  [1, 'I'],
];

const formatRomanRank = (value) => {
  let remaining = Math.trunc(Number(value));
  if (!Number.isFinite(remaining) || remaining <= 0) return '—';

  let result = '';
  ROMAN_NUMERALS.forEach(([number, numeral]) => {
    while (remaining >= number) {
      result += numeral;
      remaining -= number;
    }
  });
  return result;
};

const RankingPage = () => {
  const { user } = useAuth();
  const { getLocalizedText: t, language } = useLocalizationContext();
  const { selectedPatch: patch, selectedPatchData, setSelectedPatch } = usePatch();
  const [tab, setTab] = useState('players');
  const [search, setSearch] = useState('');
  const [clanFilter, setClanFilter] = useState('all');
  const [positionFilter, setPositionFilter] = useState('all');
  const [players, setPlayers] = useState([]);
  const [clans, setClans] = useState([]);
  const [seasons, setSeasons] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const formatNumber = useMemo(() => new Intl.NumberFormat(language), [language]);

  const loadRanking = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const responses = await Promise.all([
        apiFetch(`/api/v1/statistics/players?patch=${patch}&limit=100`),
        apiFetch('/api/v1/statistics/clans'),
        apiFetch('/api/v1/campaign/seasons'),
      ]);
      if (responses.some((response) => !response.ok)) throw new Error('ranking');
      const [playerData, clanData, seasonData] = await Promise.all(responses.map((response) => response.json()));
      setPlayers(playerData.players || []);
      setClans([...(clanData.clans || [])].sort((a, b) => (b.influence || 0) - (a.influence || 0)));
      setSeasons(seasonData.seasons || []);
    } catch {
      setError(t('ranking_load_error'));
    } finally {
      setLoading(false);
    }
  }, [patch, t]);

  useEffect(() => { loadRanking(); }, [loadRanking]);

  const visiblePlayers = useMemo(() => {
    const query = search.trim().toLocaleLowerCase(language);
    return players.filter((player) => {
      const matchesQuery = !query || [player.username, player.clan_name]
        .filter(Boolean)
        .some((value) => value.toLocaleLowerCase(language).includes(query));
      const matchesClan = clanFilter === 'all' || String(player.clan_name || '') === clanFilter;
      const position = Number(player.position || Number.MAX_SAFE_INTEGER);
      const matchesPosition = positionFilter === 'all'
        || (positionFilter === 'top10' && position <= 10)
        || (positionFilter === 'top50' && position <= 50);
      return matchesQuery && matchesClan && matchesPosition;
    });
  }, [clanFilter, language, players, positionFilter, search]);
  const podium = players.filter((player) => player.rated !== false).slice(0, 3);
  const podiumSlots = [podium[1], podium[0], podium[2]].map((player, index) => player || ({
    isEmpty: true,
    position: [2, 1, 3][index],
  }));
  const clanOptions = [...new Set(players.map((player) => player.clan_name).filter(Boolean))].sort((a, b) => a.localeCompare(b, language));
  const personalRank = players.find((player) => player.username === user?.username)?.position;
  const currentSeason = seasons.find((season) => season.status === 'active') || seasons[0];

  return (
    <PageShell className="prototype-exact-page ranking-page">
      <div className="page-title">
        <div><div className="eyebrow">{currentSeason?.name || t('ranking_season_tab')}</div><h1 className="serif">{t('ranking_title')}</h1><p className="subtitle">{t('ranking_subtitle')}</p></div>
        <label className="ranking-header-patch">
          <span className="visually-hidden">{t('ranking_patch')}</span>
          <select className="season-pill" value={patch} onChange={(event) => setSelectedPatch(event.target.value)}>
            <option value="ennorath">Ennorath</option>
            <option value="patch_202">Patch 2.02</option>
          </select>
        </label>
      </div>

      <section className="podium ranking-podium" aria-label={t('ranking_players_tab')}>
          {podiumSlots.map((player) => (
            <Surface
              as="article"
              className={`podium-card ${player.position === 1 ? 'first' : player.position === 2 ? 'second' : 'third'}${player.isEmpty ? ' empty' : ''}`}
              data-position={player.position}
              key={`${player.position}-${player.username || 'empty'}`}
            >
              <span>{formatRomanRank(player.position)}</span>
              <span className={`profile-avatar${player.position === 1 ? '' : ' small'}`} aria-hidden="true">{player.username?.slice(0, 1).toUpperCase() || '·'}</span>
              {player.isEmpty ? <b>—</b> : <b><PlayerIdentity username={player.username} /></b>}
              <small>{player.clan_name || t('ranking_waiting_for_matches')}</small>
              <strong>{player.isEmpty || player.rated === false ? '—' : formatNumber.format(player.elo)}</strong>
            </Surface>
          ))}
      </section>

      <div className="tabs" role="tablist">
        {[
          ['players', t('ranking_players_tab')],
          ['clans', t('ranking_clans_tab')],
          ['season', t('ranking_season_tab')],
        ].map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={tab === value} className={`tab${tab === value ? ' active' : ''}`} onClick={() => setTab(value)}>{label}</button>)}
      </div>
      <nav className="ranking-related-links" aria-label={t('ranking_related_pages', 'Дополнительные разделы рейтинга')}>
        <Link className="btn" to="/seasons"><HistoryRounded fontSize="small" />{t('season_archive_title')}</Link>
        <Link className="btn" to="/all-matches">{t('nav_statistics_matches', 'Все матчи')}</Link>
        <Link className="btn" to="/influence-history">{t('nav_influence_history', 'История влияния')}</Link>
      </nav>

      {tab === 'players' && (
        <section role="tabpanel" className="prototype-tab-panel">
          <Surface className="filterbar ranking-filterbar" data-section="ranking-filters">
            <input className="input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('ranking_search_player')} />
            <label className="ranking-filter-field">
              <span className="visually-hidden">{t('ranking_all_clans')}</span>
              <select className="input" value={clanFilter} onChange={(event) => setClanFilter(event.target.value)}>
                <option value="all">{t('ranking_all_clans')}</option>
                {clanOptions.map((clan) => <option value={clan} key={clan}>{clan}</option>)}
              </select>
            </label>
            <label className="ranking-filter-field">
              <span className="visually-hidden">{t('ranking_all_positions')}</span>
              <select className="input" value={positionFilter} onChange={(event) => setPositionFilter(event.target.value)}>
                <option value="all">{t('ranking_all_positions')}</option>
                <option value="top10">{t('ranking_top_ten')}</option>
                <option value="top50">{t('ranking_top_fifty')}</option>
              </select>
            </label>
            <div className="ranking-current-rank"><small>{t('ranking_my_rank')}</small><b>#{formatRomanRank(personalRank)}</b></div>
          </Surface>
          <Surface className="card panel prototype-table-card">
            {loading ? <div className="prototype-state" role="status">{t('common_loading')}</div> : error ? (
              <div className="prototype-state is-error" role="alert">{error}</div>
            ) : visiblePlayers.length === 0 ? (
              <div className="prototype-state">{t('ranking_empty_players')}</div>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>#</th><th>{t('ranking_players_tab')}</th><th>{t('ranking_clans_tab')}</th><th>ELO · {selectedPatchData.label}</th><th>W / L</th><th>{t('profile_winrate')}</th></tr></thead>
                  <tbody>{visiblePlayers.map((player) => (
                    <tr key={`${player.position}-${player.username}`}>
                      <td><span className="rank">{formatRomanRank(player.position)}</span></td>
                      <td><PlayerIdentity username={player.username} /></td>
                      <td>{player.clan_id ? <Link to={`/clans/${player.clan_id}`}>{player.clan_name}</Link> : '—'}</td>
                      <td><strong>{player.rated === false ? t('ranking_unrated', 'Без рейтинга') : formatNumber.format(player.elo)}</strong></td>
                      <td>{player.wins || 0} / {player.losses || 0}</td>
                      <td>{player.win_rate || 0}%</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            )}
          </Surface>
        </section>
      )}

      {tab === 'clans' && (
        <Surface className="card panel prototype-table-card prototype-tab-panel" role="tabpanel">
          {loading ? <div className="prototype-state" role="status">{t('common_loading')}</div> : clans.length === 0 ? (
            <div className="prototype-state">{t('ranking_empty_clans')}</div>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead><tr><th>#</th><th>{t('ranking_clans_tab')}</th><th>{t('clan_statistics_influence')}</th><th>{t('clan_statistics_members')}</th><th>{t('clan_statistics_territories')}</th><th>{t('clan_statistics_defenses')}</th></tr></thead>
                <tbody>{clans.map((clan, index) => (
                  <tr key={clan.id}>
                    <td><span className="rank">{formatRomanRank(index + 1)}</span></td>
                    <td><Link to={`/clans/${clan.id}`}>{clan.name}</Link></td>
                    <td><strong>{formatNumber.format(clan.influence || 0)}</strong></td>
                    <td>{formatNumber.format(clan.member_count || 0)}</td>
                    <td>{formatNumber.format(clan.territory_count || 0)}</td>
                    <td>{formatNumber.format(clan.defenses_won || 0)}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
        </Surface>
      )}

      {tab === 'season' && (
        <section className="prototype-tab-panel prototype-season" role="tabpanel">
          <Surface className="prototype-season__lead">
            <MilitaryTechRounded aria-hidden="true" />
            <div>
              <span>{t('ranking_season_summary')}</span>
              <h2>{currentSeason?.name || t('seasons_not_started')}</h2>
              <p>{currentSeason?.status === 'active' ? t('seasons_status_active') : t('seasons_status_completed')}</p>
            </div>
          </Surface>
          <Surface className="prototype-season__archive">
            <h2>{t('chronicle_season_archive')}</h2>
            <div className="prototype-season__list">
              {seasons.slice(0, 4).map((season) => (
                <div key={season.id}><span>{season.name}</span><strong>{season.status === 'active' ? t('seasons_status_active') : t('seasons_status_completed')}</strong></div>
              ))}
            </div>
            <Link className="prototype-button" to="/seasons">{t('ranking_open_archive')}</Link>
          </Surface>
        </section>
      )}
    </PageShell>
  );
};

export default RankingPage;
