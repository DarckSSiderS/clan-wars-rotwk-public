import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { PageShell } from '../components/ui';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { apiFetch } from '../services/apiFetch';
import './PrototypeFeaturePages.css';

const categoryMatches = (achievement, filter) => {
  if (filter === 'all') return true;
  const category = String(achievement.achievement?.category || '').toLowerCase();
  const type = String(achievement.achievement?.achievement_type || '').toLowerCase();
  if (filter === 'combat') return category.includes('combat') || type.includes('win') || type.includes('battle');
  if (filter === 'territories') return category.includes('territ') || type.includes('map') || type.includes('territ');
  return category.includes('season') || type.includes('season') || category.includes('collection');
};

const achievementTitle = (achievement, t) => {
  const rawName = String(achievement.name || '');
  const name = rawName.toLowerCase();
  if (name === 'first_battle') return t('achievement_card_first_battle');
  if (name === 'first_win') return t('achievement_card_first_win');

  const tier = name.match(/_(bronze|silver|gold|crystal)$/)?.[1];
  const type = String(achievement.achievement_type || name.replace(/_(bronze|silver|gold|crystal)$/, ''));
  let titleKey = '';
  let subject = '';

  const subjectSeries = [
    ['faction_games:', 'achievement_card_faction_games'],
    ['faction_wins:', 'achievement_card_faction_wins'],
    ['faction_winrate:', 'achievement_card_faction_mastery'],
    ['map_games:', 'achievement_card_map_games'],
    ['map_wins:', 'achievement_card_map_wins'],
    ['map_winrate:', 'achievement_card_map_mastery'],
  ];
  const subjectMatch = subjectSeries.find(([prefix]) => type.startsWith(prefix));
  if (subjectMatch) {
    titleKey = subjectMatch[1];
    subject = type.slice(subjectMatch[0].length);
  } else {
    const modeMatch = type.match(/^mode_(\dv\d)_(games|wins)$/);
    if (modeMatch) {
      titleKey = modeMatch[2] === 'wins' ? 'achievement_card_mode_wins' : 'achievement_card_mode_games';
      subject = modeMatch[1];
    } else {
      const knownTypes = {
        career_matches: 'achievement_card_career_matches',
        career_wins: 'achievement_card_career_wins',
        winning_streak: 'achievement_card_winning_streak',
        battle_hardened: 'achievement_card_battle_hardened',
        map_explorer: 'achievement_card_map_explorer',
        faction_explorer: 'achievement_card_faction_explorer',
        long_battles: 'achievement_card_long_battles',
        fast_victories: 'achievement_card_fast_victories',
        night_battles: 'achievement_card_night_battles',
        different_opponents: 'achievement_card_different_opponents',
        active_days: 'achievement_card_active_days',
        team_games: 'achievement_card_team_games',
        team_wins: 'achievement_card_team_wins',
      };
      titleKey = knownTypes[type] || '';
    }
  }

  if (!titleKey) return rawName.replaceAll('_', ' ');
  const parts = [t(titleKey, rawName)];
  if (subject) parts.push(subject);
  if (tier) parts.push(t(`achievement_tier_${tier}`, tier));
  return parts.join(' · ');
};

const AchievementsPage = () => {
  const { getLocalizedText: t, language } = useLocalizationContext();
  const [filter, setFilter] = useState('all');
  const [page, setPage] = useState(1);
  const [achievements, setAchievements] = useState([]);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const formatNumber = useMemo(() => new Intl.NumberFormat(language), [language]);

  const loadAchievements = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [listResponse, summaryResponse] = await Promise.all([
        apiFetch('/api/v1/achievements/my-achievements/'),
        apiFetch('/api/v1/achievements/my-achievements/summary/'),
      ]);
      if (!listResponse.ok || !summaryResponse.ok) throw new Error('achievements');
      setAchievements(await listResponse.json());
      setSummary(await summaryResponse.json());
    } catch {
      setError(t('achievements_load_error'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { loadAchievements(); }, [loadAchievements]);
  const visibleAchievements = achievements.filter((achievement) => categoryMatches(achievement, filter));
  const pageSize = 12;
  const pageCount = Math.max(1, Math.ceil(visibleAchievements.length / pageSize));
  const pagedAchievements = visibleAchievements.slice((page - 1) * pageSize, page * pageSize);
  useEffect(() => { setPage(1); }, [filter]);
  useEffect(() => {
    if (page > pageCount) setPage(pageCount);
  }, [page, pageCount]);
  const rareCompleted = achievements.filter((item) => item.is_completed && ['rare', 'epic', 'legendary'].includes(String(item.achievement?.rarity).toLowerCase())).length;
  const seasonalCompleted = achievements.filter((item) => item.is_completed && categoryMatches(item, 'seasonal')).length;
  const medalFor = (achievement) => {
    const category = String(achievement.category || achievement.achievement_type || '').toLowerCase();
    if (category.includes('territ') || category.includes('map')) return '✦';
    if (category.includes('season')) return '♛';
    if (category.includes('collect')) return '◇';
    return '⚔';
  };

  return (
    <PageShell className="prototype-exact-page achievements-page">
      <div className="page-title">
        <div><div className="eyebrow">{t('achievements_eyebrow')}</div><h1 className="serif">{t('achievements_page_title')}</h1><p className="subtitle">{t('achievements_page_subtitle')}</p></div>
        <div className="achievement-score"><b>{formatNumber.format(summary?.total_points || 0)}</b><small>{t('achievements_summary_points')}</small></div>
      </div>
      <section className="grid g4" data-section="achievement-progress">
        <div className="card kpi"><strong>{formatNumber.format(summary?.completed_achievements || 0)}</strong><small>{t('achievements_summary_completed')}</small><span className="delta">{t('achievements_of_total', null, { completed: summary?.completed_achievements || 0, total: summary?.total_achievements || achievements.length })}</span></div>
        <div className="card kpi"><strong>{rareCompleted}</strong><small>{t('achievements_summary_rare', 'Редких')}</small></div>
        <div className="card kpi"><strong>{seasonalCompleted}</strong><small>{t('achievements_filter_seasonal')}</small></div>
        <div className="card kpi"><strong>{Math.round(summary?.completion_percentage || 0)}%</strong><small>{t('shop_collection_progress')}</small></div>
      </section>
      <div className="tabs" role="tablist">
        {[
          ['all', t('achievements_filter_all')],
          ['combat', t('achievements_filter_combat')],
          ['territories', t('achievements_filter_territories')],
          ['seasonal', t('achievements_filter_seasonal')],
        ].map(([value, label]) => <button key={value} type="button" role="tab" aria-selected={filter === value} className={`tab${filter === value ? ' active' : ''}`} onClick={() => setFilter(value)}>{label}</button>)}
      </div>
      {filter === 'seasonal' && (
        <section className="card season-banner achievements-season-banner">
          <div><div className="eyebrow">{t('achievements_season_eyebrow')}</div><h2>{t('achievements_season_title')}</h2><p className="muted">{t('achievements_season_copy')}</p></div>
          <span className="season-pill">{t('achievements_season_status')}</span>
        </section>
      )}
      {loading ? <div className="prototype-state" role="status">{t('common_loading')}</div> : error ? (
        <div className="prototype-state is-error" role="alert"><p>{error}</p><button className="prototype-button" type="button" onClick={loadAchievements}>{t('clan_statistics_refresh')}</button></div>
      ) : visibleAchievements.length === 0 ? (
        <div className="prototype-state">{t('achievements_empty')}</div>
      ) : (
        <section className="grid g4 achievement-grid" role="tabpanel">
          {pagedAchievements.map((item) => {
            const achievement = item.achievement || {};
            const target = Math.max(Number(achievement.target_value || achievement.requirement_value || 1), 1);
            const progress = Math.min(Number(item.progress || 0), target);
            const percentage = item.is_completed ? 100 : Math.min(100, Math.round(progress / target * 100));
            return (
              <article className={`card achievement hover${achievement.is_available === false ? ' locked' : ''}`} key={item.id}>
                <div className="medal" aria-hidden="true">{medalFor(achievement)}</div>
                <h3>{achievementTitle(achievement, t)}</h3>
                <p>{achievement.description}</p>
                <div className="progress" aria-label={`${percentage}%`} role="progressbar" aria-valuenow={percentage} aria-valuemin="0" aria-valuemax="100"><i style={{ width: `${percentage}%` }} /></div>
                <small>{percentage}% · {formatNumber.format(achievement.points || 0)} XP</small>
              </article>
            );
          })}
        </section>
      )}
      {!loading && !error && visibleAchievements.length > pageSize && (
        <nav className="achievements-pagination" aria-label={t('achievements_pagination_label')}>
          <button type="button" className="btn" disabled={page === 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>{t('achievements_previous_page')}</button>
          <span>{t('achievements_page_status', null, { page, pages: pageCount })}</span>
          <button type="button" className="btn" disabled={page === pageCount} onClick={() => setPage((value) => Math.min(pageCount, value + 1))}>{t('achievements_next_page')}</button>
        </nav>
      )}
    </PageShell>
  );
};

export default AchievementsPage;
