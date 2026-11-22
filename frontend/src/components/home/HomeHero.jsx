import React from 'react';
import { Link } from 'react-router-dom';
import { useLocalizationContext } from '../../contexts/LocalizationContext';

const HomeHero = ({ summary, loading }) => {
  const { getLocalizedText: t } = useLocalizationContext();
  const territories = summary?.territories || {};
  const season = summary?.season;
  const seasonEyebrow = season
    ? t('homepage_season_dynamic', 'Сезон {number} · {name}', {
      number: season.number,
      name: season.name,
    })
    : t('homepage_season_preparing', 'Новый сезон готовится');
  const metrics = [
    [summary?.total_clans, t('homepage_clans_count', 'Кланов')],
    [territories.total, t('homepage_territories_total', 'Территорий')],
    [summary?.clan_players, t('homepage_clan_players_short', 'Игроков')],
    [summary?.active_wars?.length, t('homepage_active_wars_short', 'Активных битв')],
  ];

  return (
    <header className="home-hero">
      <div className="home-hero__copy">
        <p className="home-hero__eyebrow">
          {loading ? '—' : seasonEyebrow}
        </p>
        <h1>{t('homepage_hero_title', 'Война за Средиземье')}</h1>
        <p className="home-hero__description">
          {t(
            'homepage_hero_description_prototype',
            'Кланы сражаются за территории. Побеждайте в матчах, усиливайте свой клан, собирайте реликвии и меняйте границы мира.',
          )}
        </p>

        <div className="home-hero__actions" aria-label={t('homepage_primary_actions', 'Основные действия')}>
          <Link className="home-hero__action home-hero__action--primary" to="/map">
            {t('homepage_open_map_short', 'Открыть карту')}
          </Link>
          <Link className="home-hero__action home-hero__action--secondary" to="/clans">
            {t('homepage_season_clans', 'Кланы сезона')}
          </Link>
          <Link className="home-hero__action home-hero__action--secondary" to="/rules">
            {t('nav_rules', 'Правила ClanWar')}
          </Link>
        </div>

        <div className="home-hero__metrics" aria-label={t('homepage_campaign_numbers', 'Кампания в цифрах')}>
          {metrics.map(([value, label]) => (
            <div className="home-hero__metric" key={label}>
              <strong>{loading ? '—' : (value ?? 0).toLocaleString('ru-RU')}</strong>
              <span>{label}</span>
            </div>
          ))}
        </div>
      </div>
    </header>
  );
};

export default HomeHero;
