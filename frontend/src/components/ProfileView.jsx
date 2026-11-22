import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Tab,
  Tabs,
  TextField,
} from '@mui/material';
import {
  AutoAwesome,
  ContentCopy,
  ChatBubbleOutline,
  GroupAddOutlined,
  MapOutlined,
  MilitaryTech,
  TaskAltOutlined,
  SettingsOutlined,
} from '@mui/icons-material';

import AvatarUpload from './AvatarUpload';
import DiscordLinkPanel from './profile/DiscordLinkPanel';
import ClanCreationDialog from './ClanCreationDialog';
import CosmeticItemPreview from './CosmeticItemPreview';
import PlayerIdentity, { PlayerTitles } from './PlayerIdentity';
import QuestsSection from './QuestsSection';
import SchedulerStatus from './SchedulerStatus';
import api from '../services/api';
import DirectMessageDialog from './DirectMessageDialog';
import AchievementIcon from './AchievementIcon';
import { getAchievementTitle } from '../utils/achievementPresentation';
import { getPlayerDisplayName } from '../utils/playerIdentity';
import { PageShell, SectionHeader, Surface } from './ui';
import PlayerPresence from './PlayerPresence';
import MatchDetailsDialog from './MatchDetailsDialog';
import { GAME_PATCHES, usePatch } from '../contexts/PatchContext';

const number = (value) => Number(value || 0);
const percent = (value) => `${Math.round(number(value))}%`;

const daysSince = (value) => {
  const timestamp = Date.parse(value || '');
  if (!Number.isFinite(timestamp)) return 0;
  return Math.max(0, Math.floor((Date.now() - timestamp) / 86400000));
};

const achievementProgress = (item) => {
  const target = Math.max(1, number(item?.achievement?.target_value || item?.achievement?.requirement_value || 1));
  return item?.is_completed ? 100 : Math.min(100, Math.round((number(item?.progress) / target) * 100));
};

const MatchTable = ({ matches, compact = false, onSelectMatch, t }) => (
  matches.length ? (
    <div className="table-wrap">
      <table className="table profile-match-table">
        <thead>
          <tr>
            {!compact && <th>{t('profile_match_date', 'Дата')}</th>}
            <th>{t('profile_match_opponent', 'Противник')}</th>
            <th>{t('common_territory', 'Территория')}</th>
            <th>{t('profile_match_result', 'Результат')}</th>
            {!compact && <th>{t('profile_match_mode', 'Режим')}</th>}
            <th>ELO · {t('ranking_patch', 'патч')}</th>
          </tr>
        </thead>
        <tbody>
          {matches.map((match) => (
            <tr
              key={match.match_id}
              className="match-clickable-row"
              role="button"
              tabIndex={0}
              onClick={(event) => {
                if (!event.target.closest('a, button')) onSelectMatch?.(match);
              }}
              onKeyDown={(event) => {
                if (event.target.closest('a, button')) return;
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onSelectMatch?.(match);
                }
              }}
            >
              {!compact && <td>{match.date || '—'}</td>}
              <td>
                <b>
                  <PlayerIdentity username={match.opponent} />
                </b>
                <small>{match.player_faction || '—'} · {match.opponent_faction || '—'}</small>
              </td>
              <td>{match.map || '—'}</td>
              <td><span className={`profile-result is-${match.result}`}>{match.result === 'win' ? t('profile_match_win', 'Победа') : t('profile_match_loss', 'Поражение')}</span></td>
              {!compact && <td>{match.game_mode || '—'}</td>}
              <td className={match.result === 'win' ? 'positive' : 'negative'}>
                {match.elo == null
                  ? '—'
                  : `${Math.round(Number(match.elo))} · ${GAME_PATCHES[match.rating_patch_family]?.label || '—'}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <div className="profile-panel-empty">
      <MilitaryTech aria-hidden="true" />
      <p>{t('profile_no_matches', 'У игрока пока нет матчей.')}</p>
    </div>
  )
);

const ProfileView = ({
  t,
  language,
  navigate,
  user,
  currentUser,
  profileData,
  profileIdentity,
  currentAvatarUrl,
  userClan,
  invites,
  activeTab,
  playerStats,
  userInventory,
  userAchievements,
  settingsData,
  streamStatus,
  expProgress,
  targetUsername,
  isOwnProfile,
  isAdmin,
  isImpersonating,
  inventoryLoading,
  verificationUpdating,
  impersonationStarting,
  updatingSettings,
  settingsOpen,
  clanCreationOpen,
  balanceOpen,
  balanceAmount,
  balanceUpdating,
  verificationAction,
  verificationReason,
  onAvatarUpdate,
  onRequestVerification,
  onReviewVerification,
  onSubmitVerification,
  onImpersonate,
  onTabChange,
  onInviteResponse,
  onEquipItem,
  onSaveSettings,
  onCopyProfileLink,
  onClanCreated,
  onUpdateBalance,
  getCategoryIcon,
  setSettingsData,
  setSettingsOpen,
  setClanCreationOpen,
  setBalanceOpen,
  setBalanceAmount,
  setVerificationAction,
  setVerificationReason,
}) => {
  const { selectedPatch, selectedPatchData } = usePatch();
  const [territoryContributions, setTerritoryContributions] = useState(null);
  const [territoryLoading, setTerritoryLoading] = useState(false);
  const [territoryError, setTerritoryError] = useState('');
  const [messageOpen, setMessageOpen] = useState(false);
  const [matchFilter, setMatchFilter] = useState('all');
  const [selectedMatch, setSelectedMatch] = useState(null);
  const eloRatings = playerStats?.current_elo || {};
  const recentMatches = playerStats?.recent_matches || [];
  const equippedItems = userInventory.filter((item) => item.is_equipped);
  const losses = playerStats?.losses ?? Math.max(0, (playerStats?.total_matches || 0) - (playerStats?.wins || 0));
  const filteredMatches = matchFilter === 'all'
    ? recentMatches
    : recentMatches.filter((match) => match.result === matchFilter);
  const history = useMemo(
    () => playerStats?.elo_history?.[selectedPatch] || [],
    [playerStats?.elo_history, selectedPatch],
  );
  const eloDelta = history.length > 1
    ? Math.round(number(history.at(-1)?.elo) - number(history[0]?.elo))
    : 0;
  const formWins = recentMatches.filter((match) => match.result === 'win').length;
  const formLosses = Math.max(0, recentMatches.length - formWins);
  const formLine = recentMatches.map((match) => (match.result === 'win' ? 'W' : 'L')).join(' ');
  const favouriteMap = useMemo(() => Object.entries(playerStats?.maps_played || {})
    .sort(([, left], [, right]) => number(right.total) - number(left.total))[0] || null, [playerStats?.maps_played]);
  const favouriteFaction = useMemo(() => Object.entries(playerStats?.factions_used || {})
    .sort(([, left], [, right]) => number(right.total) - number(left.total))[0] || null, [playerStats?.factions_used]);
  const factionStats = useMemo(() => Object.entries(playerStats?.factions_used || {})
    .sort(([, left], [, right]) => number(right.total) - number(left.total)).slice(0, 4), [playerStats?.factions_used]);
  const achievementItems = (userAchievements || []).slice(0, 8);
  const completedAchievements = (userAchievements || []).filter((item) => item.is_completed).length;
  const accountAge = daysSince(user.created_at);
  const clanRole = useMemo(() => {
    if (!userClan) return '';
    if (Number(userClan.leader_id) === Number(user.id)) {
      return t('profile_clan_leader', 'Глава');
    }
    if (userClan.is_warlord) return t('clan_warlord', 'Воевода');
    if (userClan.is_trader || userClan.member_rank === 'Торговец') {
      return t('clan_role_trader', 'Торговец');
    }
    if (userClan.member_rank === 'Воин') return t('clan_role_warrior', 'Воин');
    if (userClan.member_rank === 'Салага' || userClan.member_rank === 'Новичок') {
      return t('clan_role_recruit', 'Салага');
    }
    return userClan.member_rank || t('profile_clan_member', 'Участник');
  }, [t, user.id, userClan]);
  const chartPoints = useMemo(() => {
    const values = history.map((item) => number(item.elo)).filter(Number.isFinite);
    if (values.length < 2) return '0,150 600,150';
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = Math.max(1, max - min);
    return values.map((value, index) => {
      const x = (index / (values.length - 1)) * 600;
      const y = 155 - ((value - min) / range) * 130;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }, [history]);
  const tabs = [
    ['overview', t('profile_overview_tab', 'Обзор')],
    ['matches', t('profile_matches_tab', 'Матчи')],
    ['statistics', t('profile_tab_statistics', 'Статистика')],
    ['achievements', t('profile_tab_achievements', 'Достижения')],
    ['relics', t('profile_relics_tab', 'Реликвии')],
    ['territories', t('profile_territories_tab', 'Территории')],
    ...(isOwnProfile ? [
      ['invitations', t('profile_invites_title', 'Приглашения'), <GroupAddOutlined key="invitations" />],
      ['quests', t('profile_tab_quests', 'Задания'), <TaskAltOutlined key="quests" />],
    ] : []),
  ];

  useEffect(() => {
    if (activeTab !== 'territories' || !targetUsername) return undefined;

    let active = true;
    setTerritoryLoading(true);
    setTerritoryError('');
    api.get(`/users/${encodeURIComponent(targetUsername)}/territory-contributions`)
      .then((response) => {
        if (active) setTerritoryContributions(response.data);
      })
      .catch((requestError) => {
        if (active) {
          setTerritoryContributions(null);
          setTerritoryError(requestError.response?.data?.detail || t('profile_territory_load_error', 'Не удалось загрузить вклад по территориям.'));
        }
      })
      .finally(() => {
        if (active) setTerritoryLoading(false);
      });

    return () => { active = false; };
  }, [activeTab, targetUsername, t]);

  return (
    <PageShell className={`profile-page prototype-exact-page container-fluid ${isOwnProfile ? 'own-profile' : 'public-profile'}`}>
      <Surface className="profile-header-card profile-hero">
        <div className="profile-hero__avatar-column">
          <div className="avatar-container">
            <img
              id="userAvatar"
              src={currentAvatarUrl || user.avatar_url || '/icons/profilewb.png'}
              alt={t('profile_avatar_alt', 'Аватар игрока')}
              className="user-avatar-img"
            />
          </div>
          {isOwnProfile && (
            <div className="avatar-upload-action">
              <AvatarUpload onAvatarUpdate={onAvatarUpdate} currentAvatarUrl={currentAvatarUrl || user.avatar_url} />
            </div>
          )}
        </div>

        <div className="profile-hero__copy">
          <div className="profile-hero__eyebrow profile-hero__presence">
            <PlayerPresence
              userId={user.id}
              isClaimed={user.is_claimed !== false}
              language={language}
              t={t}
            />
          </div>
          <h1 className="profile-username" id="profileUsername">
            <PlayerIdentity username={profileData.username} linkToProfile={false} showTitles={false} />
          </h1>
          {userClan && (
            <button className="profile-clan-line" type="button" onClick={() => navigate(`/clans/${userClan.id}`)}>
              {userClan.name} · {clanRole}
            </button>
          )}
          <div className="profile-hero__badges">
            <span>{t('profile_level_label', 'Уровень')} {user.level || 1}</span>
            <span>#{user.world_rank || '—'} {t('profile_world_rank', 'мира')}</span>
            <span>{String(user.language || 'ru').toUpperCase()} / EU</span>
            <span>{t('profile_days_on_site', 'На сайте {days} дней', { days: accountAge })}</span>
            {user.external_identity_status === 'verified' && <span className="is-verified">{t('profile_identity_verified', 'Игровой аккаунт подтверждён')}</span>}
            {user.external_identity_status === 'pending' && <span className="is-pending">{t('profile_identity_pending', 'Привязка ожидает подтверждения')}</span>}
          </div>
          <div className="profile-hero__titles"><PlayerTitles titles={profileIdentity.titles || []} large /></div>

          {user.role?.name === 'contentmaker' && (
            <div className="profile-socials">
              {user.telegram_url && <a href={user.telegram_url} target="_blank" rel="noreferrer">Telegram</a>}
              {user.twitch_url && <a href={user.twitch_url} target="_blank" rel="noreferrer">Twitch {streamStatus.twitch && <b>LIVE</b>}</a>}
              {user.youtube_url && <a href={user.youtube_url} target="_blank" rel="noreferrer">YouTube {streamStatus.youtube && <b>LIVE</b>}</a>}
            </div>
          )}

          {user.external_identity_status === 'unverified' && user.is_claimed && isOwnProfile && (
            <Button size="small" variant="outlined" disabled={verificationUpdating} onClick={onRequestVerification}>
              {t('profile_identity_submit', 'Отправить игровой аккаунт на проверку')}
            </Button>
          )}
          {user.external_identity_status === 'pending' && isAdmin && (!isOwnProfile || isImpersonating) && (
            <div className="profile-hero__review-actions">
              <Button size="small" color="success" variant="contained" onClick={() => onReviewVerification('approve')}>{t('profile_identity_approve', 'Подтвердить')}</Button>
              <Button size="small" color="error" variant="outlined" onClick={() => onReviewVerification('reject')}>{t('profile_identity_reject', 'Отклонить')}</Button>
            </div>
          )}
          {!isOwnProfile && user.is_claimed === false && (
            <Alert severity="info" className="profile-unclaimed-alert">
              <strong>{t('profile_unclaimed_title', 'Игровой профиль ещё не привязан')}</strong>
              <span>{t('profile_unclaimed_description', 'Матчи и прогресс уже сохраняются. Владелец ника сможет забрать профиль при регистрации.')}</span>
              {!currentUser && <Button size="small" onClick={() => navigate('/login')}>{t('profile_claim_this', 'Привязать профиль')}</Button>}
            </Alert>
          )}
        </div>

        <div className="profile-hero__actions">
          {!isOwnProfile && user.is_claimed !== false && <Button variant="outlined" startIcon={<ChatBubbleOutline />} onClick={() => setMessageOpen(true)}>{t('profile_message', 'Сообщение')}</Button>}
          <Button variant="outlined" startIcon={<ContentCopy />} onClick={onCopyProfileLink}>{t('profile_copy_link_short', 'Ссылка')}</Button>
          {isOwnProfile && <Button variant="contained" startIcon={<SettingsOutlined />} onClick={() => setSettingsOpen(true)}>{t('profile_open_settings', 'Настройки')}</Button>}
          {isAdmin && !isOwnProfile && <Button color="warning" variant="outlined" disabled={impersonationStarting} onClick={onImpersonate}>{t('profile_impersonation_open', 'Войти для проверки')}</Button>}
        </div>
      </Surface>

      <Surface className="profile-xp" data-section="profile-xp">
        <div className="profile-xp__heading">
          <span>{t('profile_level_label', 'Уровень')} {user.level || 1}</span>
          <strong>{expProgress.current} / {expProgress.max} XP</strong>
        </div>
        <div className="profile-xp__track"><span style={{ width: `${expProgress.percentage}%` }} /></div>
        <small>{t('profile_xp_remaining', 'До {level} уровня: {xp} XP · откроется дополнительный слот реликвии', {
          level: (user.level || 1) + 1,
          xp: Math.max(0, number(expProgress.max) - number(expProgress.current)).toLocaleString(),
        })}</small>
      </Surface>

      <Surface className="profile-content">
        <Tabs value={activeTab} onChange={(_, value) => onTabChange(value)} variant="scrollable" scrollButtons="auto" aria-label={t('profile_navigation', 'Разделы профиля')}>
          {tabs.map(([value, label, icon]) => <Tab key={value} value={value} label={label} icon={icon} iconPosition="start" />)}
        </Tabs>

        <div className="profile-content__panel" role="tabpanel">
          {activeTab === 'overview' && (
            <div className="profile-overview-exact">
              <section className="profile-kpis profile-kpis--split-elo grid g4" aria-label={t('profile_tab_statistics', 'Статистика')}>
                <div className={`card kpi${selectedPatch === 'ennorath' ? ' is-active-patch' : ''}`}><strong>{eloRatings.ennorath == null ? '—' : Math.round(number(eloRatings.ennorath)).toLocaleString()}</strong><small>ELO · Ennorath</small>{selectedPatch === 'ennorath' && eloDelta !== 0 && <span className={eloDelta > 0 ? 'delta' : 'negative'}>{eloDelta > 0 ? '▲ ' : '▼ '}{Math.abs(eloDelta)}</span>}</div>
                <div className={`card kpi${selectedPatch === 'patch_202' ? ' is-active-patch' : ''}`}><strong>{eloRatings.patch_202 == null ? '—' : Math.round(number(eloRatings.patch_202)).toLocaleString()}</strong><small>ELO · Patch 2.02</small>{selectedPatch === 'patch_202' && eloDelta !== 0 && <span className={eloDelta > 0 ? 'delta' : 'negative'}>{eloDelta > 0 ? '▲ ' : '▼ '}{Math.abs(eloDelta)}</span>}</div>
                <div className="card kpi"><strong>{playerStats?.wins || 0}</strong><small>{t('profile_wins', 'Побед')}</small></div>
                <div className="card kpi"><strong>{losses}</strong><small>{t('profile_losses', 'Поражения')}</small></div>
                <div className="card kpi"><strong>{percent(playerStats?.win_rate)}</strong><small>{t('profile_winrate')}</small></div>
              </section>

              <section className="section grid g2">
                <div className="card panel profile-form-card">
                  <div className="section-head">
                    <div><div className="eyebrow">{t('profile_recent_form', 'Форма')}</div><h2>{t('profile_last_ten', 'Последние 10 матчей')}</h2></div>
                    <span className="streak">{formLine || '—'}</span>
                  </div>
                  <div className="form-score"><b>{formWins}–{formLosses}</b><span className={eloDelta >= 0 ? 'positive' : 'negative'}>{eloDelta >= 0 ? '+' : ''}{eloDelta} ELO · {selectedPatchData.label}</span></div>
                  <div className="progress"><i style={{ width: `${recentMatches.length ? (formWins / recentMatches.length) * 100 : 0}%` }} /></div>
                </div>

                <div className="card panel profile-clan-summary">
                  {userClan ? (
                    <>
                      <div className="section-head"><div><div className="eyebrow">{t('profile_clan_label', 'Клан')}</div><h2>{userClan.name}</h2></div><button className="text-btn" type="button" onClick={() => navigate(`/clans/${userClan.id}`)}>{t('profile_clan_view_button', 'Профиль клана')} →</button></div>
                      <div className="member-line"><b>{t('profile_clan_role', 'Роль')}</b><span>{clanRole}</span></div>
                      <div className="member-line"><b>{t('profile_clan_days', 'В клане')}</b><span>{daysSince(userClan.joined_at || userClan.created_at)} {t('common_days', 'дней')}</span></div>
                      <div className="member-line"><b>{t('profile_clan_contribution', 'Вклад')}</b><span>{number(userClan.territory_points || userClan.base_influence).toLocaleString()} {t('profile_territory_influence', 'влияния')}</span></div>
                      <div className="member-line"><b>{t('profile_clan_rating', 'Клановый рейтинг')}</b><span>#{userClan.rank || '—'}</span></div>
                    </>
                  ) : (
                    <>
                      <div className="eyebrow">{t('profile_clan_label', 'Клан')}</div>
                      <h2>{t('profile_without_clan', 'Без клана')}</h2>
                      <p className="muted">{t('profile_without_clan_hint', 'Вступите в клан, чтобы участвовать в войнах за территории.')}</p>
                      {isOwnProfile && <Button variant="contained" onClick={() => setClanCreationOpen(true)}>{t('profile_create_clan_here', 'Создать клан')}</Button>}
                    </>
                  )}
                </div>
              </section>

              <section className="section grid g2">
                <div className="card panel">
                  <div className="section-head"><h2>{t('profile_recent_matches', 'Последние матчи')}</h2><button className="text-btn" type="button" onClick={() => onTabChange('matches')}>{t('common_all', 'Все')} →</button></div>
                  <MatchTable matches={recentMatches.slice(0, 4)} compact onSelectMatch={setSelectedMatch} t={t} />
                </div>
                <div className="card panel">
                  <div className="section-head"><h2>{t('profile_active_relics', 'Активные реликвии')}</h2><button className="text-btn" type="button" onClick={() => onTabChange('relics')}>{t('common_all', 'Все')} →</button></div>
                  <div className="relic-strip">
                    {Array.from({ length: 4 }, (_, index) => {
                      const userItem = equippedItems[index];
                      if (userItem) return <div key={userItem.id}><CosmeticItemPreview item={userItem.item} getFallbackIcon={getCategoryIcon} /><span>{userItem.item?.name || t('profile_relic', 'Реликвия')}</span></div>;
                      return <div className="empty-relic" key={`empty-${index}`}><b>{index === 3 && number(user.level) < 25 ? 25 : '◇'}</b><span>{index === 3 && number(user.level) < 25 ? t('profile_level_short', 'уровень') : t('profile_empty_slot', 'пустой слот')}</span></div>;
                    })}
                  </div>
                </div>
              </section>

              <section className="section grid g3 profile-facts">
                <div className="card panel"><div className="eyebrow">{t('profile_favourite_territory', 'Любимая территория')}</div><h3>{favouriteMap?.[0] || '—'}</h3><p className="muted">{favouriteMap ? `${favouriteMap[1].wins} ${t('profile_wins_lower', 'побед')} · ${percent(favouriteMap[1].win_rate)} ${t('profile_winrate').toLocaleLowerCase(language)}` : t('profile_no_matches', 'Матчей пока нет')}</p></div>
                <div className="card panel"><div className="eyebrow">{t('profile_favourite_faction', 'Любимая фракция')}</div><h3>{favouriteFaction?.[0] || '—'}</h3><p className="muted">{favouriteFaction ? `${favouriteFaction[1].total} ${t('profile_total_matches_lower', 'матчей')} · ${percent(favouriteFaction[1].win_rate)} ${t('profile_wins_lower', 'побед')}` : t('profile_no_matches', 'Матчей пока нет')}</p></div>
                <div className="card panel"><div className="eyebrow">{t('profile_streak', 'Серия')}</div><h3>{formWins} {t('profile_wins_lower', 'побед')}</h3><p className="muted">{t('profile_recent_sample', 'По последним доступным матчам')}</p></div>
              </section>

            </div>
          )}

          {activeTab === 'matches' && (
            <section>
              <div className="section-head profile-tab-heading"><div><div className="eyebrow">{t('profile_match_history', 'История')}</div><h2>{t('profile_matches_tab', 'Матчи')}</h2></div><div className="filters">{[['all', t('common_all', 'Все')], ['win', t('profile_wins', 'Победы')], ['loss', t('profile_losses', 'Поражения')]].map(([value, label]) => <button key={value} className={`filter ${matchFilter === value ? 'active' : ''}`} type="button" onClick={() => setMatchFilter(value)}>{label}</button>)}</div></div>
              <div className="card panel"><MatchTable matches={filteredMatches} onSelectMatch={setSelectedMatch} t={t} /></div>
              <div className="section grid g3"><div className="card kpi"><strong>{playerStats?.total_matches || 0}</strong><small>{t('profile_total_matches', 'всего матчей')}</small></div><div className="card kpi"><strong>{playerStats?.wins || 0}</strong><small>{t('profile_wins', 'побед')}</small></div><div className="card kpi"><strong>{eloDelta >= 0 ? '+' : ''}{eloDelta}</strong><small>{t('profile_season_elo', 'ELO за период')} · {selectedPatchData.label}</small></div></div>
            </section>
          )}

          {activeTab === 'statistics' && (
            <section className="profile-statistics-exact">
              <div className="grid g4"><div className="card kpi"><strong>{percent(playerStats?.win_rate)}</strong><small>{t('profile_winrate')}</small></div><div className="card kpi"><strong>{losses ? (number(playerStats?.wins) / losses).toFixed(1) : number(playerStats?.wins).toFixed(1)}</strong><small>W/L</small></div><div className="card kpi"><strong>{favouriteMap ? percent(favouriteMap[1].win_rate) : '0%'}</strong><small>{t('profile_best_map', 'лучшая карта')}</small></div><div className="card kpi"><strong>{favouriteFaction ? percent(favouriteFaction[1].win_rate) : '0%'}</strong><small>{t('profile_best_faction', 'лучшая фракция')}</small></div></div>
              <div className="section grid g2">
                <div className="card panel"><h2>{t('profile_winrate_factions', 'Winrate по фракциям')}</h2><div className="rank-race">{factionStats.map(([name, stats]) => <div key={name}><b>{name}</b><span>{percent(stats.win_rate)}</span><i style={{ width: `${Math.min(100, number(stats.win_rate))}%` }} /></div>)}{!factionStats.length && <p className="muted">{t('profile_no_statistics', 'Статистика пока не собрана.')}</p>}</div></div>
                <div className="card panel"><h2>{t('profile_factions_in_matches', 'Фракции в матчах')}</h2><div className="donut-wrap"><div className="donut" style={{ '--profile-win-angle': `${Math.min(100, number(playerStats?.win_rate)) * 3.6}deg` }}><b>{playerStats?.total_matches || 0}</b><span>{t('profile_matches_lower', 'матчей')}</span></div><div className="legend wide">{factionStats.slice(0, 3).map(([name, stats]) => <div key={name}><span>{name}</span><b>{stats.total} · {playerStats?.total_matches ? percent((stats.total / playerStats.total_matches) * 100) : '0%'}</b></div>)}</div></div></div>
              </div>
              <div className="section card panel"><h2>{t('profile_rating_dynamics', 'Динамика рейтинга')} · {selectedPatchData.label}</h2><div className="linechart tall"><svg viewBox="0 0 600 180" preserveAspectRatio="none"><polyline points={chartPoints} /></svg></div></div>
            </section>
          )}

          {activeTab === 'achievements' && (
            <section>
              <div className="section-head profile-tab-heading"><div><div className="eyebrow">{completedAchievements} {t('common_of', 'из')} {(userAchievements || []).length}</div><h2>{t('profile_tab_achievements', 'Достижения')}</h2></div>{isOwnProfile && <Button onClick={() => navigate('/achievements')}>{t('profile_full_collection', 'Полная коллекция')}</Button>}</div>
              {userAchievements ? <div className="grid g4 profile-achievement-grid">{achievementItems.map((item) => { const achievement = item.achievement || {}; const progress = achievementProgress(item); return <article className={`card achievement ${achievement.is_available === false ? 'locked' : ''}`} key={item.id}><AchievementIcon achievement={achievement} /><h3>{getAchievementTitle(achievement, t) || t('profile_achievement', 'Достижение')}</h3><p>{achievement.description || '—'}</p><div className="progress"><i style={{ width: `${progress}%` }} /></div><small>{progress}%</small></article>; })}{!achievementItems.length && <div className="profile-panel-empty"><AutoAwesome /><p>{t('achievements_empty', 'Достижения пока не рассчитаны')}</p></div>}</div> : <div className="profile-panel-loading"><div className="spinner-border" role="status" /></div>}
            </section>
          )}

          {activeTab === 'relics' && (
            <section aria-busy={inventoryLoading}>
              <div className="section-head profile-tab-heading"><div><div className="eyebrow">{userInventory.length} {t('common_of', 'из')} 42</div><h2>{t('profile_inventory_title', 'Коллекция реликвий')}</h2></div><Button onClick={() => navigate('/shop')}>{t('profile_inventory_go_to_catalog', 'Открыть каталог')}</Button></div>
              <div className="loadout compact-loadout profile-loadout">{Array.from({ length: 4 }, (_, index) => { const userItem = equippedItems[index]; const labels = [t('profile_relic_weapon', 'Оружие'), t('profile_relic_talisman', 'Талисман'), t('profile_relic_banner', 'Знамя'), t('profile_relic_special', 'Особая')]; if (userItem) return <div className="card equip-slot filled" key={userItem.id}><span>{labels[index]}</span><CosmeticItemPreview item={userItem.item} getFallbackIcon={getCategoryIcon} /><b>{userItem.item?.name}</b><small>{userItem.item?.description || t('profile_inventory_equipped', 'Экипировано')}</small>{isOwnProfile && <button className="text-btn" type="button" onClick={() => onEquipItem(userItem.id, false)}>{t('profile_inventory_unequip', 'Снять')}</button>}</div>; return <div className="card equip-slot empty" key={`slot-${index}`}><span>{labels[index]}</span><b>{index === 3 && number(user.level) < 25 ? t('profile_locked', 'Заблокировано') : t('profile_empty_slot', 'Пустой слот')}</b><small>{index === 3 && number(user.level) < 25 ? t('profile_level_required', 'Нужен 25 уровень') : t('profile_choose_relic', 'Выберите реликвию ниже')}</small></div>; })}</div>
              {userInventory.length ? <div className="profile-relic-grid inventory-grid">{userInventory.map((userItem) => (
                <article key={userItem.id} className={`inventory-item profile-relic ${userItem.is_equipped ? 'equipped' : ''}`}>
                  {userItem.is_equipped && <span className="equipped-badge">{t('profile_inventory_equipped', 'Экипировано')}</span>}
                  <div className="item-image"><CosmeticItemPreview item={userItem.item} getFallbackIcon={getCategoryIcon} /></div>
                  <h3 className="item-name">{userItem.item?.name}</h3>
                  <p className="item-description">{userItem.item?.description || t('profile_no_description', 'Описание отсутствует')}</p>
                  {isOwnProfile && <Button variant={userItem.is_equipped ? 'outlined' : 'contained'} onClick={() => onEquipItem(userItem.id, !userItem.is_equipped)}>{userItem.is_equipped ? t('profile_inventory_unequip', 'Снять') : t('profile_inventory_equip', 'Экипировать')}</Button>}
                </article>
              ))}</div> : <div className="profile-panel-empty"><AutoAwesome /><h3>{t('profile_inventory_empty_title', 'Коллекция пуста')}</h3><p>{t('profile_inventory_empty_description', 'У вас пока нет купленных предметов')}</p><Button variant="contained" onClick={() => navigate('/shop')}>{t('profile_inventory_go_to_shop', 'Перейти в магазин')}</Button></div>}
            </section>
          )}
          {activeTab === 'territories' && (
            <section className="profile-territories">
              <SectionHeader eyebrow={t('profile_territory_contribution', 'Личный вклад')} title={t('profile_territories_tab', 'Территории')} action={<Button variant="outlined" startIcon={<MapOutlined />} onClick={() => navigate('/map')}>{t('profile_open_map', 'Открыть карту')}</Button>} />
              {territoryContributions?.season_name && <p className="profile-season-caption">{territoryContributions.season_name}</p>}
              {territoryLoading && <div className="profile-panel-loading" role="status"><div className="spinner-border" /></div>}
              {territoryError && <Alert severity="error">{territoryError}</Alert>}
              {!territoryLoading && !territoryError && territoryContributions && (
                <>
                  <div className="grid g4 profile-territory-kpis">
                    <div className="card kpi"><strong>{territoryContributions.summary.matches}</strong><small>{t('profile_territory_matches', 'боёв')}</small></div>
                    <div className="card kpi"><strong>{territoryContributions.summary.wins}</strong><small>{t('profile_wins', 'побед')}</small></div>
                    <div className="card kpi"><strong>{territoryContributions.summary.territories_helped}</strong><small>{t('profile_territory_lands', 'земель')}</small></div>
                    <div className="card kpi"><strong>{number(territoryContributions.summary.score).toLocaleString()}</strong><small>{t('profile_territory_influence', 'влияния')}</small></div>
                  </div>
                  <div className="section card panel table-wrap">
                    <table className="table">
                      <thead><tr><th>{t('common_territory', 'Территория')}</th><th>{t('profile_total_matches', 'Матчи')}</th><th>{t('profile_wins', 'Победы')}</th><th>{t('profile_winrate', 'Винрейт')}</th><th>{t('profile_territory_contribution', 'Вклад')}</th></tr></thead>
                      <tbody>
                        {territoryContributions.territories.map((territory) => (
                          <tr key={territory.territory_id}>
                            <td>{territory.territory_name}</td>
                            <td>{territory.matches}</td>
                            <td>{territory.wins}</td>
                            <td>{territory.matches ? Math.round((territory.wins / territory.matches) * 100) : 0}%</td>
                            <td>+{Number(territory.score).toLocaleString()}</td>
                          </tr>
                        ))}
                        {!territoryContributions.territories.length && <tr><td colSpan="5">{t('profile_territory_empty', 'В текущем сезоне вклад ещё не зафиксирован.')}</td></tr>}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </section>
          )}
          {isOwnProfile && activeTab === 'invitations' && (
            <section className="profile-private-tab">
              <SectionHeader title={t('profile_invites_title', 'Приглашения в кланы')} />
              <div className="card panel profile-invites">
                {invites.length ? invites.map((invite) => (
                  <article key={invite.id}>
                    <div>
                      <strong>{invite.clan_name || t('profile_unknown_clan', 'Неизвестный клан')}</strong>
                      <span>{getPlayerDisplayName(invite.inviter_username, '—')}</span>
                    </div>
                    <div>
                      <Button size="small" onClick={() => onInviteResponse(invite.id, 'accepted')}>{t('profile_invites_accept', 'Принять')}</Button>
                      <Button size="small" color="error" onClick={() => onInviteResponse(invite.id, 'declined')}>{t('profile_invites_decline', 'Отклонить')}</Button>
                    </div>
                  </article>
                )) : (
                  <div className="profile-panel-empty">
                    <GroupAddOutlined />
                    <p>{t('profile_invites_no_invites_description', 'У вас пока нет приглашений в кланы')}</p>
                  </div>
                )}
              </div>
            </section>
          )}
          {isOwnProfile && activeTab === 'quests' && (
            <section className="profile-private-tab profile-quests">
              <SectionHeader title={t('profile_quests_heading', 'Путь героя')} />
              <QuestsSection />
            </section>
          )}
        </div>
      </Surface>

      {isAdmin && (
        <details className="profile-system-details">
          <summary>{t('profile_system_status', 'Состояние игровых данных')}</summary>
          <SchedulerStatus />
        </details>
      )}

      <MatchDetailsDialog
        open={Boolean(selectedMatch)}
        matchRef={selectedMatch?.match_id || selectedMatch?.id}
        initialMatch={selectedMatch}
        onClose={() => setSelectedMatch(null)}
      />

      <Dialog className="profile-settings-dialog" open={settingsOpen} onClose={() => !updatingSettings && setSettingsOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{t('profile_settings_title', 'Настройки профиля')}</DialogTitle>
        <DialogContent className="profile-dialog-fields">
          {settingsOpen && isOwnProfile && !isImpersonating && <DiscordLinkPanel t={t} />}
          <TextField select fullWidth label={t('profile_settings_language_label', 'Язык интерфейса')} value={settingsData.language} onChange={(event) => setSettingsData({ ...settingsData, language: event.target.value })}>
            <MenuItem value="ru">{t('language_russian', 'Русский')}</MenuItem><MenuItem value="en">{t('language_english', 'Английский')}</MenuItem><MenuItem value="de">{t('language_german', 'Немецкий')}</MenuItem>
          </TextField>
          <FormControlLabel control={<Checkbox checked={settingsData.allow_clan_invites} onChange={(event) => setSettingsData({ ...settingsData, allow_clan_invites: event.target.checked })} />} label={t('profile_settings_allow_clan_invites_label', 'Разрешить приглашения в клан')} />
          {user.role?.name === 'contentmaker' && <><TextField fullWidth label="Telegram URL" value={settingsData.telegram_url} onChange={(event) => setSettingsData({ ...settingsData, telegram_url: event.target.value })} /><TextField fullWidth label="Twitch URL" value={settingsData.twitch_url} onChange={(event) => setSettingsData({ ...settingsData, twitch_url: event.target.value })} /><TextField fullWidth label="YouTube URL" value={settingsData.youtube_url} onChange={(event) => setSettingsData({ ...settingsData, youtube_url: event.target.value })} /></>}
          {isAdmin && <Button variant="outlined" onClick={() => setBalanceOpen(true)}>{t('profile_balance_admin_action', 'Изменить баланс')}</Button>}
        </DialogContent>
        <DialogActions><Button onClick={() => setSettingsOpen(false)} disabled={updatingSettings}>{t('clans_cancel_button', 'Отмена')}</Button><Button variant="contained" onClick={onSaveSettings} disabled={updatingSettings}>{updatingSettings ? t('profile_settings_updating', 'Сохранение...') : t('profile_settings_save_button', 'Сохранить')}</Button></DialogActions>
      </Dialog>

      <Dialog className="profile-balance-dialog" open={balanceOpen} onClose={() => !balanceUpdating && setBalanceOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{t('profile_balance_dialog_title', 'Корректировка баланса')}</DialogTitle>
        <DialogContent className="profile-dialog-fields"><TextField autoFocus type="number" fullWidth label={t('profile_balance_amount', 'Сумма изменения (+/−)')} value={balanceAmount} onChange={(event) => setBalanceAmount(event.target.value)} inputProps={{ min: -1000000, max: 1000000 }} helperText={t('profile_balance_amount_hint', 'Положительное число пополнит баланс, отрицательное — спишет.')} /></DialogContent>
        <DialogActions><Button onClick={() => setBalanceOpen(false)}>{t('clans_cancel_button', 'Отмена')}</Button><Button variant="contained" disabled={balanceUpdating || balanceAmount === '' || Number(balanceAmount) === 0 || Math.abs(Number(balanceAmount)) > 1000000 || Number(profileData.balance || 0) + Number(balanceAmount) < 0} onClick={() => onUpdateBalance(Number(balanceAmount))}>{t('profile_balance_apply', 'Применить')}</Button></DialogActions>
      </Dialog>

      <Dialog className="profile-verification-dialog" open={Boolean(verificationAction)} onClose={() => !verificationUpdating && setVerificationAction(null)} fullWidth maxWidth="xs">
        <DialogTitle>{verificationAction === 'approve' ? t('profile_verification_approve_reason', 'Подтверждение аккаунта') : t('profile_verification_reject_reason', 'Отклонение заявки')}</DialogTitle>
        <DialogContent className="profile-dialog-fields"><TextField autoFocus multiline minRows={3} fullWidth label={t('profile_verification_reason', 'Основание решения')} value={verificationReason} onChange={(event) => setVerificationReason(event.target.value)} error={verificationReason.length > 0 && verificationReason.trim().length < 3} /></DialogContent>
        <DialogActions><Button onClick={() => setVerificationAction(null)}>{t('clans_cancel_button', 'Отмена')}</Button><Button color={verificationAction === 'approve' ? 'success' : 'error'} variant="contained" disabled={verificationUpdating || verificationReason.trim().length < 3} onClick={onSubmitVerification}>{t('profile_verification_submit_decision', 'Подтвердить решение')}</Button></DialogActions>
      </Dialog>

      <ClanCreationDialog open={clanCreationOpen} onClose={() => setClanCreationOpen(false)} onCreated={onClanCreated} />
      <DirectMessageDialog
        open={messageOpen}
        onClose={() => setMessageOpen(false)}
        username={getPlayerDisplayName(user)}
        currentUser={currentUser}
        t={t}
      />
    </PageShell>
  );
};

export default ProfileView;
