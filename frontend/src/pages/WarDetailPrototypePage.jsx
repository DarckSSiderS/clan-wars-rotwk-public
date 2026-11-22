import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { PageShell } from '../components/ui';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { clanService } from '../services/clanService';
import { territoryService } from '../services/territoryService';
import { warService } from '../services/warService';
import { getTerritoryName } from '../i18n/territories';
import { formatMoscowDateTime } from '../utils/dateTime';
import MatchDetailsDialog from '../components/MatchDetailsDialog';
import WarMatchReview from '../components/WarMatchReview';
import PlayerIdentity from '../components/PlayerIdentity';
import { getPlayerDisplayName } from '../utils/playerIdentity';
import './WarDetailPrototypePage.css';

const formatPoints = (value) => Number(value || 0).toFixed(2).replace(/\.?0+$/, '');
const initial = (value) => String(value || '?').trim().slice(0, 1).toUpperCase();
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const patchLabel = (value, t) => ({
  patch_202: 'Patch 2.02',
  ennorath: 'Ennorath',
  all: t('wars_both_patches', 'Оба патча'),
}[value] || t('wars_both_patches', 'Оба патча'));
const ELO_PATCHES = [
  { id: 'ennorath', label: 'Ennorath' },
  { id: 'patch_202', label: 'Patch 2.02' },
];
const normalizeEloPatch = (value) => ({
  ennorath: 'ennorath',
  patch_202: 'patch_202',
  '2.02': 'patch_202',
  patch202: 'patch_202',
}[String(value || '').toLowerCase()] || null);
const territoryStatusLabel = (value, fallbackActive, t) => ({
  contested: t('common_contested', 'Оспаривается'),
  active: t('map_status_active', 'Активна'),
  neutral: t('map_status_neutral', 'Нейтральная'),
}[value] || (fallbackActive ? t('common_contested', 'Оспаривается') : t('common_resolved', 'Завершено')));

const formatRemaining = (endsAt, now, t) => {
  if (!endsAt) return t('war_no_deadline', 'Без ограничения по времени');
  const seconds = Math.max(0, Math.floor((new Date(endsAt).getTime() - now) / 1000));
  if (!seconds) return t('war_window_closed', 'Окно битвы завершено');
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor(seconds % 86400 / 3600);
  const minutes = Math.floor(seconds % 3600 / 60);
  const rest = seconds % 60;
  const clock = [hours, minutes, rest].map((part) => String(part).padStart(2, '0')).join(':');
  return days ? `${t('war_days_short', null, { count: days })} ${clock}` : clock;
};

const scoreFor = (war, clanId) => (war.clan_scores || []).find((score) => score.clan_id === clanId) || {
  clan_id: clanId,
  wins: 0,
  losses: 0,
  matches: 0,
  points: 0,
  power_bonus_points: 0,
  relic_bonus_points: 0,
};

const bonusLabel = (asset, t) => {
  const labels = {
    territory_points_percent: t('clan_relic_bonus_territory', 'Очки территории'),
    war_win_points: t('clan_relic_bonus_war', 'Очки за победу'),
    attack_power: t('clan_relic_bonus_attack', 'Атака'),
    defense_power: t('clan_relic_bonus_defense', 'Защита'),
    gold_income_percent: t('clan_relic_bonus_gold', 'Доход золота'),
    resource_income_flat: t('clan_relic_bonus_resources', 'Доход ресурсов'),
  };
  return `${labels[asset?.bonus_type] || asset?.bonus_type || t('common_bonus', 'Бонус')} +${asset?.bonus_value || 0}${asset?.bonus_type?.includes('percent') || asset?.bonus_type?.includes('power') ? '%' : ''}`;
};

const Lineup = ({ clanId, clanName, group, rounds, t }) => {
  const members = group?.members || [];
  const eloByName = useMemo(() => {
    const values = new Map();
    rounds.forEach((round) => (round.participants || []).forEach((participant) => {
      const patch = normalizeEloPatch(round.patch_family || round.rating_patch_family);
      if (participant.elo == null || participant.elo_is_verified === false || !patch) return;
      const username = String(participant.username).toLowerCase();
      values.set(username, { ...values.get(username), [patch]: participant.elo });
    }));
    return values;
  }, [rounds]);
  const averageEloByPatch = Object.fromEntries(ELO_PATCHES.map(({ id }) => {
    const values = members
      .map((member) => eloByName.get(String(member.username).toLowerCase())?.[id])
      .filter((value) => value != null)
      .map(Number);
    return [id, values.length ? Math.round(values.reduce((sum, value) => sum + value, 0) / values.length) : null];
  }));

  return (
    <article className="card panel battle-lineup">
      <div className="section-head">
        <div><div className="eyebrow">{t('battle_lineup_clan', 'Состав {clan}', { clan: clanName })}</div><h2>{t('battle_lineup_title', 'Участники войны')}</h2></div>
        <div className="lineup-elo-summary" aria-label={t('battle_average_elo_by_patch')}>
          {ELO_PATCHES.map(({ id, label }) => <span key={id}><small>Elo · {label}</small><b>{averageEloByPatch[id] ?? '—'}</b></span>)}
        </div>
      </div>
      {members.length ? members.slice(0, 12).map((member, index) => {
        const ratings = eloByName.get(String(member.username).toLowerCase()) || {};
        return (
          <div className={`lineup-player${index === 0 ? ' captain' : ''}`} key={`${clanId}-${member.user_id}`}>
            <span className="player-no">{index + 1}</span>
            <div>
              <b><PlayerIdentity username={member.display_nickname || member.snapshot_nickname || member.username} /></b>
              <small>{index === 0 ? t('common_captain', 'Капитан') : t('common_player', 'Игрок')}</small>
              <span className="lineup-player__elo">
                {ELO_PATCHES.map(({ id, label }) => <span key={id}>Elo · {label} <b>{ratings[id] ?? '—'}</b></span>)}
              </span>
            </div>
            <strong>{member.wins || 0}–{member.losses || 0}</strong>
            <em>{Number(member.points || 0) >= 0 ? '+' : ''}{formatPoints(member.points)}</em>
          </div>
        );
      }) : (
        <div className="battle-inline-empty">{t('battle_lineup_empty', 'Состав ещё не подтверждён')}</div>
      )}
    </article>
  );
};

const RelicList = ({ clanName, assets, t }) => {
  const owned = (assets || []).filter((entry) => entry.owned || Number(entry.level || 0) > 0).slice(0, 3);
  return (
    <div>
      <h3>{clanName}</h3>
      <div className="battle-relic-list">
        {owned.length ? owned.map((entry, index) => (
          <div key={entry.asset?.id || index}>
            <img src={`/design-prototype/relic_${(Number(entry.asset?.id || index) % 12) + 1}.webp`} alt="" />
            <span><b>{entry.asset?.name || t('common_relic', 'Реликвия')}</b><small>{bonusLabel(entry.asset, t)}</small></span>
            <em>{t('map_status_active', 'Активна').toLocaleUpperCase()} · {entry.level || 1}</em>
          </div>
        )) : <div className="battle-relic-empty"><span><b>{t('battle_relics_empty', 'Нет активных реликвий')}</b><small>{t('battle_relics_empty_copy', 'Счёт рассчитывается без клановых модификаторов.')}</small></span></div>}
      </div>
    </div>
  );
};

const WarDetailPrototypePage = () => {
  const { warId } = useParams();
  const { getLocalizedText: t, language } = useLocalizationContext();
  const [war, setWar] = useState(null);
  const [territory, setTerritory] = useState(null);
  const [attackerAssets, setAttackerAssets] = useState([]);
  const [defenderAssets, setDefenderAssets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [now, setNow] = useState(Date.now());
  const [selectedMatch, setSelectedMatch] = useState(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError('');
    warService.getWar(warId).then(async (loadedWar) => {
      if (!alive) return;
      setWar(loadedWar);
      const [loadedTerritory, loadedAttackerAssets, loadedDefenderAssets] = await Promise.all([
        territoryService.getTerritoryById(loadedWar.territory_id),
        clanService.getClanAssets(loadedWar.attacking_clan_id).catch(() => []),
        loadedWar.defending_clan_id ? clanService.getClanAssets(loadedWar.defending_clan_id).catch(() => []) : Promise.resolve([]),
      ]);
      if (!alive) return;
      setTerritory(loadedTerritory);
      setAttackerAssets(loadedAttackerAssets || []);
      setDefenderAssets(loadedDefenderAssets || []);
    }).catch((loadError) => {
      if (alive) setError(loadError.response?.data?.detail || t('wars_load_error', 'Не удалось загрузить войну'));
    }).finally(() => {
      if (alive) setLoading(false);
    });
    return () => { alive = false; };
  }, [t, warId]);

  useEffect(() => {
    if (war?.status !== 'active') return undefined;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [war?.status]);

  const rounds = useMemo(() => [...(war?.match_breakdown || [])].sort((left, right) => new Date(left.played_at) - new Date(right.played_at)), [war]);
  const attackerScore = war ? scoreFor(war, war.attacking_clan_id) : scoreFor({}, null);
  const defenderScore = war ? scoreFor(war, war.defending_clan_id) : scoreFor({}, null);
  const totalPoints = Number(attackerScore.points || 0) + Number(defenderScore.points || 0);
  const attackerShare = totalPoints ? Math.max(0, Math.min(100, Math.round(Number(attackerScore.points || 0) / totalPoints * 100))) : 50;
  const defenderShare = 100 - attackerShare;
  const scoreDifference = Number(attackerScore.points || 0) - Number(defenderScore.points || 0);
  const scoreLeader = scoreDifference === 0
    ? { name: null, score: null }
    : scoreDifference > 0
      ? { name: war?.attacking_clan_name, score: attackerScore }
      : { name: war?.defending_clan_name, score: defenderScore };
  const allMembers = (war?.side_groups || []).flatMap((group) => group.members || []);
  const mvp = [...allMembers].sort((left, right) => Number(right.points || 0) - Number(left.points || 0))[0];
  const attackerGroup = (war?.side_groups || []).find((group) => group.clan_id === war?.attacking_clan_id);
  const defenderGroup = (war?.side_groups || []).find((group) => group.clan_id === war?.defending_clan_id);
  const participantCount = (attackerGroup?.member_count || attackerGroup?.members?.length || 0) + (defenderGroup?.member_count || defenderGroup?.members?.length || 0);
  const territoryName = war ? getTerritoryName(war.territory_name, language) : '';

  if (loading) return <PageShell className="prototype-exact-page war-detail-prototype"><div className="prototype-state" role="status">{t('common_loading', 'Загрузка...')}</div></PageShell>;
  if (error || !war) return <PageShell className="prototype-exact-page war-detail-prototype"><div className="prototype-state is-error" role="alert">{error || t('war_not_found', 'Война не найдена')}</div></PageShell>;

  const defenderName = war.defending_clan_name || t('wars_neutral_land', 'Нейтральная земля');
  const statusLive = war.status === 'active';
  const awaitingReplays = statusLive && war.ends_at && new Date(war.ends_at).getTime() <= now;
  const statusLabel = awaitingReplays ? t('battle_finalizing') : statusLive ? t('battle_in_progress') : t('wars_completed');
  const winnerName = war.winner_clan_name || scoreLeader.name;
  const highlightedClanId = war.winner_clan_id
    || (scoreDifference < 0 && war.defending_clan_id ? war.defending_clan_id : war.attacking_clan_id);
  const highlightedClanName = winnerName
    || (Number(highlightedClanId) === Number(war.defending_clan_id) ? defenderName : war.attacking_clan_name);

  return (
    <PageShell className="prototype-exact-page war-detail-prototype">
      <nav className="battle-breadcrumb" aria-label={t('common_breadcrumbs', 'Навигация')}>
        <Link to="/battles">← {t('homepage_all_battles', 'Все битвы')}</Link><span>/</span><span>{war.attacking_clan_name} vs {defenderName}</span><span className={`status ${statusLive ? 'live' : 'completed'}`}>{statusLabel}</span>
      </nav>

      <section className="card battle-detail-hero" data-section="battle-summary">
        <div className="battle-detail-top">
          <div><div className="eyebrow">{t('battle_for_territory', 'Битва за {territory}', { territory: territoryName })}</div><h1>{t('battle_full_summary', 'Полная сводка битвы')}</h1></div>
          <div className={`battle-watch${statusLive ? '' : ' is-complete'}`}><span className="live-pulse" /><div><b>{statusLabel}</b><small>{awaitingReplays ? t('battle_waiting_replays') : statusLive ? `${formatRemaining(war.ends_at, now, t)} ${t('battle_until_close', 'до завершения окна')}` : formatMoscowDateTime(war.ended_at || war.ends_at, '', language)}</small></div></div>
        </div>
        <div className="detail-vs">
          <div className="detail-side attacker">
            <span className="crest-big" style={{ background: war.attacking_clan_map_color || '#526346' }}>
              {war.attacking_clan_avatar_url ? <img src={war.attacking_clan_avatar_url} alt="" /> : initial(war.attacking_clan_name)}
            </span>
            <div><small>{t('war_attacking_clan', 'Атакующий клан')}</small><h2><Link to={`/clans/${war.attacking_clan_id}`}>{war.attacking_clan_name}</Link></h2><p>{patchLabel(war.attacker_patch, t)}</p></div>
            <strong>{formatPoints(attackerScore.points)}</strong>
          </div>
          <div className="detail-center">
            <div className="vsmark">VS</div>
            <div className="detail-score-caption">{t('war_score_title', 'Общий счёт войны')}</div>
            <div className="battle-progress big" role="img" aria-label={`${attackerShare}% — ${defenderShare}%`}>
              <span className="battle-progress__attacker" style={{ width: `${attackerShare}%`, background: war.attacking_clan_map_color || '#526346' }} />
              <span className="battle-progress__defender" style={{ width: `${defenderShare}%`, background: war.defending_clan_map_color || '#727773' }} />
            </div>
            <small>{attackerShare}% · {scoreLeader.name || t('war_tied', 'Равный счёт')}</small>
          </div>
          <div className="detail-side defender">
            <strong>{formatPoints(defenderScore.points)}</strong>
            <div><small>{t('war_defending_clan', 'Защищающийся клан')}</small><h2>{war.defending_clan_id ? <Link to={`/clans/${war.defending_clan_id}`}>{defenderName}</Link> : defenderName}</h2><p>{war.defending_clan_id ? patchLabel(war.defender_patch, t) : t('wars_neutral_capture', 'Захват нейтральной территории')}</p></div>
            <span className="crest-big silver" style={{ background: war.defending_clan_map_color || '#727773' }}>
              {war.defending_clan_avatar_url ? <img src={war.defending_clan_avatar_url} alt="" /> : initial(defenderName)}
            </span>
          </div>
        </div>
        <div className="battle-summary-grid">
          <div><span>{t('common_territory', 'Территория')}</span><b>{territoryName}</b></div>
          <div><span>{t('battle_format', 'Формат')}</span><b>{war.scoring_version?.includes('squad') ? t('battle_format_squads', 'Отряды') : t('battle_format_elo', 'Рейтинг ELO')} · {war.attack_route === 'sea' ? t('wars_sea_attack', 'Море') : t('wars_land_attack', 'Суша')}</b></div>
          <div><span>{t('battle_reward', 'Награда')}</span><b>{war.influence_cost || territory?.influence_value || 0} {t('common_influence', 'влияния')}</b></div>
          <div><span>{t('battle_land_status', 'Статус земли')}</span><b>{territoryStatusLabel(territory?.status, statusLive, t)}</b></div>
          <div><span>{t('battle_matches_played', 'Матчей сыграно')}</span><b>{war.tracked_matches || 0} / {war.required_wins || '—'}</b></div>
          <div><span>{t('battle_participants', 'Участники')}</span><b>{participantCount || '—'}</b></div>
        </div>
      </section>

      <section className="section grid g2" data-section="battle-lineups">
        <Lineup clanId={war.attacking_clan_id} clanName={war.attacking_clan_name} group={attackerGroup} rounds={rounds} t={t} />
        <Lineup clanId={war.defending_clan_id} clanName={defenderName} group={defenderGroup} rounds={rounds} t={t} />
      </section>

      <section className="section card panel" data-section="battle-rounds">
        <div className="section-head"><div><div className="eyebrow">{t('war_matches_title', 'Матчи войны')}</div><h2>{t('battle_rounds_title', 'Раунды и результаты')}</h2></div><span className="muted">{war.tracked_matches || 0} {t('battle_matches_counted', 'матчей засчитано')}</span></div>
        <div className="round-list">
          {rounds.length ? rounds.map((round, index) => (
            <div
              className={`round-row match-clickable-card ${round.is_counted ? 'done' : 'rejected'}`}
              key={round.id}
              role="button"
              tabIndex={0}
              onClick={(event) => {
                if (!event.target.closest('a, button')) setSelectedMatch(round);
              }}
              onKeyDown={(event) => {
                if (event.target.closest('a, button')) return;
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  setSelectedMatch(round);
                }
              }}
            >
              <span className="round-id">{index + 1}</span>
              <div className="round-players"><b><PlayerIdentity username={round.winner.username} /></b><span>vs</span><b><PlayerIdentity username={round.loser.username} /></b></div>
              <div className="round-map">{round.map_name || territoryName} · {round.game_mode || '1v1'}</div>
              <strong>1 : 0</strong>
              <span className="round-points">+{formatPoints(round.winner.total_points)} : +{formatPoints(round.loser.total_points)}</span>
              <span className={`status ${round.is_counted ? 'completed' : 'rejected'}`}>{round.is_counted ? (round.winner.clan_name || getPlayerDisplayName(round.winner)) : t('battle_rejected', 'Отклонён')}</span>
            </div>
          )) : <div className="battle-inline-empty">{t('war_no_matches', 'Матчи пока не обнаружены.')}</div>}
        </div>
      </section>

      <section className="section grid g3 battle-insight-grid">
        <div className="card panel battle-insight"><div className="eyebrow">{t('battle_pace', 'Темп')}</div><strong>{Number(attackerScore.points || 0) - Number(defenderScore.points || 0) >= 0 ? '+' : ''}{formatPoints(Number(attackerScore.points || 0) - Number(defenderScore.points || 0))}</strong><h3>{scoreLeader.name || t('war_tied', 'Равный счёт')}</h3><p>{t('battle_advantage_copy', 'Текущий перевес по общему счёту войны: {share}%.', { share: Math.max(attackerShare, 100 - attackerShare) })}</p></div>
        <div className="card panel battle-insight"><div className="eyebrow">MVP</div><strong>{initial(getPlayerDisplayName({ username: mvp?.username, display_name: mvp?.display_nickname }))}</strong><h3>{getPlayerDisplayName({ username: mvp?.username, display_name: mvp?.display_nickname }, '—')}</h3><p>{mvp ? `${mvp.wins || 0} ${t('profile_wins', 'побед')} · +${formatPoints(mvp.points)} ${t('common_points', 'очков')}` : t('battle_mvp_waiting', 'Определится после первых матчей.')}</p></div>
        <div className="card panel battle-insight"><div className="eyebrow">{t('battle_key_factor', 'Ключевой фактор')}</div><strong>{Math.max(war.attacker_power || 0, war.defender_power || 0)}%</strong><h3>{war.attacker_power >= war.defender_power ? t('wars_attack', 'Бонус атаки') : t('wars_defense', 'Бонус защиты')}</h3><p>{t('battle_power_copy', 'Клановые модификаторы уже включены в итоговые очки.')}</p></div>
      </section>

      <section className="section grid g2">
        <article className="card panel" data-section="battle-timeline"><div className="section-head"><div><div className="eyebrow">{t('chronicle_title', 'Хронология')}</div><h2>{t('battle_event_feed', 'Лента событий')}</h2></div></div><div className="battle-timeline">{[...rounds].reverse().slice(0, 5).map((round, index) => <div key={round.id}><time>{new Intl.DateTimeFormat(language, { hour: '2-digit', minute: '2-digit' }).format(new Date(round.played_at))}</time><span className={`dot ${index % 3 === 0 ? 'green' : index % 3 === 1 ? 'gold' : 'red'}`} /><p><b>{getPlayerDisplayName(round.winner.username)} {t('war_defeated', 'победил')} {getPlayerDisplayName(round.loser.username)}</b><small>{round.map_name || territoryName} · +{formatPoints(round.winner.total_points)}</small></p></div>)}<div><time>{war.started_at ? new Intl.DateTimeFormat(language, { hour: '2-digit', minute: '2-digit' }).format(new Date(war.started_at)) : '00:00'}</time><span className="dot" /><p><b>{t('battle_started', 'Битва началась')}</b><small>{formatMoscowDateTime(war.started_at, '', language)}</small></p></div></div></article>
        <article className="card panel" data-section="battle-territory-result"><div className="section-head"><div><div className="eyebrow">{t('battle_stake', 'Ставка войны')}</div><h2>{territoryName}</h2></div><Link className="btn" to={`/map?territory=${war.territory_id}`}>{t('battle_show_map', 'Показать на карте')}</Link></div><div className="territory-result"><div className="territory-symbol">{initial(territoryName)}</div><div><span>{t('battle_current_owner', 'Текущий владелец')}</span><b>{territory?.owner_clan_name || defenderName}</b><small>{territory?.region || t('common_unknown_region', 'Регион не указан')} · +{territory?.daily_income || 0} / {t('common_day', 'день')}</small></div></div><div className="territory-rule"><span>{t('battle_if_attacker_wins', 'Если победит атакующий клан')}</span><b>{war.attacking_clan_name}: +{war.influence_cost || territory?.influence_value || 0} {t('common_influence', 'влияния')}</b></div><div className="territory-rule danger"><span>{t('battle_if_defender_wins', 'Если победит защищающийся клан')}</span><b>{war.defending_clan_id ? t('battle_territory_remains', 'Территория остаётся под контролем защитника') : t('battle_capture_stops', 'Захват территории будет остановлен')}</b></div><div className="defense-meter"><div><span>{t('battle_territory_defense', 'Защита территории')}</span><b>{territory?.stronghold_power || territory?.fortifications || 0}</b></div><div className="progress xl"><i style={{ width: `${clamp(Number(territory?.fortifications || 0) * 10, 3, 100)}%` }} /></div></div></article>
      </section>

      <section className="section card panel" data-section="battle-relics"><div className="section-head"><div><div className="eyebrow">{t('battle_modifiers', 'Модификаторы войны')}</div><h2>{t('battle_clan_relics', 'Клановые реликвии')}</h2></div><Link className="muted" to={`/clans/${war.attacking_clan_id}`}>{t('battle_open_vault', 'Открыть хранилище')} →</Link></div><div className="battle-relic-columns"><RelicList clanName={war.attacking_clan_name} assets={attackerAssets} t={t} /><RelicList clanName={defenderName} assets={defenderAssets} t={t} /></div></section>

      <MatchDetailsDialog
        open={Boolean(selectedMatch)}
        matchRef={selectedMatch?.match_id || selectedMatch?.id}
        initialMatch={selectedMatch}
        onClose={() => setSelectedMatch(null)}
      >
        {selectedMatch && <WarMatchReview key={`${war.id}:${selectedMatch.id}`} war={war} result={selectedMatch} onReviewed={(updatedWar) => {
          setWar(updatedWar);
          setSelectedMatch(updatedWar.match_breakdown?.find((match) => match.id === selectedMatch.id) || null);
        }} />}
      </MatchDetailsDialog>

      <footer className="section battle-detail-footer"><Link className="btn" to="/battles">← {t('battle_back_to_list', 'Вернуться к списку битв')}</Link><Link className="btn primary" to={`/clans/${highlightedClanId}`}>{t('battle_open_clan', 'Открыть клан')} {highlightedClanName}</Link></footer>
    </PageShell>
  );
};

export default WarDetailPrototypePage;
