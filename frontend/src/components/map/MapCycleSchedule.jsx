import React from 'react';
import { ArrowForward, EventOutlined } from '@mui/icons-material';
import { Link } from 'react-router-dom';
import { useLocalizationContext } from '../../contexts/LocalizationContext';
import { formatMoscowDateTime } from '../../utils/dateTime';
import './MapCycleSchedule.css';

export default function MapCycleSchedule({ navigation }) {
  const { t, language } = useLocalizationContext();
  const cycle = navigation?.cycle;
  if (!cycle || !Number.isSafeInteger(cycle.number) || cycle.number < 1) return null;
  const phase = {
    scheduled: 'map_schedule_scheduled',
    registration: 'map_schedule_registration',
    preparation: 'map_schedule_preparation',
    battle: 'map_schedule_active',
    replay_loading: 'map_schedule_replays',
    settlement: 'map_schedule_settlement',
    rest: 'map_schedule_rest',
    complete: 'map_schedule_complete',
    season_ended: 'map_schedule_season_ended',
  }[cycle.phase];
  if (!phase) return null;

  const betweenCycles = ['rest', 'complete'].includes(cycle.phase);
  const waitingForResults = ['settlement', 'replay_loading'].includes(cycle.phase);
  const hasNext = !cycle.season_end_requested && cycle.phase !== 'season_ended';
  const next = { label: t('map_schedule_next', null, { number: cycle.number + 1 }),
    value: cycle.next_cycle_starts_at, note: t('map_schedule_next_pending'), featured: true };
  const dates = betweenCycles ? [
    { label: t('map_schedule_rest_started'), value: cycle.settled_at }, ...(hasNext ? [next] : []),
  ] : waitingForResults ? [
    { label: t('map_schedule_battle_end'), value: cycle.battle_ends_at }, ...(hasNext ? [next] : []),
  ] : cycle.phase === 'season_ended' ? [
    { label: t('map_schedule_settlement'), value: cycle.settled_at },
  ] : [
    { label: t('map_schedule_preparation'), value: cycle.preparation_at, featured: cycle.phase === 'preparation' },
    { label: t('map_schedule_battle_start'), value: cycle.battle_at, featured: cycle.phase === 'battle' },
    { label: t('map_schedule_battle_end'), value: cycle.battle_ends_at },
  ];
  const visible = dates.filter(item => Number.isFinite(Date.parse(item.value)) || item.note);
  return <section className="map-cycle-schedule" aria-label={t('map_schedule_title')}>
    <div className="map-cycle-schedule__state">
      <EventOutlined aria-hidden="true" />
      <div>
        <strong>{t('map_schedule_number', null, { number: cycle.number })}</strong>
        <span>{t(phase)}</span>
      </div>
    </div>
    {visible.length > 0 && <dl className="map-cycle-schedule__dates">
      {visible.map(item => <div key={item.label} className={item.featured ? 'map-cycle-schedule__featured' : undefined}>
        <dt>{item.label}</dt>
        <dd>{Number.isFinite(Date.parse(item.value)) ? (
          <time dateTime={item.value}>{formatMoscowDateTime(item.value, '', language)}</time>
        ) : item.note}</dd>
      </div>)}
    </dl>}
    <Link className="map-cycle-schedule__link" to={navigation.href}>
      {t('map_schedule_battles_link')}<ArrowForward aria-hidden="true" />
    </Link>
  </section>;
}
