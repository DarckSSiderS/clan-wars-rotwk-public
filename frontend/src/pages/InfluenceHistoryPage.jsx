import React, { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AccountBalanceRounded,
  FlagRounded,
  HistoryRounded,
  LandscapeRounded,
  TrendingDownRounded,
  TrendingUpRounded,
} from '@mui/icons-material';
import api from '../services/api';
import StatisticsLayout from '../components/StatisticsLayout';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { getTerritoryName } from '../i18n/territories';
import './CampaignPages.css';

const formatDate = (value, language) => value
  ? new Intl.DateTimeFormat(language, {
      timeZone: 'Europe/Moscow',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value))
  : '—';

const InfluenceHistoryPage = () => {
  const { getLocalizedText: t, language } = useLocalizationContext();
  const formatNumber = useMemo(() => new Intl.NumberFormat(language), [language]);
  const [data, setData] = useState({ clans: [], events: [] });
  const [seasons, setSeasons] = useState([]);
  const [clanId, setClanId] = useState('');
  const [seasonId, setSeasonId] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.get('/campaign/seasons')
      .then((response) => active && setSeasons(response.data.seasons || []))
      .catch(() => active && setSeasons([]));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    api.get('/campaign/influence-history', {
      params: {
        clan_id: clanId || undefined,
        season_id: seasonId || undefined,
        limit: 300,
      },
    })
      .then((response) => active && setData(response.data))
      .catch(() => active && setError(t('influence_history_load_error')))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [clanId, seasonId, t]);

  const selectedClan = useMemo(
    () => data.clans?.find((clan) => String(clan.id) === String(clanId)),
    [clanId, data.clans],
  );
  const totalInfluence = (data.clans || []).reduce((sum, clan) => sum + clan.influence, 0);
  const territoryInfluence = (data.clans || []).reduce((sum, clan) => sum + clan.territory_influence, 0);
  const positiveEvents = (data.events || []).filter((event) => event.amount > 0).length;

  return (
    <StatisticsLayout
      title={t('influence_history_title')}
      subtitle={t('influence_history_subtitle')}
      icon={HistoryRounded}
      action={(
        <div className="campaign-filters">
          <label>
            <span>{t('influence_history_season')}</span>
            <select value={seasonId} onChange={(event) => setSeasonId(event.target.value)}>
              <option value="">{t('influence_history_all_time')}</option>
              {seasons.map((season) => (
                <option value={season.id} key={season.id}>{season.name}</option>
              ))}
            </select>
          </label>
          <label>
            <span>{t('influence_history_clan')}</span>
            <select value={clanId} onChange={(event) => setClanId(event.target.value)}>
              <option value="">{t('influence_history_all_clans')}</option>
              {(data.clans || []).map((clan) => (
                <option value={clan.id} key={clan.id}>{clan.name}</option>
              ))}
            </select>
          </label>
        </div>
      )}
    >
      <div className="statistics-summary-grid">
        <div className="statistics-summary-item">
          <AccountBalanceRounded />
          <div><strong className="statistics-summary-value">{formatNumber.format(selectedClan?.influence ?? totalInfluence)}</strong><span className="statistics-summary-label">{t('influence_history_current')}</span></div>
        </div>
        <div className="statistics-summary-item">
          <LandscapeRounded />
          <div><strong className="statistics-summary-value">{formatNumber.format(selectedClan?.territory_influence ?? territoryInfluence)}</strong><span className="statistics-summary-label">{t('influence_history_territories')}</span></div>
        </div>
        <div className="statistics-summary-item">
          <FlagRounded />
          <div><strong className="statistics-summary-value">{selectedClan ? 1 : data.clans?.length || 0}</strong><span className="statistics-summary-label">{t('influence_history_clans_summary')}</span></div>
        </div>
        <div className="statistics-summary-item">
          <TrendingUpRounded />
          <div><strong className="statistics-summary-value">{positiveEvents}</strong><span className="statistics-summary-label">{t('influence_history_positive')}</span></div>
        </div>
      </div>

      <div className="statistics-grid campaign-history-grid">
        <section className="statistics-panel">
          <div className="statistics-panel-header">
            <h2 className="statistics-panel-title"><FlagRounded />{t('influence_history_standings')}</h2>
            <span className="statistics-panel-meta">{t('influence_history_by_influence')}</span>
          </div>
          <div className="campaign-clan-ranking">
            {(data.clans || []).map((clan, index) => (
              <button
                className={`campaign-clan-row ${String(clan.id) === String(clanId) ? 'is-selected' : ''}`}
                type="button"
                onClick={() => setClanId(String(clan.id) === String(clanId) ? '' : String(clan.id))}
                key={clan.id}
              >
                <span className="campaign-rank">{index + 1}</span>
                <span className="campaign-clan-mark" style={{ '--clan-color': clan.map_color || '#777777' }}>
                  {clan.avatar_url ? <img src={clan.avatar_url} alt="" /> : clan.name.slice(0, 1)}
                </span>
                <span className="campaign-clan-name">{clan.name}</span>
                <strong>{formatNumber.format(clan.influence)}</strong>
              </button>
            ))}
          </div>
        </section>

        <section className="statistics-panel">
          <div className="statistics-panel-header">
            <h2 className="statistics-panel-title"><HistoryRounded />{t('influence_history_feed')}</h2>
            <span className="statistics-panel-meta">{t('influence_history_events', null, { count: data.events?.length || 0 })}</span>
          </div>
          {loading ? (
            <div className="statistics-state"><div><div className="statistics-loader" />{t('influence_history_loading')}</div></div>
          ) : error ? (
            <div className="statistics-state">{error}</div>
          ) : data.events?.length ? (
            <div className="influence-timeline">
              {data.events.map((event) => (
                <article className={`influence-event ${event.amount >= 0 ? 'is-positive' : 'is-negative'}`} key={event.id}>
                  <span className="influence-event__icon">
                    {event.amount >= 0 ? <TrendingUpRounded /> : <TrendingDownRounded />}
                  </span>
                  <div className="influence-event__body">
                    <div className="influence-event__heading">
                      <Link to={`/clans/${event.clan_id}`}>{event.clan_name}</Link>
                      <strong>{event.amount > 0 ? '+' : ''}{event.amount}</strong>
                    </div>
                    <span>
                      {t(`influence_action_${event.action}`, event.action_label || t('influence_action_default'))}
                      {event.territory_name ? `: ${getTerritoryName(event.territory_name, language)}` : ''}
                    </span>
                    <small>{event.balance_before} → {event.balance_after} · {formatDate(event.created_at, language)} {t('timezone_moscow_short')}</small>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="statistics-state">{t('influence_history_empty')}</div>
          )}
        </section>
      </div>
    </StatisticsLayout>
  );
};

export default InfluenceHistoryPage;
