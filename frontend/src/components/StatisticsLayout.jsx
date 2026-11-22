import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  BarChartRounded,
  TimelineRounded,
  SportsEsportsRounded,
} from '@mui/icons-material';
import './StatisticsLayout.css';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const tabs = [
  {
    to: '/statistics',
    labelKey: 'nav_statistics_overall',
    icon: BarChartRounded,
  },
  {
    to: '/all-matches',
    labelKey: 'nav_statistics_matches',
    icon: SportsEsportsRounded,
  },
  {
    to: '/influence-history',
    labelKey: 'common_influence',
    icon: TimelineRounded,
  },
];

const StatisticsLayout = ({
  title,
  subtitle,
  icon: HeaderIcon = BarChartRounded,
  action,
  children,
}) => {
  const { getLocalizedText: t } = useLocalizationContext();

  return (
  <main className="statistics-page">
    <div className="statistics-shell">
      <header className="statistics-header">
        <div className="statistics-title-block">
          <span className="statistics-title-icon" aria-hidden="true">
            {React.createElement(HeaderIcon)}
          </span>
          <div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
        </div>
        {action && <div className="statistics-header-action">{action}</div>}
      </header>

      <nav className="statistics-tabs" aria-label={t('statistics_sections')}>
        {tabs.map(({ to, labelKey, icon: TabIcon }) => (
          <NavLink
            key={to}
            to={to}
            end
            className={({ isActive }) => (
              `statistics-tab${isActive ? ' statistics-tab-active' : ''}`
            )}
          >
            {React.createElement(TabIcon)}
            <span>{t(labelKey)}</span>
          </NavLink>
        ))}
      </nav>

      {children}
    </div>
  </main>
  );
};

export default StatisticsLayout;
