import React, { useMemo } from 'react';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import AchievementIcon from './AchievementIcon';
import { normalizeAchievementTier } from '../utils/achievementPresentation';
import './ProfileAchievements.css';

const LEVELS = [
  { key: 'bronze', labelKey: 'achievements_tier_bronze' },
  { key: 'silver', labelKey: 'achievements_tier_silver' },
  { key: 'gold', labelKey: 'achievements_tier_gold' },
  { key: 'crystal', labelKey: 'achievements_tier_crystal' },
];

const SERIES_KEYS = new Set([
  'career_matches', 'career_wins', 'winning_streak', 'battle_hardened',
  'map_explorer', 'faction_explorer', 'long_battles', 'fast_victories',
  'night_battles', 'different_opponents', 'active_days', 'team_games', 'team_wins',
]);

const subjectFromType = (type) => String(type || '').split(':').slice(1).join(':');

const seriesTitle = (type, fallback, t) => {
  if (SERIES_KEYS.has(type)) return t(`achievement_${type}`, fallback);

  const mode = String(type || '').match(/^mode_(\dv\d)_(games|wins)$/);
  if (mode) return t(`achievement_mode_${mode[2]}`, fallback, { mode: mode[1] });

  for (const prefix of [
    'faction_games', 'faction_wins', 'faction_winrate',
    'map_games', 'map_wins', 'map_winrate',
  ]) {
    if (String(type).startsWith(`${prefix}:`)) {
      return t(`achievement_${prefix}`, fallback, { subject: subjectFromType(type) });
    }
  }

  if (fallback === 'first_battle' || fallback === 'first_win') {
    return t(`achievement_${fallback}`, fallback);
  }
  return fallback || t('achievements_title', 'Достижение');
};

const tierKey = (item, index, total) => {
  const name = String(item.achievement?.name || '');
  const namedTier = LEVELS.find((level) => name.endsWith(`_${level.key}`));
  if (namedTier) return namedTier.key;
  if (total === 4) return LEVELS[index].key;
  return normalizeAchievementTier(item.achievement?.rarity);
};

const tierGoal = (item, t) => {
  const achievement = item.achievement || {};
  const requirement = String(achievement.requirement_type || '');
  const parts = requirement.split(':');
  if ((parts[0] === 'faction_winrate' || parts[0] === 'map_winrate') && parts.length > 3) {
    return t('achievement_winrate_goal', null, { rate: parts[2], matches: parts[3] });
  }
  return `${achievement.target_value || achievement.requirement_value || 1}`;
};

const groupAchievements = (items) => {
  const groups = new Map();
  (items || []).forEach((item) => {
    const achievement = item.achievement || {};
    const key = achievement.achievement_type || `single:${achievement.id || item.id}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  });

  return [...groups.entries()].map(([key, levels]) => {
    levels.sort((left, right) => {
      const leftRequirement = String(left.achievement?.requirement_type || '').split(':');
      const rightRequirement = String(right.achievement?.requirement_type || '').split(':');
      const leftTarget = Number(leftRequirement[3] || left.achievement?.target_value || 0);
      const rightTarget = Number(rightRequirement[3] || right.achievement?.target_value || 0);
      return leftTarget - rightTarget;
    });
    return { key, levels };
  });
};

const ProfileAchievements = ({ achievements }) => {
  const { getLocalizedText: t } = useLocalizationContext();
  const groups = useMemo(() => groupAchievements(achievements), [achievements]);
  const completedSeries = groups.filter(({ levels }) => levels.some((item) => item.is_completed)).length;

  return (
    <section className="profile-achievements">
      <header className="profile-achievements__header">
        <div>
          <span className="profile-achievements__eyebrow">
            {t('achievements_eyebrow', 'Награды профиля')}
          </span>
          <h6>{t('achievements_title', 'Достижения')}</h6>
        </div>
        <span className="profile-achievements__counter">{completedSeries} / {groups.length}</span>
      </header>

      {groups.length > 0 ? (
        <div className="profile-achievements__grid">
          {groups.map(({ key, levels }) => {
            const completed = levels.filter((item) => item.is_completed);
            const next = levels.find((item) => !item.is_completed);
            const current = completed.at(-1) || levels[0];
            const display = next || current;
            const achievement = display.achievement || {};
            const target = Math.max(Number(achievement.target_value || achievement.requirement_value || 1), 1);
            const progressValue = Math.min(Number(display.progress || 0), target);
            const progress = Math.min(Math.round((progressValue / target) * 100), 100);
            const currentTier = tierKey(current, Math.max(completed.length - 1, 0), levels.length);
            const currentLevel = LEVELS.find((level) => level.key === currentTier) || LEVELS[0];
            const isMaxed = !next;

            return (
              <article className={`achievement-series achievement-series--${currentTier} ${isMaxed ? 'is-maxed' : ''}`} key={key}>
                <div className="achievement-series__top">
                  <AchievementIcon achievement={achievement} />
                  <div>
                    <span className="achievement-series__tier">
                      {isMaxed
                        ? t('achievements_highest_tier', 'Высшая ступень')
                        : t('achievements_current_reward', null, {
                          tier: t(currentLevel.labelKey, 'Бронза'),
                        })}
                    </span>
                    <h6>{seriesTitle(achievement.achievement_type, achievement.name, t)}</h6>
                  </div>
                </div>

                <div
                  className="achievement-series__levels"
                  aria-label={t('achievements_tiers_label', 'Ступени достижения')}
                >
                  {levels.map((item, index) => {
                    const level = tierKey(item, index, levels.length);
                    const levelDefinition = LEVELS.find((entry) => entry.key === level);
                    return (
                      <div
                        className={`achievement-level achievement-level--${level} ${item.is_completed ? 'is-complete' : ''}`}
                        key={item.id}
                      >
                        <span className="achievement-level__medal" />
                        <span>{t(levelDefinition?.labelKey || 'achievements_reward', 'Награда')}</span>
                        <strong>{tierGoal(item, t)}</strong>
                      </div>
                    );
                  })}
                </div>

                <div className="achievement-series__progress-label">
                  <span>
                    {isMaxed
                      ? t('achievements_all_tiers', 'Все ступени получены')
                      : t('achievements_next_goal', null, { goal: tierGoal(display, t) })}
                  </span>
                  <strong>
                    {isMaxed ? t('achievements_done', 'Готово') : `${progressValue} / ${target}`}
                  </strong>
                </div>
                <div className="achievement-series__progress" aria-hidden="true">
                  <span style={{ width: `${isMaxed ? 100 : progress}%` }} />
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="profile-achievements__empty">
          {t('achievements_empty', 'Достижения пока не рассчитаны')}
        </div>
      )}
    </section>
  );
};

export default ProfileAchievements;
