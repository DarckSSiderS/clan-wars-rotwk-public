import React, { useState, useEffect } from 'react';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { Link } from 'react-router-dom';
import { getFactionIcon } from '../data/factions';
import PlayerIdentity from './PlayerIdentity';
import { apiFetch } from '../services/apiFetch';
import './StatisticsSection.css';

const ELO_PATCHES = [
  { id: 'patch_202', label: 'Patch 2.02', color: '#58a9ff' },
  { id: 'ennorath', label: 'Ennorath', color: '#ff6262' },
];

const EloChart = ({ history, color, ariaLabel }) => {
  const values = history.map((item) => Number(item.elo));
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const spread = Math.max(1, maximum - minimum);
  const width = 480;
  const height = 112;
  const padding = 8;
  const points = values.map((value, index) => {
    const x = values.length === 1
      ? width / 2
      : padding + (index / (values.length - 1)) * (width - padding * 2);
    const y = height - padding - ((value - minimum) / spread) * (height - padding * 2);
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg
      className="elo-history-chart"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel}
    >
      <line x1="0" y1={height - 1} x2={width} y2={height - 1} className="elo-chart-axis" />
      <polyline points={points} fill="none" stroke={color} strokeWidth="4" vectorEffect="non-scaling-stroke" />
    </svg>
  );
};

const StatisticsSection = ({ playerStats, targetUsername }) => {
  const { getLocalizedText, loadPageTexts, language } = useLocalizationContext();
  
  const [activeSubTab, setActiveSubTab] = useState('overall');
  const [recentMatches, setRecentMatches] = useState([]);
  const [liveMatches, setLiveMatches] = useState([]);
  const [liveUpdatedAt, setLiveUpdatedAt] = useState(null);
  const [selectedMapPreview, setSelectedMapPreview] = useState(null);
  const [loading] = useState(false);
  const locale = language === 'de' ? 'de-DE' : language === 'en' ? 'en-US' : 'ru-RU';

  useEffect(() => {
    const loadAllMatches = async () => {
      try {
        const response = await apiFetch(`/api/v1/users/${targetUsername}/matches/all`);

        if (response.ok) {
          const data = await response.json();
          setRecentMatches(data);
        }
      } catch (error) {
        console.error('Ошибка загрузки всех матчей:', error);
      }
    };

    const loadLiveMatches = async () => {
      try {
        const response = await apiFetch(`/api/v1/statistics/live?player=${encodeURIComponent(targetUsername)}`);

        if (response.ok) {
          const data = await response.json();
          const sourceMatches = Array.isArray(data) ? data : (data.matches || []);
          setLiveUpdatedAt(data.updated_at || null);
          setLiveMatches(sourceMatches.map((match) => {
            const playerIsFirst = match.player1 === targetUsername;
            return {
              ...match,
              player_faction: playerIsFirst ? match.player1_faction : match.player2_faction,
              opponent_player: playerIsFirst ? match.player2 : match.player1,
              opponent_faction: playerIsFirst ? match.player2_faction : match.player1_faction,
            };
          }));
        }
      } catch (error) {
        console.error('Ошибка загрузки LIVE матчей:', error);
      }
    };

    loadPageTexts('profile', language);
    loadPageTexts('common', language);
    if (!targetUsername) return undefined;
    loadAllMatches();
    loadLiveMatches();
    const refreshTimer = window.setInterval(loadLiveMatches, 10 * 60 * 1000);
    return () => window.clearInterval(refreshTimer);
  }, [loadPageTexts, language, targetUsername]);

  const getWinRateClass = (winRate) => {
    if (winRate >= 70) return 'excellent';
    if (winRate >= 60) return 'good';
    if (winRate >= 50) return 'average';
    return 'poor';
  };

  const getMapIcon = (mapStats) => {
    return mapStats?.map_preview_url || '/icons/map-scroll.svg';
  };

  const useMapFallback = (event) => {
    if (event.currentTarget.src.endsWith('/icons/map-scroll.svg')) return;
    event.currentTarget.src = '/icons/map-scroll.svg';
    event.currentTarget.classList.add('is-fallback');
  };

  const openMapPreview = (url, name) => {
    if (!url) return;
    setSelectedMapPreview({ url, name });
  };

  const getLocalizedFactionName = (faction) => {
    const factionMap = {
      'Гондор': 'faction_gondor',
      'Рохан': 'faction_rohan',
      'Изенгард': 'faction_isengard',
      'Мордор': 'faction_mordor',
      'Ангмар': 'faction_angmar',
      'Мглистые Горы': 'faction_misty_mountains',
      'Лотлориэн': 'faction_lothlorien',
      'Имладрис': 'faction_imladris',
      'Арнор': 'faction_arnor',
      'Харад': 'faction_harad',
      'Гномы': 'faction_dwarves'
    };
    
    const identifier = factionMap[faction];
    if (identifier) {
      return getLocalizedText(identifier, faction);
    }
    return faction;
  };

  const formatMatchDate = (dateString) => {
    const date = new Date(dateString);
    return date.toLocaleDateString(locale, {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  const renderOverallStats = () => {
    if (!playerStats || playerStats.total_matches === 0) {
      return (
        <div className="text-center text-muted">
          <img src="/icons/axeswb.png" alt="No Data" style={{ width: '60px', height: '60px', marginBottom: '1rem' }} />
          <h6>{getLocalizedText('profile_statistics_no_data_title', 'Нет данных о матчах')}</h6>
          <p>{getLocalizedText('profile_statistics_no_data_description', 'У вас пока нет сыгранных матчей')}</p>
        </div>
      );
    }

    return (
      <div>
        {/* Основная статистика */}
        <div className="main-stats-container mb-4">
          <div className="main-stats-header">
            <h6 className="text-gradient mb-0">
              <img src="/icons/axeswb.png" alt="Chart" style={{ width: '20px', height: '20px', marginRight: '8px' }} />
              {getLocalizedText('profile_statistics_overall', 'Общая статистика')}
            </h6>
            <span className={`winrate-badge ${getWinRateClass(playerStats.win_rate)}`}>
              {playerStats.win_rate}%
            </span>
          </div>
          <div className="main-stats-grid">
            <div className="main-stat-card">
              <div className="main-stat-icon">
                <img src="/icons/axeswb.png" alt="Gamepad" style={{ width: '24px', height: '24px' }} />
              </div>
              <div className="main-stat-content">
                <div className="main-stat-number">{playerStats.total_matches}</div>
                <div className="main-stat-label">{getLocalizedText('profile_statistics_total_matches', 'Всего матчей')}</div>
              </div>
            </div>
            <div className="main-stat-card wins">
              <div className="main-stat-icon">
                <img src="/icons/sauronwb.png" alt="Trophy" style={{ width: '24px', height: '24px' }} />
              </div>
              <div className="main-stat-content">
                <div className="main-stat-number">{playerStats.wins}</div>
                <div className="main-stat-label">{getLocalizedText('profile_statistics_wins', 'Победы')}</div>
              </div>
            </div>
            <div className="main-stat-card losses">
              <div className="main-stat-icon">
                <img src="/icons/towerwb.png" alt="Loss" style={{ width: '24px', height: '24px' }} />
              </div>
              <div className="main-stat-content">
                <div className="main-stat-number">{playerStats.losses}</div>
                <div className="main-stat-label">{getLocalizedText('profile_statistics_losses', 'Поражения')}</div>
              </div>
            </div>
          </div>
          <div className="main-stats-progress">
            <div className="progress-bar">
              <div className="progress-fill wins" style={{ width: `${(playerStats.wins / playerStats.total_matches) * 100}%` }}></div>
              <div className="progress-fill losses" style={{ width: `${(playerStats.losses / playerStats.total_matches) * 100}%` }}></div>
            </div>
          </div>
        </div>

        {ELO_PATCHES.some(({ id }) => playerStats.elo_history?.[id]?.length) && (
          <div className="elo-history-container mb-4">
            <div className="elo-history-heading">
              <div>
                <h6 className="text-gradient mb-1">{getLocalizedText('profile_statistics_elo_history', 'История Elo')}</h6>
                <p>{getLocalizedText('profile_statistics_elo_history_description', 'Снимки сохраняются в момент импорта каждого матча')}</p>
              </div>
            </div>
            <div className="elo-history-grid">
              {ELO_PATCHES.map((patch) => {
                const history = playerStats.elo_history?.[patch.id] || [];
                if (!history.length) return null;
                const first = history[0];
                const latest = history[history.length - 1];
                const change = Number(latest.elo) - Number(first.elo);
                return (
                  <article className="elo-history-card" key={patch.id}>
                    <div className="elo-history-card-header">
                      <div>
                        <span>{patch.label}</span>
                        <strong>{latest.elo} Elo</strong>
                      </div>
                      <span className={`elo-change ${change >= 0 ? 'positive' : 'negative'}`}>
                        {change >= 0 ? '+' : ''}{change.toFixed(0)}
                      </span>
                    </div>
                    <EloChart
                      history={history}
                      color={patch.color}
                      ariaLabel={getLocalizedText('profile_statistics_elo_chart', 'Динамика Elo: {patch}', { patch: patch.label })}
                    />
                    <div className="elo-history-card-footer">
                      <span>{getLocalizedText('profile_statistics_elo_snapshots', '{count} снимков', { count: history.length })}</span>
                      <span>
                        {getLocalizedText('profile_statistics_elo_updated', 'Обновлено {date}', {
                          date: new Date(latest.captured_at || latest.played_at).toLocaleDateString(locale),
                        })}
                      </span>
                    </div>
                  </article>
                );
              })}
            </div>
          </div>
        )}

        {/* Топ фракции */}
        {Object.keys(playerStats.factions_used || {}).length > 0 && (
          <div className="top-factions-container mb-4">
            <h6 className="text-gradient mb-3">
              <img src="/icons/towerwb.png" alt="Flag" style={{ width: '20px', height: '20px', marginRight: '8px' }} />
              {getLocalizedText('profile_statistics_top_factions', 'Топ 3 лучшие фракции')}
            </h6>
            <div className="top-factions-grid">
              {Object.entries(playerStats.factions_used)
                .sort(([,a], [,b]) => b.wins - a.wins)
                .slice(0, 3)
                .map(([faction, factionStats], index) => {
                  const factionIcon = getFactionIcon(faction, 'large');
                  return (
                    <div key={faction} className="top-faction-card">
                      <div className="rank-badge">#{index + 1}</div>
                      <div className="faction-info">
                        {factionIcon && <img src={factionIcon} alt={faction} className="faction-icon" />}
                        <div className="faction-details">
                          <div className="faction-name">{getLocalizedFactionName(faction)}</div>
                                                     <div className="faction-stats">
                             <span className="wins">{factionStats.wins} {getLocalizedText('profile_statistics_match_result_win', 'W')}</span>
                             <span className="losses">{factionStats.losses} {getLocalizedText('profile_statistics_match_result_loss', 'L')}</span>
                             <span className={`winrate ${getWinRateClass(factionStats.win_rate)}`}>
                               {factionStats.win_rate}%
                             </span>
                           </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        )}

        {/* Топ карты */}
        {playerStats.maps_played && Object.keys(playerStats.maps_played).length > 0 && (
          <div className="top-maps-container">
            <h6 className="text-gradient mb-3">
              <img src="/icons/map-scroll.svg" alt="" style={{ width: '22px', height: '22px', marginRight: '8px' }} />
              {getLocalizedText('profile_statistics_top_maps', 'Лучшие карты по винрейту')}
            </h6>
            <div className="top-maps-grid">
              {Object.entries(playerStats.maps_played)
                .sort(([,a], [,b]) => b.win_rate - a.win_rate)
                .slice(0, 3)
                .map(([map, mapStats]) => {
                  const mapIcon = getMapIcon(mapStats);
                  return (
                    <div key={map} className="top-map-card">
                      <div className="map-info">
                        {mapStats.map_preview_url ? (
                          <button
                            type="button"
                            className="map-preview-button"
                            onClick={() => openMapPreview(mapStats.map_preview_url, map)}
                            title={getLocalizedText('profile_statistics_enlarge_map', 'Увеличить карту «{map}»', { map })}
                          >
                            <img src={mapIcon} alt={map} className="map-icon" onError={useMapFallback} />
                          </button>
                        ) : (
                          <img src={mapIcon} alt={map} className="map-icon is-fallback" onError={useMapFallback} />
                        )}
                        <div className="map-details">
                          <div className="map-name">{map}</div>
                          <div className="map-stats">
                            <span className="games">{mapStats.total} {getLocalizedText('profile_statistics_matches_played', 'игр')}</span>
                            <span className={`winrate ${getWinRateClass(mapStats.win_rate)}`}>
                              {mapStats.win_rate}%
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderFactionsStats = () => {
    // Получаем только те фракции, на которых есть статистика, и сортируем по количеству игр
    const factionsWithStats = playerStats?.factions_used 
      ? Object.entries(playerStats.factions_used)
          .sort(([,a], [,b]) => b.total - a.total) // Сортируем по убыванию количества игр
          .map(([faction]) => faction)
      : [];
    
    if (factionsWithStats.length === 0) {
      return (
        <div className="text-center text-muted">
          <img src="/icons/towerwb.png" alt="No Factions" style={{ width: '60px', height: '60px', marginBottom: '1rem' }} />
          <h6>{getLocalizedText('profile_statistics_no_factions', 'Нет данных по фракциям')}</h6>
          <p>{getLocalizedText('profile_statistics_no_factions_description', 'У вас пока нет сыгранных матчей на различных фракциях')}</p>
        </div>
      );
    }

    return (
      <div className="factions-stats-container">
        <div className="factions-grid">
          {factionsWithStats.map((faction) => {
            const factionStats = playerStats.factions_used[faction];
            
            const winRateClass = getWinRateClass(factionStats.win_rate);
            const factionIcon = getFactionIcon(faction, 'large');
            
            return (
              <div key={faction} className="faction-stat-card">
                <div className="faction-header">
                  <div className="faction-info">
                    {factionIcon && <img src={factionIcon} alt={faction} className="faction-icon" />}
                    <div className="faction-details">
                                                 <div className="faction-name">{getLocalizedFactionName(faction)}</div>
                      <div className="faction-meta">
                        <span className="games-count">{factionStats.total} {getLocalizedText('profile_statistics_matches_played', 'игр')}</span>
                        <span className={`winrate-badge ${winRateClass}`}>{factionStats.win_rate}%</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="faction-stats">
                  <div className="stat-row">
                    <div className="stat-item wins">
                      <div className="stat-number">{factionStats.wins}</div>
                      <div className="stat-label">{getLocalizedText('profile_statistics_wins', 'Победы')}</div>
                    </div>
                    <div className="stat-item losses">
                      <div className="stat-number">{factionStats.losses}</div>
                      <div className="stat-label">{getLocalizedText('profile_statistics_losses', 'Поражения')}</div>
                    </div>
                  </div>
                  <div className="faction-progress">
                    <div className="progress-bar">
                      <div className="progress-fill wins" style={{ width: `${factionStats.total > 0 ? (factionStats.wins / factionStats.total) * 100 : 0}%` }}></div>
                      <div className="progress-fill losses" style={{ width: `${factionStats.total > 0 ? (factionStats.losses / factionStats.total) * 100 : 0}%` }}></div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderAllMatches = () => {
    if (recentMatches.length === 0) {
      return (
        <div className="text-center text-muted">
          <img src="/icons/axeswb.png" alt="No Matches" style={{ width: '60px', height: '60px', marginBottom: '1rem' }} />
          <h6>{getLocalizedText('profile_statistics_no_matches', 'Нет матчей')}</h6>
          <p>{getLocalizedText('profile_statistics_no_matches_description', 'У вас пока нет сыгранных матчей')}</p>
        </div>
      );
    }

    return (
      <div className="all-matches-container">
        <div className="matches-grid">
          {recentMatches.map((match) => {
            const isWinner = match.winner_player === targetUsername;
            const opponent = isWinner ? match.loser_player : match.winner_player;
            const factionIcon = getFactionIcon(match.player_faction, 'small');
            
            return (
              <div key={match.id} className={`match-card ${isWinner ? 'win' : 'loss'}`}>
                <div className="match-header">
                  <div className="match-result">
                    <span className={`result-badge ${isWinner ? 'win' : 'loss'}`}>
                      {isWinner ? getLocalizedText('profile_statistics_match_result_win', 'Победа') : getLocalizedText('profile_statistics_match_result_loss', 'Поражение')}
                    </span>
                    <span className="match-date">{formatMatchDate(match.match_date)}</span>
                  </div>
                  <div className="match-map">
                    {match.map_preview_url ? (
                      <button
                        type="button"
                        className="match-map-preview-button"
                        onClick={() => openMapPreview(match.map_preview_url, match.map_name)}
                        title={getLocalizedText('profile_statistics_enlarge_map', 'Увеличить карту «{map}»', { map: match.map_name })}
                      >
                        <img src={match.map_preview_url} alt={match.map_name} className="match-map-preview" onError={useMapFallback} />
                      </button>
                    ) : (
                      <img src="/icons/map-scroll.svg" alt={match.map_name} className="match-map-preview is-fallback" />
                    )}
                    <span>{match.map_name}</span>
                  </div>
                </div>
                <div className="match-details">
                  <div className="player-info">
                    <img src={factionIcon} alt={match.player_faction} className="faction-icon" />
                    <div className="player-details">
                      <PlayerIdentity username={targetUsername} usernameClassName="entity-link player-name" />
                      <div className="player-faction">{getLocalizedFactionName(match.player_faction)}</div>
                    </div>
                  </div>
                  <div className="vs-separator">{getLocalizedText('profile_statistics_vs', 'VS')}</div>
                  <div className="opponent-info">
                    <img src={getFactionIcon(match.opponent_faction, 'small')} alt={match.opponent_faction} className="faction-icon" />
                    <div className="opponent-details">
                      <PlayerIdentity username={opponent} usernameClassName="entity-link opponent-name" />
                      <div className="opponent-faction">{getLocalizedFactionName(match.opponent_faction)}</div>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderLiveMatches = () => {
    if (liveMatches.length === 0) {
      return (
        <div className="text-center text-muted">
          <img src="/icons/vswb.png" alt="No Live Matches" style={{ width: '60px', height: '60px', marginBottom: '1rem' }} />
          <h6>{getLocalizedText('profile_statistics_no_live_matches', 'Нет активных матчей')}</h6>
          <p>{getLocalizedText('profile_statistics_no_live_matches_description', 'У вас нет активных матчей в данный момент')}</p>
        </div>
      );
    }

    return (
      <div className="live-matches-container">
        <div className="live-matches-grid">
          {liveMatches.map((match) => {
            const factionIcon = getFactionIcon(match.player_faction, 'small');
            
            return (
              <div key={match.id} className="live-match-card">
                <div className="live-match-header">
                  <div className="live-indicator">
                    <span className="live-dot"></span>
                    {getLocalizedText('profile_statistics_tab_live_matches', 'LIVE матчи')}
                  </div>
                  <div className="match-map">
                    <span>{match.map_name}</span>
                  </div>
                </div>
                <div className="live-match-details">
                  <div className="player-info">
                    <img src={factionIcon} alt={match.player_faction} className="faction-icon" />
                    <div className="player-details">
                      <PlayerIdentity username={targetUsername} usernameClassName="entity-link player-name" />
                      <div className="player-faction">{getLocalizedFactionName(match.player_faction)}</div>
                    </div>
                  </div>
                  <div className="vs-separator">{getLocalizedText('profile_statistics_vs', 'VS')}</div>
                  <div className="opponent-info">
                    <img src={getFactionIcon(match.opponent_faction, 'small')} alt={match.opponent_faction} className="faction-icon" />
                    <div className="opponent-details">
                      <PlayerIdentity username={match.opponent_player} usernameClassName="entity-link opponent-name" />
                      <div className="opponent-faction">{getLocalizedFactionName(match.opponent_faction)}</div>
                    </div>
                  </div>
                </div>
                <div className="live-match-status">
                  <span className="status-text">{getLocalizedText('profile_statistics_loading', 'В процессе')}</span>
                  <span className="match-duration">{match.duration || '0:00'}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="text-center">
        <div className="spinner-border text-primary" role="status">
          <span className="visually-hidden">{getLocalizedText('profile_statistics_loading', 'Загрузка статистики...')}</span>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Подвкладки */}
      <ul className="nav nav-tabs mb-3" role="tablist">
        <li className="nav-item" role="presentation">
          <button
            className={`nav-link ${activeSubTab === 'overall' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('overall')}
          >
            <img src="/icons/axeswb.png" alt="Overall" style={{ width: '16px', height: '16px', marginRight: '8px' }} />
            {getLocalizedText('profile_statistics_tab_overall', 'Общая')}
          </button>
        </li>
        <li className="nav-item" role="presentation">
          <button
            className={`nav-link ${activeSubTab === 'factions' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('factions')}
          >
            <img src="/icons/towerwb.png" alt="Factions" style={{ width: '16px', height: '16px', marginRight: '8px' }} />
            {getLocalizedText('profile_statistics_tab_factions', 'Фракции')}
          </button>
        </li>
        <li className="nav-item" role="presentation">
          <button
            className={`nav-link ${activeSubTab === 'recent' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('recent')}
          >
            <img src="/icons/sauronwb.png" alt="Recent" style={{ width: '16px', height: '16px', marginRight: '8px' }} />
                         {getLocalizedText('profile_statistics_tab_all_matches', 'Все матчи')}
          </button>
        </li>
        <li className="nav-item" role="presentation">
          <button
            className={`nav-link ${activeSubTab === 'live' ? 'active' : ''}`}
            onClick={() => setActiveSubTab('live')}
          >
            <img src="/icons/vswb.png" alt="Live" style={{ width: '16px', height: '16px', marginRight: '8px' }} />
            {getLocalizedText('profile_statistics_tab_live_matches', 'LIVE матчи')}
          </button>
        </li>
      </ul>

      {/* Контент подвкладок */}
      <div className="tab-content">
        <div className={`tab-pane fade ${activeSubTab === 'overall' ? 'show active' : ''}`}>
          {renderOverallStats()}
        </div>
        
        <div className={`tab-pane fade ${activeSubTab === 'factions' ? 'show active' : ''}`}>
          {renderFactionsStats()}
        </div>
        
                 <div className={`tab-pane fade ${activeSubTab === 'recent' ? 'show active' : ''}`}>
           {renderAllMatches()}
         </div>
        
        <div className={`tab-pane fade ${activeSubTab === 'live' ? 'show active' : ''}`}>
          {liveUpdatedAt && (
            <div className="text-muted small mb-3">
              {getLocalizedText('profile_statistics_live_updated', 'LIVE-данные обновлены {date}; следующее обновление не позднее чем через 10 минут', {
                date: new Date(liveUpdatedAt).toLocaleString(locale),
              })}
            </div>
          )}
          {renderLiveMatches()}
        </div>
      </div>
      {selectedMapPreview && (
        <div
          className="profile-map-viewer"
          role="dialog"
          aria-modal="true"
          aria-label={getLocalizedText('profile_statistics_map_dialog', 'Карта «{map}»', { map: selectedMapPreview.name })}
          onClick={(event) => {
            if (event.target === event.currentTarget) setSelectedMapPreview(null);
          }}
        >
          <div className="profile-map-viewer__content">
            <div className="profile-map-viewer__header">
              <strong>{selectedMapPreview.name}</strong>
              <button type="button" onClick={() => setSelectedMapPreview(null)} aria-label={getLocalizedText('profile_statistics_close_map', 'Закрыть карту')}>×</button>
            </div>
            <img src={selectedMapPreview.url} alt={selectedMapPreview.name} onError={useMapFallback} />
          </div>
        </div>
      )}
    </div>
  );
};

export default StatisticsSection; 
