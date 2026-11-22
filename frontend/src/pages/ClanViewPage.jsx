import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import PlayerIdentity from '../components/PlayerIdentity';
import RulesContextLink from '../components/RulesContextLink';
import {
  Container,
  Paper,
  Typography,
  Box,
  Avatar,
  Button,
  Grid,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemAvatar,
  ListItemSecondaryAction,
  ListItemText,
  Chip,
  Divider,
  CircularProgress,
  Alert,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Tabs,
  Tab,
  FormControl,
  FormControlLabel,
  InputLabel,
  Select,
  MenuItem,
  Tooltip,
  LinearProgress,
  Switch,
} from '@mui/material';
import {
  Group,
  Edit,
  Delete,
  PersonAdd,
  ExitToApp,
  MoreVert,
  Check,
  Close,
  EmojiEvents,
  TrendingUp,
  Timeline,
  WorkspacePremium,
  Gavel,
  OutlinedFlag,
  Shield,
  Storefront,
  Park,
  Navigation,
  Visibility,
  Construction,
  Spa,
  Whatshot,
  Campaign,
  VpnKey,
  WaterDrop,
  AutoAwesome,
  History,
  SwapHoriz,
  HourglassTop,
  AccessTime,
  Route,
  Payments,
  ArrowForward,
  DirectionsBoat,
  Add,
  Settings,
} from '@mui/icons-material';
import { clanService } from '../services/clanService';
import { warService } from '../services/warService';
import { cycleCampaignService } from '../services/cycleCampaignService';
import { clanCycleBattle, currentClanBattles, clanHistoryMessage } from '../utils/clanCycleHistory';
import { userService } from '../services/userService';
import { territoryService } from '../services/territoryService';
import { useAuth } from '../contexts/AuthContext';
import { showSuccess, showError, confirmAction } from '../utils/notifications';
import ClanAvatarUpload from '../components/ClanAvatarUpload';
import { useLocalization } from '../hooks/useLocalization';
import useCampaignNavigation from '../hooks/useCampaignNavigation';
import usePreseasonStatus from '../hooks/usePreseasonStatus';
import { cycleMessage } from '../utils/cycleBattleView';
import { getTerritoryName } from '../i18n/territories';
import { formatMoscowDateTime } from '../utils/dateTime';
import { getMemberEloRatings } from '../utils/memberElo';
import { orderClanMembers } from '../utils/clanMemberOrder';
import { loadClanMemberStats } from '../utils/clanMemberStats';
import { getPlayerDisplayName } from '../utils/playerIdentity';
import { presenceService } from '../services/presenceService';
import { PresenceBadge } from '../components/PlayerPresence';
import { getRelicArtwork } from '../content/clanRelics';
import { getSeasonAward, getTerritoryAwards } from '../content/clanAwards';
import ClanColorPicker from '../components/ClanColorPicker';
import {
  CLAN_RESOURCES,
  CLAN_RESOURCE_BY_KEY,
} from '../components/clan/clanResources';
import ClanResourceSummary from '../components/clan/ClanResourceSummary';
import { EconomyContent } from './CycleEconomyPage';
import { economyMessage } from '../utils/cycleEconomyView';
import './ClanViewPage.css';

const CaravanGlyph = ({ className = '' }) => (
  <span className={`caravan-glyph ${className}`} aria-hidden="true">🐪</span>
);

const MARKET_ROUTE_LABEL_KEYS = {
  land: 'market_route_land',
  sea: 'market_route_sea',
  mixed: 'market_route_mixed',
};

const CLAN_TAB_VALUES = {
  overview: 0, members: 1, territories: 2, market: 3, relics: 4,
  battles: 5, history: 6, development: 'lands', barter: 'barter',
};

const formatRemainingTime = (targetDate, t, now = Date.now()) => {
  if (!targetDate) return t('market_time_unknown');
  const seconds = Math.max(0, Math.floor((new Date(targetDate).getTime() - now) / 1000));
  if (seconds === 0) return t('market_delivery_finishing');
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days} ${t('time_day_short')} ${hours} ${t('time_hour_short')}`;
  if (hours > 0) return `${hours} ${t('time_hour_short')} ${minutes} ${t('time_minute_short')}`;
  return `${Math.max(1, minutes)} ${t('time_minute_short')}`;
};

const formatRelicEffect = (asset, level, t) => {
  const value = (asset.bonus_value || 0) * level;
  const effects = {
    territory_points_percent: t('clan_relic_effect_influence', '+{value}% к постоянному влиянию от земель', { value }),
    war_win_points: t('clan_relic_effect_war_points', '+{value} очк. к каждой победе в войне', { value }),
    attack_power: t('clan_relic_effect_attack', '+{value}% к коэффициенту атаки', { value }),
    defense_power: t('clan_relic_effect_defense', '+{value}% к коэффициенту защиты', { value }),
    population_cost_percent: t('clan_relic_effect_population_cost', '-{value}% к золотой цене развития населения', { value }),
    gold_income_percent: t('clan_relic_effect_gold_income', '+{value}% к ежедневному доходу золота', { value }),
    fortification_cost_percent: t('clan_relic_effect_fortification_cost', '-{value}% к золотой цене укреплений', { value }),
    population_growth_percent: t('clan_relic_effect_population_growth', '+{value}% к приросту населения за улучшение', { value: value / 10 }),
    resource_income_flat: t('clan_relic_effect_resource_income', '+{value} ресурса с каждой земли в сутки', { value }),
  };
  return effects[asset.bonus_type] || t('clan_relic_effect_unknown', '{value} ({type})', {
    value,
    type: asset.bonus_type,
  });
};

const RELIC_ICONS = {
  royal_charter: WorkspacePremium,
  war_foundry: Gavel,
  mithril_standard: OutlinedFlag,
  granite_bastion: Shield,
  merchant_guild: Storefront,
  white_tree: Park,
  red_arrow: Navigation,
  iron_crown: WorkspacePremium,
  palantir: Visibility,
  dwarf_anvil: Construction,
  ents_seed: Spa,
  mordor_forge: Whatshot,
  helms_horn: Campaign,
  ring_of_barahir: VpnKey,
  galadhrim_mirror: WaterDrop,
};

const EMPTY_RELIC_FORM = {
  key: '',
  name: '',
  description: '',
  bonus_type: 'attack_power',
  bonus_value: 1,
  gold_cost: 0,
  iron_cost: 0,
  wood_cost: 0,
  food_cost: 0,
  mithril_cost: 0,
  required_influence_level_1: 175,
  required_influence_level_2: 525,
  required_influence_level_3: 1050,
  is_available: true,
};

function CycleHistoryRows({ battles, clanId, language, t, loading }) {
  return <tbody>{battles.map(battle => {
    const row = clanCycleBattle(battle, clanId);
    return <tr key={row.id}>
      <td>{row.opponents.map(side => side.clan_name || `${cycleMessage('common_clan', language)} #${side.clan_id}`).join(' · ') || t('homepage_neutral_side')}</td>
      <td><Link to={row.href}>{getTerritoryName(row.territory_name, language)}</Link><small className="clan-cycle-history-meta">{cycleMessage('cycle_number', language)} {row.cycle_number ?? row.cycle_id}</small></td>
      <td>{row.ownScore} : {row.opponents.map(side => side.score).join(' / ') || '—'}</td>
      <td className={row.result === 'win' ? 'positive' : row.result === 'loss' ? 'negative' : 'muted'}>{clanHistoryMessage(row.result, language)}</td>
    </tr>;
  })}{!battles.length && <tr><td colSpan="4" className="muted">{loading ? cycleMessage('common_loading', language) : t('clan_no_wars')}</td></tr>}</tbody>;
}

function LegacyWarArchive({ clanId, language, t }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({ data: null, error: false });
  useEffect(() => {
    if (!open || state.data) return undefined;
    let active = true;
    warService.getClanWars(clanId).then(data => { if (active) setState({ data, error: false }); })
      .catch(() => { if (active) setState({ data: null, error: true }); });
    return () => { active = false; };
  }, [clanId, open, state.data]);
  return <details className="clan-legacy-archive" onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>{clanHistoryMessage('archive', language)}</summary>
    {open && (state.error ? <p role="alert">{clanHistoryMessage('unavailable', language)}</p>
      : !state.data ? <p role="status">{cycleMessage('common_loading', language)}</p>
        : state.data.length ? <ul>{state.data.map(war => <li key={war.id}><Link to={`/battles/${war.id}`}>{getTerritoryName(war.territory_name, language)}</Link><time>{formatMoscowDateTime(war.ended_at || war.started_at, '—', language)}</time></li>)}</ul>
          : <p>{t('clan_no_wars')}</p>)}
  </details>;
}

const ClanViewPage = () => {
  const { clanId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { getTextSync, language } = useLocalization('clan');
  const campaign = useCampaignNavigation();
  const preseason = usePreseasonStatus();
  const legacyEconomy = preseason.resolved && !preseason.open && !campaign.loading && campaign.navigation?.mode === 'legacy';
  const cycleHistoryMode = !campaign.loading && campaign.navigation?.mode === 'cycle_v1';
  const cycleId = !campaign.loading && campaign.navigation?.mode === 'cycle_v1' ? campaign.navigation.cycleId : null;
  const locale = language === 'de' ? 'de-DE' : language === 'en' ? 'en-US' : 'ru-RU';
  const resourceLabel = (key) => getTextSync(
    CLAN_RESOURCE_BY_KEY[key]?.labelKey || 'resource_secondary',
  );
  const routeLabel = (mode) => getTextSync(MARKET_ROUTE_LABEL_KEYS[mode] || 'market_route_land');
  
  const [clan, setClan] = useState(null);
  const [members, setMembers] = useState([]);
  const sortedMembers = useMemo(() => orderClanMembers(members, clan?.leader_id), [members, clan?.leader_id]);
  const memberStatsRequest = useRef(0);
  useEffect(() => () => { memberStatsRequest.current++; }, [clanId]);
  const [applications, setApplications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [editData, setEditData] = useState({});
  const [inviteDialogOpen, setInviteDialogOpen] = useState(false);
  const [inviteUsername, setInviteUsername] = useState('');
  const [, setInviting] = useState(false);
  const [membersStats, setMembersStats] = useState({});
  const [clanAssets, setClanAssets] = useState([]);
  const [relicSelection, setRelicSelection] = useState([]);
  const [relicLoadoutSaving, setRelicLoadoutSaving] = useState(false);
  const [adminAssets, setAdminAssets] = useState([]);
  const [relicEditorOpen, setRelicEditorOpen] = useState(false);
  const [editingRelicId, setEditingRelicId] = useState(null);
  const [relicForm, setRelicForm] = useState(EMPTY_RELIC_FORM);
  const [relicSaving, setRelicSaving] = useState(false);
  const [clanEconomy, setClanEconomy] = useState(null);
  const [clanWars, setClanWars] = useState([]);
  const [cycleHistoryState, setCycleHistoryState] = useState({ clanId: null, data: null, error: false });
  const cycleHistory = cycleHistoryMode && cycleHistoryState.clanId === clanId ? cycleHistoryState.data : null;
  const currentCycleBattles = currentClanBattles(cycleHistory);
  useEffect(() => {
    if (!cycleHistoryMode || !clanId) return undefined;
    const controller = new AbortController();
    setCycleHistoryState({ clanId, data: null, error: false });
    cycleCampaignService.getClanHistory(clanId, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setCycleHistoryState({ clanId, data, error: false });
    }).catch(() => {
      if (!controller.signal.aborted) setCycleHistoryState({ clanId, data: null, error: true });
    });
    return () => controller.abort();
  }, [clanId, cycleHistoryMode]);
  const [ownedTerritories, setOwnedTerritories] = useState([]);
  const [searchParams, setSearchParams] = useSearchParams();
  const tabKey = searchParams.get('tab');
  const clanSectionTab = Object.hasOwn(CLAN_TAB_VALUES, tabKey)
    ? CLAN_TAB_VALUES[tabKey] : (window.location.hash === '#relics' ? 4 : 0);
  const setClanSectionTab = value => {
    const key = Object.keys(CLAN_TAB_VALUES).find(key => CLAN_TAB_VALUES[key] === value)
      || (['market', 'relics'].includes(value) ? value : 'overview');
    setSearchParams(previous => {
      const next = new URLSearchParams(previous);
      next.set('tab', key);
      return next;
    }, { preventScrollReset: true });
  };
  const [memberFilter, setMemberFilter] = useState('all');
  const [warFilter, setWarFilter] = useState('all');
  const [tradeForm, setTradeForm] = useState({
    give_resource: 'wood',
    give_amount: 1,
    receive_resource: 'iron',
    receive_amount: 1,
    expires_in_days: 7,
  });
  const [trading, setTrading] = useState(false);
  const [marketData, setMarketData] = useState({
    offers: [],
    clan_activity: [],
    caravans: [],
  });
  const [marketClock, setMarketClock] = useState(Date.now());
  const [applicationsDialogOpen, setApplicationsDialogOpen] = useState(false);
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [userClan, setUserClan] = useState(null);
  const [applicationDialogOpen, setApplicationDialogOpen] = useState(false);
  const [applicationMessage, setApplicationMessage] = useState('');
  const [submittingApplication, setSubmittingApplication] = useState(false);
  const memberIdsKey = useMemo(
    () => members.map((member) => Number(member.user_id)).filter(Boolean).sort((a, b) => a - b).join(','),
    [members],
  );

  useEffect(() => {
    if (!memberIdsKey) return undefined;
    let active = true;
    const refreshPresence = async () => {
      try {
        const statuses = await presenceService.getMany(memberIdsKey.split(',').map(Number));
        if (!active) return;
        const byUser = new Map(statuses.map((status) => [Number(status.user_id), status]));
        setMembers((current) => current.map((member) => ({
          ...member,
          ...(byUser.get(Number(member.user_id)) || {}),
        })));
      } catch {
        // Existing member data remains usable if presence polling is unavailable.
      }
    };
    refreshPresence();
    const interval = window.setInterval(refreshPresence, 30_000);
    window.addEventListener('focus', refreshPresence);
    return () => {
      active = false;
      window.clearInterval(interval);
      window.removeEventListener('focus', refreshPresence);
    };
  }, [memberIdsKey]);

  useEffect(() => {
    if (!marketData.caravans.length) return undefined;
    const timer = window.setInterval(() => setMarketClock(Date.now()), 30000);
    return () => window.clearInterval(timer);
  }, [marketData.caravans.length]);

  useEffect(() => {
    if (!legacyEconomy || clanSectionTab !== 3 || !clanId) return undefined;
    const refreshMarket = async () => {
      try {
        setMarketData(await clanService.getMarket(clanId));
      } catch {
        // The visible state remains usable if a background refresh fails.
      }
    };
    const timer = window.setInterval(refreshMarket, 60000);
    return () => window.clearInterval(timer);
  }, [clanId, clanSectionTab, legacyEconomy]);

  // Поиск пользователей без клана
  const handleSearchUsers = async (searchTerm) => {
    if (!searchTerm.trim()) {
      setSearchResults([]);
      return;
    }

    setSearching(true);
    try {
      const users = await userService.searchUsersWithoutClan(searchTerm);
      setSearchResults(users);
    } catch (error) {
      console.error('Ошибка поиска пользователей:', error);
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  };

  // Обработка изменения поля поиска
  const handleSearchChange = (e) => {
    const value = e.target.value;
    setInviteUsername(value);
    handleSearchUsers(value);
  };

  // Выбор пользователя из результатов поиска
  const handleSelectUser = (user) => {
    setInviteUsername(user.username);
    setSearchResults([]);
  };

  const loadMembersStats = useCallback(async (membersList) => {
    const request = ++memberStatsRequest.current;
    const stats = await loadClanMemberStats(membersList, id => userService.getUserStats(id, clanId));
    if (request === memberStatsRequest.current) setMembersStats(stats);
  }, [clanId]);

  const loadApplications = useCallback(async () => {
    try {
      const applicationsData = await clanService.getApplications(clanId);
      setApplications(applicationsData);
    } catch (error) {
      console.error('Ошибка загрузки заявок:', error);
    }
  }, [clanId]);

  const loadUserClan = useCallback(async () => {
    try {
      const userClanData = await clanService.getMyClan();
      setUserClan(userClanData);
    } catch {
      // Пользователь не состоит в клане
      setUserClan(null);
    }
  }, []);

  const loadClanData = useCallback(async () => {
    try {
      const [clanData, membersData, assetsData, economyData, warsData, market, territoriesData] = await Promise.all([
        clanService.getClan(clanId),
        clanService.getClanMembers(clanId),
        legacyEconomy ? clanService.getClanAssets(clanId) : Promise.resolve([]),
        legacyEconomy ? clanService.getClanEconomy(clanId) : Promise.resolve(null),
        legacyEconomy ? warService.getClanWars(clanId) : Promise.resolve([]),
        legacyEconomy ? clanService.getMarket(clanId) : Promise.resolve({ offers: [], clan_activity: [], caravans: [] }),
        territoryService.getAllTerritories(),
      ]);
      
      setClan(clanData);
      setClanAssets(assetsData);
      setRelicSelection(
        assetsData.filter((entry) => entry.active).map((entry) => entry.asset.id),
      );
      setClanEconomy(economyData);
      setClanWars(warsData);
      setMarketData(market);
      setOwnedTerritories((territoriesData || []).filter(
        (territory) => Number(territory.owner_clan_id) === Number(clanId),
      ));
      
      // Убеждаемся, что лидер клана есть в списке участников
      let processedMembers = [...membersData];
      const leaderInMembers = membersData.some(member => member.user_id === clanData.leader_id);
      
      if (!leaderInMembers && clanData.leader_id) {
        // Получаем информацию о лидере клана
        try {
          const leaderUser = await userService.getUser(clanData.leader_id);
          processedMembers.unshift({
            id: 0, // Временный ID
            user_id: clanData.leader_id,
            clan_id: clanData.id,
            rank: 'Глава клана',
            joined_at: clanData.created_at,
            username: leaderUser.username,
            avatar_url: leaderUser.avatar_url
          });
        } catch (error) {
          console.error('Ошибка загрузки данных лидера:', error);
          // Если не удалось загрузить данные лидера, используем заглушку
          processedMembers.unshift({
            id: 0,
            user_id: clanData.leader_id,
            clan_id: clanData.id,
            rank: 'Глава клана',
            joined_at: clanData.created_at,
            username: getTextSync('clan_unknown_user', 'Неизвестный пользователь'),
            avatar_url: null
          });
        }
      }
      
      setMembers(orderClanMembers(processedMembers, clanData.leader_id));
      setEditData({
        name: clanData.name,
        motto: clanData.motto || '',
        description: clanData.description || '',
        preferred_patch: clanData.preferred_patch || 'all',
        map_color: clanData.map_color || null,
        is_recruiting: clanData.is_recruiting !== false,
      });
      
      setLoading(false);
      // Основная страница доступна до получения вторичной статистики состава.
      void loadMembersStats(processedMembers);
      
      // Загружаем заявки, если пользователь является лидером
      if (clanData.leader_id === user?.id) {
        loadApplications();
      }
    } catch (error) {
      console.error('Error loading clan data:', error);
      setError(getTextSync('clan_loading_error', 'Ошибка при загрузке данных клана'));
    } finally {
      setLoading(false);
    }
  }, [clanId, getTextSync, loadApplications, loadMembersStats, user?.id, legacyEconomy]);

  useEffect(() => {
    if (clanId && !campaign.loading) {
      loadClanData();
    }
    if (user?.id) {
      loadUserClan();
    }
  }, [clanId, loadClanData, loadUserClan, user?.id, campaign.loading]);

  const isLeader = clan?.leader_id === user?.id;
  const isAdmin = user?.role?.name === 'admin' || user?.is_admin_impersonation;
  const canManageAdminClan = clan?.is_admin_clan && isAdmin;
  
  // Проверяем членство, включая лидера клана
  const isMember = members.some(member => member.user_id === user?.id) || isLeader;
  const cycleEconomy = Boolean(cycleId && user && isMember
    && String(clan?.id) === String(clanId) && String(userClan?.id) === String(clanId));
  const economyTabs = [
    ['relics', economyMessage('relics', language)],
    ['lands', language === 'en' ? 'Development' : 'Развитие'],
    ['market', economyMessage('trade', language)],
  ];
  const requestedTab = cycleEconomy && [3, 4].includes(clanSectionTab)
    ? (clanSectionTab === 4 ? 'relics' : 'market') : clanSectionTab;
  const normalizedEconomyTab = requestedTab === 'barter' ? 'market' : requestedTab;
  const economyTab = cycleEconomy && economyTabs.some(([value]) => value === normalizedEconomyTab) ? normalizedEconomyTab : null;
  const sectionTab = economyTab || ([0, 1, 2, 6].includes(requestedTab)
    || (legacyEconomy && [3, 4, 5].includes(requestedTab)) ? requestedTab : 0);
  const [economyVisited, setEconomyVisited] = useState(false);
  useEffect(() => { if (economyTab) setEconomyVisited(true); }, [economyTab]);
  const canApplyToClan = Boolean(
    !isMember
    && !isLeader
    && user
    && !userClan
    && !clan?.is_admin_clan
    && !clan?.is_deleted,
  );

  const handleUpdateClan = async () => {
    try {
      await clanService.updateClan(clanId, editData);
      showSuccess(getTextSync('clan_update_success', 'Клан успешно обновлен!'));
      setIsEditing(false);
      loadClanData();
    } catch {
      showError(getTextSync('clan_update_error', 'Ошибка при обновлении клана'));
    }
  };

  const handleDeleteClan = async () => {
    // Только лидер может удалить клан
    if (!isLeader) {
      showError(getTextSync('clan_only_leader_can_delete', 'Только лидер клана может удалить клан.'));
      return;
    }
    
    const confirmed = await confirmAction(
      getTextSync('clan_delete_confirm_message', 'Вы уверены, что хотите удалить клан? Это действие нельзя отменить. Все участники будут исключены из клана.'),
      getTextSync('clan_delete_confirm_title', 'Удаление клана')
    );
    
    if (confirmed) {
      try {
        await clanService.deleteClan(clanId);
        showSuccess(getTextSync('clan_delete_success', 'Клан успешно удален!'));
        navigate('/clans');
      } catch (deleteError) {
        showError(deleteError.response?.data?.detail || getTextSync('clan_delete_error', 'Ошибка при удалении клана'));
      }
    }
  };

  const handleLeaveClan = async () => {
    // Лидер не может покинуть клан
    if (isLeader) {
      showError(getTextSync('clan_leader_cannot_leave', 'Лидер клана не может покинуть клан. Передайте лидерство другому участнику.'));
      return;
    }
    
    const confirmed = await confirmAction(
      getTextSync('clan_leave_confirm_message', 'Вы уверены, что хотите покинуть клан?'),
      getTextSync('clan_leave_confirm_title', 'Выход из клана')
    );
    
    if (confirmed) {
      try {
        await clanService.leaveClan(clanId);
        showSuccess(getTextSync('clan_leave_success', 'Вы покинули клан'));
        navigate('/clans');
      } catch {
        showError(getTextSync('clan_leave_error', 'Ошибка при выходе из клана'));
      }
    }
  };

  const handleKickMember = async (userId) => {
    const confirmed = await confirmAction(
      getTextSync('clan_kick_confirm_message', 'Вы уверены, что хотите исключить этого участника?'),
      getTextSync('clan_kick_confirm_title', 'Исключение участника')
    );
    
    if (confirmed) {
      try {
        if (clan?.is_admin_clan) {
          await clanService.removeAdminClanMember(clanId, userId);
        } else {
          await clanService.kickMember(clanId, userId);
        }
        showSuccess(getTextSync('clan_kick_success', 'Участник исключен из клана'));
        loadClanData();
      } catch {
        showError(getTextSync('clan_kick_error', 'Ошибка при исключении участника'));
      }
    }
  };

  const handleTransferLeadership = async (userId) => {
    const confirmed = await confirmAction(
      getTextSync('clan_transfer_leadership_confirm_message', 'Вы уверены, что хотите передать лидерство этому участнику? После передачи вы станете обычным участником клана.'),
      getTextSync('clan_transfer_leadership_confirm_title', 'Передача лидерства')
    );
    
    if (confirmed) {
      try {
        await clanService.transferLeadership(clanId, userId);
        showSuccess(getTextSync('clan_transfer_leadership_success', 'Лидерство передано'));
        loadClanData();
      } catch {
        showError(getTextSync('clan_transfer_leadership_error', 'Ошибка при передаче лидерства'));
      }
    }
  };

  const handleApplicationResponse = async (applicationId, status) => {
    try {
      await clanService.respondToApplication(applicationId, status);
      showSuccess(status === 'accepted'
        ? getTextSync('clan_application_accept_success', 'Заявка принята')
        : getTextSync('clan_application_decline_success', 'Заявка отклонена'));
      loadApplications();
      loadClanData(); // Перезагружаем данные клана, так как мог добавиться новый участник
    } catch {
      showError(getTextSync('clan_application_processing_error', 'Ошибка при обработке заявки'));
    }
  };

  const handleOpenApplications = () => {
    setApplicationsDialogOpen(true);
  };

  const handleCloseInviteDialog = () => {
    setInviteDialogOpen(false);
    setInviteUsername('');
    setSearchResults([]);
  };

  const handleInviteSpecificUser = async (selectedUser) => {
    setInviting(true);
    try {
      if (clan?.is_admin_clan) {
        await clanService.appointAdminClanMember(clanId, selectedUser.id);
        showSuccess(getTextSync('clan_admin_member_appointed', null, {
          player: getPlayerDisplayName(selectedUser),
        }));
        await loadClanData();
      } else {
        await clanService.inviteUser(clanId, selectedUser.id);
        showSuccess(`${getTextSync('clan_invite_success', 'Приглашение отправлено пользователю')} ${getPlayerDisplayName(selectedUser)}!`);
      }
      setInviteDialogOpen(false);
      setInviteUsername('');
      setSearchResults([]);
    } catch {
      showError(getTextSync('clan_invite_error', 'Ошибка при отправке приглашения'));
    } finally {
      setInviting(false);
    }
  };

  const handleResetAdminSandbox = async () => {
    const confirmed = await confirmAction(
      getTextSync('clan_admin_sandbox_confirm'),
      getTextSync('clan_admin_sandbox_title'),
    );
    if (!confirmed) return;
    try {
      await clanService.resetAdminClanSandbox(clanId);
      showSuccess(getTextSync('clan_admin_sandbox_success'));
      await loadClanData();
    } catch (resetError) {
      showError(resetError.response?.data?.detail || getTextSync('clan_admin_sandbox_error'));
    }
  };

  const handleSubmitApplication = async () => {
    if (submittingApplication) return;
    if (!applicationMessage.trim()) {
      showError(getTextSync('clan_enter_message_error', 'Пожалуйста, введите сообщение для заявки'));
      return;
    }

    setSubmittingApplication(true);
    try {
      await clanService.applyToClan(clanId, applicationMessage);
      showSuccess(getTextSync('clan_application_success', 'Заявка отправлена и ожидает решения главы клана.'));
      setApplicationDialogOpen(false);
      setApplicationMessage('');
    } catch (applicationError) {
      const detail = applicationError.response?.data?.detail;
      showError(typeof detail === 'string' ? detail : getTextSync('clan_application_error', 'Ошибка при отправке заявки'));
    } finally {
      setSubmittingApplication(false);
    }
  };

  const handleAvatarUpdate = (newAvatarUrl) => {
    setClan(prevClan => ({
      ...prevClan,
      avatar_url: newAvatarUrl
    }));
  };

  const getMemberRole = (member) => {
    if (member.user_id === clan?.leader_id) return 'Глава клана';
    if (member.is_trader || member.rank === 'Торговец') return 'Торговец';
    if (member.rank === 'Воин') return 'Воин';
    return 'Салага';
  };

  const getMemberRoleLabel = (member) => {
    const role = getMemberRole(member);
    if (role === 'Глава клана') return getTextSync('clan_role_head', 'Глава клана');
    if (role === 'Торговец') return getTextSync('clan_role_trader', 'Торговец');
    if (role === 'Воин') return getTextSync('clan_role_warrior', 'Воин');
    return getTextSync('clan_role_recruit', 'Салага');
  };

  const canManageEconomy = isLeader || members.some(
    (member) => member.user_id === user?.id && getMemberRole(member) === 'Торговец',
  );

  const handlePurchaseAsset = async (assetId) => {
    try {
      await clanService.purchaseClanAsset(clanId, assetId);
      showSuccess(getTextSync('clan_relic_purchase_success', 'Реликвия клана куплена или улучшена'));
      await loadClanData();
    } catch (purchaseError) {
      showError(purchaseError.response?.data?.detail || getTextSync('clan_relic_purchase_error', 'Не удалось купить реликвию'));
    }
  };

  const toggleRelicSelection = (assetId) => {
    setRelicSelection((current) => {
      if (current.includes(assetId)) {
        return current.filter((id) => id !== assetId);
      }
      if (current.length >= 4) {
        showError(getTextSync('clan_relic_loadout_limit'));
        return current;
      }
      return [...current, assetId];
    });
  };

  const handleSaveRelicLoadout = async () => {
    setRelicLoadoutSaving(true);
    try {
      await clanService.updateRelicLoadout(clanId, relicSelection);
      showSuccess(getTextSync('clan_relic_loadout_success'));
      await loadClanData();
    } catch (loadoutError) {
      showError(loadoutError.response?.data?.detail || getTextSync('clan_relic_loadout_error'));
    } finally {
      setRelicLoadoutSaving(false);
    }
  };

  const fillRelicForm = (asset = null) => {
    setEditingRelicId(asset?.id || null);
    setRelicForm(asset ? {
      key: asset.key,
      name: asset.name,
      description: asset.description || '',
      bonus_type: asset.bonus_type,
      bonus_value: asset.bonus_value || 0,
      gold_cost: asset.gold_cost || 0,
      iron_cost: asset.iron_cost || 0,
      wood_cost: asset.wood_cost || 0,
      food_cost: asset.food_cost || 0,
      mithril_cost: asset.mithril_cost || 0,
      required_influence_level_1: asset.required_influence_level_1 || 0,
      required_influence_level_2: asset.required_influence_level_2 || 0,
      required_influence_level_3: asset.required_influence_level_3 || 0,
      is_available: asset.is_available !== false,
    } : { ...EMPTY_RELIC_FORM });
  };

  const openRelicEditor = async (asset = null) => {
    try {
      const assets = await clanService.getAdminClanAssets();
      setAdminAssets(assets);
      fillRelicForm(asset);
      setRelicEditorOpen(true);
    } catch (adminError) {
      showError(adminError.response?.data?.detail || getTextSync('clan_relic_editor_open_error'));
    }
  };

  const handleRelicSave = async () => {
    setRelicSaving(true);
    try {
      if (editingRelicId) {
        await clanService.updateClanAsset(editingRelicId, relicForm);
      } else {
        await clanService.createClanAsset(relicForm);
      }
      showSuccess(getTextSync(editingRelicId ? 'clan_relic_updated' : 'clan_relic_created'));
      setRelicEditorOpen(false);
      await loadClanData();
    } catch (adminError) {
      const detail = adminError.response?.data?.detail;
      showError(typeof detail === 'string' ? detail : getTextSync('clan_relic_save_error'));
    } finally {
      setRelicSaving(false);
    }
  };

  const handleMemberRoleChange = async (member, role) => {
    try {
      await clanService.setMemberRole(clanId, member.user_id, role);
      const roleLabels = {
        'Торговец': getTextSync('clan_role_trader', 'Торговец'),
        'Воин': getTextSync('clan_role_warrior', 'Воин'),
        'Салага': getTextSync('clan_role_recruit', 'Салага'),
      };
      showSuccess(getTextSync('clan_role_changed', 'Роль игрока изменена: {role}', { role: roleLabels[role] || role }));
      await loadClanData();
    } catch (roleError) {
      showError(roleError.response?.data?.detail || getTextSync('clan_role_change_error', 'Не удалось изменить роль участника'));
    }
  };

  const handleMemberWarlordChange = async (member) => {
    try {
      await clanService.setMemberWarlord(clanId, member.user_id, !member.is_warlord);
      showSuccess(getTextSync(
        member.is_warlord ? 'clan_warlord_removed' : 'clan_warlord_assigned',
        member.is_warlord ? 'Статус Воеводы снят' : 'Воевода назначен',
      ));
      await loadClanData();
    } catch (warlordError) {
      showError(warlordError.response?.data?.detail || getTextSync('clan_warlord_change_error', 'Не удалось изменить статус Воеводы'));
    }
  };

  const handleTrade = async () => {
    setTrading(true);
    try {
      await clanService.createMarketOffer({
        creator_clan_id: Number(clanId),
        ...tradeForm,
        give_amount: Number(tradeForm.give_amount),
        receive_amount: Number(tradeForm.receive_amount),
        expires_in_days: Number(tradeForm.expires_in_days),
      });
      showSuccess(getTextSync('market_offer_created_success'));
      setMarketData(await clanService.getMarket(clanId));
    } catch (tradeError) {
      showError(tradeError.response?.data?.detail || getTextSync('market_offer_create_error'));
    } finally {
      setTrading(false);
    }
  };

  const handleAcceptOffer = async (offerId) => {
    setTrading(true);
    try {
      await clanService.acceptMarketOffer(offerId, Number(clanId));
      showSuccess(getTextSync('market_offer_accepted_success'));
      const [market, economy] = await Promise.all([
        clanService.getMarket(clanId),
        clanService.getClanEconomy(clanId),
      ]);
      setMarketData(market);
      setClanEconomy(economy);
    } catch (tradeError) {
      showError(tradeError.response?.data?.detail || getTextSync('market_offer_accept_error'));
    } finally {
      setTrading(false);
    }
  };

  const handleCancelOffer = async (offerId) => {
    setTrading(true);
    try {
      await clanService.cancelMarketOffer(offerId);
      showSuccess(getTextSync('market_offer_canceled_success'));
      setMarketData(await clanService.getMarket(clanId));
    } catch (tradeError) {
      showError(tradeError.response?.data?.detail || getTextSync('market_offer_cancel_error'));
    } finally {
      setTrading(false);
    }
  };

  const marketResource = (key) => CLAN_RESOURCE_BY_KEY[key] || {
    key,
    labelKey: 'resource_secondary',
    color: '#bdbdbd',
    Icon: SwapHoriz,
  };

  const renderCargo = (resourceKey, amount) => {
    const { color, Icon } = marketResource(resourceKey);
    return (
      <Box className="market-cargo">
        <Icon sx={{ color }} />
        <Box>
          <Typography variant="caption" color="text.secondary">{resourceLabel(resourceKey)}</Typography>
          <Typography fontWeight={900}>{Number(amount || 0).toLocaleString(language)}</Typography>
        </Box>
      </Box>
    );
  };

  const renderRouteNames = (route = []) => {
    if (!route.length) return getTextSync('market_route_pending');
    const localizedNames = route.map((territory) => getTerritoryName(territory.name, language));
    if (route.length <= 4) return localizedNames.join(' → ');
    return `${localizedNames[0]} → ${localizedNames[1]} → ${getTextSync('market_route_more', null, { count: route.length - 4 })} → ${localizedNames.at(-2)} → ${localizedNames.at(-1)}`;
  };

  const marketQuoteReason = (quote) => {
    const reasonKeys = {
      accepter_has_no_territory: 'market_quote_no_territory',
      no_delivery_route: 'market_quote_no_delivery_route',
    };
    const translationKey = reasonKeys[quote?.reason_code];
    return translationKey ? getTextSync(translationKey) : quote?.reason;
  };

  const getLiveCaravanProgress = (caravan) => {
    const departedAt = new Date(caravan.departed_at).getTime();
    const eta = new Date(caravan.eta).getTime();
    const duration = Math.max(1, eta - departedAt);
    return Math.min(100, Math.max(0, ((marketClock - departedAt) / duration) * 100));
  };

  const groupedMarketCaravans = Object.values(
    marketData.caravans.reduce((groups, caravan) => {
      if (!groups[caravan.offer_id]) groups[caravan.offer_id] = [];
      groups[caravan.offer_id].push(caravan);
      return groups;
    }, {})
  );

  const renderMarketOffer = (offer, history = false) => {
    const isOwn = Number(offer.creator_clan_id) === Number(clanId);
    const canAccept = canManageEconomy
      && !isOwn
      && offer.status === 'open'
      && offer.quote?.available !== false;
    const statusLabels = {
      open: getTextSync('market_status_open'),
      in_transit: getTextSync('market_status_in_transit'),
      completed: getTextSync('market_status_completed'),
      canceled: getTextSync('market_status_canceled'),
      expired: getTextSync('market_status_expired'),
      failed: getTextSync('market_status_failed'),
    };
    const route = offer.route?.length ? offer.route : offer.quote?.route || [];
    const shippingCost = isOwn
      ? offer.creator_shipping_cost
      : offer.quote?.accepter_shipping_cost ?? offer.accepter_shipping_cost;
    const arrivalAt = offer.eta || offer.quote?.estimated_arrival_at;
    const routeMode = offer.route_mode || offer.quote?.route_mode || 'land';
    return (
      <Paper className={`market-offer market-offer--${offer.status}`} key={offer.id}>
        <Box className="market-offer__header">
          <Box minWidth={0}>
            <Typography variant="overline">{getTextSync('market_caravan_number', null, { id: offer.id })}</Typography>
            <Typography
              component={Link}
              to={`/clans/${offer.creator_clan_id}`}
              className="entity-link"
              fontWeight={900}
            >
              {offer.creator_clan_name || getTextSync('map_clan_fallback', null, { id: offer.creator_clan_id })}
            </Typography>
          </Box>
          <Chip
            size="small"
            className={`market-status market-status--${offer.status}`}
            label={statusLabels[offer.status] || offer.status}
          />
        </Box>
        <Box className="market-offer__exchange">
          {renderCargo(offer.give_resource, offer.give_amount)}
          <Box className="market-offer__swap" aria-label={getTextSync('market_exchange_to')}>
            <ArrowForward />
          </Box>
          {renderCargo(offer.receive_resource, offer.receive_amount)}
        </Box>
        {offer.status === 'open' && (
          <Typography variant="caption" color="text.secondary">
            {getTextSync('market_available_until', null, { date: formatMoscowDateTime(offer.expires_at, '', language) })}
          </Typography>
        )}
        {(offer.route_steps || offer.quote?.route_steps) && (
          <Box className="market-route-panel">
            <Box className="market-route-panel__path">
              <Route fontSize="small" />
              <Typography variant="body2">{renderRouteNames(route)}</Typography>
            </Box>
            <Box className="market-route-panel__facts">
              <span>
                {routeMode === 'sea' ? <DirectionsBoat fontSize="small" /> : <CaravanGlyph />}
                {routeLabel(routeMode)}
              </span>
              <span><Route fontSize="small" />{getTextSync('market_transitions', null, { count: offer.route_steps || offer.quote.route_steps })}</span>
              <span><AccessTime fontSize="small" />{getTextSync('market_travel_hours', null, { hours: offer.quote?.travel_hours || (offer.route_steps * 6) })}</span>
              <span><Payments fontSize="small" />{getTextSync('market_gold_cost', null, { value: shippingCost ?? '—' })}</span>
            </Box>
            {arrivalAt && (
              <Box className="market-route-panel__arrival">
                <HourglassTop fontSize="small" />
                <Box>
                  <Typography variant="caption" color="text.secondary">{getTextSync('market_expected_arrival')}</Typography>
                  <Typography variant="body2" fontWeight={800}>
                    {getTextSync('market_arrival_in', null, {
                      date: formatMoscowDateTime(arrivalAt, '', language),
                      remaining: formatRemainingTime(arrivalAt, getTextSync, marketClock),
                    })}
                  </Typography>
                </Box>
              </Box>
            )}
          </Box>
        )}
        {offer.status === 'open' && offer.quote?.available === false && (
          <Alert severity="warning" variant="outlined" sx={{ mt: 1 }}>
            {marketQuoteReason(offer.quote)}
          </Alert>
        )}
        {offer.accepted_by_clan_id && (
          <Typography variant="caption" color="text.secondary">
            {getTextSync('market_second_clan')}: <Link className="entity-link" to={`/clans/${offer.accepted_by_clan_id}`}>
              {offer.accepted_by_clan_name}
            </Link>
          </Typography>
        )}
        {!history && (
          <Box className="market-offer__actions">
            {canAccept && (
              <Button
                size="small"
                variant="contained"
                startIcon={<CaravanGlyph />}
                disabled={trading}
                onClick={() => handleAcceptOffer(offer.id)}
              >
                {getTextSync('market_accept')}
              </Button>
            )}
            {isOwn && offer.status === 'open' && canManageEconomy && (
              <Button
                size="small"
                color="inherit"
                disabled={trading}
                onClick={() => handleCancelOffer(offer.id)}
              >
                {getTextSync('market_remove')}
              </Button>
            )}
          </Box>
        )}
      </Paper>
    );
  };

  const renderMarket = () => (
    <Box className="clan-market-section">
      <Box className="market-heading">
        <Box>
          <Typography variant="overline" className="market-heading__eyebrow">{getTextSync('market_court')}</Typography>
          <Typography variant="h5" fontWeight={900}>{getTextSync('market_title')}</Typography>
          <Typography variant="body2" color="text.secondary">
            {getTextSync('market_explanation')}
          </Typography>
          <RulesContextLink context="market" section="market" />
        </Box>
        <Box className="market-heading__stats">
          <Box>
            <Typography variant="caption">{getTextSync('market_open_offers')}</Typography>
            <strong>{marketData.offers.length}</strong>
          </Box>
          <Box>
            <Typography variant="caption">{getTextSync('market_caravans_transit')}</Typography>
            <strong>{groupedMarketCaravans.length}</strong>
          </Box>
        </Box>
      </Box>

      <Box className="market-requirements" aria-label={getTextSync('market_requirements')}>
        <Typography className="market-requirements__title">
          {getTextSync('market_requirements_title')}
        </Typography>
        <Box><strong>1</strong><span>{getTextSync('market_requirement_land')}</span></Box>
        <Box><strong>2</strong><span>{getTextSync('market_requirement_role')}</span></Box>
        <Box><strong>3</strong><span>{getTextSync('market_requirement_cargo')}</span></Box>
        <Box><strong>4</strong><span>{getTextSync('market_requirement_route')}</span></Box>
      </Box>

      {canManageEconomy && (
        <Box className="market-create">
          <Box className="market-create__title">
            <Box>
              <Typography variant="overline">{getTextSync('market_new_caravan')}</Typography>
              <Typography variant="h6" fontWeight={900}>{getTextSync('market_create_offer')}</Typography>
            </Box>
            <Typography variant="caption" color="text.secondary">
              {getTextSync('market_quote_hint')}
            </Typography>
          </Box>
          <Box className="market-create__trade">
            <Box className="market-create__side market-create__side--give">
              <Typography variant="caption">{getTextSync('market_clan_gives')}</Typography>
              <TextField select size="small" label={getTextSync('market_resource')} value={tradeForm.give_resource} onChange={(event) => setTradeForm({ ...tradeForm, give_resource: event.target.value })}>
                {CLAN_RESOURCES.slice(0, 5).map(({ key }) => <MenuItem key={key} value={key}>{resourceLabel(key)}</MenuItem>)}
              </TextField>
              <TextField size="small" type="number" inputProps={{ min: 1 }} label={getTextSync('market_amount')} value={tradeForm.give_amount} onChange={(event) => setTradeForm({ ...tradeForm, give_amount: event.target.value })} />
            </Box>
            <Box className="market-create__direction"><SwapHoriz /></Box>
            <Box className="market-create__side market-create__side--receive">
              <Typography variant="caption">{getTextSync('market_clan_receives')}</Typography>
              <TextField select size="small" label={getTextSync('market_resource')} value={tradeForm.receive_resource} onChange={(event) => setTradeForm({ ...tradeForm, receive_resource: event.target.value })}>
                {CLAN_RESOURCES.slice(0, 5).map(({ key }) => <MenuItem key={key} value={key}>{resourceLabel(key)}</MenuItem>)}
              </TextField>
              <TextField size="small" type="number" inputProps={{ min: 1 }} label={getTextSync('market_amount')} value={tradeForm.receive_amount} onChange={(event) => setTradeForm({ ...tradeForm, receive_amount: event.target.value })} />
            </Box>
          </Box>
          <Box className="market-create__footer">
            <TextField select size="small" label={getTextSync('market_offer_duration')} value={tradeForm.expires_in_days} onChange={(event) => setTradeForm({ ...tradeForm, expires_in_days: event.target.value })}>
              {[3, 7, 14].map((count) => <MenuItem value={count} key={count}>{getTextSync('market_days', null, { count })}</MenuItem>)}
            </TextField>
            <Button
              variant="contained"
              startIcon={<Storefront />}
              onClick={handleTrade}
              disabled={trading || tradeForm.give_resource === tradeForm.receive_resource}
            >
              {getTextSync('market_publish')}
            </Button>
          </Box>
        </Box>
      )}

      {marketData.caravans.length > 0 && (
        <Box className="market-block market-block--caravans">
          <Box className="market-block__heading">
            <Box>
              <Typography variant="overline">{getTextSync('market_live_routes')}</Typography>
              <Typography variant="h6" fontWeight={900}>{getTextSync('market_shipments_title')}</Typography>
            </Box>
            <CaravanGlyph className="market-block__caravan-glyph" />
          </Box>
          <Box className="caravan-grid">
            {groupedMarketCaravans.map((caravans) => {
              const primaryCaravan = caravans[0];
              const offer = marketData.clan_activity.find(
                (item) => Number(item.id) === Number(primaryCaravan.offer_id)
              );
              const progress = getLiveCaravanProgress(primaryCaravan);
              const route = offer?.route?.length ? offer.route : primaryCaravan.route;
              const shippingTotal = Number(offer?.creator_shipping_cost || 0)
                + Number(offer?.accepter_shipping_cost || 0);
              const routeMode = offer?.route_mode || primaryCaravan.route_mode || 'land';
              const sameClansAtWar = clanWars.some((war) => {
                if (war.status !== 'active') return false;
                const warClanIds = [
                  Number(war.attacking_clan_id),
                  Number(war.defending_clan_id),
                ];
                return warClanIds.includes(Number(primaryCaravan.from_clan_id))
                  && warClanIds.includes(Number(primaryCaravan.to_clan_id));
              });
              return (
                <Paper
                  className={`caravan-card caravan-card--exchange caravan-card--${routeMode}`}
                  key={primaryCaravan.offer_id}
                >
                  <Box className="caravan-card__title">
                    <Box className="caravan-card__icon">
                      {routeMode === 'sea' ? <DirectionsBoat /> : <CaravanGlyph />}
                    </Box>
                    <Box minWidth={0}>
                      <Typography variant="overline">{getTextSync('market_caravan_number', null, { id: primaryCaravan.offer_id })}</Typography>
                      <Typography variant="h6" fontWeight={900}>
                        {primaryCaravan.from_clan_name} ↔ {primaryCaravan.to_clan_name}
                      </Typography>
                    </Box>
                    {sameClansAtWar && (
                      <Chip
                        className="caravan-card__war-badge"
                        icon={<Gavel />}
                        label={getTextSync('market_clans_at_war')}
                        size="small"
                      />
                    )}
                  </Box>
                  <Box className="caravan-card__exchange">
                    {caravans.map((caravan) => (
                      <Box className="caravan-card__cargo-side" key={caravan.id}>
                        <Typography variant="caption">
                          {getTextSync('market_clan_sent', null, { clan: caravan.from_clan_name })}
                        </Typography>
                        {renderCargo(caravan.resource, caravan.amount)}
                      </Box>
                    ))}
                    <Box className="caravan-card__exchange-icon" aria-hidden="true">
                      <SwapHoriz />
                    </Box>
                  </Box>
                  <Box className="caravan-card__progress">
                    <LinearProgress variant="determinate" value={progress} />
                    <Typography>{Math.round(progress)}%</Typography>
                  </Box>
                  <Box className="caravan-card__metrics">
                    <Box>
                      <AccessTime />
                      <Typography variant="caption">{getTextSync('market_remaining')}</Typography>
                      <strong>{formatRemainingTime(primaryCaravan.eta, getTextSync, marketClock)}</strong>
                    </Box>
                    <Box>
                      <Payments />
                      <Typography variant="caption">{getTextSync('market_delivery')}</Typography>
                      <strong>{getTextSync('market_gold_cost', null, { value: shippingTotal })}</strong>
                      <Typography variant="caption">
                        {getTextSync('market_both_sides_cost', null, {
                          first: offer?.creator_shipping_cost || 0,
                          second: offer?.accepter_shipping_cost || 0,
                        })}
                      </Typography>
                    </Box>
                    <Box>
                      <HourglassTop />
                      <Typography variant="caption">{getTextSync('market_arrival_moscow')}</Typography>
                      <strong>{formatMoscowDateTime(primaryCaravan.eta, '', language)}</strong>
                    </Box>
                  </Box>
                  <Box className="caravan-card__route">
                    {routeMode === 'sea' ? <DirectionsBoat /> : <Route />}
                    <Box>
                      <Typography variant="caption">
                        {getTextSync('market_route_segments_owned', null, {
                          route: routeLabel(routeMode),
                          count: offer?.route_steps || Math.max(1, route.length - 1),
                        })}
                      </Typography>
                      <Typography fontWeight={800}>{renderRouteNames(route)}</Typography>
                    </Box>
                  </Box>
                </Paper>
              );
            })}
          </Box>
        </Box>
      )}

      <Box className="market-block">
        <Box className="market-block__heading">
          <Box>
            <Typography variant="overline">{getTextSync('market_public')}</Typography>
            <Typography variant="h6" fontWeight={900}>{getTextSync('market_other_offers')}</Typography>
          </Box>
          <Storefront />
        </Box>
        <Box className="market-offer-grid">
          {marketData.offers.filter((offer) => Number(offer.creator_clan_id) !== Number(clanId)).map((offer) => renderMarketOffer(offer))}
          {!marketData.offers.some((offer) => Number(offer.creator_clan_id) !== Number(clanId)) && (
            <Alert severity="info" variant="outlined">{getTextSync('market_no_other_offers')}</Alert>
          )}
        </Box>
      </Box>

      <Box className="market-block">
        <Box className="market-block__heading">
          <Box>
            <Typography variant="overline">{getTextSync('market_archive_own')}</Typography>
            <Typography variant="h6" fontWeight={900}>{getTextSync('market_clan_trades')}</Typography>
          </Box>
          <History />
        </Box>
        <Box className="market-offer-grid">
          {marketData.clan_activity.map((offer) => renderMarketOffer(offer, offer.status !== 'open'))}
          {!marketData.clan_activity.length && (
            <Typography color="text.secondary">{getTextSync('market_empty_history')}</Typography>
          )}
        </Box>
      </Box>
    </Box>
  );

  const renderClanAssets = () => (
    <Box>
      {isAdmin && (
        <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 1.5 }}>
          <Button
            variant="outlined"
            startIcon={<Add />}
            onClick={() => openRelicEditor()}
          >
            {getTextSync('clan_relic_editor_create')}
          </Button>
        </Box>
      )}
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {getTextSync('clan_relics_description', 'Уникальные реликвии работают постоянно. Цена следующего уровня рассчитывается по действующим правилам кампании и показана на карточке.')}
      </Typography>
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))', lg: 'repeat(3, minmax(0, 1fr))' }, gap: 2 }}>
        {clanAssets.map(({ asset, owned, level, clan_influence: clanInfluence, next_required_influence: nextRequiredInfluence, influence_unlocked: influenceUnlocked, next_costs: nextCosts }) => {
          const priceMultiplier = [1, 5, 15][Math.min(level || 0, 2)];
          const costItems = ['gold', 'iron', 'wood', 'food', 'mithril']
            .map(resource => ({
              key: resource,
              amount: Number(nextCosts?.[resource] ?? asset[`${resource}_cost`] * priceMultiplier),
              ...CLAN_RESOURCE_BY_KEY[resource],
            }))
            .filter(({ amount }) => amount > 0);
          const RelicIcon = RELIC_ICONS[asset.key] || AutoAwesome;
          return (
              <Card key={asset.id} variant="outlined" sx={{ height: '100%', minHeight: 280 }}>
                <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                  <Box display="flex" justifyContent="space-between" alignItems="flex-start" gap={1.5}>
                    <Box display="flex" alignItems="center" gap={1.25} minWidth={0}>
                      <Avatar variant="rounded" sx={{ width: 40, height: 40, bgcolor: 'rgba(255,72,72,0.12)', color: 'primary.main' }}>
                        <RelicIcon fontSize="small" />
                      </Avatar>
                      <Typography variant="h6" sx={{ fontSize: '1rem', lineHeight: 1.25 }}>{asset.name}</Typography>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <Chip size="small" label={`${level || 0}/${asset.max_level || 3}`} color={owned ? 'success' : 'default'} />
                      {isAdmin && (
                        <Tooltip title={getTextSync('clan_relic_editor_configure')}>
                          <IconButton size="small" onClick={() => openRelicEditor(asset)}>
                            <Settings fontSize="small" />
                          </IconButton>
                        </Tooltip>
                      )}
                    </Box>
                  </Box>
                  <Typography variant="body2" color="text.secondary" sx={{ minHeight: 92, mt: 1 }}>
                    {asset.description}
                  </Typography>
                  <Typography variant="body2" color="primary.main" fontWeight={800} sx={{ mt: 1 }}>
                    {owned
                      ? getTextSync('clan_relic_current_effect', 'Текущий эффект')
                      : getTextSync('clan_relic_level_one_effect', 'Эффект I уровня')}: {formatRelicEffect(asset, Math.max(level || 1, 1), getTextSync)}
                  </Typography>
                  <Box
                    sx={{
                      mt: 1.5,
                      mb: 1.5,
                      p: 1.25,
                      border: '1px solid rgba(246, 196, 83, 0.38)',
                      bgcolor: 'rgba(246, 196, 83, 0.07)',
                      borderRadius: 1,
                    }}
                  >
                    <Typography variant="caption" fontWeight={800} color="warning.main" display="block" sx={{ mb: 0.75 }}>
                      {level >= (asset.max_level || 3)
                        ? getTextSync('clan_relic_max_level', 'РЕЛИКВИЯ УЛУЧШЕНА ДО МАКСИМУМА')
                        : owned
                          ? getTextSync('clan_relic_upgrade_price', 'ЦЕНА УЛУЧШЕНИЯ')
                          : getTextSync('clan_relic_purchase_price', 'ЦЕНА ПОКУПКИ')}
                    </Typography>
                    {level < (asset.max_level || 3) && (
                      <Box>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, flexWrap: 'wrap' }}>
                          {costItems.map(({ key, amount, color, Icon: icon }) => (
                            <Tooltip title={resourceLabel(key)} key={key} arrow>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                {React.createElement(icon, { sx: { color, fontSize: 20 } })}
                                <Typography variant="body2" fontWeight={800}>{amount}</Typography>
                                <Typography variant="caption" color="text.secondary">{resourceLabel(key)}</Typography>
                              </Box>
                            </Tooltip>
                          ))}
                        </Box>
                        <Typography
                          variant="caption"
                          color={influenceUnlocked ? 'success.main' : 'error.main'}
                          fontWeight={800}
                          display="block"
                          sx={{ mt: 1 }}
                        >
                          {getTextSync('clan_relic_influence_requirement', 'Нужно влияния: {required}. У клана: {current}. Влияние не списывается.', {
                            required: nextRequiredInfluence || 0,
                            current: clanInfluence || 0,
                          })}
                        </Typography>
                      </Box>
                    )}
                  </Box>
                  {canManageEconomy && level < (asset.max_level || 3) && (
                    <Button fullWidth size="small" variant="contained" disabled={!influenceUnlocked} sx={{ mt: 'auto', pt: 1, pb: 1 }} onClick={() => handlePurchaseAsset(asset.id)}>
                      {owned
                        ? getTextSync('clan_relic_upgrade', 'Улучшить реликвию')
                        : getTextSync('clan_relic_purchase', 'Купить реликвию')}
                    </Button>
                  )}
                </CardContent>
              </Card>
          );
        })}
      </Box>
      <Dialog
        open={relicEditorOpen}
        onClose={() => !relicSaving && setRelicEditorOpen(false)}
        fullWidth
        maxWidth="md"
      >
        <DialogTitle>
          {getTextSync(editingRelicId ? 'clan_relic_editor_title' : 'clan_relic_editor_new')}
        </DialogTitle>
        <DialogContent dividers>
          <Box sx={{ display: 'grid', gap: 2 }}>
            <TextField
              select
              label={getTextSync('clan_relic_editor_select')}
              value={editingRelicId || ''}
              onChange={(event) => {
                const selectedId = Number(event.target.value);
                fillRelicForm(
                  selectedId
                    ? adminAssets.find((asset) => asset.id === selectedId)
                    : null,
                );
              }}
            >
              <MenuItem value="">{getTextSync('clan_relic_editor_new')}</MenuItem>
              {adminAssets.map((asset) => (
                <MenuItem key={asset.id} value={asset.id}>
                  {asset.name}{asset.is_available ? '' : getTextSync('clan_relic_editor_disabled_suffix')}
                </MenuItem>
              ))}
            </TextField>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '1fr 2fr' }, gap: 2 }}>
              <TextField
                label={getTextSync('clan_relic_editor_key')}
                value={relicForm.key}
                onChange={(event) => setRelicForm({ ...relicForm, key: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') })}
                helperText={getTextSync('clan_relic_editor_key_help')}
              />
              <TextField
                label={getTextSync('clans_sort_name')}
                value={relicForm.name}
                onChange={(event) => setRelicForm({ ...relicForm, name: event.target.value })}
              />
            </Box>
            <TextField
              label={getTextSync('clan_relic_editor_description')}
              multiline
              minRows={3}
              value={relicForm.description}
              onChange={(event) => setRelicForm({ ...relicForm, description: event.target.value })}
            />
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: '2fr 1fr' }, gap: 2 }}>
              <TextField
                select
                label={getTextSync('clan_relic_editor_effect_type')}
                value={relicForm.bonus_type}
                onChange={(event) => setRelicForm({ ...relicForm, bonus_type: event.target.value })}
              >
                {[
                  ['territory_points_percent', 'clan_relic_effect_territory'],
                  ['war_win_points', 'clan_relic_effect_war_win'],
                  ['attack_power', 'clan_relic_effect_attack_power'],
                  ['defense_power', 'clan_relic_effect_defense_power'],
                  ['population_cost_percent', 'clan_relic_effect_population_discount'],
                  ['gold_income_percent', 'clan_relic_effect_gold_income'],
                  ['fortification_cost_percent', 'clan_relic_effect_fortification_discount'],
                  ['population_growth_percent', 'clan_relic_effect_population_growth'],
                  ['resource_income_flat', 'clan_relic_effect_resource_income'],
                ].map(([value, labelKey]) => (
                  <MenuItem key={value} value={value}>{getTextSync(labelKey)}</MenuItem>
                ))}
              </TextField>
              <TextField
                label={getTextSync('clan_relic_editor_effect_per_level')}
                type="number"
                value={relicForm.bonus_value}
                onChange={(event) => setRelicForm({ ...relicForm, bonus_value: Math.max(0, Number(event.target.value)) })}
              />
            </Box>
            <Typography variant="subtitle2" fontWeight={800}>{getTextSync('clan_relic_editor_base_price')}</Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(125px, 1fr))', gap: 1.5 }}>
              {['gold', 'iron', 'wood', 'food', 'mithril'].map((resource) => (
                <TextField
                  key={resource}
                  label={resourceLabel(resource)}
                  type="number"
                  value={relicForm[`${resource}_cost`]}
                  onChange={(event) => setRelicForm({
                    ...relicForm,
                    [`${resource}_cost`]: Math.max(0, Number(event.target.value)),
                  })}
                />
              ))}
            </Box>
            <Typography variant="subtitle2" fontWeight={800}>{getTextSync('clan_relic_editor_influence')}</Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' }, gap: 1.5 }}>
              {[1, 2, 3].map((level) => (
                <TextField
                  key={level}
                  label={getTextSync('clan_relic_editor_level', null, { level })}
                  type="number"
                  value={relicForm[`required_influence_level_${level}`]}
                  onChange={(event) => setRelicForm({
                    ...relicForm,
                    [`required_influence_level_${level}`]: Math.max(0, Number(event.target.value)),
                  })}
                />
              ))}
            </Box>
            <FormControl fullWidth>
              <InputLabel>{getTextSync('clan_relic_editor_availability')}</InputLabel>
              <Select
                value={relicForm.is_available ? 'active' : 'disabled'}
                label={getTextSync('clan_relic_editor_availability')}
                onChange={(event) => setRelicForm({ ...relicForm, is_available: event.target.value === 'active' })}
              >
                <MenuItem value="active">{getTextSync('clan_relic_editor_available')}</MenuItem>
                <MenuItem value="disabled">{getTextSync('clan_relic_editor_disabled')}</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRelicEditorOpen(false)} disabled={relicSaving}>{getTextSync('common_cancel')}</Button>
          <Button variant="contained" onClick={handleRelicSave} disabled={relicSaving || !relicForm.key || !relicForm.name}>
            {relicSaving ? getTextSync('map_admin_saving') : getTextSync('common_save')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );

  const renderClanWars = () => {
    const completedWars = clanWars.filter((war) => war.status === 'completed');
    const wonWars = completedWars.filter(
      (war) => Number(war.winner_clan_id) === Number(clan.id),
    );
    const lostWars = completedWars.filter(
      (war) => war.winner_clan_id
        && Number(war.winner_clan_id) !== Number(clan.id),
    );
    const territoryInfluence = Math.max(
      0,
      Number(clan.territory_points || 0) - Number(clan.base_influence || 0),
    );

    return (
      <Paper sx={{ p: 3, mt: 2 }} className="clan-war-history">
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: 'repeat(2, 1fr)', md: 'repeat(5, 1fr)' },
            gap: 1.5,
            mb: 3,
          }}
        >
          {[
            [getTextSync('clan_war_current_influence', 'Текущее влияние'), clan.territory_points || 0],
            [getTextSync('clan_war_territory_influence', 'Влияние земель'), territoryInfluence],
            [getTextSync('clan_war_total', 'Всего войн'), clanWars.length],
            [getTextSync('clan_war_wins', 'Побед'), wonWars.length],
            [getTextSync('clan_war_losses', 'Поражений'), lostWars.length],
          ].map(([label, value]) => (
            <Box
              key={label}
              sx={{
                p: 1.5,
                border: '1px solid rgba(255,255,255,0.12)',
                bgcolor: 'rgba(255,255,255,0.025)',
              }}
            >
              <Typography variant="caption" color="text.secondary">{label}</Typography>
              <Typography variant="h5" fontWeight={800}>{value}</Typography>
            </Box>
          ))}
        </Box>

        {clanWars.length === 0 ? (
          <Alert severity="info" variant="outlined">
            {getTextSync('clan_war_empty', 'Клан пока не участвовал в войнах за территории.')}
          </Alert>
        ) : (
          <Box sx={{ display: 'grid', gap: 1.5 }}>
            {clanWars.map((war) => {
              const ownScore = (war.clan_scores || []).find(
                (score) => Number(score.clan_id) === Number(clan.id),
              );
              const attackerScore = (war.clan_scores || []).find(
                (score) => Number(score.clan_id) === Number(war.attacking_clan_id),
              );
              const defenderScore = (war.clan_scores || []).find(
                (score) => Number(score.clan_id) === Number(war.defending_clan_id),
              );
              const resultKey = war.status === 'active'
                ? 'active'
                : Number(war.winner_clan_id) === Number(clan.id)
                  ? 'win'
                  : war.status === 'canceled'
                    ? 'canceled'
                    : 'loss';
              const result = getTextSync(`clan_war_result_${resultKey}`);
              const winnerName = Number(war.winner_clan_id) === Number(war.attacking_clan_id)
                ? war.attacking_clan_name
                : Number(war.winner_clan_id) === Number(war.defending_clan_id)
                  ? war.defending_clan_name
                  : null;
              const sides = [
                {
                  role: getTextSync('clan_war_attack', 'АТАКА'),
                  id: war.attacking_clan_id,
                  name: war.attacking_clan_name,
                  score: attackerScore,
                  accent: '#ff5b57',
                  background: 'rgba(255, 72, 72, 0.075)',
                  icon: <Box component="span" sx={{ fontSize: 24, lineHeight: 1 }} aria-hidden="true">⚔</Box>,
                },
                {
                  role: getTextSync('clan_war_defense', 'ЗАЩИТА'),
                  id: war.defending_clan_id,
                  name: war.defending_clan_name || getTextSync('wars_neutral_land', 'Нейтральная земля'),
                  score: defenderScore,
                  accent: '#69aef0',
                  background: 'rgba(79, 159, 232, 0.075)',
                  icon: <Shield sx={{ fontSize: 24 }} />,
                },
              ];

              return (
                <Card
                  key={war.id}
                  variant="outlined"
                  role="link"
                  tabIndex={0}
                  onClick={() => navigate(`/battles/${war.id}`)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      navigate(`/battles/${war.id}`);
                    }
                  }}
                  sx={{ cursor: 'pointer' }}
                >
                  <CardContent sx={{ p: { xs: 2, md: 2.5 } }}>
                    <Box
                      display="flex"
                      justifyContent="space-between"
                      alignItems="center"
                      gap={2}
                      flexWrap="wrap"
                    >
                      <Box>
                        <Typography variant="caption" color="text.secondary" fontWeight={800}>
                          {getTextSync('clan_war_for_territory', 'ВОЙНА ЗА ТЕРРИТОРИЮ')}
                        </Typography>
                        <Typography variant="h6">{getTerritoryName(war.territory_name, language)}</Typography>
                      </Box>
                      <Chip
                        label={result}
                        color={
                          resultKey === 'win'
                            ? 'success'
                            : resultKey === 'loss'
                              ? 'error'
                              : resultKey === 'active'
                                ? 'warning'
                                : 'default'
                        }
                        variant="outlined"
                      />
                    </Box>

                    <Box
                      sx={{
                        position: 'relative',
                        display: 'grid',
                        gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' },
                        gap: 1.5,
                        my: 2,
                      }}
                    >
                      {sides.map((side) => {
                        const isWinner = side.id
                          && Number(war.winner_clan_id) === Number(side.id);
                        return (
                          <Box
                            key={side.role}
                            sx={{
                              position: 'relative',
                              minHeight: 142,
                              p: 1.75,
                              border: '1px solid',
                              borderColor: isWinner ? 'rgba(245, 196, 81, 0.65)' : `${side.accent}55`,
                              borderLeft: `4px solid ${isWinner ? '#f5c451' : side.accent}`,
                              bgcolor: isWinner ? 'rgba(245, 196, 81, 0.1)' : side.background,
                              boxShadow: isWinner
                                ? 'inset 0 0 28px rgba(245, 196, 81, 0.08), 0 0 18px rgba(245, 196, 81, 0.12)'
                                : 'none',
                            }}
                          >
                            <Box display="flex" alignItems="center" gap={1.5}>
                              <Box display="flex" alignItems="center" gap={1.25} minWidth={0}>
                                <Box
                                  sx={{
                                    width: 38,
                                    height: 38,
                                    flex: '0 0 38px',
                                    display: 'grid',
                                    placeItems: 'center',
                                    color: side.accent,
                                    border: '1px solid',
                                    borderColor: `${side.accent}88`,
                                    bgcolor: `${side.accent}14`,
                                  }}
                                >
                                  {side.icon}
                                </Box>
                                <Box minWidth={0}>
                                  <Typography variant="caption" sx={{ color: side.accent, fontWeight: 900 }}>
                                    {side.role}
                                  </Typography>
                                  <Typography
                                    variant="body1"
                                    fontWeight={900}
                                    sx={{ lineHeight: 1.2, overflowWrap: 'anywhere' }}
                                  >
                                    {side.id ? (
                                      <Link
                                        className="entity-link"
                                        to={`/clans/${side.id}`}
                                        onClick={(event) => event.stopPropagation()}
                                      >
                                        {side.name}
                                      </Link>
                                    ) : side.name}
                                  </Typography>
                                </Box>
                              </Box>
                              {isWinner && (
                                <Chip
                                  size="small"
                                  icon={<EmojiEvents />}
                                  label={getTextSync('wars_winner', 'Победитель')}
                                  variant="outlined"
                                  sx={{
                                    position: 'absolute',
                                    top: -12,
                                    right: 10,
                                    zIndex: 2,
                                    color: '#f5c451',
                                    borderColor: 'rgba(245, 196, 81, 0.65)',
                                    bgcolor: 'rgba(245, 196, 81, 0.08)',
                                    '& .MuiChip-icon': { color: '#f5c451' },
                                  }}
                                />
                              )}
                            </Box>
                            <Box display="flex" alignItems="baseline" justifyContent="space-between" mt={2}>
                              <Typography variant="caption" color="text.secondary">{getTextSync('wars_territory_points', 'Очки территории')}</Typography>
                              <Typography variant="h5" fontWeight={900} sx={{ color: isWinner ? '#f5c451' : side.accent }}>
                                {Number(side.score?.points || 0).toFixed(2)}
                              </Typography>
                            </Box>
                            <Typography variant="caption" color="text.secondary">
                              {getTextSync('clan_war_side_record', '{wins} побед · {losses} поражений · {matches} матчей', {
                                wins: side.score?.wins || 0,
                                losses: side.score?.losses || 0,
                                matches: side.score?.matches || 0,
                              })}
                            </Typography>
                          </Box>
                        );
                      })}
                      <Box
                        sx={{
                          display: { xs: 'none', sm: 'grid' },
                          position: 'absolute',
                          top: '50%',
                          left: '50%',
                          width: 30,
                          height: 30,
                          placeItems: 'center',
                          transform: 'translate(-50%, -50%)',
                          borderRadius: '50%',
                          border: '1px solid rgba(255,255,255,0.22)',
                          bgcolor: '#181818',
                          color: 'text.secondary',
                          fontSize: 9,
                          fontWeight: 900,
                        }}
                      >
                        VS
                      </Box>
                    </Box>

                    <Box
                      sx={{
                        display: 'flex',
                        alignItems: { xs: 'flex-start', sm: 'center' },
                        justifyContent: 'space-between',
                        flexDirection: { xs: 'column', sm: 'row' },
                        gap: 1,
                      }}
                    >
                      <Typography variant="body2" fontWeight={800}>
                        {war.status === 'active'
                          ? getTextSync('clan_war_continues', 'Сражение продолжается')
                          : winnerName
                            ? getTextSync('clan_war_winner_named', 'Победитель: {clan}', { clan: winnerName })
                            : war.status === 'canceled'
                              ? getTextSync('clan_war_canceled', 'Война отменена')
                              : getTextSync('clan_war_winner_unknown', 'Победитель не определён')}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {new Date(war.started_at).toLocaleString(locale, {
                          timeZone: 'Europe/Moscow',
                        })}
                        {war.ended_at
                          ? ` - ${new Date(war.ended_at).toLocaleString(locale, {
                            timeZone: 'Europe/Moscow',
                          })}`
                          : ''}
                      </Typography>
                    </Box>
                    <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                      {getTextSync('clan_war_contribution', 'Вклад этого клана: {points} очка', {
                        points: Number(ownScore?.points || 0).toFixed(2),
                      })}
                    </Typography>
                  </CardContent>
                </Card>
              );
            })}
          </Box>
        )}
      </Paper>
    );
  };

  const renderMembersList = () => (
    <List>
      {sortedMembers.map((member) => (
        <ListItem key={member.id} divider>
          <ListItemAvatar>
            <Avatar src={member.avatar_url || '/default-avatar.png'}>
              {member.username ? member.username.charAt(0).toUpperCase() : '?'}
            </Avatar>
          </ListItemAvatar>
          <ListItemText
            primary={
              <Box display="flex" alignItems="center" gap={1}>
                <PlayerIdentity username={member.username} usernameClassName="entity-link" />
                {member.user_id === clan.leader_id && (
                  <img src="/icons/sauronwb.png" alt={getTextSync('clan_role_head', 'Глава клана')} style={{ width: '16px', height: '16px' }} />
                )}
                {member.is_warlord && (
                  <Tooltip title={getTextSync('clan_warlord', 'Воевода')} arrow>
                    <WorkspacePremium className="clan-warlord-icon" aria-label={getTextSync('clan_warlord', 'Воевода')} />
                  </Tooltip>
                )}
              </Box>
            }
            secondary={`${getMemberRoleLabel(member)} · ${getTextSync('clan_member_since', 'В клане с')} ${new Date(member.joined_at).toLocaleDateString(locale)}`}
          />
          {isLeader && member.user_id !== user?.id && (
            <Box
              display="flex"
              gap={1}
              flexWrap="wrap"
              justifyContent="flex-end"
              sx={{ ml: 2 }}
            >
                <Button
                  size="small"
                  variant="outlined"
                  onClick={() => handleTransferLeadership(member.user_id)}
                >
                  {getTextSync('clan_make_leader', 'Сделать лидером')}
                </Button>
                <FormControl size="small" sx={{ minWidth: 126 }}>
                  <Select
                    value={getMemberRole(member)}
                    onChange={(event) => handleMemberRoleChange(member, event.target.value)}
                    aria-label={getTextSync('clan_member_role_aria', 'Роль игрока {username}', { username: getPlayerDisplayName(member.username) })}
                  >
                    <MenuItem value="Торговец">{getTextSync('clan_role_trader', 'Торговец')}</MenuItem>
                    <MenuItem value="Воин">{getTextSync('clan_role_warrior', 'Воин')}</MenuItem>
                    <MenuItem value="Салага">{getTextSync('clan_role_recruit', 'Салага')}</MenuItem>
                  </Select>
                </FormControl>
                <Button
                  size="small"
                  variant={member.is_warlord ? 'contained' : 'outlined'}
                  color="warning"
                  startIcon={<WorkspacePremium />}
                  disabled={member.warlord_busy}
                  onClick={() => handleMemberWarlordChange(member)}
                >
                  {member.warlord_busy
                    ? getTextSync('clan_warlord_busy', 'В походе')
                    : member.is_warlord
                    ? getTextSync('clan_warlord_remove', 'Снять Воеводу')
                    : getTextSync('clan_warlord_assign', 'Назначить Воеводой')}
                </Button>
                <Button
                  size="small"
                  variant="outlined"
                  color="error"
                  onClick={() => handleKickMember(member.user_id)}
                >
                  {getTextSync('clan_kick_member', 'Исключить')}
                </Button>
            </Box>
          )}
          
          {/* Для лидера показываем только кнопку передачи лидерства */}
          {isLeader && member.user_id === user?.id && (
            <Box className="clan-member-self-actions">
              <Typography variant="body2" color="text.secondary">
                {getTextSync('clan_you_are_leader', 'Вы - глава клана')}
              </Typography>
              <Button
                size="small"
                variant={member.is_warlord ? 'contained' : 'outlined'}
                color="warning"
                startIcon={<WorkspacePremium />}
                disabled={member.warlord_busy}
                onClick={() => handleMemberWarlordChange(member)}
              >
                {member.warlord_busy
                  ? getTextSync('clan_warlord_busy', 'В походе')
                  : member.is_warlord
                  ? getTextSync('clan_warlord_remove', 'Снять Воеводу')
                  : getTextSync('clan_warlord_assign', 'Назначить Воеводой')}
              </Button>
            </Box>
          )}
        </ListItem>
      ))}
    </List>
  );

  const renderMembersStats = () => (
    <TableContainer component={Paper} sx={{ mt: 2 }} className="stats-table">
      <Table>
        <TableHead>
          <TableRow>
            <TableCell>{getTextSync('clan_stats_player', 'Игрок')}</TableCell>
            <TableCell align="center">{getTextSync('clan_stats_level', 'Уровень')}</TableCell>
            <TableCell align="center">{getTextSync('clan_stats_elo_ennorath', 'Elo Ennorath')}</TableCell>
            <TableCell align="center">{getTextSync('clan_stats_elo_patch_202', 'Elo Patch 2.02')}</TableCell>
            <TableCell align="center">{getTextSync('clan_stats_matches', 'Матчей')}</TableCell>
            <TableCell align="center">{getTextSync('clan_stats_wins', 'Побед')}</TableCell>
            <TableCell align="center">{getTextSync('clan_stats_losses', 'Поражений')}</TableCell>
            <TableCell align="center">{getTextSync('clan_stats_winrate', 'Винрейт')}</TableCell>
            <TableCell align="center">{getTextSync('clan_stats_role', 'Роль')}</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {sortedMembers.map((member) => {
            const statsUnavailable = !membersStats[member.user_id];
            const stats = membersStats[member.user_id] || {
              total_matches: 0,
              wins: 0,
              losses: 0,
              win_rate: 0,
              level: 1,
              experience: 0,
              elo_ratings: {},
              elo_patch: 'all'
            };
            const eloRatings = getMemberEloRatings(stats);
            
            return (
              <TableRow key={member.id}>
                <TableCell>
                  <Box display="flex" alignItems="center" gap={1}>
                    <Avatar src={member.avatar_url || '/default-avatar.png'} sx={{ width: 32, height: 32 }} className="member-avatar">
                      {member.username ? member.username.charAt(0).toUpperCase() : '?'}
                    </Avatar>
                    <Box>
                      <Typography variant="body2" fontWeight="bold">
                        <PlayerIdentity username={member.username} usernameClassName="entity-link" />
                        {member.is_warlord && (
                          <Tooltip title={getTextSync('clan_warlord', 'Воевода')} arrow>
                            <WorkspacePremium className="clan-warlord-icon clan-warlord-icon--stats" aria-label={getTextSync('clan_warlord', 'Воевода')} />
                          </Tooltip>
                        )}
                      </Typography>
                      {member.user_id === clan.leader_id && (
                        <Chip 
                          label={getTextSync('clan_role_leader', 'Лидер')} 
                          size="small" 
                          color="primary" 
                          className="leader-chip"
                          icon={<img src="/icons/sauronwb.png" alt={getTextSync('clan_role_head', 'Глава клана')} style={{ width: '12px', height: '12px' }} />}
                        />
                      )}
                    </Box>
                  </Box>
                </TableCell>
                <TableCell align="center" className="member-stats-cell level">
                  <Typography variant="body2" fontWeight="bold">
                    {statsUnavailable ? '\u2014' : stats.level}
                  </Typography>
                </TableCell>
                <TableCell align="center" className="member-stats-cell experience">
                  <Typography variant="body2" fontWeight="bold">
                    {statsUnavailable ? '\u2014' : eloRatings.ennorath}
                  </Typography>
                </TableCell>
                <TableCell align="center" className="member-stats-cell experience">
                  <Typography variant="body2" fontWeight="bold">
                    {statsUnavailable ? '\u2014' : eloRatings.patch202}
                  </Typography>
                </TableCell>
                <TableCell align="center" className="member-stats-cell matches">
                  <Typography variant="body2">
                    {statsUnavailable ? '\u2014' : stats.total_matches}
                  </Typography>
                </TableCell>
                <TableCell align="center" className="member-stats-cell wins">
                  <Typography variant="body2" fontWeight="bold">
                    {statsUnavailable ? '\u2014' : stats.wins}
                  </Typography>
                </TableCell>
                <TableCell align="center" className="member-stats-cell losses">
                  <Typography variant="body2" fontWeight="bold">
                    {statsUnavailable ? '\u2014' : stats.losses}
                  </Typography>
                </TableCell>
                <TableCell align="center">
                  <Chip 
                    label={statsUnavailable ? '\u2014' : `${stats.win_rate}%`}
                    size="small" 
                    className={`winrate-chip ${stats.win_rate >= 60 ? 'excellent' : stats.win_rate >= 50 ? 'good' : 'poor'}`}
                  />
                </TableCell>
                <TableCell align="center" className="member-role">
                  <Typography variant="body2">
                    {getMemberRoleLabel(member)}
                  </Typography>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );

  const renderClanOverview = () => {
    const overviewBattles = cycleHistoryMode ? currentCycleBattles : clanWars;
    const completedWars = overviewBattles.filter(war => cycleHistoryMode ? war.completed_at : war.status === 'completed');
    const wonWars = completedWars.filter((war) => Number(war.winner_clan_id) === Number(clan.id));
    const winRate = completedWars.length ? Math.round((wonWars.length / completedWars.length) * 100) : 0;
    const leader = members.find((member) => Number(member.user_id) === Number(clan.leader_id));
    const territoryGoal = 8;
    const goalProgress = Math.min(100, Math.round((ownedTerritories.length / territoryGoal) * 100));
    const weekdayActivity = Array.from({ length: 7 }, () => 0);
    overviewBattles.forEach((war) => {
      const date = new Date(war.started_at || war.created_at || 0);
      if (!Number.isNaN(date.getTime())) weekdayActivity[(date.getDay() + 6) % 7] += 1;
    });
    const activityMax = Math.max(1, ...weekdayActivity);
    const seasonAward = getSeasonAward(clan.rank, getTextSync);
    const territoryAwards = getTerritoryAwards(ownedTerritories, getTextSync);

    return (
      <Box className="clan-prototype-overview">
        {preseason.open && isMember && <Alert severity="info"><Link to="/preseason">{getTextSync('preseason_title')}</Link><p>{getTextSync('preseason_open')}</p><strong>{getTextSync('preseason_treasury')}: 1000 / 30 / 30 / 20 / 5</strong></Alert>}
        <section className="grid g4 clan-kpis">
          <article className="card kpi"><strong>#{clan.rank || '—'}</strong><small>{getTextSync('clan_overview_rating')}</small></article>
          <article className="card kpi"><strong>{Number(clan.territory_points || 0).toLocaleString(locale)}</strong><small>{getTextSync('clan_overview_points')}</small></article>
          <article className="card kpi"><strong>{winRate}%</strong><small>{getTextSync('clan_overview_wins')}</small></article>
          <article className="card kpi"><strong>{ownedTerritories.length}</strong><small>{getTextSync('clan_overview_territories')}</small></article>
        </section>

        <section className="section grid g2 clan-overview-grid">
          <article className="card panel">
            <div className="eyebrow">{getTextSync('clan_overview_about')}</div>
            <h2 className="serif">{clan.motto || clan.name}</h2>
            <p className="muted">{clan.description || getTextSync('clan_description_missing', 'Описание отсутствует')}</p>
            <div className="member-line"><b>{getTextSync('clan_overview_leader')}</b><span>{getPlayerDisplayName(leader?.username, '—')}</span></div>
            <div className="member-line"><b>{getTextSync('clans_created')}</b><span>{new Date(clan.created_at).toLocaleDateString(locale)}</span></div>
            <div className="member-line"><b>{getTextSync('nav_language')}</b><span>{language.toUpperCase()}</span></div>
            <div className="member-line"><b>{getTextSync('clans_game_patch')}</b><span>{clan.preferred_patch === 'patch_202' ? 'Patch 2.02' : clan.preferred_patch === 'ennorath' ? 'Ennorath' : '2.02 + Ennorath'}</span></div>
          </article>
          <article className="card panel">
            <div className="eyebrow">{getTextSync('clan_overview_season_goal')}</div>
            <h2>{getTextSync('clan_overview_crown')}</h2>
            <p className="muted">{getTextSync('clan_overview_goal_copy', null, { count: territoryGoal })}</p>
            <div className="progress"><i style={{ width: `${goalProgress}%` }} /></div>
            <div className="quest-meta"><span>{goalProgress}%</span><span>{getTextSync('clan_overview_goal_meta', null, { count: territoryGoal })}</span></div>
            <hr />
            <h3>{getTextSync('clan_overview_strengths')}</h3>
            <div className="chip-row"><span className="chip">{getTextSync('clan_overview_fighters', null, { count: members.length })}</span><span className="chip">{getTextSync('clan_overview_victories', null, { count: wonWars.length })}</span><span className="chip">{getTextSync('clan_overview_lands', null, { count: ownedTerritories.length })}</span></div>
          </article>
        </section>

        <section className="section clan-awards-section">
          <div className="section-head"><div><div className="eyebrow">{getTextSync('clan_chronicle')}</div><h2>{getTextSync('clan_awards_title')}</h2><p className="subtitle">{getTextSync('clan_awards_copy')}</p></div></div>
          <div className="clan-awards-grid">
            {seasonAward && <article className="card clan-award-card is-permanent"><img src={seasonAward.image} alt="" /><div><span>{getTextSync('clan_award_permanent')}</span><h3>{seasonAward.label}</h3><p>{seasonAward.description}</p></div></article>}
            {territoryAwards.map((award) => <article className="card clan-award-card is-regional" key={award.image}><img src={award.image} alt="" /><div><span>{getTextSync('clan_award_regional')}</span><h3>{award.label}</h3><p>{award.description}</p></div></article>)}
            {!seasonAward && !territoryAwards.length && <article className="card panel clan-awards-empty"><EmojiEvents /><div><h3>{getTextSync('clan_awards_empty_title')}</h3><p className="muted">{getTextSync('clan_awards_empty_copy')}</p></div></article>}
          </div>
        </section>

        <section className="section grid g2">
          <article className="card panel">
            <div className="section-head"><h2>{getTextSync('clan_recent_battles')}</h2><button type="button" className="text-btn" onClick={() => setClanSectionTab(6)}>{getTextSync('clan_show_all')}</button></div>
            {cycleHistoryMode && cycleHistoryState.error && <p role="alert">{clanHistoryMessage('unavailable', language)}</p>}
            <div className="table-wrap">
              <table className="table clan-overview-battles">
                <thead><tr><th>{getTextSync('profile_match_opponent')}</th><th>{getTextSync('common_unknown_territory')}</th><th>{getTextSync('clan_battle_score')}</th><th>{getTextSync('profile_match_result')}</th></tr></thead>
                {cycleHistoryMode ? <CycleHistoryRows battles={currentCycleBattles.slice(0, 4)} clanId={clanId} language={language} t={getTextSync} loading={!cycleHistory && !cycleHistoryState.error} /> : <tbody>
                  {clanWars.slice(0, 4).map((war) => {
                    const ownIsAttacker = Number(war.attacking_clan_id) === Number(clan.id);
                    const opponent = ownIsAttacker ? war.defending_clan_name : war.attacking_clan_name;
                    const ownScore = (war.clan_scores || []).find((score) => Number(score.clan_id) === Number(clan.id));
                    const opponentScore = (war.clan_scores || []).find((score) => Number(score.clan_id) !== Number(clan.id));
                    const won = Number(war.winner_clan_id) === Number(clan.id);
                    return <tr key={war.id} onClick={() => navigate(`/battles/${war.id}`)}><td>{opponent || getTextSync('homepage_neutral_side')}</td><td>{getTerritoryName(war.territory_name, language)}</td><td>{Math.round(Number(ownScore?.points || 0))}:{Math.round(Number(opponentScore?.points || 0))}</td><td className={won ? 'positive' : war.status === 'active' ? 'muted' : 'negative'}>{war.status === 'active' ? 'LIVE' : won ? getTextSync('profile_match_win') : getTextSync('profile_match_loss')}</td></tr>;
                  })}
                  {!clanWars.length && <tr><td colSpan="4" className="muted">{getTextSync('clan_no_wars')}</td></tr>}
                </tbody>}
              </table>
            </div>
          </article>
          <article className="card panel">
            <div className="section-head"><h2>{getTextSync('clan_roster_activity')}</h2></div>
            <div className="activity-bars" aria-label={getTextSync('clan_weekday_activity')}>
              {['weekday_mon', 'weekday_tue', 'weekday_wed', 'weekday_thu', 'weekday_fri', 'weekday_sat', 'weekday_sun'].map((dayKey, index) => <div key={dayKey}><span>{getTextSync(dayKey)}</span><i style={{ height: `${Math.max(8, (weekdayActivity[index] / activityMax) * 100)}%` }} title={getTextSync('clan_activity_events', null, { count: weekdayActivity[index] })} /></div>)}
            </div>
            <p className="activity-caption">{getTextSync('clan_activity_caption')}</p>
          </article>
        </section>

      </Box>
    );
  };

  const renderClanPlayersPrototype = () => {
    const officers = members.filter((member) => Number(member.user_id) === Number(clan.leader_id) || member.is_warlord || getMemberRole(member) !== 'Салага');
    const visibleMembers = memberFilter === 'officers'
      ? officers
      : memberFilter === 'online'
        ? members.filter((member) => member.is_online)
        : members;
    const leader = members.find((member) => Number(member.user_id) === Number(clan.leader_id));

    return (
      <section className="clan-players-panel">
        <div className="section-head">
          <div><div className="eyebrow">{getTextSync('clan_roster')}</div><h2>{getTextSync('clan_players_count', null, { count: members.length })}</h2></div>
          <div className="filters">
            {[['all', 'common_all'], ['online', 'clan_filter_online'], ['officers', 'clan_officers']].map(([value, labelKey]) => <button key={value} type="button" className={`filter ${memberFilter === value ? 'active' : ''}`} onClick={() => setMemberFilter(value)}>{getTextSync(labelKey)}</button>)}
          </div>
        </div>
        <div className="card panel table-wrap">
          <table className="table clan-player-table">
            <thead><tr><th>#</th><th>{getTextSync('common_player')}</th><th>{getTextSync('profile_clan_role')}</th><th>Elo · Ennorath</th><th>Elo · Patch 2.02</th><th>{getTextSync('profile_winrate')}</th><th>{getTextSync('map_mode_activity')}</th></tr></thead>
            <tbody>
              {visibleMembers.map((member, index) => {
                const stats = membersStats[member.user_id] || {};
                const eloRatings = getMemberEloRatings(stats);
                return <tr key={member.id}><td>{index + 1}</td><td><PlayerIdentity username={member.username} usernameClassName="entity-link" /></td><td>{Number(member.user_id) === Number(clan.leader_id) ? getTextSync('common_captain') : member.is_warlord ? getTextSync('clan_officer') : getMemberRoleLabel(member)}</td><td>{eloRatings.ennorath}</td><td>{eloRatings.patch202}</td><td>{Math.round(Number(stats.win_rate || 0))}%</td><td><PresenceBadge presence={member} language={language} /></td></tr>;
              })}
              {!visibleMembers.length && <tr><td colSpan="7" className="muted">{getTextSync('clan_players_filter_empty')}</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="section grid g3 clan-role-cards">
          <div className="card panel"><h3>{getTextSync('common_captain')}</h3><p className="muted">{getTextSync('clan_captain_copy')}</p><b>{getPlayerDisplayName(leader?.username, '—')}</b></div>
          <div className="card panel"><h3>{getTextSync('clan_officers')}</h3><p className="muted">{getTextSync('clan_officers_copy')}</p><b>{officers.filter((member) => Number(member.user_id) !== Number(clan.leader_id)).map((member) => getPlayerDisplayName(member.username)).join(' · ') || '—'}</b></div>
          <div className="card panel"><h3>{getTextSync('clan_recruiting')}</h3><p className="muted">{getTextSync('clan_recruiting_copy')}</p>{canApplyToClan && clan.is_recruiting !== false ? <button className="btn" type="button" onClick={() => setApplicationDialogOpen(true)}>{getTextSync('clan_apply')}</button> : <span className="status ok">{isMember ? getTextSync('clan_roster_member_status') : clan.is_recruiting === false ? getTextSync('clans_recruiting_closed') : getTextSync('clan_recruiting_invite_only')}</span>}</div>
        </div>
        {isLeader && <section className="section card clan-management-roster clan-management-roster--open"><div className="clan-management-roster__heading"><h2>{getTextSync('clan_roster_management')}</h2><p>{getTextSync('clan_roster_management_copy')}</p></div><div className="panel">{renderMembersList()}</div></section>}
        <details className="section card clan-management-roster"><summary>{getTextSync('clan_roster_advanced')}</summary><div className="panel">{renderMembersStats()}</div></details>
      </section>
    );
  };

  const renderClanRelicsPrototype = () => {
    const ownedAssets = clanAssets.filter(({ owned, level }) => owned || Number(level) > 0);
    const activeAssets = ownedAssets.filter(({ active }) => active);
    const combatBonus = activeAssets.reduce((sum, { asset, level }) => ['attack_power', 'defense_power', 'war_win_points'].includes(asset.bonus_type) ? sum + Number(asset.bonus_value || 0) * Number(level || 1) : sum, 0);
    const lockedUntil = ownedAssets[0]?.loadout_locked_until || clanAssets[0]?.loadout_locked_until;
    const loadoutLocked = lockedUntil && new Date(lockedUntil).getTime() > Date.now();
    const storedSelection = activeAssets.map(({ asset }) => asset.id).sort((a, b) => a - b);
    const pendingSelection = [...relicSelection].sort((a, b) => a - b);
    const selectionChanged = JSON.stringify(storedSelection) !== JSON.stringify(pendingSelection);
    const canEditLoadout = isLeader || isAdmin;

    return (
      <section className="clan-relics-prototype">
        <div className="section-head"><div><div className="eyebrow">{getTextSync('clan_relics_shared_storage')}</div><h2>{getTextSync('clan_tab_relics')}</h2><p className="subtitle">{getTextSync('clan_relics_loadout_copy')}</p></div>{isAdmin && <button className="btn" type="button" onClick={() => openRelicEditor()}>{getTextSync('clan_relics_add')}</button>}</div>
        <div className="grid g4"><div className="card kpi"><strong>{ownedAssets.length}</strong><small>{getTextSync('clan_relics_owned_count')}</small></div><div className="card kpi"><strong>{activeAssets.length} / 4</strong><small>{getTextSync('clan_relics_active_slots')}</small></div><div className="card kpi"><strong>+{combatBonus}%</strong><small>{getTextSync('clan_relics_combat_bonus')}</small></div><div className="card kpi"><strong>{clanAssets.length}</strong><small>{getTextSync('clan_relics_types_available')}</small></div></div>
        <div className="section card panel clan-loadout">
          <div className="section-head">
            <div><div className="eyebrow">{getTextSync('clan_relics_combat_loadout')}</div><h2>{getTextSync('profile_active_relics')}</h2></div>
            <div className="clan-loadout-actions">
              <span className="muted">{loadoutLocked ? getTextSync('clan_relics_change_available', null, { date: new Date(lockedUntil).toLocaleString(locale) }) : getTextSync('clan_relics_lock_copy')}</span>
              {canEditLoadout && <button className="btn" type="button" disabled={!selectionChanged || loadoutLocked || relicLoadoutSaving} onClick={handleSaveRelicLoadout}>{getTextSync(relicLoadoutSaving ? 'clan_relics_saving' : 'clan_relics_save_loadout')}</button>}
            </div>
          </div>
          <div className="clan-loadout-grid">{Array.from({ length: 4 }, (_, index) => { const selectedId = relicSelection[index]; const entry = ownedAssets.find(({ asset }) => asset.id === selectedId); if (!entry) return <div className="clan-slot locked" key={`empty-${index}`}><div className="slot-plus">+</div><div><span>{getTextSync('shop_slot')} {index + 1}</span><b>{getTextSync('clan_relics_slot_free')}</b><small>{getTextSync('clan_relics_choose')}</small></div></div>; return <div className="clan-slot active" key={entry.asset.id}><div className="clan-relic-glyph"><img src={getRelicArtwork(entry.asset.key)} alt="" /></div><div><span>{getTextSync('clan_relics_slot_level', null, { slot: index + 1, level: entry.level })}</span><b>{entry.asset.name}</b><small>{formatRelicEffect(entry.asset, entry.level || 1, getTextSync)}</small></div></div>; })}</div>
        </div>
        <div className="section">
          <div className="section-head"><div><div className="eyebrow">{getTextSync('clan_relics_collection')}</div><h2>{getTextSync('clan_relics_all')}</h2></div></div>
          <div className="clan-relic-grid">
            {clanAssets.map(({ asset, owned, level, influence_unlocked: influenceUnlocked, next_costs: nextCosts }) => {
              const selected = relicSelection.includes(asset.id);
              const nextLevelAvailable = Number(level || 0) < Number(asset.max_level || 3);
              const priceMultiplier = [1, 5, 15][Math.min(Number(level || 0), 2)];
              const priceItems = CLAN_RESOURCES.slice(0, 5)
                .map(({ key }) => ({
                  key,
                  amount: Number(nextCosts?.[key] ?? Number(asset[`${key}_cost`] || 0) * priceMultiplier),
                }))
                .filter(({ amount }) => amount > 0);
              return (
                <article className={`card clan-relic-card ${owned ? 'owned' : ''} ${selected ? 'selected' : ''}`} key={asset.id}>
                  <div className="clan-relic-art">
                    <img src={getRelicArtwork(asset.key)} alt="" />
                    <span className="relic-state">{selected ? getTextSync('clan_relics_in_loadout') : owned ? getTextSync('clan_relics_level', null, { level }) : getTextSync('clan_relics_world_storage')}</span>
                  </div>
                  <div className="clan-relic-body">
                    <div className="relic-rarity">{asset.bonus_type.replaceAll('_', ' ')}</div>
                    <h3>{asset.name}</h3>
                    <p>{formatRelicEffect(asset, Math.max(level || 1, 1), getTextSync)}</p>
                    <div className="clan-relic-price" aria-label={getTextSync('clan_relic_price', 'Цена')}>
                      <span>{nextLevelAvailable ? getTextSync('clan_relic_price', 'Цена') : getTextSync('clan_relic_max_level', 'Максимальный уровень')}</span>
                      {nextLevelAvailable && (
                        <strong>{priceItems.map(({ key, amount }) => `${amount.toLocaleString(locale)} ${resourceLabel(key)}`).join(' · ') || '0'}</strong>
                      )}
                    </div>
                    <div className="clan-relic-actions">
                      {canEditLoadout && owned && <button className="clan-relic-select" type="button" aria-pressed={selected} disabled={loadoutLocked} onClick={() => toggleRelicSelection(asset.id)}>{getTextSync(selected ? 'clan_relics_remove' : 'clan_relics_select')}</button>}
                      {canManageEconomy && nextLevelAvailable && <button className="btn" disabled={!influenceUnlocked} type="button" onClick={() => handlePurchaseAsset(asset.id)}>{getTextSync(owned ? 'clan_relics_upgrade_short' : 'clan_relics_acquire')}</button>}
                      {isAdmin && <button className="text-btn" type="button" onClick={() => openRelicEditor(asset)}>{getTextSync('rules_tab_command')}</button>}
                    </div>
                  </div>
                </article>
              );
            })}
            {!clanAssets.length && <div className="card panel clan-empty-panel">{getTextSync('clan_relics_empty')}</div>}
          </div>
        </div>
        {canManageEconomy && <details className="section card clan-management-roster"><summary>{getTextSync('clan_relics_advanced')}</summary><div className="panel">{renderClanAssets()}</div></details>}
      </section>
    );
  };

  const renderClanBattlesPrototype = () => {
    const visibleWars = clanWars.filter((war) => {
      if (warFilter === 'all') return true;
      const won = Number(war.winner_clan_id) === Number(clan.id);
      return warFilter === 'wins' ? won : war.status === 'completed' && !won;
    });
    return (
      <section className="clan-battles-prototype">
        <div className="section-head"><div><div className="eyebrow">{getTextSync('clan_tab_war_history')}</div><h2>{getTextSync('clan_battles_title')}</h2></div><div className="filters">{[['all', 'common_all'], ['wins', 'profile_wins'], ['losses', 'profile_match_loss']].map(([value, labelKey]) => <button key={value} className={`filter ${warFilter === value ? 'active' : ''}`} type="button" onClick={() => setWarFilter(value)}>{getTextSync(labelKey)}</button>)}</div></div>
        <div className="card panel table-wrap"><table className="table"><thead><tr><th>{getTextSync('profile_match_date')}</th><th>{getTextSync('profile_match_opponent')}</th><th>{getTextSync('common_unknown_territory')}</th><th>{getTextSync('clan_battle_score')}</th><th>{getTextSync('profile_match_result')}</th><th>{getTextSync('admin_campaign_rules_unit_points')}</th></tr></thead><tbody>{visibleWars.map((war) => { const ownIsAttacker = Number(war.attacking_clan_id) === Number(clan.id); const opponent = ownIsAttacker ? war.defending_clan_name : war.attacking_clan_name; const ownScore = (war.clan_scores || []).find((score) => Number(score.clan_id) === Number(clan.id)); const opponentScore = (war.clan_scores || []).find((score) => Number(score.clan_id) !== Number(clan.id)); const won = Number(war.winner_clan_id) === Number(clan.id); return <tr key={war.id} onClick={() => navigate(`/battles/${war.id}`)}><td>{new Date(war.started_at).toLocaleDateString(locale)}</td><td>{opponent || getTextSync('homepage_neutral_side')}</td><td>{getTerritoryName(war.territory_name, language)}</td><td>{Math.round(Number(ownScore?.points || 0))}:{Math.round(Number(opponentScore?.points || 0))}</td><td className={won ? 'positive' : war.status === 'active' ? 'muted' : 'negative'}>{war.status === 'active' ? 'LIVE' : won ? getTextSync('profile_match_win') : getTextSync('profile_match_loss')}</td><td>{Math.round(Number(ownScore?.points || 0))}</td></tr>; })}{!visibleWars.length && <tr><td colSpan="6" className="muted">{getTextSync('clan_battles_filter_empty')}</td></tr>}</tbody></table></div>
        <details className="section card clan-management-roster"><summary>{getTextSync('clan_battles_details')}</summary><div className="clan-expanded-war-details">{renderClanWars()}</div></details>
      </section>
    );
  };

  const renderClanTerritories = () => {
    const vulnerable = [...ownedTerritories]
      .sort((left, right) => Number(left.fortifications || 0) - Number(right.fortifications || 0))
      .slice(0, 3);
    return (
      <section className="clan-territories-panel">
      <div className="section-head">
        <div><div className="eyebrow">{getTextSync('clan_territories_holdings')}</div><h2>{getTextSync('clan_territories_count', null, { count: ownedTerritories.length })}</h2></div>
        <button className="btn" type="button" onClick={() => navigate('/map')}>{getTextSync('clan_territories_open_map')}</button>
      </div>
      {ownedTerritories.length ? (
        <div className="grid g3 clan-territory-grid">
          {ownedTerritories.map((territory) => (
            <article className="card territory-card" key={territory.id}>
              <b>{getTerritoryName(territory.name, language)}</b>
              <span>{territory.region}</span>
              {legacyEconomy && <><small>{getTextSync('clan_territory_population', null, { count: Number(territory.population || 0).toLocaleString(language) })}</small>
              <div className="progress"><i style={{ width: `${Math.min(100, Number(territory.fortifications || 0) * 10)}%` }} /></div>
              <em>{getTextSync('clan_territory_fortifications_income', null, { fortifications: territory.fortifications || 0, income: territory.resource_wealth || 0 })}</em></>}
            </article>
          ))}
        </div>
      ) : (
        <div className="card panel clan-empty-panel">{getTextSync('clan_territories_empty')}</div>
      )}
      {legacyEconomy && <div className="section card panel clan-border-summary">
        <h3>{getTextSync('clan_border')}</h3>
        <p className="muted">{getTextSync('clan_border_copy')}</p>
        <div className="chip-row">{vulnerable.map((territory) => <span className={`chip ${Number(territory.fortifications || 0) < 5 ? 'danger' : ''}`} key={territory.id}>{getTextSync('clan_border_defence', null, { territory: getTerritoryName(territory.name, language), value: territory.fortifications || 0 })}</span>)}{!vulnerable.length && <span className="chip">{getTextSync('clan_border_empty')}</span>}</div>
      </div>}
    </section>
    );
  };

  const renderClanHistory = () => {
    if (cycleHistoryMode) return <section className="clan-history-panel clan-cycle-history">
      <h2>{cycleMessage('cycle_history', language)}</h2>
      {cycleHistoryState.error && <p role="alert">{clanHistoryMessage('unavailable', language)}</p>}
      <div className="table-wrap"><table className="table"><thead><tr><th>{getTextSync('profile_match_opponent')}</th><th>{getTextSync('common_unknown_territory')}</th><th>{getTextSync('clan_battle_score')}</th><th>{getTextSync('profile_match_result')}</th></tr></thead>
        <CycleHistoryRows battles={cycleHistory?.battles || []} clanId={clanId} language={language} t={getTextSync} loading={!cycleHistory && !cycleHistoryState.error} />
      </table></div>
      <LegacyWarArchive key={clanId} clanId={clanId} language={language} t={getTextSync} />
    </section>;
    const history = [
      {
        key: 'created',
        date: clan.created_at,
        title: getTextSync('clan_history_founded'),
        description: getTextSync('clan_history_founded_copy', null, { clan: clan.name }),
      },
      ...clanWars.filter((war) => war.status === 'completed').map((war) => ({
        key: `war-${war.id}`,
        date: war.ended_at || war.started_at,
        title: getTextSync(Number(war.winner_clan_id) === Number(clan.id) ? 'clan_history_war_victory' : 'clan_history_war_completed'),
        description: getTextSync('clan_history_battle_copy', null, { territory: getTerritoryName(war.territory_name, language) }),
        warId: war.id,
      })),
    ].sort((left, right) => new Date(right.date || 0) - new Date(left.date || 0));

    const completed = clanWars.filter((war) => war.status === 'completed');
    const wins = completed.filter((war) => Number(war.winner_clan_id) === Number(clan.id)).length;
    return (
      <section className="grid g2 clan-history-panel">
        <div className="card panel">
          <div className="eyebrow">{getTextSync('clan_chronicle')}</div><h2>{getTextSync('homepage_current_season')}</h2>
          <div className="history-list">
            {history.slice(0, 8).map((event) => <div key={event.key}><time>{formatMoscowDateTime(event.date, '—', language)}</time><b>{event.warId ? <Link to={`/battles/${event.warId}`}>{event.title}</Link> : event.title}</b><p>{event.description}</p></div>)}
          </div>
        </div>
        <div className="card panel">
          <div className="eyebrow">{getTextSync('chronicle_season_archive')}</div><h2>{getTextSync('clan_history_best_results')}</h2>
          <div className="table-wrap"><table className="table"><thead><tr><th>{getTextSync('clan_history_period')}</th><th>{getTextSync('clans_place')}</th><th>{getTextSync('seasons_lands')}</th><th>{getTextSync('profile_winrate')}</th></tr></thead><tbody><tr><td>{getTextSync('clan_history_current')}</td><td>#{clan.rank || '—'}</td><td>{ownedTerritories.length}</td><td>{completed.length ? Math.round((wins / completed.length) * 100) : 0}%</td></tr></tbody></table></div>
          <p className="muted clan-history-note">{getTextSync('clan_history_archive_note')}</p>
        </div>
      </section>
    );
  };

  if (loading) {
    return (
      <Container>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container>
        <Alert severity="error" sx={{ mt: 4 }}>
          {getTextSync('clan_loading_error', 'Ошибка при загрузке данных клана')}
        </Alert>
      </Container>
    );
  }

  if (!clan) {
    return (
      <Container>
        <Alert severity="warning" sx={{ mt: 4 }}>
          {getTextSync('clan_not_found', 'Клан не найден')}
        </Alert>
      </Container>
    );
  }

  return (
    <Container maxWidth={false} className={`clan-view-page prototype-exact-page${economyTab && !isEditing ? ' clan-view-page--economy' : ''}`}>
      {clan.is_deleted && (
        <Alert severity="info" className="clan-archived-notice">
          <strong>{getTextSync('clan_archived', 'Клан расформирован')}.</strong>{' '}
          {getTextSync('clan_archived_notice', 'Клан сохранён в истории: его земли, влияние и войны остаются на карте, но новых действий от его имени быть не может.')}
        </Alert>
      )}
      
      {/* Заголовок клана */}
      <Paper component="header" className="clan-header">
        <Box display="flex" justifyContent="space-between" alignItems="flex-start" className="clan-header-layout">
          <Box display="flex" alignItems="center" className="clan-identity">
            {isLeader ? (
              <ClanAvatarUpload
                clanId={clanId}
                currentAvatarUrl={clan.avatar_url}
                onAvatarUpdate={handleAvatarUpdate}
                size={economyTab && !isEditing ? 64 : 104}
              />
            ) : (
              <Avatar
                key={`clan-avatar-${clan.avatar_url}`} // Принудительное обновление при изменении URL
                src={clan.avatar_url ? `${clan.avatar_url}?t=${Date.now()}` : '/default-clan-avatar.png'}
                sx={{ width: economyTab && !isEditing ? 64 : 104, height: economyTab && !isEditing ? 64 : 104 }}
              >
                <Group />
              </Avatar>
            )}
            <Box className="clan-copy">
              {isEditing ? (
                <Box>
                  <TextField
                    value={editData.name}
                    onChange={(e) => setEditData({ ...editData, name: e.target.value })}
                    variant="outlined"
                    size="small"
                    sx={{ mb: 1 }}
                  />
                  <TextField
                    value={editData.motto || ''}
                    onChange={(e) => setEditData({ ...editData, motto: e.target.value })}
                    variant="outlined"
                    size="small"
                    fullWidth
                    label={getTextSync('clans_motto_label', 'Девиз клана')}
                    inputProps={{ maxLength: 160 }}
                    sx={{ mb: 1 }}
                  />
                  <TextField
                    value={editData.description}
                    onChange={(e) => setEditData({ ...editData, description: e.target.value })}
                    variant="outlined"
                    multiline
                    rows={2}
                    fullWidth
                  />
                  <FormControl fullWidth size="small" sx={{ mt: 1 }}>
                    <InputLabel id="edit-clan-patch-label">{getTextSync('clans_game_patch', 'Игровой патч')}</InputLabel>
                    <Select
                      labelId="edit-clan-patch-label"
                      value={editData.preferred_patch || 'all'}
                      label={getTextSync('clans_game_patch', 'Игровой патч')}
                      onChange={(event) => setEditData({
                        ...editData,
                        preferred_patch: event.target.value,
                      })}
                    >
                      <MenuItem value="patch_202">Patch 2.02</MenuItem>
                      <MenuItem value="ennorath">Ennorath</MenuItem>
                      <MenuItem value="all">{getTextSync('clans_both_patches', 'Оба патча')}</MenuItem>
                    </Select>
                  </FormControl>
                  {!clan.is_admin_clan && (
                    <FormControlLabel
                      sx={{ mt: 1, ml: 0 }}
                      control={(
                        <Switch
                          checked={editData.is_recruiting !== false}
                          onChange={(event) => setEditData({
                            ...editData,
                            is_recruiting: event.target.checked,
                          })}
                        />
                      )}
                      label={getTextSync('clan_recruiting_toggle', 'Клан принимает заявки')}
                    />
                  )}
                  {!clan.is_admin_clan && (
                    <ClanColorPicker
                      value={editData.map_color}
                      clanId={Number(clanId)}
                      allowAdminOverride={isAdmin}
                      label={getTextSync('clan_choose_map_color', 'Выберите цвет владений')}
                      onChange={(mapColor) => setEditData({
                        ...editData,
                        map_color: mapColor,
                      })}
                    />
                  )}
                </Box>
              ) : (
                <Box>
                  <Typography variant="h4" gutterBottom className="clan-name serif">
                    {clan.name}
                  </Typography>
                  <Chip
                    className="clan-level-badge"
                    color="primary"
                    variant="outlined"
                    label={getTextSync('clan_level_badge', null, { level: clan.level ?? 1 })}
                  />
                  <Typography variant="body1" color="text.secondary" paragraph>{clan.motto || getTextSync('clan_description_missing', 'Описание отсутствует')} · {getTextSync('clan_founded_in', null, { year: new Date(clan.created_at).getFullYear() })}</Typography>
                  <RulesContextLink context="clan" section="getting-started" />
                 </Box>
              )}
            </Box>
          </Box>
          
          {!clan.is_deleted && <details
            className={`clan-management-menu${canApplyToClan ? ' clan-management-menu--direct-application' : ''}`}
            open={canApplyToClan ? true : undefined}
          >
            <summary>{(isLeader || canManageAdminClan)
              ? getTextSync('clan_management')
              : canApplyToClan
                ? (clan.is_recruiting !== false
                  ? getTextSync('clan_apply', 'Подать заявку')
                  : getTextSync('clans_recruiting_closed', 'Набор закрыт'))
                : getTextSync('clan_actions')}</summary>
            <Box display="flex" gap={1} className="clan-actions">
            {(isLeader || canManageAdminClan) && (
              <>
                {isEditing ? (
                  <>
                    <Button
                      variant="contained"
                      onClick={handleUpdateClan}
                      size="small"
                    >
                      {getTextSync('clan_save', 'Сохранить')}
                    </Button>
                    <Button
                      variant="outlined"
                      onClick={() => setIsEditing(false)}
                      size="small"
                    >
                      {getTextSync('clan_cancel', 'Отмена')}
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      variant="outlined"
                      startIcon={<Edit />}
                      onClick={() => setIsEditing(true)}
                      size="small"
                    >
                      {getTextSync('clan_edit', 'Редактировать')}
                    </Button>
                    <Button
                      variant="outlined"
                      startIcon={<PersonAdd />}
                      onClick={() => setInviteDialogOpen(true)}
                      size="small"
                    >
                      {clan.is_admin_clan
                        ? getTextSync('clan_appoint_member', 'Назначить участника')
                        : getTextSync('clan_invite', 'Пригласить')}
                    </Button>
                    {!clan.is_admin_clan && <Button
                      variant="outlined"
                      startIcon={<Group />}
                      onClick={handleOpenApplications}
                      size="small"
                    >
                      {getTextSync('clan_applications', 'Заявки')} ({applications.length})
                    </Button>}
                    {canManageAdminClan && (
                      <Button
                        variant="outlined"
                        color="warning"
                        startIcon={<AutoAwesome />}
                        onClick={handleResetAdminSandbox}
                        size="small"
                      >
                        {getTextSync('clan_admin_sandbox_button')}
                      </Button>
                    )}
                    {!clan.is_admin_clan && <Button
                      variant="contained"
                      color="error"
                      startIcon={<Delete />}
                      onClick={handleDeleteClan}
                      size="small"
                      className="error"
                    >
                      {getTextSync('clan_delete', 'Удалить клан')}
                    </Button>}
                  </>
                )}
              </>
            )}
            
            {isMember && !isLeader && (
              <Button
                variant="outlined"
                color="error"
                startIcon={<ExitToApp />}
                onClick={handleLeaveClan}
                size="small"
                className="error"
              >
                {getTextSync('clan_leave', 'Покинуть клан')}
              </Button>
            )}
            
            {/* Кнопка подачи заявки для пользователей без клана */}
            {canApplyToClan && clan.is_recruiting !== false && (
              <Button
                variant="contained"
                color="primary"
                startIcon={<PersonAdd />}
                onClick={() => setApplicationDialogOpen(true)}
                size="small"
              >
                {getTextSync('clan_apply', 'Подать заявку')}
              </Button>
            )}

            {canApplyToClan && clan.is_recruiting === false && (
              <Alert severity="info" variant="outlined">
                {getTextSync('clans_recruiting_closed', 'Набор закрыт')}
              </Alert>
            )}

            {!isMember && user && !userClan && clan.is_admin_clan && (
              <Alert severity="info" variant="outlined">
                {getTextSync('clan_admin_members_only', 'В этот системный клан участников назначает только администратор.')}
              </Alert>
            )}
            
            {/* Информация для пользователей, которые уже состоят в другом клане */}
            {!isMember && !isLeader && user && userClan && (
              <Typography variant="body2" color="text.secondary">
                {getTextSync('clan_already_in_clan', 'Вы уже состоите в клане')} "{userClan.name}"
              </Typography>
            )}
            </Box>
          </details>}
        </Box>
        {legacyEconomy && <Box className="clan-header-resource-ribbon">
          <Box className="eyebrow">{getTextSync('clan_treasury', 'Казна и влияние')}</Box>
          <ClanResourceSummary
            economy={clanEconomy}
            getResourceLabel={resourceLabel}
            ariaLabel={getTextSync('clan_resources_aria')}
          />
        </Box>}
        {campaign.error && <Alert severity="warning" action={<Button onClick={campaign.refresh}>{cycleMessage('common_retry', language)}</Button>}>{cycleMessage('cycle_request_failed', language)}</Alert>}
      </Paper>

      {/* Участники клана - расширенная секция */}
      <Paper className="clan-section-tabs">
        <Tabs value={sectionTab} onChange={(e, newValue) => setClanSectionTab(newValue)} variant="scrollable" scrollButtons="auto">
          <Tab value={0} label={getTextSync('clan_tab_overview', 'Обзор')} />
          <Tab value={1} label={getTextSync('clan_tab_members', 'Игроки')} />
          <Tab value={2} label={getTextSync('clan_tab_territories', 'Территории')} />
          {cycleEconomy && economyTabs.map(([value, label]) => <Tab key={value} value={value} label={label}
            id={`clan-economy-tab-${value}`} aria-controls={`ce-panel-${value}`} />)}
          {legacyEconomy && <Tab value={3} label={getTextSync('clan_tab_market', 'Торговля')} />}
          {legacyEconomy && <Tab value={4} label={getTextSync('clan_tab_relics', 'Реликвии клана')} />}
          {legacyEconomy && <Tab value={5} label={getTextSync('clan_tab_battles', 'Битвы')} />}
          <Tab value={6} label={getTextSync('clan_tab_history', 'История')} />
        </Tabs>
      </Paper>

      {sectionTab === 0 && (
        renderClanOverview()
      )}

      {sectionTab === 1 && renderClanPlayersPrototype()}

      {sectionTab === 2 && renderClanTerritories()}

      {cycleEconomy && (economyTab || economyVisited) && <div className="clan-cycle-economy" hidden={!economyTab}>
        <EconomyContent key={`${user.id}:${cycleId}:${clanId}`} cycleId={cycleId} clanId={clanId}
          activeTab={economyTab || 'relics'} visible={Boolean(economyTab)} tradeMode={requestedTab === 'barter' ? 'barter' : 'market'}
          onTradeModeChange={setClanSectionTab} embedded labelledBy={`clan-economy-tab-${economyTab}`} />
      </div>}

      {legacyEconomy && sectionTab === 3 && renderMarket()}

      {legacyEconomy && sectionTab === 4 && renderClanRelicsPrototype()}

      {legacyEconomy && sectionTab === 5 && renderClanBattlesPrototype()}

      {sectionTab === 6 && renderClanHistory()}

      {/* Модальное окно приглашения */}
      <Dialog open={inviteDialogOpen} onClose={handleCloseInviteDialog} maxWidth="sm" fullWidth className="invite-dialog">
        <DialogTitle>{getTextSync('clan_invite_user_title', 'Пригласить пользователя')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label={getTextSync('clan_invite_username_label', 'Имя пользователя')}
            fullWidth
            variant="outlined"
            value={inviteUsername}
            onChange={handleSearchChange}
            InputProps={{
              endAdornment: searching ? <CircularProgress size={20} /> : null,
            }}
          />
          {searchResults.length > 0 && (
            <Box sx={{ mt: 2 }} className="search-results-container">
              <Typography variant="subtitle2" color="text.secondary">
                {getTextSync('clan_search_results', 'Результаты поиска')} ({searchResults.length}):
              </Typography>
              <List>
                {searchResults.map((user) => (
                  <ListItem
                    button
                    key={user.id}
                    onClick={() => handleSelectUser(user)}
                    selected={inviteUsername === user.username}
                  >
                    <ListItemAvatar>
                      <Avatar src={user.avatar_url}>
                        {user.username ? user.username.charAt(0).toUpperCase() : '?'}
                      </Avatar>
                    </ListItemAvatar>
                    <ListItemText primary={<PlayerIdentity username={user.username} usernameClassName="entity-link" />} />
                    <ListItemSecondaryAction>
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<PersonAdd />}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleInviteSpecificUser(user);
                        }}
                      >
                        {clan?.is_admin_clan ? getTextSync('clan_appoint') : getTextSync('clan_invite_specific_user', 'Пригласить')}
                      </Button>
                    </ListItemSecondaryAction>
                  </ListItem>
                ))}
              </List>
            </Box>
          )}
          {searchResults.length === 0 && inviteUsername.trim() && !searching && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary">
                {getTextSync('clan_users_not_found', 'Пользователи не найдены')}
              </Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseInviteDialog}>
            {getTextSync('clan_close', 'Закрыть')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Модальное окно заявок */}
      <Dialog 
        open={applicationsDialogOpen} 
        onClose={() => setApplicationsDialogOpen(false)}
        maxWidth="md"
        fullWidth
        className="applications-dialog"
      >
        <DialogTitle>{getTextSync('clan_applications_title', 'Заявки на вступление в клан')}</DialogTitle>
        <DialogContent>
          {applications.length === 0 ? (
            <Box display="flex" justifyContent="center" alignItems="center" minHeight="200px">
              <Typography variant="body1" color="text.secondary">
                {getTextSync('clan_no_applications', 'Заявок на вступление нет')}
              </Typography>
            </Box>
          ) : (
            <List>
              {applications.map((application) => (
                <ListItem key={application.id} divider className="application-item">
                  <ListItemAvatar>
                    <Avatar src={application.user.avatar_url}>
                      {application.user.username ? application.user.username.charAt(0).toUpperCase() : '?'}
                    </Avatar>
                  </ListItemAvatar>
                  <ListItemText
                    primary={<PlayerIdentity username={application.user.username} usernameClassName="entity-link" />}
                    secondary={
                      <Box>
                        <Typography variant="body2" color="text.secondary">
                          {application.message || getTextSync('clan_application_message_not_specified', 'Сообщение не указано')}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {getTextSync('clan_application_submitted_at', 'Подана')}: {new Date(application.created_at).toLocaleDateString(locale)}
                        </Typography>
                      </Box>
                    }
                  />
                  <ListItemSecondaryAction className="application-actions">
                    <IconButton
                      size="small"
                      color="success"
                      className="accept"
                      onClick={() => handleApplicationResponse(application.id, 'accepted')}
                    >
                      <Check />
                    </IconButton>
                    <IconButton
                      size="small"
                      color="error"
                      className="decline"
                      onClick={() => handleApplicationResponse(application.id, 'declined')}
                    >
                      <Close />
                    </IconButton>
                  </ListItemSecondaryAction>
                </ListItem>
              ))}
            </List>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setApplicationsDialogOpen(false)}>
            {getTextSync('clan_close', 'Закрыть')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Модальное окно подачи заявки */}
      <Dialog 
        open={applicationDialogOpen} 
        onClose={() => setApplicationDialogOpen(false)}
        maxWidth="sm"
        fullWidth
        className="application-dialog"
      >
        <DialogTitle>{getTextSync('clan_apply_to_clan_title', 'Подать заявку на вступление в клан')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label={getTextSync('clan_application_message_label', 'Сообщение для клана')}
            fullWidth
            multiline
            rows={3}
            variant="outlined"
            value={applicationMessage}
            onChange={(e) => setApplicationMessage(e.target.value)}
            sx={{ mb: 2 }}
          />
          <Typography variant="body2" color="text.secondary">
            {getTextSync('clan_application_please_write', 'Пожалуйста, напишите сообщение, почему вы хотите вступить в этот клан. Это поможет лидеру понять вашу мотивацию.')}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setApplicationDialogOpen(false)}>
            {getTextSync('clan_cancel', 'Отмена')}
          </Button>
          <Button
            variant="contained"
            onClick={handleSubmitApplication}
            disabled={submittingApplication}
          >
            {submittingApplication ? <CircularProgress size={24} /> : getTextSync('clan_submit_application', 'Подать заявку')}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
};

export default ClanViewPage; 
