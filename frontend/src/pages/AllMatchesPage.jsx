import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CalendarMonthRounded,
  ClearRounded,
  ExtensionRounded,
  FilterAltRounded,
  GroupsRounded,
  MapRounded,
  SearchRounded,
  SportsEsportsRounded,
} from '@mui/icons-material';
import {
  Checkbox,
  Menu,
  MenuItem,
} from '@mui/material';
import { apiFetch } from '../services/apiFetch';
import MatchDetailsDialog from '../components/MatchDetailsDialog';
import StatisticsLayout from '../components/StatisticsLayout';
import PlayerIdentity from '../components/PlayerIdentity';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { FACTIONS, getFactionIcon, getFactionName, getFactionTone } from '../data/factions';
import { formatMoscowDate, formatMoscowTime } from '../utils/dateTime';
import './AllMatchesPage.css';

const defaultFilters = {
  factions: [],
  player: '',
  patch: 'all',
  game_mode: 'all',
  date_from: '',
  date_to: '',
};

const PATCH_LABELS = {
  all: null,
  ennorath: 'Ennorath',
  patch_202: 'Patch 2.02',
};

const MODE_LABELS = {
  all: null,
  '1v1': '1v1',
  '2v2': '2v2',
  '3v3': '3v3',
  '4v4': '4v4',
};

const readSavedFilters = () => {
  try {
    const saved = JSON.parse(localStorage.getItem('allMatchesFilters'));
    return {
      ...defaultFilters,
      ...(saved || {}),
      factions: Array.isArray(saved?.factions) ? saved.factions : [],
      patch: Object.prototype.hasOwnProperty.call(PATCH_LABELS, saved?.patch) ? saved.patch : 'all',
      game_mode: Object.prototype.hasOwnProperty.call(MODE_LABELS, saved?.game_mode) ? saved.game_mode : 'all',
    };
  } catch {
    return defaultFilters;
  }
};

const formatDuration = (duration) => {
  if (!duration && duration !== 0) {
    return '';
  }
  if (typeof duration === 'string') {
    return duration;
  }

  const totalSeconds = Math.max(0, Math.round(duration));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
};

const AllMatchesPage = () => {
  const { getLocalizedText, language } = useLocalizationContext();
  const savedFilters = useMemo(readSavedFilters, []);
  const [matches, setMatches] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState(savedFilters);
  const [playerInput, setPlayerInput] = useState(savedFilters.player);
  const [currentPage, setCurrentPage] = useState(() => {
    const savedPage = Number.parseInt(localStorage.getItem('allMatchesPage'), 10);
    return Number.isFinite(savedPage) && savedPage > 0 ? savedPage : 1;
  });
  const [totalPages, setTotalPages] = useState(1);
  const [totalMatches, setTotalMatches] = useState(0);
  const numberFormatter = useMemo(() => new Intl.NumberFormat(language), [language]);
  const patchLabels = useMemo(() => ({
    ...PATCH_LABELS,
    all: getLocalizedText('matches_all_mods', 'Все моды'),
  }), [getLocalizedText]);
  const modeLabels = useMemo(() => ({
    ...MODE_LABELS,
    all: getLocalizedText('matches_all_formats', 'Все форматы'),
  }), [getLocalizedText]);
  const [factionMenuAnchor, setFactionMenuAnchor] = useState(null);
  const [brokenMapPreviews, setBrokenMapPreviews] = useState(() => new Set());
  const [selectedMatch, setSelectedMatch] = useState(null);

  const factionFilter = filters.factions.join(',');

  useEffect(() => {
    if (playerInput === filters.player) {
      return undefined;
    }

    const timeout = window.setTimeout(() => {
      setFilters((current) => ({ ...current, player: playerInput }));
      setCurrentPage(1);
    }, 450);

    return () => window.clearTimeout(timeout);
  }, [filters.player, playerInput]);

  useEffect(() => {
    localStorage.setItem('allMatchesFilters', JSON.stringify(filters));
  }, [filters]);

  useEffect(() => {
    localStorage.setItem('allMatchesPage', String(currentPage));
  }, [currentPage]);

  useEffect(() => {
    const controller = new AbortController();

    const loadMatches = async () => {
      setLoading(true);
      setError('');

      const params = new URLSearchParams({
        page: String(currentPage),
        limit: '25',
      });

      if (filters.player) params.set('player', filters.player);
      if (filters.date_from) params.set('date_from', filters.date_from);
      if (filters.date_to) params.set('date_to', filters.date_to);
      if (factionFilter) params.set('faction', factionFilter);
      if (filters.patch !== 'all') params.set('patch', filters.patch);
      if (filters.game_mode !== 'all') params.set('game_mode', filters.game_mode);

      try {
        const response = await apiFetch(`/api/v1/statistics/matches?${params}`, {
          signal: controller.signal,
        });

        if (!response.ok) {
          throw new Error(getLocalizedText('matches_load_error'));
        }

        const data = await response.json();
        setMatches(data.matches || []);
        setBrokenMapPreviews(new Set());
        setTotalPages(Math.max(1, data.total_pages || 1));
        setTotalMatches(data.total_matches || 0);
      } catch (requestError) {
        if (requestError.name !== 'AbortError') {
          console.error('Ошибка загрузки матчей:', requestError);
          setError(requestError.message);
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };

    loadMatches();
    return () => controller.abort();
  }, [
    currentPage,
    factionFilter,
    filters.date_from,
    filters.date_to,
    filters.game_mode,
    getLocalizedText,
    filters.patch,
    filters.player,
  ]);

  const visiblePages = useMemo(() => {
    const pageCount = Math.min(5, totalPages);
    const start = Math.max(
      1,
      Math.min(currentPage - 2, Math.max(1, totalPages - pageCount + 1)),
    );
    return Array.from({ length: pageCount }, (_, index) => start + index);
  }, [currentPage, totalPages]);

  const toggleFaction = (faction) => {
    setFilters((current) => ({
      ...current,
      factions: current.factions.includes(faction)
        ? current.factions.filter((item) => item !== faction)
        : [...current.factions, faction],
    }));
    setCurrentPage(1);
  };

  const setDateFilter = (field, value) => {
    setFilters((current) => ({ ...current, [field]: value }));
    setCurrentPage(1);
  };

  const setSelectFilter = (field, value) => {
    setFilters((current) => ({ ...current, [field]: value }));
    setCurrentPage(1);
  };

  const clearFilters = () => {
    setFilters(defaultFilters);
    setPlayerInput('');
    setCurrentPage(1);
  };

  const renderFaction = (faction) => {
    return (
      <span className={`match-faction match-faction-${getFactionTone(faction)}`}>
        <img src={getFactionIcon(faction, 'small')} alt="" loading="lazy" />
        <span>{faction ? getFactionName(faction, language) : getLocalizedText('matches_faction_unknown', 'Фракция не указана')}</span>
      </span>
    );
  };

  const renderTeam = (match, isWinner) => {
    const participants = (match.participants || []).filter(
      (participant) => participant.is_winner === isWinner && !participant.is_observer,
    );
    const fallback = [{
      username: isWinner ? match.winner_player : match.loser_player,
      faction: isWinner ? match.winner_faction : match.loser_faction,
    }];
    return (
      <div className="match-team">
        {(participants.length ? participants : fallback).map((participant) => (
          <div
            className={`match-player ${isWinner ? 'match-player-winner' : 'match-player-loser'}`}
            key={participant.id || participant.username}
          >
            <div className="match-player-heading">
              <PlayerIdentity username={participant.username} />
              {participant.elo != null && (
                <span className="match-player-elo">
                  Elo {Math.round(Number(participant.elo))} · {patchLabels[match.rating_patch_family] || '—'}
                </span>
              )}
            </div>
            {renderFaction(participant.faction)}
          </div>
        ))}
      </div>
    );
  };

  const hasFilters = Boolean(
    filters.factions.length
    || filters.player
    || filters.patch !== 'all'
    || filters.game_mode !== 'all'
    || filters.date_from
    || filters.date_to,
  );

  return (
    <StatisticsLayout
      title={getLocalizedText('matches_all_title', 'Все матчи')}
      subtitle={getLocalizedText('matches_all_subtitle', 'История рейтинговых матчей с быстрым поиском и фильтрацией')}
      icon={SportsEsportsRounded}
      action={(
        <span className="all-matches-total">
          {getLocalizedText('matches_found', null, { count: numberFormatter.format(totalMatches) })}
        </span>
      )}
    >
      <section className="statistics-panel all-matches-filters">
        <div className="statistics-panel-header">
          <h2 className="statistics-panel-title">
            <FilterAltRounded />
            {getLocalizedText('matches_filters', 'Фильтры')}
          </h2>
          {hasFilters && (
            <button className="all-matches-clear" type="button" onClick={clearFilters}>
              <ClearRounded fontSize="small" />
              {getLocalizedText('matches_reset', 'Сбросить')}
            </button>
          )}
        </div>
        <div className="all-matches-filter-grid">
          <label className="all-matches-field">
            <span>{getLocalizedText('matches_player', 'Игрок')}</span>
            <div className="all-matches-input-wrap">
              <SearchRounded />
              <input
                type="search"
                value={playerInput}
                onChange={(event) => setPlayerInput(event.target.value)}
                placeholder={getLocalizedText('matches_player_placeholder', 'Ник игрока')}
              />
            </div>
          </label>

          <div className="all-matches-field">
            <span>{getLocalizedText('matches_factions', 'Фракции')}</span>
            <button
              className="all-matches-select"
              type="button"
              onClick={(event) => setFactionMenuAnchor(event.currentTarget)}
            >
              <span>
                {filters.factions.length
                  ? getLocalizedText('matches_selected', null, { count: filters.factions.length })
                  : getLocalizedText('matches_all_factions', 'Все фракции')}
              </span>
              <FilterAltRounded />
            </button>
            <Menu
              anchorEl={factionMenuAnchor}
              open={Boolean(factionMenuAnchor)}
              onClose={() => setFactionMenuAnchor(null)}
              slotProps={{
                paper: {
                  sx: {
                    width: 260,
                    maxHeight: 360,
                    border: '1px solid rgba(255,255,255,.14)',
                    borderRadius: '6px',
                    background: '#1a1a1c',
                    color: '#fff',
                  },
                },
              }}
            >
              {FACTIONS.map((faction) => (
                <MenuItem
                  key={faction}
                  onClick={() => toggleFaction(faction)}
                  sx={{ minHeight: 40, fontSize: '.86rem' }}
                >
                  <Checkbox
                    checked={filters.factions.includes(faction)}
                    size="small"
                    sx={{
                      color: 'rgba(255,255,255,.45)',
                      '&.Mui-checked': { color: '#ff5b5b' },
                    }}
                  />
                  {getFactionName(faction, language)}
                </MenuItem>
              ))}
            </Menu>
          </div>

          <label className="all-matches-field">
            <span>{getLocalizedText('matches_mod', 'Мод')}</span>
            <div className="all-matches-input-wrap">
              <ExtensionRounded />
              <select
                value={filters.patch}
                onChange={(event) => setSelectFilter('patch', event.target.value)}
              >
                {Object.entries(patchLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
          </label>

          <label className="all-matches-field">
            <span>{getLocalizedText('matches_format', 'Формат матча')}</span>
            <div className="all-matches-input-wrap">
              <GroupsRounded />
              <select
                value={filters.game_mode}
                onChange={(event) => setSelectFilter('game_mode', event.target.value)}
              >
                {Object.entries(modeLabels).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
          </label>

          <label className="all-matches-field">
            <span>{getLocalizedText('matches_date_from', 'Дата от')}</span>
            <div className="all-matches-input-wrap">
              <CalendarMonthRounded />
              <input
                type="date"
                value={filters.date_from}
                onChange={(event) => setDateFilter('date_from', event.target.value)}
              />
            </div>
          </label>

          <label className="all-matches-field">
            <span>{getLocalizedText('matches_date_to', 'Дата до')}</span>
            <div className="all-matches-input-wrap">
              <CalendarMonthRounded />
              <input
                type="date"
                value={filters.date_to}
                onChange={(event) => setDateFilter('date_to', event.target.value)}
              />
            </div>
          </label>
        </div>

        {(filters.factions.length > 0
          || filters.patch !== 'all'
          || filters.game_mode !== 'all') && (
          <div className="all-matches-filter-tags">
            {filters.patch !== 'all' && (
              <button type="button" onClick={() => setSelectFilter('patch', 'all')}>
                {patchLabels[filters.patch]}
                <ClearRounded />
              </button>
            )}
            {filters.game_mode !== 'all' && (
              <button type="button" onClick={() => setSelectFilter('game_mode', 'all')}>
                {modeLabels[filters.game_mode]}
                <ClearRounded />
              </button>
            )}
            {filters.factions.map((faction) => (
              <button key={faction} type="button" onClick={() => toggleFaction(faction)}>
                {getFactionName(faction, language)}
                <ClearRounded />
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="statistics-panel">
        <div className="statistics-panel-header">
          <h2 className="statistics-panel-title">
            <SportsEsportsRounded />
            {getLocalizedText('statistics_matches', 'Матчи')}
          </h2>
          <span className="statistics-panel-meta">
            {getLocalizedText('matches_page', null, { current: currentPage, total: totalPages })}
          </span>
        </div>

        {loading ? (
          <div className="statistics-state">
            <div>
              <div className="statistics-loader" />
              {getLocalizedText('matches_loading', 'Загружаем матчи')}
            </div>
          </div>
        ) : error ? (
          <div className="statistics-state">{error}</div>
        ) : matches.length === 0 ? (
          <div className="statistics-state">{getLocalizedText('matches_empty', 'По выбранным фильтрам матчей нет')}</div>
        ) : (
          <div className="all-matches-table-wrap">
            <table className="all-matches-table">
              <thead>
                <tr>
                  <th>{getLocalizedText('matches_date', 'Дата')}</th>
                  <th>{getLocalizedText('matches_winning_team', 'Победившая команда')}</th>
                  <th>{getLocalizedText('matches_losing_team', 'Проигравшая команда')}</th>
                  <th>{getLocalizedText('matches_map_mod_format', 'Карта, мод и формат')}</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((match) => (
                  <tr
                    key={match.id}
                    className="match-clickable-row"
                    role="button"
                    tabIndex={0}
                    onClick={(event) => {
                      if (!event.target.closest('a, button')) setSelectedMatch(match);
                    }}
                    onKeyDown={(event) => {
                      if (event.target.closest('a, button')) return;
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        setSelectedMatch(match);
                      }
                    }}
                  >
                    <td>
                      <strong>{formatMoscowDate(match.match_date, '', language)}</strong>
                      <span>{formatMoscowTime(match.match_date, '', language)}</span>
                    </td>
                    <td>
                      {renderTeam(match, true)}
                    </td>
                    <td>
                      {renderTeam(match, false)}
                    </td>
                    <td>
                      <div className="match-map-cell">
                        <div className="match-map-copy">
                          <strong className="match-map-name">
                            {match.map_name || getLocalizedText('matches_map_unknown', 'Карта не указана')}
                          </strong>
                          <span className="match-map-meta">
                            {[
                              patchLabels[match.rating_patch_family]
                                || match.patch_name
                                || match.patch_version,
                              modeLabels[match.game_mode]
                                || String(match.game_mode || '').replace(' versus ', 'v').replace(' vs ', 'v'),
                              formatDuration(match.duration),
                            ]
                              .filter(Boolean)
                              .join(' · ') || getLocalizedText('matches_ranked', 'Рейтинговый матч')}
                          </span>
                        </div>
                        <button
                          className="match-map-preview"
                          type="button"
                          disabled={!match.map_preview_url || brokenMapPreviews.has(match.id)}
                          aria-label={getLocalizedText('matches_enlarge_map', null, { map: match.map_name || '' })}
                          onClick={() => setSelectedMatch(match)}
                        >
                          {match.map_preview_url && !brokenMapPreviews.has(match.id) ? (
                            <img
                              src={match.map_preview_url}
                              alt={getLocalizedText('match_details_map_alt', null, { map: match.map_name || '' })}
                              loading="lazy"
                              onError={() => setBrokenMapPreviews((current) => {
                                const next = new Set(current);
                                next.add(match.id);
                                return next;
                              })}
                            />
                          ) : (
                            <MapRounded aria-hidden="true" />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {totalPages > 1 && (
        <nav className="all-matches-pagination" aria-label={getLocalizedText('matches_pagination', 'Страницы матчей')}>
          <button
            type="button"
            disabled={currentPage === 1}
            onClick={() => setCurrentPage((page) => page - 1)}
          >
            {getLocalizedText('matches_previous', 'Назад')}
          </button>
          {visiblePages.map((page) => (
            <button
              key={page}
              type="button"
              className={page === currentPage ? 'is-active' : ''}
              onClick={() => setCurrentPage(page)}
            >
              {page}
            </button>
          ))}
          <button
            type="button"
            disabled={currentPage === totalPages}
            onClick={() => setCurrentPage((page) => page + 1)}
          >
            {getLocalizedText('matches_next', 'Далее')}
          </button>
        </nav>
      )}

      <MatchDetailsDialog
        open={Boolean(selectedMatch)}
        matchRef={selectedMatch?.match_id || selectedMatch?.id}
        initialMatch={selectedMatch}
        onClose={() => setSelectedMatch(null)}
      />
    </StatisticsLayout>
  );
};

export default AllMatchesPage;
