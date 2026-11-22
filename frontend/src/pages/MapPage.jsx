import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Alert, Avatar, Box, Button, Typography, Paper, Container, IconButton, Tooltip, Chip, Divider, Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress, LinearProgress, TextField, MenuItem, FormControlLabel, Switch, Drawer, useMediaQuery } from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { FullscreenExit, Close, Shield, Security, People, AttachMoney, LocationOn, Flag, TrendingUp, Construction, MilitaryTech, AccessTime, CheckCircle, Anchor, DirectionsBoat, Settings } from '@mui/icons-material';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { useAuth } from '../contexts/AuthContext';
import useCampaignNavigation from '../hooks/useCampaignNavigation';
import useCycleMap from '../hooks/useCycleMap';
import useUpcomingMap from '../hooks/useUpcomingMap';
import usePreseasonStatus from '../hooks/usePreseasonStatus';
import { CycleMapLayer, CycleMapPanel, CycleMapTerritorySummary, CycleMapLegend } from '../components/map/CycleMap';
import MapCycleSchedule from '../components/map/MapCycleSchedule';
import { campaignTerritoryBattle } from '../utils/campaignNavigation';
import { isArchiveInterseason } from '../utils/seasonArchive';
import { cycleMessage } from '../utils/cycleBattleView';
import { Link } from 'react-router-dom';
import { clanService } from '../services/clanService';
import { territoryService } from '../services/territoryService';
import { warService } from '../services/warService';
import { diplomacyService } from '../services/diplomacyService';
import { publicFetch } from '../services/apiFetch';
import { formatMoscowDateTime } from '../utils/dateTime';
import {
  CLAN_COLORS,
  CLAN_TERRITORY_HOVER_OPACITY,
  CLAN_TERRITORY_OPACITY,
  CLAN_TERRITORY_SELECTED_OPACITY,
  getClanTerritoryPaint,
} from '../constants/clanColors';
import { getTerritoryDescription, getTerritoryName } from '../i18n/territories';
import { getWarScoreSplit } from '../utils/mapWarVisuals';
import WarDeploymentDialog from '../components/WarDeploymentDialog';
import MapCanvasControls from '../components/map/MapCanvasControls';
import MapSearchToolbar from '../components/map/MapSearchToolbar';
import RulesContextLink from '../components/RulesContextLink';
import {
  FoodResourceIcon as KebabDining,
  GoldResourceIcon as MonetizationOn,
  IronResourceIcon as Hardware,
  MithrilResourceIcon as Diamond,
  WoodResourceIcon as Forest,
} from '../components/ResourceIcon';
import './MapPage.css';

const PROTECTED_ADMIN_TERRITORIES = new Set(['Тол-Фалас']);
const DEFAULT_MAP_LAYERS = {
  wars: true,
  trade: true,
  clanIcons: true,
  attackable: false,
};

const NEUTRAL_STYLE = { fill: 'rgba(116, 125, 118, 0.22)', stroke: 'rgba(230, 226, 205, 0.42)' };
const WAR_STYLE = { fill: 'rgba(220, 53, 69, 0.68)', stroke: '#ffdb6d' };
const RELATION_STROKES = {
  own: '#72c98b',
  allied: '#77b9ff',
  enemy: '#ef7979',
  neutral: '#a7aaa5',
};

const areTerritoriesAdjacent = (source, target) => {
  if (!source?.id || !target?.id) return false;
  const sourceAdjacent = Array.isArray(source.adjacent_territory_ids) ? source.adjacent_territory_ids.map(Number) : [];
  const targetAdjacent = Array.isArray(target.adjacent_territory_ids) ? target.adjacent_territory_ids.map(Number) : [];
  return sourceAdjacent.includes(Number(target.id)) || targetAdjacent.includes(Number(source.id));
};

const canReachTerritory = (source, target) => Boolean(
  source?.id
  && target?.id
  && (
    areTerritoriesAdjacent(source, target)
    || (source.has_port && target.is_coastal)
  )
);

const CLAN_PALETTE = CLAN_COLORS.map(getClanTerritoryPaint);
const SVG_NAMESPACE = 'http://www.w3.org/2000/svg';

const appendWarFillGradient = (defs, {
  id,
  attackerColor,
  defenderColor,
  attackerShare,
  opacity,
}) => {
  const gradient = document.createElementNS(SVG_NAMESPACE, 'linearGradient');
  gradient.setAttribute('id', id);
  gradient.setAttribute('x1', '0%');
  gradient.setAttribute('y1', '0%');
  gradient.setAttribute('x2', '100%');
  gradient.setAttribute('y2', '0%');

  [
    { offset: '0%', color: attackerColor },
    { offset: `${attackerShare}%`, color: attackerColor },
    { offset: `${attackerShare}%`, color: defenderColor },
    { offset: '100%', color: defenderColor },
  ].forEach(({ offset, color }) => {
    const stop = document.createElementNS(SVG_NAMESPACE, 'stop');
    stop.setAttribute('offset', offset);
    stop.setAttribute('stop-color', color);
    stop.setAttribute('stop-opacity', String(opacity));
    gradient.appendChild(stop);
  });

  defs.appendChild(gradient);
};

const getStaticMapEmblemUrl = (avatarUrl) => {
  if (!avatarUrl || typeof window === 'undefined') return null;
  try {
    const parsed = new URL(avatarUrl, window.location.origin);
    if (parsed.origin !== window.location.origin) return null;
    const match = parsed.pathname.match(/^\/images\/clans\/([^/]+)$/);
    return match
      ? `/api/v1/clans/map-emblem/${encodeURIComponent(match[1])}`
      : null;
  } catch {
    return null;
  }
};

const RESOURCE_META = {
  gold: { labelKey: 'resource_gold', fallback: 'Золото', color: '#f6c453', Icon: MonetizationOn },
  iron: { labelKey: 'resource_iron', fallback: 'Железо', color: '#aeb7c2', Icon: Hardware },
  wood: { labelKey: 'resource_wood', fallback: 'Дерево', color: '#62a66f', Icon: Forest },
  food: { labelKey: 'resource_food', fallback: 'Еда', color: '#ef6c5b', Icon: KebabDining },
  mithril: { labelKey: 'resource_mithril', fallback: 'Мифрил', color: '#65c7e8', Icon: Diamond },
};

const TERRITORY_UPGRADES = {
  population: { labelKey: 'map_upgrade_population', descriptionKey: 'map_upgrade_population_description', Icon: People, color: '#66bb6a' },
  fortifications: { labelKey: 'map_upgrade_fortifications', descriptionKey: 'map_upgrade_fortifications_description', Icon: Construction, color: '#90a4ae' },
  offense: { labelKey: 'map_upgrade_offense', descriptionKey: 'map_upgrade_offense_description', Icon: MilitaryTech, color: '#ef5350' },
  naval: { labelKey: 'map_upgrade_naval', descriptionKey: 'map_upgrade_naval_description', Icon: DirectionsBoat, color: '#42a5f5' },
};

const getPopulationIncomeBonusPercent = (population) => (
  Math.round(Math.min(20, Math.max(0, Number(population) || 0) / 100) * 100) / 100
);

const getDailyIncomePreview = (baseIncome, population) => {
  const base = Math.max(0, Number(baseIncome) || 0);
  const populationBonus = getPopulationIncomeBonusPercent(population);
  return Math.round(base * (1 + populationBonus / 100) * 100) / 100;
};

const CaravanGlyph = ({ className = '' }) => (
  <span className={`caravan-glyph ${className}`} aria-hidden="true">🐪</span>
);

const MapPage = () => {
  const { getLocalizedText, loadPageTexts, language } = useLocalizationContext();
  const { user } = useAuth();
  const { navigation: lastCampaignNavigation, loading: campaignNavigationLoading,
    error: campaignNavigationError, refresh: refreshCampaignNavigation } = useCampaignNavigation(60_000);
  const campaignNavigation = campaignNavigationLoading ? null : lastCampaignNavigation;
  const isInterseason = isArchiveInterseason(campaignNavigation);
  const upcomingMap = useUpcomingMap(isInterseason);
  const preseason = usePreseasonStatus();
  const isLegacyCampaign = campaignNavigation?.mode === 'legacy' && !isInterseason;
  const cycleMap = useCycleMap(campaignNavigation?.cycleId, user?.id);
  const legacyDialogAvailable = !campaignNavigationError && lastCampaignNavigation?.mode === 'legacy' && !isArchiveInterseason(lastCampaignNavigation);
  const theme = useTheme();
  const isCompactMap = useMediaQuery(theme.breakpoints.down('md'));
  const territoryName = (territoryOrName) => getTerritoryName(
    typeof territoryOrName === 'string' ? territoryOrName : territoryOrName?.name,
    language,
  );
  const resourceName = (resource, fallbackKey = 'resource_secondary') => {
    const metadata = RESOURCE_META[resource];
    return metadata
      ? getLocalizedText(metadata.labelKey, metadata.fallback)
      : getLocalizedText(fallbackKey, 'второй ресурс');
  };

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [hoveredRegion, setHoveredRegion] = useState(null);
  const [selectedRegion, setSelectedRegion] = useState(null);
  const [svgContent, setSvgContent] = useState('');
  const svgRef = useRef(null);
  const hoverRequestRef = useRef(0);
  const clickRequestRef = useRef(0);
  const [territories, setTerritories] = useState([]);
  const [legacyActiveWars, setActiveWars] = useState([]);
  const activeWars = useMemo(() => isLegacyCampaign ? legacyActiveWars : [], [isLegacyCampaign, legacyActiveWars]);
  const selectedCycleBattle = campaignTerritoryBattle(campaignNavigation, selectedRegion?.id);
  const [tradeCaravans, setTradeCaravans] = useState([]);
  const [myClan, setMyClan] = useState(null);
  const [diplomacy, setDiplomacy] = useState([]);
  const [attackMessage, setAttackMessage] = useState(null);
  const [attackingTerritoryId, setAttackingTerritoryId] = useState(null);
  const [deploymentDialogOpen, setDeploymentDialogOpen] = useState(false);
  const [adminRouteSource, setAdminRouteSource] = useState(null);
  const [territoryDialogOpen, setTerritoryDialogOpen] = useState(false);
  const [managedTerritory, setManagedTerritory] = useState(null);
  const [managedEconomy, setManagedEconomy] = useState(null);
  const [selectedTerritoryEconomy, setSelectedTerritoryEconomy] = useState(null);
  const [economyLoading, setEconomyLoading] = useState(false);
  const [upgradingType, setUpgradingType] = useState(null);
  const [adminDialogOpen, setAdminDialogOpen] = useState(false);
  const [adminForm, setAdminForm] = useState(null);
  const [adminSaving, setAdminSaving] = useState(false);
  const [currentTime, setCurrentTime] = useState(Date.now());
  const [mapLayers, setMapLayers] = useState(DEFAULT_MAP_LAYERS);
  const [layerFilterOpen, setLayerFilterOpen] = useState(false);
  const [mapSearch, setMapSearch] = useState('');
  const [mapRegion, setMapRegion] = useState('all');

  const getClanNames = useCallback((territory, type) => {
    const nameKey = type === 'attacking' ? 'attacking_clan_names' : 'defending_clan_names';
    const idKey = type === 'attacking' ? 'attacking_clans' : 'defending_clans';
    const names = territory?.[nameKey];
    if (Array.isArray(names) && names.length > 0) {
      return names;
    }

    const ids = territory?.[idKey];
    if (Array.isArray(ids) && ids.length > 0) {
      return ids.map(id => getLocalizedText('map_clan_fallback', null, { id }));
    }

    return [];
  }, [getLocalizedText]);

  const getOwnerName = useCallback((territory) => (
    territory?.owner_clan_name
    || territory?.owner
    || (territory?.owner_clan_id
      ? getLocalizedText('map_clan_fallback', null, { id: territory.owner_clan_id })
      : null)
  ), [getLocalizedText]);

  const clanColorByKey = useMemo(() => {
    const keys = [...new Set(
      territories
        .filter((territory) => !territory?.owner_clan_is_admin && (territory?.owner_clan_id || getOwnerName(territory)))
        .map((territory) => String(territory.owner_clan_id || getOwnerName(territory)))
    )].sort((left, right) => left.localeCompare(right, 'ru', { numeric: true }));
    return new Map(keys.map((key, index) => [key, CLAN_PALETTE[index % CLAN_PALETTE.length]]));
  }, [getOwnerName, territories]);

  const clanMapColorById = useMemo(() => {
    const colors = new Map();
    activeWars.forEach((war) => {
      if (war?.attacking_clan_id && war.attacking_clan_map_color) {
        colors.set(Number(war.attacking_clan_id), war.attacking_clan_map_color);
      }
      if (war?.defending_clan_id && war.defending_clan_map_color) {
        colors.set(Number(war.defending_clan_id), war.defending_clan_map_color);
      }
    });
    territories.forEach((territory) => {
      const clanId = Number(territory?.owner_clan_id);
      if (!clanId || territory?.owner_clan_is_admin) return;
      if (territory.owner_clan_map_color) {
        colors.set(clanId, territory.owner_clan_map_color);
        return;
      }
      if (!colors.has(clanId)) {
        const key = String(territory.owner_clan_id || getOwnerName(territory) || '');
        colors.set(clanId, (clanColorByKey.get(key) || CLAN_PALETTE[0]).stroke);
      }
    });
    return colors;
  }, [activeWars, clanColorByKey, getOwnerName, territories]);

  const getClanMapStyle = useCallback((territory) => {
    if (territory?.owner_clan_is_admin) {
      return {
        fill: 'rgba(0, 0, 0, 0)',
        stroke: 'rgba(230, 226, 205, 0.48)',
      };
    }
    const clanColor = territory?.owner_clan_map_color
      || clanMapColorById.get(Number(territory?.owner_clan_id));
    if (clanColor) {
      return getClanTerritoryPaint(clanColor);
    }
    const key = String(territory?.owner_clan_id || getOwnerName(territory) || '');
    return clanColorByKey.get(key) || CLAN_PALETTE[0];
  }, [clanColorByKey, clanMapColorById, getOwnerName]);

  const activeWarsByTerritory = useMemo(() => {
    const index = new Map();
    activeWars
      .filter((war) => war.status === 'active')
      .forEach((war) => {
        const territoryId = Number(war.territory_id);
        if (!index.has(territoryId)) {
          index.set(territoryId, []);
        }
        index.get(territoryId).push(war);
      });
    return index;
  }, [activeWars]);

  const getTerritoryVisualState = useCallback((territory) => {
    const attackers = getClanNames(territory, 'attacking');
    const defenders = getClanNames(territory, 'defending');
    const hasActiveWar = activeWarsByTerritory.has(Number(territory?.id));

    if (hasActiveWar) {
      return 'war';
    }
    if (attackers.length > 0) {
      return 'attack';
    }
    if (defenders.length > 0 && getOwnerName(territory)) {
      return 'defense';
    }
    if (getOwnerName(territory)) {
      return 'owned';
    }
    return 'neutral';
  }, [activeWarsByTerritory, getClanNames, getOwnerName]);

  const territoriesByPath = useMemo(() => {
    const index = new Map();
    territories.forEach(territory => {
      if (territory?.svg_path_data) {
        index.set(territory.svg_path_data, territory);
      }
    });
    return index;
  }, [territories]);

  const territoriesByName = useMemo(() => {
    const index = new Map();
    territories.forEach(territory => {
      if (territory?.name) {
        index.set(territory.name, territory);
      }
    });
    return index;
  }, [territories]);

  const getTerritoryMapStyle = useCallback((territory) => {
    const state = getTerritoryVisualState(territory);

    if (getOwnerName(territory)) return getClanMapStyle(territory);
    if (state === 'war' || territory?.id && activeWarsByTerritory.has(Number(territory.id))) {
      const activeWar = (activeWarsByTerritory.get(Number(territory?.id)) || [])[0];
      return activeWar?.attacking_clan_map_color
        ? getClanTerritoryPaint(activeWar.attacking_clan_map_color)
        : WAR_STYLE;
    }
    return NEUTRAL_STYLE;
  }, [activeWarsByTerritory, getClanMapStyle, getOwnerName, getTerritoryVisualState]);

  const strongholds = useMemo(() => territories
    .filter((territory) => Number(territory.stronghold_power || 0) > 0)
    .sort((left, right) => getTerritoryName(left.name, language).localeCompare(getTerritoryName(right.name, language), language)), [language, territories]);
  const alliedClanIds = useMemo(() => new Set(
    diplomacy.filter((relation) => relation.status === 'allied').map((relation) => (
      Number(relation.clan_low.id) === Number(myClan?.id)
        ? Number(relation.clan_high.id)
        : Number(relation.clan_low.id)
    )),
  ), [diplomacy, myClan?.id]);
  const hostileClanIds = useMemo(() => new Set(
    diplomacy.filter((relation) => relation.status === 'hostile').map((relation) => (
      Number(relation.clan_low.id) === Number(myClan?.id)
        ? Number(relation.clan_high.id)
        : Number(relation.clan_low.id)
    )),
  ), [diplomacy, myClan?.id]);

  const selectSearchResult = () => {
    const query = mapSearch.trim().toLocaleLowerCase(language);
    if (!query) return;
    const match = territories.find((territory) => [territoryName(territory), getOwnerName(territory)]
      .filter(Boolean)
      .some((value) => String(value).toLocaleLowerCase(language).includes(query)));
    if (match) {
      setSelectedRegion(match);
      setHoveredRegion(null);
    }
  };

  const handleMapSearchChange = (value) => {
    setMapSearch(value);
    const exactValue = value.trim().toLocaleLowerCase(language);
    if (!exactValue) return;
    const exactMatch = territories.find((territory) => (
      territoryName(territory).toLocaleLowerCase(language) === exactValue
      || String(getOwnerName(territory) || '').toLocaleLowerCase(language) === exactValue
    ));
    if (exactMatch) {
      setSelectedRegion(exactMatch);
      setHoveredRegion(null);
    }
  };

  const getAttackInfluenceCost = useCallback((territory) => {
    if (!territory) return 0;
    return Math.max(0, Number(territory.required_influence) || 0);
  }, []);

  const getServerDateMs = (value) => {
    if (!value) return 0;
    const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`;
    const timestamp = new Date(normalized).getTime();
    return Number.isNaN(timestamp) ? 0 : timestamp;
  };

  const nextAttackAtMs = getServerDateMs(myClan?.next_attack_at);
  const attackCooldownMs = Math.max(0, nextAttackAtMs - currentTime);
  const isAttackTurnReady = !nextAttackAtMs || attackCooldownMs === 0;
  const formatAttackCooldown = (milliseconds) => {
    const totalSeconds = Math.max(0, Math.ceil(milliseconds / 1000));
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    const parts = [];
    if (days) parts.push(`${days} ${getLocalizedText('time_day_short', 'д.')}`);
    if (days || hours) parts.push(`${hours} ${getLocalizedText('time_hour_short', 'ч.')}`);
    parts.push(`${minutes} ${getLocalizedText('time_minute_short', 'мин.')}`);
    if (!days) parts.push(`${seconds} ${getLocalizedText('time_second_short', 'сек.')}`);
    return parts.join(' ');
  };

  const isAdmin = user?.role?.name === 'admin';
  const isClanLeader = Boolean(myClan && user && myClan.leader_id === user.id);
  const ownedClanTerritories = useMemo(
    () => territories.filter((territory) => Number(territory.owner_clan_id) === Number(myClan?.id)),
    [myClan?.id, territories],
  );
  const clanTerritoryCount = ownedClanTerritories.length;
  const canChallengeNeutralWar = useCallback((territory) => {
    const wars = activeWarsByTerritory.get(Number(territory?.id)) || [];
    return wars.length === 1
      && wars[0].war_type === 'neutral_capture'
      && !wars[0].defending_clan_id
      && wars[0].attacking_clan_id !== myClan?.id;
  }, [activeWarsByTerritory, myClan?.id]);
  const isCampaignTargetAvailable = useCallback((territory) => Boolean(
    isLegacyCampaign && territory?.id
    && territory.is_playable !== false
    && !PROTECTED_ADMIN_TERRITORIES.has(territory.name)
    && Number(territory.owner_clan_id || 0) !== Number(myClan?.id)
    && (territory.required_territories || 0) <= clanTerritoryCount
    && ((activeWarsByTerritory.get(Number(territory.id)) || []).length === 0 || canChallengeNeutralWar(territory))
  ), [activeWarsByTerritory, canChallengeNeutralWar, clanTerritoryCount, myClan?.id, isLegacyCampaign]);
  const findAttackSourceForTarget = useCallback((territory) => {
    if (!territory?.id || clanTerritoryCount === 0) return null;
    return ownedClanTerritories.find((source) => canReachTerritory(source, territory)) || null;
  }, [clanTerritoryCount, ownedClanTerritories]);
  const attackSource = useMemo(() => (
    mapLayers.attackable
    && selectedRegion?.id
    && Number(selectedRegion.owner_clan_id) === Number(myClan?.id)
      ? selectedRegion
      : null
  ), [mapLayers.attackable, myClan?.id, selectedRegion]);
  const isAttackTargetForSource = useCallback((source, territory) => Boolean(
    source?.id
    && Number(source.owner_clan_id) === Number(myClan?.id)
    && isCampaignTargetAvailable(territory)
    && !alliedClanIds.has(Number(territory?.owner_clan_id || 0))
    && (myClan?.territory_points || 0) >= getAttackInfluenceCost(territory)
    && canReachTerritory(source, territory)
  ), [alliedClanIds, getAttackInfluenceCost, isCampaignTargetAvailable, myClan?.id, myClan?.territory_points]);
  const isSelectedOwnTerritory = Boolean(
    selectedRegion?.id
    && myClan
    && Number(selectedRegion.owner_clan_id) === Number(myClan.id)
  );
  const selectedAttackSource = selectedRegion?.id
    ? findAttackSourceForTarget(selectedRegion)
    : null;
  const canAttackSelected = Boolean(
    selectedRegion?.id
    && isClanLeader
    && isAttackTurnReady
    && Number(selectedRegion.owner_clan_id || 0) !== Number(myClan?.id)
    && !alliedClanIds.has(Number(selectedRegion.owner_clan_id || 0))
    && isCampaignTargetAvailable(selectedRegion)
    && (clanTerritoryCount === 0 || selectedAttackSource)
    && (myClan?.territory_points || 0) >= getAttackInfluenceCost(selectedRegion)
  );

  const getAttackDisabledReason = (territory) => {
    if (!territory?.id) return getLocalizedText('map_select_territory_reason', 'Выберите территорию на карте');
    if (!myClan) return getLocalizedText('map_clan_required_reason', 'Для атаки необходимо состоять в клане');
    if (!isClanLeader) return getLocalizedText('map_leader_required_reason', 'Атаку может начать только глава клана');
    if (!isAttackTurnReady) return getLocalizedText('map_next_attack', null, { time: formatAttackCooldown(attackCooldownMs) });
    if (territory.is_playable === false) return getLocalizedText('map_unavailable_reason', 'Эта территория пока недоступна в кампании');
    if (PROTECTED_ADMIN_TERRITORIES.has(territory.name)) return getLocalizedText('map_admin_island_reason', 'Административный остров нельзя атаковать');
    if (Number(territory.owner_clan_id) === Number(myClan.id)) return getLocalizedText('map_own_territory_reason', 'Нельзя атаковать свою территорию');
    if (alliedClanIds.has(Number(territory.owner_clan_id || 0))) {
      return getLocalizedText('map_allied_attack_reason', 'Нельзя атаковать территорию союзного клана');
    }
    if ((territory.required_territories || 0) > clanTerritoryCount) {
      return getLocalizedText('map_required_territories_reason', null, { count: territory.required_territories });
    }
    if (clanTerritoryCount > 0 && !findAttackSourceForTarget(territory)) return getLocalizedText('map_no_route_reason', 'До цели нет сухопутного или морского пути');
    if ((myClan.territory_points || 0) < getAttackInfluenceCost(territory)) {
      return getLocalizedText('map_influence_shortage_reason', null, {
        required: getAttackInfluenceCost(territory),
        current: myClan.territory_points || 0,
      });
    }
    if ((activeWarsByTerritory.get(Number(territory.id)) || []).length > 0 && !canChallengeNeutralWar(territory)) return getLocalizedText('map_war_already_active_reason', 'За эту территорию уже воюют два клана');
    return '';
  };

  function renderClanLinks(territory, type) {
    const names = getClanNames(territory, type);
    const ids = territory?.[type === 'attacking' ? 'attacking_clans' : 'defending_clans'] || [];
    return names.reduce((items, name, index) => {
      const clanId = ids[index];
      const link = clanId ? (
        <Link key={`${name}-${clanId}`} className="entity-link" to={`/clans/${clanId}`}>{name}</Link>
      ) : <span key={`${name}-${index}`}>{name}</span>;
      return index === 0 ? [link] : [...items, ', ', link];
    }, []);
  }

  const normalizeTerritory = useCallback((territory, fallback) => ({
    ...fallback,
    ...territory,
    name: territory?.name || fallback?.name || getLocalizedText('map_unknown_territory', 'Неизвестная территория'),
    region: territory?.region || fallback?.region || null,
    svg_path_data: territory?.svg_path_data || fallback?.svg_path_data || null,
    status: territory?.status || 'neutral',
    trade_routes: territory?.trade_routes || [],
    special_resources: territory?.special_resources || [],
  }), [getLocalizedText]);

  const resolveTerritoryForPath = useCallback(async (path) => {
    const regionName = path.getAttribute('data-name');
    const regionId = path.getAttribute('data-region');
    const pathData = path.getAttribute('d');
    const fallback = {
      id: `${regionId || 'region'}:${regionName || pathData?.slice(0, 16)}`,
      name: regionName,
      region: regionId,
      svg_path_data: pathData,
      status: 'neutral',
    };

    let territory = null;
    if (pathData && territoriesByPath.has(pathData)) {
      territory = territoriesByPath.get(pathData);
    }
    if (!territory && regionName && territoriesByName.has(regionName)) {
      territory = territoriesByName.get(regionName);
    }
    if (!territory && pathData) {
      territory = await territoryService.getTerritoryByPathData(pathData);
    }
    if (!territory && regionName) {
      territory = await territoryService.getTerritoryByName(regionName);
    }
    if (!territory && regionId && Number.isInteger(Number(regionId))) {
      territory = await territoryService.getTerritoryById(regionId);
    }

    return normalizeTerritory(territory, fallback);
  }, [normalizeTerritory, territoriesByName, territoriesByPath]);

  useEffect(() => {
    loadPageTexts('map', language);
    // Загружаем статистику территорий
    loadMapData();
  }, [language, loadPageTexts]);

  useEffect(() => {
    if ((!myClan?.next_attack_at || isAttackTurnReady) && !tradeCaravans.length) {
      return undefined;
    }
    const timer = window.setInterval(() => setCurrentTime(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [myClan?.next_attack_at, isAttackTurnReady, tradeCaravans.length]);

  useEffect(() => {
    const territoryId = selectedRegion?.id;
    if (!territoryId || !isLegacyCampaign) {
      setSelectedTerritoryEconomy(null);
      return undefined;
    }

    let cancelled = false;
    setSelectedTerritoryEconomy(null);
    territoryService.getTerritoryEconomy(territoryId)
      .then((economy) => {
        if (!cancelled) setSelectedTerritoryEconomy(economy);
      })
      .catch(() => {
        if (!cancelled) setSelectedTerritoryEconomy(null);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedRegion?.id, isLegacyCampaign]);

  const loadMapData = async () => {
    try {
      const [allTerritories, wars, market] = await Promise.all([
        territoryService.getAllTerritories(),
        warService.getActiveWars().catch(() => []),
        clanService.getMarket().catch(() => ({ caravans: [] })),
      ]);
      setTerritories(allTerritories);
      setActiveWars(wars);
      setTradeCaravans(market.caravans || []);

      try {
        const clan = await clanService.getMyClan();
        const economy = await clanService.getClanEconomy(clan.id).catch(() => ({}));
        setMyClan({ ...clan, ...economy });
        setDiplomacy(await diplomacyService.list(clan.id).catch(() => []));
      } catch {
        setMyClan(null);
        setDiplomacy([]);
      }
    } catch (error) {
      console.error('Error loading territory map data:', error);
    }
  };

  useEffect(() => {
    const timer = window.setInterval(() => {
      warService.getActiveWars()
        .then(setActiveWars)
        .catch(() => {});
    }, 10 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, []);

  const openTerritoryManagement = async (territory) => {
    if (!isLegacyCampaign) return;
    setManagedTerritory(territory);
    setManagedEconomy(null);
    setTerritoryDialogOpen(true);
    setEconomyLoading(true);
    try {
      setManagedEconomy(await territoryService.getTerritoryEconomy(territory.id));
    } catch {
      setAttackMessage({ severity: 'error', text: getLocalizedText('map_economy_load_error', 'Не удалось загрузить экономику территории') });
    } finally {
      setEconomyLoading(false);
    }
  };

  const getAdminTerritoryForm = (territory) => ({
      resource_wealth: territory.resource_wealth || 0,
      influence_value: territory.influence_value || 0,
      required_influence: territory.required_influence || 0,
      resource_type: territory.resource_type || 'iron',
      resource_output: territory.resource_output || 0,
      secondary_resource_type: territory.secondary_resource_type || '',
      population: territory.population || 0,
      development_level: territory.development_level || 0,
      fortifications: territory.fortifications || 0,
      offense_level: territory.offense_level || 0,
      is_playable: territory.is_playable !== false,
      is_coastal: Boolean(territory.is_coastal),
      has_port: Boolean(territory.has_port),
      port_level: territory.port_level || 0,
      fleet_level: territory.fleet_level || 0,
      required_territories: territory.required_territories || 0,
      stronghold_power: territory.stronghold_power || 0,
  });

  const openAdminTerritoryEditor = (territory) => {
    if (!isLegacyCampaign) return;
    setAdminForm(getAdminTerritoryForm(territory));
    setManagedTerritory(territory);
    setAdminDialogOpen(true);
  };

  const handleAdminTerritorySave = async () => {
    if (!isLegacyCampaign || !managedTerritory?.id || !adminForm) return;
    setAdminSaving(true);
    try {
      const normalizedForm = {
        ...adminForm,
        secondary_resource_type: adminForm.stronghold_power > 0
          ? (
            adminForm.secondary_resource_type
            || ['iron', 'wood', 'food', 'mithril'].find(
              (resource) => resource !== adminForm.resource_type,
            )
          )
          : null,
        port_level: adminForm.has_port ? adminForm.port_level : 0,
        fleet_level: adminForm.has_port
          ? Math.min(adminForm.fleet_level, adminForm.port_level)
          : 0,
      };
      const originalForm = getAdminTerritoryForm(managedTerritory);
      const payload = Object.fromEntries(
        Object.entries(normalizedForm).filter(
          ([field, value]) => value !== originalForm[field]
        )
      );
      if (Object.keys(payload).length === 0) {
        setAdminDialogOpen(false);
        setAttackMessage({
          severity: 'info',
          text: getLocalizedText('map_no_admin_changes', null, { territory: territoryName(managedTerritory) }),
        });
        return;
      }
      const updated = normalizeTerritory(
        await territoryService.updateTerritory(
          managedTerritory.id,
          payload,
          getLocalizedText('map_admin_save_error', 'Не удалось сохранить параметры территории'),
        ),
        managedTerritory
      );
      setManagedTerritory(updated);
      setSelectedRegion(updated);
      setTerritories((current) => current.map(
        (territory) => Number(territory.id) === Number(updated.id)
          ? normalizeTerritory(updated, territory)
          : territory
      ));
      setAdminDialogOpen(false);
      setAttackMessage({
        severity: 'success',
        text: getLocalizedText('map_admin_saved', null, { territory: territoryName(updated) }),
      });
      await loadMapData();
    } catch (error) {
      setAttackMessage({
        severity: 'error',
        text: error.message || getLocalizedText('map_admin_save_error', 'Не удалось сохранить параметры территории'),
      });
    } finally {
      setAdminSaving(false);
    }
  };

  const handleTerritoryUpgrade = async (upgradeType) => {
    if (!isLegacyCampaign || !managedTerritory?.id) return;
    setUpgradingType(upgradeType);
    try {
      const result = await territoryService.upgradeTerritory(
        managedTerritory.id,
        upgradeType,
        getLocalizedText('map_upgrade_error', 'Не удалось улучшить территорию'),
      );
      const refreshedTerritory = normalizeTerritory(result.territory, managedTerritory);
      setManagedTerritory(refreshedTerritory);
      setSelectedRegion(refreshedTerritory);
      setManagedEconomy(await territoryService.getTerritoryEconomy(managedTerritory.id));
      setAttackMessage({ severity: 'success', text: getLocalizedText('map_upgrade_bought', null, { territory: territoryName(managedTerritory) }) });
      await loadMapData();
    } catch (error) {
      setAttackMessage({ severity: 'error', text: error.message || getLocalizedText('map_upgrade_error', 'Не удалось улучшить территорию') });
    } finally {
      setUpgradingType(null);
    }
  };

  const canAffordUpgrade = (cost = {}) => Object.entries(cost).every(
    ([resource, amount]) => (myClan?.[resource] || 0) >= amount
  );

  const getNextResourcePayout = (territory) => {
    if (territory?.last_resource_payout_at) {
      return new Date(new Date(territory.last_resource_payout_at).getTime() + 24 * 60 * 60 * 1000);
    }
    if (territory?.resource_income_ready_at) return new Date(territory.resource_income_ready_at);
    if (!territory?.owned_since) return null;
    return new Date(new Date(territory.owned_since).getTime() + 72 * 60 * 60 * 1000);
  };

  // Загрузка SVG и настройка интерактивности
  useEffect(() => {
    publicFetch('/map-interactive.svg')
      .then(response => response.text())
      .then(data => {
        setSvgContent(data);
        // Сбрасываем hover и selection при загрузке нового SVG
        setHoveredRegion(null);
        setSelectedRegion(null);
        
        // Дополнительная очистка классов при загрузке
        setTimeout(() => {
          if (svgRef.current) {
            const paths = svgRef.current.querySelectorAll('path.interactive-region');
            paths.forEach(path => {
              path.classList.remove('hovered', 'selected');
            });
          }
        }, 100);
      })
      .catch(error => {
        console.error('❌ Error loading SVG:', error);
      });
  }, []);

  // Обработка интерактивности регионов через прямые обработчики событий
  // Вставка SVG контента в DOM
  useEffect(() => {
    if (svgRef.current && svgContent) {
      svgRef.current.innerHTML = svgContent;
      const svg = svgRef.current.querySelector('svg');
      if (svg) {
        const viewBox = (svg.getAttribute('viewBox') || '')
          .trim()
          .split(/\s+/)
          .map(Number);
        if (viewBox.length === 4 && viewBox.every(Number.isFinite)) {
          svg.setAttribute('width', String(viewBox[2]));
          svg.setAttribute('height', String(viewBox[3]));
        }
        svg.setAttribute('preserveAspectRatio', 'xMidYMid meet');
        svg.style.width = '100%';
        svg.style.height = '100%';
        svg.style.maxWidth = '100%';
        svg.style.maxHeight = '100%';
        svg.style.display = 'block';
      }

      const seenPaths = new Set();
      svgRef.current.querySelectorAll('path.interactive-region').forEach(path => {
        const pathData = path.getAttribute('d');
        if (pathData && seenPaths.has(pathData)) {
          path.remove();
          return;
        }
        if (pathData) {
          seenPaths.add(pathData);
        }
        path.setAttribute('vector-effect', 'non-scaling-stroke');
      });
    }
  }, [svgContent, isFullscreen]);

  // Обработка интерактивности регионов после вставки svgContent
  useEffect(() => {
    if (!svgContent || !svgRef.current) return;

    const cleanupFns = [];
    const timer = setTimeout(() => {
      const paths = svgRef.current.querySelectorAll('path.interactive-region');

      paths.forEach(path => {
        path.classList.remove('hovered', 'selected');
        path.style.pointerEvents = 'all';
        path.style.cursor = 'pointer';
        path.setAttribute('tabindex', '0');
        path.setAttribute('role', 'button');
        path.setAttribute(
          'aria-label',
          path.getAttribute('data-name') || getLocalizedText('map_territory', 'Территория'),
        );

        const handleEnter = async () => {
          const requestId = ++hoverRequestRef.current;
          const territory = await resolveTerritoryForPath(path);
          if (requestId === hoverRequestRef.current) {
            setHoveredRegion(territory);
          }
        };

        const handleLeave = () => {
          hoverRequestRef.current += 1;
          setHoveredRegion(null);
        };

        const handleClick = async () => {
          const requestId = ++clickRequestRef.current;
          const territory = await resolveTerritoryForPath(path);
          if (requestId !== clickRequestRef.current) return;
          setSelectedRegion(territory);
          setHoveredRegion(null);
          if (mapLayers.attackable && myClan?.id) {
            setAdminRouteSource(null);
            return;
          }
          if (isAdmin && !attackSource?.id) {
            setAdminRouteSource(territory);
          }
        };

        const handleKeyDown = (event) => {
          if (event.key !== 'Enter' && event.key !== ' ') return;
          event.preventDefault();
          handleClick();
        };

        path.addEventListener('mouseenter', handleEnter);
        path.addEventListener('mouseleave', handleLeave);
        path.addEventListener('focus', handleEnter);
        path.addEventListener('blur', handleLeave);
        path.addEventListener('click', handleClick);
        path.addEventListener('keydown', handleKeyDown);

        cleanupFns.push(() => {
          path.removeEventListener('mouseenter', handleEnter);
          path.removeEventListener('mouseleave', handleLeave);
          path.removeEventListener('focus', handleEnter);
          path.removeEventListener('blur', handleLeave);
          path.removeEventListener('click', handleClick);
          path.removeEventListener('keydown', handleKeyDown);
        });
      });

    }, 0);

    return () => {
      clearTimeout(timer);
      cleanupFns.forEach((cleanup) => cleanup());
    };
  }, [attackSource, getLocalizedText, isAdmin, isFullscreen, mapLayers.attackable, myClan?.id, resolveTerritoryForPath, svgContent]);


  // Обновление стилей территорий при изменении hoveredRegion и selectedRegion
  useEffect(() => {
    if (svgRef.current) {
      const svg = svgRef.current.querySelector('svg');
      svg?.querySelector('#territory-war-fill-defs')?.remove();
      const warFillDefs = document.createElementNS(SVG_NAMESPACE, 'defs');
      warFillDefs.setAttribute('id', 'territory-war-fill-defs');
      svg?.insertBefore(warFillDefs, svg.firstChild);
      const paths = svgRef.current.querySelectorAll('path.interactive-region');
      
      paths.forEach(path => {
        const regionId = path.getAttribute('data-region');
        const regionName = path.getAttribute('data-name');
        const regionNameLower = regionName?.toLowerCase();
        const pathData = path.getAttribute('d');
        const territory = territoriesByPath.get(pathData) || territoriesByName.get(regionName);
        const mapStyle = getTerritoryMapStyle(territory);
        const visualState = getTerritoryVisualState(territory);
        const activeWar = (activeWarsByTerritory.get(Number(territory?.id)) || [])
          .find((war) => war.status === 'active');
        let territoryFill = mapStyle.fill;
        let territoryHoverFill = mapStyle.hoverFill || mapStyle.fill;
        let territorySelectedFill = mapStyle.selectedFill || mapStyle.fill;

        if (activeWar?.defending_clan_id) {
          const { attackerShare, defenderShare } = getWarScoreSplit(activeWar);
          const attackerColor = activeWar.attacking_clan_map_color
            || clanMapColorById.get(Number(activeWar.attacking_clan_id))
            || '#e53935';
          const defenderColor = activeWar.defending_clan_map_color
            || clanMapColorById.get(Number(activeWar.defending_clan_id))
            || '#42a5f5';
          const gradientKey = String(activeWar.id || territory?.id || regionName || 'unknown')
            .replace(/[^a-z0-9_-]/gi, '-');
          [
            ['base', CLAN_TERRITORY_OPACITY],
            ['hover', CLAN_TERRITORY_HOVER_OPACITY],
            ['selected', CLAN_TERRITORY_SELECTED_OPACITY],
          ].forEach(([variant, opacity]) => appendWarFillGradient(warFillDefs, {
            id: `territory-war-fill-${gradientKey}-${variant}`,
            attackerColor,
            defenderColor,
            attackerShare,
            opacity,
          }));
          territoryFill = `url(#territory-war-fill-${gradientKey}-base)`;
          territoryHoverFill = `url(#territory-war-fill-${gradientKey}-hover)`;
          territorySelectedFill = `url(#territory-war-fill-${gradientKey}-selected)`;
          path.setAttribute('data-war-attacker-share', String(attackerShare));
          path.setAttribute('data-war-defender-share', String(defenderShare));
        } else if (activeWar?.attacking_clan_id) {
          const attackerColor = activeWar.attacking_clan_map_color
            || clanMapColorById.get(Number(activeWar.attacking_clan_id))
            || '#e53935';
          const attackerPaint = getClanTerritoryPaint(attackerColor);
          territoryFill = attackerPaint.fill;
          territoryHoverFill = attackerPaint.hoverFill;
          territorySelectedFill = attackerPaint.selectedFill;
          path.removeAttribute('data-war-attacker-share');
          path.removeAttribute('data-war-defender-share');
        } else {
          path.removeAttribute('data-war-attacker-share');
          path.removeAttribute('data-war-defender-share');
        }

        path.classList.remove('state-neutral', 'state-owned', 'state-attack', 'state-defense', 'state-war', 'relation-own', 'relation-allied', 'relation-enemy', 'relation-neutral', 'campaign-target', 'admin-route-target', 'campaign-locked');
        path.classList.add(`state-${visualState}`);
        const ownerClanId = Number(territory?.owner_clan_id || 0);
        const relation = !ownerClanId
          ? 'neutral'
          : ownerClanId === Number(myClan?.id)
            ? 'own'
            : alliedClanIds.has(ownerClanId)
              ? 'allied'
              : hostileClanIds.has(ownerClanId)
                ? 'enemy'
                : 'neutral';
        path.classList.add(`relation-${relation}`);
        path.style.setProperty('--territory-fill', territoryFill);
        path.style.setProperty('--territory-hover-fill', territoryHoverFill);
        path.style.setProperty('--territory-selected-fill', territorySelectedFill);
        path.style.setProperty(
          '--territory-stroke',
          myClan?.id ? RELATION_STROKES[relation] : mapStyle.stroke,
        );
        path.style.setProperty(
          '--territory-stroke-width',
          visualState === 'war' ? '4px' : visualState === 'owned' ? '2.75px' : '2px'
        );
        path.style.pointerEvents = 'all';
        if (territory?.is_playable === false) {
          path.classList.add('campaign-locked');
        } else if (
          isAdmin
          && adminRouteSource?.id
          && territory
          && Number(territory.id) !== Number(adminRouteSource.id)
          && !PROTECTED_ADMIN_TERRITORIES.has(territory.name)
          && canReachTerritory(adminRouteSource, territory)
        ) {
          path.classList.add('admin-route-target');
        } else if (
          mapLayers.attackable
          && attackSource?.id
          && territory
          && isAttackTargetForSource(attackSource, territory)
        ) {
          path.classList.add('campaign-target');
        }

        // Очищаем все классы
        path.classList.remove('hovered', 'selected');

        // Проверяем точное совпадение для selected
        let isSelected = false;
        if (selectedRegion) {
          // Проверяем по path data (самый надежный способ)
          if (selectedRegion.svg_path_data === pathData) {
            isSelected = true;
          }
          // Затем проверяем по точному имени
          else if (regionName && selectedRegion.name.toLowerCase() === regionNameLower) {
            isSelected = true;
          }
          // Затем проверяем по ID
          else if (selectedRegion.id === regionId) {
            isSelected = true;
          }
        }

        // Проверяем точное совпадение для hovered
        let isHovered = false;
        if (hoveredRegion && !isSelected) {
          // Проверяем по path data (самый надежный способ)
          if (hoveredRegion.svg_path_data === pathData) {
            isHovered = true;
          }
          // Затем проверяем по точному имени
          else if (regionName && hoveredRegion.name.toLowerCase() === regionNameLower) {
            isHovered = true;
          }
          // Затем проверяем по ID
          else if (hoveredRegion.id === regionId) {
            isHovered = true;
          }
        }

        // Применяем стили
        if (isSelected) {
          path.classList.add('selected');
        } else if (isHovered) {
          path.classList.add('hovered');
        }
      });
    }
  }, [activeWarsByTerritory, adminRouteSource, alliedClanIds, attackSource, clanMapColorById, getTerritoryMapStyle, getTerritoryVisualState, hostileClanIds, hoveredRegion, isAdmin, isAttackTargetForSource, isFullscreen, mapLayers.attackable, myClan, selectedRegion, territoriesByName, territoriesByPath]);

  useEffect(() => {
    const svg = svgRef.current?.querySelector('svg');
    svg?.querySelector('.clan-territory-emblems')?.remove();
    if (!svg || !territories.length || !mapLayers.clanIcons) return undefined;
    const timer = window.setTimeout(() => {
      const currentSvg = svgRef.current?.querySelector('svg');
      if (!currentSvg) return;
      const svgNs = SVG_NAMESPACE;
      const layer = document.createElementNS(svgNs, 'g');
      layer.setAttribute('class', 'clan-territory-emblems');
      layer.setAttribute('aria-hidden', 'true');
      const defs = document.createElementNS(svgNs, 'defs');
      layer.appendChild(defs);
      const activeFrontSourceTerritoryIds = new Set(
        activeWars
          .filter((war) => war.defending_clan_id && war.source_territory_id)
          .map((war) => Number(war.source_territory_id))
      );
      const activeFrontTargetTerritoryIds = new Set(
        activeWars
          .filter((war) => war.defending_clan_id && war.source_territory_id)
          .map((war) => Number(war.territory_id))
      );

      currentSvg.querySelectorAll('path.interactive-region').forEach((path, emblemIndex) => {
        const pathData = path.getAttribute('d');
        const regionName = path.getAttribute('data-name');
        const territory = territoriesByPath.get(pathData) || territoriesByName.get(regionName);
        if (territory?.owner_clan_is_admin) return;
        const territoryWars = activeWarsByTerritory.get(Number(territory?.id)) || [];
        const activeWar = territoryWars.find((war) => war.status === 'active') || null;
        const neutralWar = !territory?.owner_clan_id
          ? territoryWars.find((war) => war.status === 'active')
          : null;
        const neutralChallenge = Boolean(neutralWar?.defending_clan_id);
        if (activeFrontSourceTerritoryIds.has(Number(territory?.id))) return;
        if (activeFrontTargetTerritoryIds.has(Number(territory?.id)) && !neutralChallenge) return;

        const emblemSides = neutralChallenge
          ? [
            {
              role: 'attacker',
              clanId: neutralWar.attacking_clan_id,
              name: neutralWar.attacking_clan_name,
              avatarUrl: neutralWar.attacking_clan_avatar_url,
              mapEmblemUrl: neutralWar.attacking_clan_map_emblem_url,
              color: neutralWar.attacking_clan_map_color,
            },
            {
              role: 'defender',
              clanId: neutralWar.defending_clan_id,
              name: neutralWar.defending_clan_name,
              avatarUrl: neutralWar.defending_clan_avatar_url,
              mapEmblemUrl: neutralWar.defending_clan_map_emblem_url,
              color: neutralWar.defending_clan_map_color,
            },
          ]
          : [{
            role: neutralWar ? 'attacker' : 'owner',
            clanId: territory?.owner_clan_id || neutralWar?.attacking_clan_id,
            name: getOwnerName(territory) || neutralWar?.attacking_clan_name,
            avatarUrl: territory?.owner_clan_avatar_url || neutralWar?.attacking_clan_avatar_url,
            mapEmblemUrl: territory?.owner_clan_map_emblem_url || neutralWar?.attacking_clan_map_emblem_url,
            color: territory?.owner_clan_map_color || neutralWar?.attacking_clan_map_color,
          }];
        if (!emblemSides[0]?.clanId) return;
        const box = path.getBBox();
        const shortestSide = Math.min(box.width, box.height);
        if (!Number.isFinite(shortestSide) || shortestSide < 10) return;
        const paired = emblemSides.length === 2;
        const size = paired
          ? Math.max(48, Math.min(78, shortestSide * 0.72))
          : Math.max(45, Math.min(92, shortestSide * 0.828));
        const centerX = box.x + box.width / 2;
        const centerY = box.y + box.height / 2;
        const emblemGap = paired ? size * 1.08 : 0;

        emblemSides.forEach((side, sideIndex) => {
          const emblemName = side.name || `Клан #${side.clanId}`;
          const emblemImageUrl = side.mapEmblemUrl || getStaticMapEmblemUrl(side.avatarUrl);
          const primaryColor = side.color
            || clanMapColorById.get(Number(side.clanId))
            || '#8f9794';
          const offsetX = paired ? (sideIndex - 0.5) * emblemGap : 0;
          const group = document.createElementNS(svgNs, 'g');
          group.setAttribute(
            'class',
            `clan-territory-emblem${side.role === 'attacker' ? ' clan-territory-emblem--attacking' : ''}${paired ? ' clan-territory-emblem--contested' : ''}`,
          );
          group.setAttribute('transform', `translate(${centerX + offsetX} ${centerY})`);
          group.setAttribute('data-clan-role', side.role);
          group.setAttribute('data-clan-id', String(side.clanId));
          if (activeWar?.id) group.setAttribute('data-war-id', String(activeWar.id));
          group.style.setProperty('--clan-emblem-primary', primaryColor);

          const backdrop = document.createElementNS(svgNs, 'circle');
          backdrop.setAttribute('r', String(size / 2));
          backdrop.setAttribute('class', 'clan-territory-emblem__backdrop');
          group.appendChild(backdrop);

          const label = document.createElementNS(svgNs, 'text');
          label.textContent = (emblemName || '?').trim().charAt(0).toUpperCase();
          label.setAttribute('class', 'clan-territory-emblem__letter');
          label.setAttribute('text-anchor', 'middle');
          label.setAttribute('dominant-baseline', 'central');
          label.setAttribute('font-size', String(size * 0.62));
          group.appendChild(label);

          if (emblemImageUrl) {
            const clipId = `clan-territory-emblem-clip-${emblemIndex}-${side.role}`;
            const clipPath = document.createElementNS(svgNs, 'clipPath');
            clipPath.setAttribute('id', clipId);
            const clipCircle = document.createElementNS(svgNs, 'circle');
            clipCircle.setAttribute('r', String(size / 2));
            clipPath.appendChild(clipCircle);
            defs.appendChild(clipPath);

            const image = document.createElementNS(svgNs, 'image');
            image.setAttribute('href', emblemImageUrl);
            image.setAttribute('x', String(-size / 2));
            image.setAttribute('y', String(-size / 2));
            image.setAttribute('width', String(size));
            image.setAttribute('height', String(size));
            image.setAttribute('preserveAspectRatio', 'xMidYMid slice');
            image.setAttribute('clip-path', `url(#${clipId})`);
            image.setAttribute('class', 'clan-territory-emblem__image');
            image.addEventListener('error', () => image.remove(), { once: true });
            group.appendChild(image);
          }
          layer.appendChild(group);
        });
      });
      currentSvg.appendChild(layer);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [
    territories,
    svgContent,
    territoriesByPath,
    territoriesByName,
    activeWars,
    activeWarsByTerritory,
    clanMapColorById,
    getOwnerName,
    isFullscreen,
    mapLayers.clanIcons,
  ]);

  useEffect(() => {
    const wrapper = svgRef.current;
    const svg = wrapper?.querySelector('svg');
    if (!svg) return;

    svg.querySelector('#clan-war-arrow-layer')?.remove();
    const arrows = (mapLayers.wars ? activeWars : [])
      .filter(war => war.source_territory_id && war.territory_id)
      .map(war => {
        const attackerScore = (war.clan_scores || []).find(
          score => Number(score.clan_id) === Number(war.attacking_clan_id)
        );
        const defenderScore = (war.clan_scores || []).find(
          score => Number(score.clan_id) === Number(war.defending_clan_id)
        );
        return {
          warId: Number(war.id),
          sourceId: Number(war.source_territory_id),
          targetId: Number(war.territory_id),
          label: war.attacking_clan_name || getLocalizedText('map_attack_generic', 'Атака'),
          pending: false,
          attackerId: Number(war.attacking_clan_id),
          attackerName: war.attacking_clan_name,
          attackerAvatarUrl: war.attacking_clan_avatar_url,
          attackerColor: war.attacking_clan_map_color,
          attackerPoints: Math.max(0, Number(attackerScore?.points) || 0),
          defenderId: war.defending_clan_id ? Number(war.defending_clan_id) : null,
          defenderName: war.defending_clan_name,
          defenderAvatarUrl: war.defending_clan_avatar_url,
          defenderColor: war.defending_clan_map_color,
          defenderPoints: Math.max(0, Number(defenderScore?.points) || 0),
        };
      });

    if (
      selectedAttackSource?.id
      && selectedRegion?.id
      && Number(selectedAttackSource.id) !== Number(selectedRegion.id)
      && isCampaignTargetAvailable(selectedRegion)
      && canReachTerritory(selectedAttackSource, selectedRegion)
    ) {
      arrows.push({
        sourceId: Number(selectedAttackSource.id),
        targetId: Number(selectedRegion.id),
        label: getLocalizedText('map_attack_direction', 'Направление атаки'),
        pending: true,
      });
    }

    if (arrows.length === 0) return;

    const svgNs = 'http://www.w3.org/2000/svg';
    const layer = document.createElementNS(svgNs, 'g');
    layer.setAttribute('id', 'clan-war-arrow-layer');
    layer.setAttribute('aria-label', getLocalizedText('map_attack_directions', 'Направления атак кланов'));
    layer.style.pointerEvents = 'none';

    const defs = document.createElementNS(svgNs, 'defs');
    const marker = document.createElementNS(svgNs, 'marker');
    marker.setAttribute('id', 'clan-war-arrowhead');
    marker.setAttribute('viewBox', '0 0 12 12');
    marker.setAttribute('refX', '10');
    marker.setAttribute('refY', '6');
    marker.setAttribute('markerWidth', '64');
    marker.setAttribute('markerHeight', '64');
    marker.setAttribute('markerUnits', 'userSpaceOnUse');
    marker.setAttribute('orient', 'auto-start-reverse');
    const markerPath = document.createElementNS(svgNs, 'path');
    markerPath.setAttribute('d', 'M 0 0 L 12 6 L 0 12 z');
    markerPath.setAttribute('fill', '#ff2d2d');
    markerPath.setAttribute('stroke', '#660b0b');
    markerPath.setAttribute('stroke-width', '1.5');
    marker.appendChild(markerPath);

    const filter = document.createElementNS(svgNs, 'filter');
    filter.setAttribute('id', 'clan-war-arrow-glow');
    filter.setAttribute('x', '-40%');
    filter.setAttribute('y', '-40%');
    filter.setAttribute('width', '180%');
    filter.setAttribute('height', '180%');
    const shadow = document.createElementNS(svgNs, 'feDropShadow');
    shadow.setAttribute('dx', '0');
    shadow.setAttribute('dy', '0');
    shadow.setAttribute('stdDeviation', '3');
    shadow.setAttribute('flood-color', '#ff3d2e');
    shadow.setAttribute('flood-opacity', '0.95');
    filter.appendChild(shadow);
    defs.append(marker, filter);
    layer.appendChild(defs);

    const findPath = (territory) => {
      if (!territory) return null;
      return [...svg.querySelectorAll('path.interactive-region')].find(path => (
        (territory.svg_path_data && path.getAttribute('d') === territory.svg_path_data)
        || (territory.name && path.getAttribute('data-name') === territory.name)
      ));
    };

    const getCenter = (path) => {
      const box = path.getBBox();
      return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    };

    const getFrontColor = (color, clanId, fallback) => (
      color
      || clanMapColorById.get(Number(clanId))
      || fallback
    );

    const appendFrontEmblem = ({
      arrow,
      index,
      side,
      point,
      name,
      avatarUrl,
      color,
      percentage,
    }) => {
      const group = document.createElementNS(svgNs, 'g');
      group.setAttribute('class', `clan-war-front-emblem clan-war-front-emblem--${side}`);
      group.setAttribute('transform', `translate(${point.x} ${point.y})`);
      group.style.setProperty('--clan-war-color', color);

      const title = document.createElementNS(svgNs, 'title');
      title.textContent = getLocalizedText('map_front_line_title', null, {
        clan: name || getLocalizedText('map_clan_generic', 'Клан'),
        value: Math.round(percentage),
      });
      group.appendChild(title);

      const backdrop = document.createElementNS(svgNs, 'circle');
      backdrop.setAttribute('r', '37');
      backdrop.setAttribute('class', 'clan-war-front-emblem__backdrop');
      group.appendChild(backdrop);

      if (avatarUrl) {
        const clipId = `clan-war-front-clip-${arrow.warId || 'pending'}-${index}-${side}`;
        const clipPath = document.createElementNS(svgNs, 'clipPath');
        clipPath.setAttribute('id', clipId);
        const clipCircle = document.createElementNS(svgNs, 'circle');
        clipCircle.setAttribute('r', '30');
        clipPath.appendChild(clipCircle);
        defs.appendChild(clipPath);

        const image = document.createElementNS(svgNs, 'image');
        image.setAttribute('href', avatarUrl);
        image.setAttribute('x', '-30');
        image.setAttribute('y', '-30');
        image.setAttribute('width', '60');
        image.setAttribute('height', '60');
        image.setAttribute('preserveAspectRatio', 'xMidYMid slice');
        image.setAttribute('clip-path', `url(#${clipId})`);
        image.setAttribute('class', 'clan-war-front-emblem__image');
        group.appendChild(image);
      } else {
        const letter = document.createElementNS(svgNs, 'text');
        letter.textContent = (name || '?').trim().charAt(0).toUpperCase();
        letter.setAttribute('class', 'clan-war-front-emblem__letter');
        letter.setAttribute('text-anchor', 'middle');
        letter.setAttribute('dominant-baseline', 'central');
        group.appendChild(letter);
      }

      const score = document.createElementNS(svgNs, 'text');
      score.textContent = `${Math.round(percentage)}%`;
      score.setAttribute('x', '0');
      score.setAttribute('y', '50');
      score.setAttribute('class', 'clan-war-front-emblem__score');
      score.setAttribute('text-anchor', 'middle');
      group.appendChild(score);
      layer.appendChild(group);
    };

    const appendBattleMarker = ({ point, tangent }) => {
      const group = document.createElementNS(svgNs, 'g');
      group.setAttribute('class', 'clan-war-front-clash');
      group.setAttribute('transform', `translate(${point.x} ${point.y})`);

      [
        { className: 'sword', glyph: '⚔︎', direction: -1 },
        { className: 'shield', glyph: '🛡︎', direction: 1 },
      ].forEach(({ className, glyph, direction }) => {
        const iconX = tangent.x * 12 * direction;
        const iconY = tangent.y * 12 * direction;

        const icon = document.createElementNS(svgNs, 'text');
        icon.textContent = glyph;
        icon.setAttribute('x', String(iconX));
        icon.setAttribute('y', String(iconY + 0.5));
        icon.setAttribute('class', `clan-war-front-clash__icon clan-war-front-clash__icon--${className}`);
        icon.setAttribute('text-anchor', 'middle');
        icon.setAttribute('dominant-baseline', 'central');
        group.appendChild(icon);
      });
      layer.appendChild(group);
    };

    arrows.forEach((arrow, index) => {
      const source = territories.find(item => Number(item.id) === arrow.sourceId);
      const target = territories.find(item => Number(item.id) === arrow.targetId);
      const sourcePath = findPath(source);
      const targetPath = findPath(target);
      if (!sourcePath || !targetPath) return;

      const start = getCenter(sourcePath);
      const end = getCenter(targetPath);
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const distance = Math.max(Math.hypot(dx, dy), 1);
      const hasActiveFront = !arrow.pending && Boolean(arrow.defenderId);
      const curve = Math.min(
        Math.max(
          distance * (hasActiveFront ? 0.52 : 0.28),
          hasActiveFront ? 110 : 54,
        ),
        hasActiveFront ? 240 : 180,
      )
        * (index % 2 === 0 ? 1 : -1);
      const midX = (start.x + end.x) / 2 - (dy / distance) * curve;
      const midY = (start.y + end.y) / 2 + (dx / distance) * curve;
      const pathData = `M ${start.x} ${start.y} Q ${midX} ${midY} ${end.x} ${end.y}`;

      const outline = document.createElementNS(svgNs, 'path');
      outline.setAttribute('d', pathData);
      outline.setAttribute('class', 'clan-war-arrow-outline');
      outline.setAttribute('vector-effect', 'non-scaling-stroke');
      layer.appendChild(outline);

      if (!arrow.pending && arrow.defenderId) {
        const totalPoints = arrow.attackerPoints + arrow.defenderPoints;
        const attackerShare = totalPoints > 0
          ? arrow.attackerPoints / totalPoints
          : 0.5;
        const defenderShare = 1 - attackerShare;
        const totalLength = Math.max(outline.getTotalLength(), 1);
        const attackerLength = totalLength * attackerShare;
        const defenderLength = totalLength * defenderShare;
        const attackerColor = getFrontColor(arrow.attackerColor, arrow.attackerId, '#e53935');
        const defenderColor = getFrontColor(arrow.defenderColor, arrow.defenderId, '#42a5f5');

        const base = document.createElementNS(svgNs, 'path');
        base.setAttribute('d', pathData);
        base.setAttribute('class', 'clan-war-front-base');
        base.setAttribute('vector-effect', 'non-scaling-stroke');
        layer.appendChild(base);

        const attackerLine = document.createElementNS(svgNs, 'path');
        attackerLine.setAttribute('d', pathData);
        attackerLine.setAttribute('class', 'clan-war-front-line clan-war-front-line--attacker');
        attackerLine.setAttribute('stroke-dasharray', `${attackerLength} ${totalLength}`);
        attackerLine.setAttribute('vector-effect', 'non-scaling-stroke');
        attackerLine.setAttribute('data-war-id', String(arrow.warId));
        attackerLine.setAttribute('data-front-share', String(attackerShare));
        attackerLine.style.setProperty('--clan-war-color', attackerColor);
        layer.appendChild(attackerLine);

        const reversePathData = `M ${end.x} ${end.y} Q ${midX} ${midY} ${start.x} ${start.y}`;
        const defenderLine = document.createElementNS(svgNs, 'path');
        defenderLine.setAttribute('d', reversePathData);
        defenderLine.setAttribute('class', 'clan-war-front-line clan-war-front-line--defender');
        defenderLine.setAttribute('stroke-dasharray', `${defenderLength} ${totalLength}`);
        defenderLine.setAttribute('vector-effect', 'non-scaling-stroke');
        defenderLine.setAttribute('data-war-id', String(arrow.warId));
        defenderLine.setAttribute('data-front-share', String(defenderShare));
        defenderLine.style.setProperty('--clan-war-color', defenderColor);
        layer.appendChild(defenderLine);

        const clashLength = Math.max(0, Math.min(totalLength, attackerLength));
        const clashPoint = outline.getPointAtLength(clashLength);
        const tangentStart = outline.getPointAtLength(Math.max(0, clashLength - 2));
        const tangentEnd = outline.getPointAtLength(Math.min(totalLength, clashLength + 2));
        const tangentDistance = Math.max(
          Math.hypot(tangentEnd.x - tangentStart.x, tangentEnd.y - tangentStart.y),
          1,
        );
        const tangent = {
          x: (tangentEnd.x - tangentStart.x) / tangentDistance,
          y: (tangentEnd.y - tangentStart.y) / tangentDistance,
        };
        const emblemGap = Math.min(66, totalLength * 0.17);
        const attackerPoint = outline.getPointAtLength(
          Math.max(0, Math.min(totalLength, clashLength - emblemGap))
        );
        const defenderPoint = outline.getPointAtLength(
          Math.max(0, Math.min(totalLength, clashLength + emblemGap))
        );

        if (target?.owner_clan_id) {
          appendFrontEmblem({
            arrow,
            index,
            side: 'attacker',
            point: attackerPoint,
            name: arrow.attackerName,
            avatarUrl: arrow.attackerAvatarUrl,
            color: attackerColor,
            percentage: attackerShare * 100,
          });
          appendFrontEmblem({
            arrow,
            index,
            side: 'defender',
            point: defenderPoint,
            name: arrow.defenderName,
            avatarUrl: arrow.defenderAvatarUrl,
            color: defenderColor,
            percentage: defenderShare * 100,
          });
        }
        appendBattleMarker({ point: clashPoint, tangent });
        return;
      }

      const path = document.createElementNS(svgNs, 'path');
      path.setAttribute('d', pathData);
      path.setAttribute('class', `clan-war-arrow${arrow.pending ? ' clan-war-arrow--pending' : ''}`);
      path.setAttribute('marker-end', 'url(#clan-war-arrowhead)');
      path.setAttribute('filter', 'url(#clan-war-arrow-glow)');
      path.setAttribute('vector-effect', 'non-scaling-stroke');
      layer.appendChild(path);

      const highlight = document.createElementNS(svgNs, 'path');
      highlight.setAttribute('d', pathData);
      highlight.setAttribute('class', 'clan-war-arrow-highlight');
      highlight.setAttribute('vector-effect', 'non-scaling-stroke');
      layer.appendChild(highlight);

      const origin = document.createElementNS(svgNs, 'circle');
      origin.setAttribute('cx', String(start.x));
      origin.setAttribute('cy', String(start.y));
      origin.setAttribute('r', '28');
      origin.setAttribute('class', 'clan-war-arrow-origin');
      layer.appendChild(origin);

      const originIcon = document.createElementNS(svgNs, 'text');
      originIcon.setAttribute('x', String(start.x));
      originIcon.setAttribute('y', String(start.y + 0.5));
      originIcon.setAttribute('class', 'clan-war-arrow-origin-icon');
      originIcon.setAttribute('text-anchor', 'middle');
      originIcon.setAttribute('dominant-baseline', 'central');
      originIcon.textContent = '⚔';
      layer.appendChild(originIcon);
    });

    const emblemLayer = svg.querySelector('.clan-territory-emblems');
    if (emblemLayer) {
      svg.insertBefore(layer, emblemLayer);
    } else {
      svg.appendChild(layer);
    }
    return () => layer.remove();
  }, [activeWars, clanMapColorById, getLocalizedText, isCampaignTargetAvailable, isFullscreen, mapLayers.wars, selectedAttackSource, selectedRegion, svgContent, territories]);

  useEffect(() => {
    const svg = svgRef.current?.querySelector('svg');
    if (!svg) return undefined;
    svg.querySelector('#trade-caravan-layer')?.remove();
    if (!tradeCaravans.length || !mapLayers.trade) return undefined;

    const svgNs = 'http://www.w3.org/2000/svg';
    const layer = document.createElementNS(svgNs, 'g');
    layer.setAttribute('id', 'trade-caravan-layer');
    layer.setAttribute('aria-label', getLocalizedText('map_trade_caravans', 'Торговые караваны'));
    layer.style.pointerEvents = 'none';
    const warLayer = svg.querySelector('#clan-war-arrow-layer');
    if (warLayer) {
      svg.insertBefore(layer, warLayer);
    } else {
      svg.appendChild(layer);
    }

    const findTerritoryPath = (territoryId) => {
      const territory = territories.find(
        (item) => Number(item.id) === Number(territoryId),
      );
      if (!territory) return null;
      return [...svg.querySelectorAll('path.interactive-region')].find((path) => (
        path.getAttribute('d') === territory.svg_path_data
        || path.getAttribute('data-name') === territory.name
      ));
    };
    const centerOf = (path) => {
      const box = path.getBBox();
      return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
    };
    const caravanProgress = (caravan) => {
      const departed = new Date(caravan.departed_at).getTime();
      const eta = new Date(caravan.eta).getTime();
      if (!Number.isFinite(departed) || !Number.isFinite(eta) || eta <= departed) {
        return Math.max(0, Math.min(1, Number(caravan.progress_percent || 0) / 100));
      }
      return Math.max(0, Math.min(1, (currentTime - departed) / (eta - departed)));
    };
    const caravanRouteMode = (caravan) => {
      if (caravan.route_mode) return caravan.route_mode;
      return (caravan.route || []).some((step) => step.via === 'sea')
        ? 'sea'
        : 'land';
    };

    const drawnRoutes = new Set();
    tradeCaravans.forEach((caravan) => {
      const routeMode = caravanRouteMode(caravan);
      const points = (caravan.route || [])
        .map((step) => findTerritoryPath(step.territory_id))
        .filter(Boolean)
        .map(centerOf);
      if (points.length < 2) return;
      if (!drawnRoutes.has(caravan.offer_id)) {
        const pointData = points.map((point) => `${point.x},${point.y}`).join(' ');
        const routeOutline = document.createElementNS(svgNs, 'polyline');
        routeOutline.setAttribute('points', pointData);
        routeOutline.setAttribute(
          'class',
          `trade-caravan-route-outline trade-caravan-route-outline--${routeMode}`,
        );
        routeOutline.setAttribute('vector-effect', 'non-scaling-stroke');
        layer.appendChild(routeOutline);

        const routeLine = document.createElementNS(svgNs, 'polyline');
        routeLine.setAttribute('points', pointData);
        routeLine.setAttribute(
          'class',
          `trade-caravan-route trade-caravan-route--${routeMode}`,
        );
        routeLine.setAttribute('vector-effect', 'non-scaling-stroke');
        const routeTitle = document.createElementNS(svgNs, 'title');
        routeTitle.textContent = `${
          routeMode === 'sea'
            ? getLocalizedText('map_sea_trade_route', 'Морской торговый путь')
            : getLocalizedText('map_land_trade_route', 'Сухопутный торговый путь')
        }: ${caravan.from_clan_name} ↔ ${caravan.to_clan_name}`;
        routeLine.appendChild(routeTitle);
        layer.appendChild(routeLine);
        drawnRoutes.add(caravan.offer_id);
      }
      const progress = caravanProgress(caravan);
      const segmentProgress = progress * (points.length - 1);
      const segmentIndex = Math.min(
        points.length - 2,
        Math.floor(segmentProgress),
      );
      const localProgress = segmentProgress - segmentIndex;
      const start = points[segmentIndex];
      const end = points[segmentIndex + 1];
      const x = start.x + (end.x - start.x) * localProgress;
      const y = start.y + (end.y - start.y) * localProgress;

      const marker = document.createElementNS(svgNs, 'g');
      marker.setAttribute(
        'class',
        `trade-caravan-marker trade-caravan-marker--${routeMode}`,
      );
      marker.setAttribute('transform', `translate(${x} ${y})`);
      const title = document.createElementNS(svgNs, 'title');
      title.textContent = `${caravan.from_clan_name} → ${caravan.to_clan_name}`;
      marker.appendChild(title);
      const backdrop = document.createElementNS(svgNs, 'circle');
      backdrop.setAttribute('r', '31');
      backdrop.setAttribute('class', 'trade-caravan-marker__backdrop');
      marker.appendChild(backdrop);
      const vehicle = document.createElementNS(svgNs, 'text');
      vehicle.setAttribute('x', '0');
      vehicle.setAttribute('y', '1');
      vehicle.setAttribute(
        'class',
        routeMode === 'sea'
          ? 'trade-caravan-marker__ship'
          : 'trade-caravan-marker__camel',
      );
      vehicle.setAttribute('text-anchor', 'middle');
      vehicle.setAttribute('dominant-baseline', 'central');
      vehicle.textContent = routeMode === 'sea' ? '⛵' : '🐪';
      marker.appendChild(vehicle);
      layer.appendChild(marker);
    });

    return () => layer.remove();
  }, [currentTime, getLocalizedText, isFullscreen, mapLayers.trade, svgContent, territories, tradeCaravans]);





  // Обработка событий полноэкранного режима
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(Boolean(document.fullscreenElement));
    };

    const root = document.documentElement;
    const body = document.body;
    if (isFullscreen) {
      root.classList.add('map-fullscreen-lock');
      body.classList.add('map-fullscreen-lock');
    } else {
      root.classList.remove('map-fullscreen-lock');
      body.classList.remove('map-fullscreen-lock');
    }

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => {
      document.removeEventListener('fullscreenchange', handleFullscreenChange);
      root.classList.remove('map-fullscreen-lock');
      body.classList.remove('map-fullscreen-lock');
    };
  }, [isFullscreen]);



  const handleResetSelection = () => {
    setHoveredRegion(null);
    setSelectedRegion(null);
    setAdminRouteSource(null);
  };

  const getTradeRoutesForTerritory = (territory) => {
    if (!territory?.id) return [];
    const routes = new Map();
    tradeCaravans.forEach((caravan) => {
      const crossesTerritory = (caravan.route || []).some(
        (step) => Number(step.territory_id) === Number(territory.id),
      );
      if (!crossesTerritory || routes.has(caravan.offer_id)) return;
      routes.set(caravan.offer_id, caravan);
    });
    return [...routes.values()];
  };

  const handleLayerToggle = (key, checked) => {
    setMapLayers((current) => ({ ...current, [key]: checked }));
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {
        setIsFullscreen(false);
      });
    } else {
      document.exitFullscreen().catch(() => undefined);
    }
  };

  useEffect(() => {
    if (!campaignNavigationLoading && !legacyDialogAvailable) {
      setDeploymentDialogOpen(false);
      setAttackingTerritoryId(null);
    }
  }, [campaignNavigationLoading, legacyDialogAvailable]);

  const handleAttackTerritory = () => {
    if (!isLegacyCampaign || !selectedRegion?.id || !canAttackSelected) return;
    setAttackingTerritoryId(selectedRegion.id);
    setAttackMessage(null);
    setDeploymentDialogOpen(true);
  };

  const handleDeploymentClose = () => {
    setDeploymentDialogOpen(false);
    setAttackingTerritoryId(null);
  };

  const handleWarCreated = async (war) => {
    setAttackMessage({
      severity: 'success',
      text: getLocalizedText('map_war_started', null, {
        territory: getTerritoryName(war.territory_name || selectedRegion?.name, language),
      }),
    });
    setDeploymentDialogOpen(false);
    setAttackingTerritoryId(null);
    await loadMapData();
    setSelectedRegion(prev => prev ? { ...prev, status: 'contested' } : prev);
  };

  // Если в полноэкранном режиме, показываем только карту
  const panelTerritory = selectedRegion || hoveredRegion;
  const panelEconomy = panelTerritory?.id === selectedRegion?.id
    ? selectedTerritoryEconomy
    : null;
  const panelDailyGold = panelEconomy?.daily_income_with_clan_bonus
    ?? panelEconomy?.daily_income
    ?? getDailyIncomePreview(panelTerritory?.resource_wealth, panelTerritory?.population);
  const panelResourceRewards = panelEconomy?.daily_resource_rewards
    ?? (panelTerritory?.stronghold_power > 0 && panelTerritory?.secondary_resource_type
      ? [
        { resource: panelTerritory.resource_type, amount: 1 },
        { resource: panelTerritory.secondary_resource_type, amount: 1 },
      ]
      : [{ resource: panelTerritory?.resource_type, amount: panelTerritory?.resource_output || 1 }]);
  const clanDailyResourceRewards = useMemo(() => {
    const totals = new Map();
    (myClan?.territories || []).forEach((territory) => {
      (territory.daily_resource_rewards || []).forEach(({ resource, amount }) => {
        totals.set(resource, (totals.get(resource) || 0) + Number(amount || 0));
      });
    });
    return [...totals.entries()].map(([resource, amount]) => ({ resource, amount }));
  }, [myClan?.territories]);
  const adjacentTerritories = panelTerritory
    ? (panelTerritory.adjacent_territory_ids || [])
      .map((id) => territories.find((territory) => Number(territory.id) === Number(id)))
      .filter(Boolean)
    : [];
  const formatPanelNumber = (value) => Number(value || 0).toLocaleString(language, {
    maximumFractionDigits: 2,
  });

  if (isFullscreen) {
    return (
      <Box className="map-fullscreen-shell">
        <CycleMapLayer svgRef={svgRef} svgContent={svgContent} fullscreen={isFullscreen} data={cycleMap.data} territories={territories} enabled={mapLayers.wars} language={language} />
                 {/* Панель управления */}
         <Box className="map-fullscreen-controls">
           <Tooltip title={getLocalizedText('map_exit_fullscreen', 'Выйти из полноэкранного режима')}>
             <IconButton aria-label={getLocalizedText('map_exit_fullscreen', 'Выйти из полноэкранного режима')} onClick={toggleFullscreen} size="small" sx={{ color: 'white' }}>
               <FullscreenExit />
             </IconButton>
           </Tooltip>
         </Box>

                                                                                                                                                                                                                                                                                                                                                                                                                                               {/* Карта */}
                           <Box className="map-fullscreen-canvas">
              <Box className="map-fullscreen-stage">
                                                               <div
                   ref={svgRef}
                   className="fullscreen-svg-host"
                 />
             </Box>
         </Box>

                                   {/* Информационная панель */}
                     {(hoveredRegion || selectedRegion) && (
             <Paper
               className="fullscreen-territory-panel"
               sx={{
                 backgroundColor: 'rgba(0, 0, 0, 0.9)',
                 backdropFilter: 'blur(10px)',
                 border: '1px solid rgba(255, 255, 255, 0.2)'
               }}
             >
               <Typography variant="h6" color="primary" gutterBottom sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', minWidth: 0 }}>
                 <LocationOn sx={{ mr: 1 }} />
                 {territoryName(selectedRegion || hoveredRegion)}
                 {selectedRegion && (
                   <Chip 
                     label={getLocalizedText('map_selected_territory', 'Выбранная территория')}
                     size="small" 
                     color="success" 
                     sx={{ ml: 1 }}
                   />
                 )}
               </Typography>
               
               {/* Статус */}
               <Chip 
                 label={(selectedRegion || hoveredRegion).status === 'contested'
                   ? getLocalizedText('map_status_contested', 'Оспаривается')
                   : (selectedRegion || hoveredRegion).status === 'active'
                     ? getLocalizedText('map_status_active', 'Активна')
                     : getLocalizedText('map_status_neutral', 'Нейтральная')}
                 color={(selectedRegion || hoveredRegion).status === 'contested' ? 'error' : 
                        (selectedRegion || hoveredRegion).status === 'active' ? 'success' : 'default'}
                 size="small"
                 sx={{ mb: 1 }}
               />
               
               {/* Основная информация */}
               <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                 {getTerritoryDescription(
                   (selectedRegion || hoveredRegion)?.name,
                   (selectedRegion || hoveredRegion)?.description,
                   language,
                 )}
               </Typography>
               <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
                 <Chip size="small" color="warning" variant="outlined" label={getLocalizedText('map_strategic_potential', null, { value: (selectedRegion || hoveredRegion).prosperity_score || 0 })} />
                 <Chip size="small" color="success" variant="outlined" label={getLocalizedText('map_daily_gold', null, { value: (selectedRegion || hoveredRegion).daily_income || 0 })} />
                 <Chip
                   size="small"
                   color="info"
                   variant="outlined"
                   label={(selectedRegion || hoveredRegion).stronghold_power > 0
                     ? getLocalizedText('map_resources_summary', null, {
                       primary: resourceName((selectedRegion || hoveredRegion).resource_type, 'resource_iron'),
                       secondary: resourceName((selectedRegion || hoveredRegion).secondary_resource_type),
                     })
                     : getLocalizedText('map_resource_summary', null, {
                       resource: resourceName((selectedRegion || hoveredRegion).resource_type, 'resource_iron'),
                       value: (selectedRegion || hoveredRegion).resource_output || 1,
                     })}
                 />
               </Box>
               
               <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
               <Chip
                 icon={<AttachMoney />}
                 label={`${getLocalizedText('map_base_income', 'Базовый доход')}: ${(selectedRegion || hoveredRegion).resource_wealth || 0}`}
                   size="small" 
                   variant="outlined"
                 />
                 <Chip 
                   icon={<Shield />} 
                   label={`${getLocalizedText('map_fortifications', 'Укрепления')}: ${(selectedRegion || hoveredRegion).fortifications || 0}`}
                   size="small" 
                   variant="outlined"
                 />
               </Box>
               
               {getOwnerName(selectedRegion || hoveredRegion) && (
                 <Typography variant="caption" color="success.main" display="block">
                   {getLocalizedText('map_owner', 'Владелец территории')}: {getOwnerName(selectedRegion || hoveredRegion)}
                 </Typography>
               )}
             </Paper>
           )}
      </Box>
    );
  }

     return (
     <Container maxWidth={false} className="map-page prototype-exact-page">
       <CycleMapLayer svgRef={svgRef} svgContent={svgContent} fullscreen={isFullscreen} data={cycleMap.data} territories={territories} enabled={mapLayers.wars} language={language} />
       <Box className="page-title map-page-title">
         <Box>
           <div className="eyebrow">{getLocalizedText('map_prototype_eyebrow', 'Стратегическая карта')}</div>
           <h1 className="serif">{getLocalizedText('map_prototype_title', 'Карта Средиземья')}</h1>
           {!isInterseason && <p className="subtitle">{getLocalizedText('map_prototype_description', 'Выберите территорию, изучите её историю и начните наступление.')}</p>}
           <div className="map-page-actions"><RulesContextLink context="map" section="territories" /></div>
           {isInterseason && <Alert className="map-interseason-notice" severity="info" role="status">{getLocalizedText('season_archive_interseason')}{preseason.open && <><br /><Link to="/preseason">{getLocalizedText('preseason_title')}</Link></>}</Alert>}
         </Box>
         <Box className="map-page-messages">
          {isClanLeader && myClan && (
            <Box className="map-clan-command-ribbon" aria-label={getLocalizedText('map_clan_command_summary', 'Сводка главы клана')}>
              <span><Flag /> {getLocalizedText('common_influence', 'Влияние')} <strong>{formatPanelNumber(myClan.territory_points)}</strong></span>
            </Box>
          )}
          {attackMessage && (
            <Alert severity={attackMessage.severity} sx={{ mt: 2 }}>
              {attackMessage.text}
            </Alert>
          )}
        </Box>
       </Box>

       <MapCycleSchedule navigation={lastCampaignNavigation} />
       <MapSearchToolbar
         searchValue={mapSearch}
         territories={territories}
         strongholds={strongholds}
         regionValue={mapRegion}
         getTerritoryLabel={territoryName}
         labels={{
           controls: getLocalizedText('map_controls', 'Управление картой'),
           searchPlaceholder: getLocalizedText('map_search_placeholder', 'Найти территорию или клан'),
           strongholds: getLocalizedText('map_strongholds', 'Крепости'),
         }}
         onSearchChange={handleMapSearchChange}
         onSearchSubmit={selectSearchResult}
         onRegionChange={(territoryId) => {
           setMapRegion(territoryId);
           if (territoryId !== 'all') {
             const territory = strongholds.find((item) => Number(item.id) === Number(territoryId));
             if (territory) setSelectedRegion(territory);
           }
         }}
       />

       <CycleMapLegend data={cycleMap.data} enabled={mapLayers.wars} language={language} />
       <Box className="strategic-map-layout">
         {/* Одно содержимое используется в desktop-панели и мобильном Drawer. */}
         {(() => {
           const renderTerritoryDetails = ({ onClose = null } = {}) => (
             <>
               <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 1 }}>
                 <Typography id="mobile-territory-panel-title" variant="h6">
                   {getLocalizedText('map_territory', 'Территория')}
                 </Typography>
                 {onClose && (
                   <IconButton
                     aria-label={getLocalizedText('common_close', 'Закрыть')}
                     onClick={onClose}
                     sx={{ flex: '0 0 auto', width: 40, height: 40 }}
                   >
                     <Close />
                   </IconButton>
                 )}
               </Box>
           
           {(selectedRegion || hoveredRegion) ? (
              <Box>
                <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1, mb: 1.5 }}>
                  <LocationOn color="primary" sx={{ mt: 0.25, flex: '0 0 auto' }} />
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="h6" color="primary" sx={{ lineHeight: 1.25, overflowWrap: 'break-word', wordBreak: 'normal' }}>
                      {territoryName(selectedRegion || hoveredRegion)}
                    </Typography>
                    {selectedRegion && <Typography variant="caption" color="text.secondary">{getLocalizedText('map_selected_territory', 'Выбранная территория')}</Typography>}
                  </Box>
                </Box>
                
                {/* Статус территории */}
                <Box sx={{ mb: 2 }}>
                  <Chip 
                    label={(selectedRegion || hoveredRegion).is_playable === false
                      ? getLocalizedText('map_status_unavailable', 'Недоступна')
                      : (selectedRegion || hoveredRegion).status === 'contested'
                        ? getLocalizedText('map_status_contested', 'Оспаривается')
                        : (selectedRegion || hoveredRegion).status === 'active'
                          ? getLocalizedText('map_status_active', 'Активна')
                          : getLocalizedText('map_status_neutral', 'Нейтральная')}
                    color={(selectedRegion || hoveredRegion).is_playable === false ? 'default' :
                           (selectedRegion || hoveredRegion).status === 'contested' ? 'error' : 
                           (selectedRegion || hoveredRegion).status === 'active' ? 'success' : 'default'}
                    size="small"
                    sx={{ mb: 1 }}
                  />
                </Box>

                {selectedRegion && campaignNavigation?.mode === 'cycle_v1' && <>
                  {selectedCycleBattle && <Button fullWidth component={Link} to={selectedCycleBattle.href} variant="contained" startIcon={<Shield />} sx={{ my: 1 }}>
                    {getLocalizedText('map_open_active_battle')} #{selectedCycleBattle.battle_id}
                  </Button>}
                  <CycleMapPanel key={`${campaignNavigation?.cycleId}:${selectedRegion.id}:${cycleMap.data?.clan_id}`} {...cycleMap} territoryId={selectedRegion.id} territoryName={selectedRegion.name} cycleId={campaignNavigation?.cycleId} language={language} />
                </>}
                {((selectedRegion || hoveredRegion).has_port || (selectedRegion || hoveredRegion).stronghold_power > 0) && (
                  <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap', mb: 2 }}>
                    {(selectedRegion || hoveredRegion).has_port && (
                      <Chip
                        size="small"
                        color="info"
                        variant="outlined"
                        icon={<Anchor />}
                        label={isLegacyCampaign ? getLocalizedText('map_naval_level', null, {
                          level: Math.max((selectedRegion || hoveredRegion).port_level || 0, (selectedRegion || hoveredRegion).fleet_level || 0),
                        }) : getLocalizedText('map_admin_has_port')}
                      />
                    )}
                    {(selectedRegion || hoveredRegion).stronghold_power > 0 && (
                      <Chip
                        size="small"
                        color="warning"
                        variant="outlined"
                        label={getLocalizedText('map_great_fortress', null, { count: (selectedRegion || hoveredRegion).required_territories })}
                      />
                    )}
                  </Box>
                )}
                
                {/* Статистика */}
                {isInterseason && <p className="map-upcoming-label">{getLocalizedText('season_map_upcoming')}</p>}
                {isInterseason && upcomingMap.error ? <Alert severity="warning">{getLocalizedText('season_map_unavailable')} <Button onClick={upcomingMap.refresh}>{getLocalizedText('season_archive_retry')}</Button></Alert> : !isLegacyCampaign ? <CycleMapTerritorySummary data={isInterseason ? upcomingMap.data : cycleMap.data} territoryId={panelTerritory.id}
                  cycleId={campaignNavigation?.cycleId} language={language} hasPort={panelTerritory.has_port}
                  influence={isInterseason ? upcomingMap.data?.territories.find(row => row.territory_id === panelTerritory.id)?.influence_value : panelTerritory.influence_value} /> : <Box className="territory-summary">
                  <Box className="territory-summary__section">
                    <Typography className="territory-summary__heading">
                      {getLocalizedText('map_section_economy', 'Экономика')}
                    </Typography>
                    <Box className="territory-summary__grid">
                      <Box className="territory-summary__metric">
                        <Typography><AttachMoney /> {getLocalizedText('resource_gold', 'Золото')}</Typography>
                        <strong>{formatPanelNumber(panelDailyGold)}</strong>
                        <span>{getLocalizedText('map_per_day', 'за сутки')}</span>
                      </Box>
                      <Box className="territory-summary__metric">
                        <Typography>{React.createElement(RESOURCE_META[panelResourceRewards[0]?.resource]?.Icon || Hardware)} {getLocalizedText('map_resource_yield', 'Добыча')}</Typography>
                        <strong>{panelResourceRewards.map(({ resource, amount }) => `${resourceName(resource)} +${amount}`).join(' · ')}</strong>
                        <span>{getLocalizedText('map_every_day_after_ready', 'раз в сутки после 72 ч.')}</span>
                      </Box>
                    </Box>
                  </Box>

                  <Box className="territory-summary__section">
                    <Typography className="territory-summary__heading">
                      {getLocalizedText('map_section_influence', 'Влияние')}
                    </Typography>
                    <Box className="territory-summary__grid">
                      <Box className="territory-summary__metric">
                        <Typography><TrendingUp /> {getLocalizedText('map_ownership_influence', 'Влияние владения')}</Typography>
                        <strong>{getLocalizedText('map_permanent_value', null, { value: panelEconomy?.territory_influence ?? (panelTerritory.influence_value || 0) })}</strong>
                      </Box>
                      <Box className="territory-summary__metric">
                        <Typography><Flag /> {getLocalizedText('map_attack_requirement', 'Нужно для атаки')}</Typography>
                        <strong>{getLocalizedText('map_influence_value', null, { value: getAttackInfluenceCost(panelTerritory) })}</strong>
                      </Box>
                    </Box>
                  </Box>

                  <Box className="territory-summary__section">
                    <Typography className="territory-summary__heading">
                      {getLocalizedText('map_section_development', 'Развитие')}
                    </Typography>
                    <Box className="territory-summary__grid">
                      <Box className="territory-summary__metric"><Typography><People /> {getLocalizedText('map_population', 'Население')}</Typography><strong>{formatPanelNumber(panelTerritory.population)}</strong></Box>
                      <Box className="territory-summary__metric"><Typography><Shield /> {getLocalizedText('map_fortifications', 'Укрепления')}</Typography><strong>{panelTerritory.fortifications || 0}/10</strong></Box>
                      <Box className="territory-summary__metric"><Typography><MilitaryTech /> {getLocalizedText('map_land_attack', 'Сухопутная атака')}</Typography><strong>{panelTerritory.offense_level || 0}/10</strong></Box>
                      <Box className="territory-summary__metric"><Typography><Security /> {getLocalizedText('map_value', 'Ценность')}</Typography><strong>{formatPanelNumber(panelTerritory.strategic_value)}/10</strong></Box>
                      {panelTerritory.has_port && (
                        <Box className="territory-summary__metric"><Typography><DirectionsBoat /> {getLocalizedText('map_upgrade_naval', 'Морская мощь')}</Typography><strong>{panelEconomy?.naval_level ?? Math.max(panelTerritory.port_level || 0, panelTerritory.fleet_level || 0)}/10</strong></Box>
                      )}
                    </Box>
                  </Box>
                </Box>}
                
                {/* Владелец и кланы */}
                {getOwnerName(selectedRegion || hoveredRegion) && (
                  <Box className="territory-owner-card">
                    <Box className="territory-owner-card__header">
                      <Avatar
                        className="territory-owner-card__avatar"
                        src={(selectedRegion || hoveredRegion).owner_clan_map_emblem_url
                          || (selectedRegion || hoveredRegion).owner_clan_avatar_url
                          || undefined}
                      >
                        {(getOwnerName(selectedRegion || hoveredRegion) || '?').charAt(0)}
                      </Avatar>
                      <Box minWidth={0}>
                        <Typography className="territory-owner-card__eyebrow">
                          {getLocalizedText('map_owner', 'Владелец территории')}
                        </Typography>
                        {(selectedRegion || hoveredRegion).owner_clan_id ? (
                          <Link
                            className="entity-link territory-owner-card__name"
                            to={`/clans/${(selectedRegion || hoveredRegion).owner_clan_id}`}
                          >
                            {getOwnerName(selectedRegion || hoveredRegion)}
                          </Link>
                        ) : (
                          <Typography className="territory-owner-card__name">
                            {getOwnerName(selectedRegion || hoveredRegion)}
                          </Typography>
                        )}
                      </Box>
                    </Box>
                    <Box className="territory-owner-card__dates">
                      <Box>
                        <AccessTime />
                        <span>{getLocalizedText('map_controlled_since', 'Под контролем с')}</span>
                        <strong>
                          {formatMoscowDateTime(
                            (selectedRegion || hoveredRegion).owned_since,
                            getLocalizedText('map_after_capture', 'после захвата'),
                            language,
                          )}
                        </strong>
                      </Box>
                      {isLegacyCampaign && <Box>
                        {React.createElement(
                          RESOURCE_META[(selectedRegion || hoveredRegion).resource_type]?.Icon || Hardware
                        )}
                        <span>{getLocalizedText('map_next_yield', 'Следующая добыча')}</span>
                        <strong>
                          {formatMoscowDateTime(
                            panelEconomy?.next_resource_payout_at
                              || getNextResourcePayout(selectedRegion || hoveredRegion),
                            getLocalizedText('map_after_capture', 'после захвата'),
                            language,
                          )}
                        </strong>
                      </Box>}
                    </Box>
                  </Box>
                )}
                
                {getClanNames(selectedRegion || hoveredRegion, 'attacking').length > 0 && (
                  <Box className="territory-war-side territory-war-side--attack">
                    <MilitaryTech className="territory-war-side__icon" />
                    <Box minWidth={0}>
                      <Typography className="territory-war-side__label">{getLocalizedText('map_attacking_clan', 'Атакующий клан')}</Typography>
                      <Box className="territory-war-side__name">
                        {renderClanLinks(selectedRegion || hoveredRegion, 'attacking')}
                      </Box>
                    </Box>
                  </Box>
                )}
                
                {getClanNames(selectedRegion || hoveredRegion, 'defending').length > 0 && (
                  <Box className="territory-war-side territory-war-side--defense">
                    <Shield className="territory-war-side__icon" />
                    <Box minWidth={0}>
                      <Typography className="territory-war-side__label">{getLocalizedText('map_defending_clan', 'Защищающийся клан')}</Typography>
                      <Box className="territory-war-side__name">
                        {renderClanLinks(selectedRegion || hoveredRegion, 'defending')}
                      </Box>
                    </Box>
                  </Box>
                )}

                {getTradeRoutesForTerritory(selectedRegion || hoveredRegion).map((caravan) => {
                  const isSeaRoute = caravan.route_mode === 'sea'
                    || (caravan.route || []).some((step) => step.via === 'sea');
                  return (
                  <Box
                    className={`territory-trade-route${isSeaRoute ? ' territory-trade-route--sea' : ''}`}
                    key={caravan.offer_id}
                  >
                    {isSeaRoute
                      ? <DirectionsBoat className="territory-trade-route__icon" />
                      : <CaravanGlyph className="territory-trade-route__icon" />}
                    <Box minWidth={0}>
                      <Typography className="territory-trade-route__label">
                        {isSeaRoute
                          ? getLocalizedText('map_sea_delivery', 'Морская доставка')
                          : getLocalizedText('map_land_caravan', 'Сухопутный корован')} #{caravan.offer_id}
                      </Typography>
                      <Typography className="territory-trade-route__name">
                        {caravan.from_clan_name} ↔ {caravan.to_clan_name}
                      </Typography>
                      <Typography variant="caption">
                        {getLocalizedText('map_arrival', null, { date: formatMoscowDateTime(caravan.eta, '', language) })}
                      </Typography>
                    </Box>
                  </Box>
                  );
                })}
                
                {/* Описание */}
                <Divider sx={{ my: 1 }} />
                {selectedRegion && (
                  <Box sx={{ mt: 2, mb: 2 }}>
                    {campaignNavigationError && <Alert severity="error" sx={{ mb: 1 }}>
                      {cycleMessage('cycle_request_failed', language)}
                      <Button onClick={refreshCampaignNavigation}>{cycleMessage('common_retry', language)}</Button>
                    </Alert>}
                    {!isInterseason && campaignNavigation?.mode === 'cycle_v1' && campaignNavigation.href && !selectedCycleBattle && <Button fullWidth component={Link} to={campaignNavigation.href} variant="outlined" startIcon={<Shield />}>
                      {cycleMessage('cycle_battles_title', language)}
                    </Button>}
                    {(activeWarsByTerritory.get(Number(selectedRegion.id)) || []).map((war) => (
                      <Button key={war.id} fullWidth component={Link} to={`/battles/${war.id}`} variant="contained" startIcon={<Shield />} sx={{ mb: 1 }}>
                        {getLocalizedText('map_open_active_battle')} #{war.id}
                      </Button>
                    ))}
                    {isLegacyCampaign && isAdmin && (
                      <Button
                        fullWidth
                        variant="outlined"
                        color="info"
                        startIcon={<Settings />}
                        onClick={() => openAdminTerritoryEditor(selectedRegion)}
                        sx={{ mb: 1 }}
                      >
                        {getLocalizedText('map_territory_settings', 'Параметры территории')}
                      </Button>
                    )}
                    {isLegacyCampaign && (isSelectedOwnTerritory ? (
                      <Box sx={{ display: 'grid', gap: 1 }}>
                        {isClanLeader && (
                          <Button
                            fullWidth
                            variant="contained"
                            startIcon={<TrendingUp />}
                            onClick={() => openTerritoryManagement(selectedRegion)}
                          >
                            {getLocalizedText('map_manage_territory', 'Управление территорией')}
                          </Button>
                        )}
                      </Box>
                    ) : (
                      <>
                        <Button
                          fullWidth
                          variant="contained"
                          color="error"
                          startIcon={<Flag />}
                          onClick={handleAttackTerritory}
                          disabled={!canAttackSelected || attackingTerritoryId === selectedRegion.id}
                        >
                          {attackingTerritoryId === selectedRegion.id
                            ? getLocalizedText('map_starting_attack', 'Начинаем атаку...')
                            : getLocalizedText('map_attack_cost', null, { value: getAttackInfluenceCost(selectedRegion) })}
                        </Button>
                        {!canAttackSelected && (
                          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                            {getAttackDisabledReason(selectedRegion)}
                          </Typography>
                        )}
                      </>
                    ))}
                  </Box>
                )}
                
                {/* Специальные ресурсы */}
              </Box>
            ) : (
              myClan ? (
                <Box className="map-clan-economy-overview">
                  <Typography className="territory-summary__heading">{getLocalizedText('map_clan_total_income', 'Общий доход владений')}</Typography>
                  <Box className="territory-summary__grid">
                    <Box className="territory-summary__metric">
                      <Typography><AttachMoney /> {getLocalizedText('resource_gold', 'Золото')}</Typography>
                      <strong>+{formatPanelNumber(myClan.daily_income)}</strong>
                      <span>{getLocalizedText('map_per_day', 'за сутки')}</span>
                    </Box>
                    <Box className="territory-summary__metric">
                      <Typography><Hardware /> {getLocalizedText('map_rare_resources_total', 'Редкие ресурсы')}</Typography>
                      <strong>{clanDailyResourceRewards.length
                        ? clanDailyResourceRewards.map(({ resource, amount }) => `${resourceName(resource)} +${formatPanelNumber(amount)}`).join(' · ')
                        : '—'}</strong>
                      <span>{getLocalizedText('map_per_day_after_ready', 'за сутки после готовности')}</span>
                    </Box>
                  </Box>
                  <Typography variant="body2" color="text.secondary">{getLocalizedText('map_select_for_territory_details', 'Выберите землю, чтобы открыть её бонусы и развитие.')}</Typography>
                </Box>
              ) : (
                <Box><Typography variant="body2" color="text.secondary">{getLocalizedText('map_hover_region', 'Наведите на регион для получения информации')}</Typography></Box>
              )
            )}
             </>
           );

           if (isCompactMap) {
             return (
               <Drawer
                 anchor="bottom"
                 open={Boolean(selectedRegion)}
                 onClose={handleResetSelection}
                 transitionDuration={{ enter: 180, exit: 160 }}
                 slotProps={{
                   paper: {
                     className: 'mobile-territory-drawer',
                     role: 'dialog',
                     'aria-labelledby': 'mobile-territory-panel-title',
                     sx: {
                       maxHeight: '72dvh',
                       overflowY: 'auto',
                       backgroundColor: 'rgba(20, 20, 21, 0.98)',
                       backgroundImage: 'none',
                     },
                   },
                 }}
               >
                 <Box sx={{ p: 2 }}>
                   {renderTerritoryDetails({ onClose: handleResetSelection })}
                 </Box>
               </Drawer>
             );
           }

           return (
             <Paper
               component="aside"
               aria-label={getLocalizedText('map_territory', 'Территория')}
               className="strategic-map-shell territory-side-panel"
               elevation={3}
               sx={{
                 backgroundColor: 'background.paper',
                 border: '1px solid rgba(255, 255, 255, 0.1)',
                 p: 2,
                 overflow: 'auto',
               }}
             >
               {renderTerritoryDetails()}
             </Paper>
           );
         })()}

         {/* Карта */}
         <Paper
           component="section"
           role="region"
           aria-label={getLocalizedText('nav_map', 'Карта')}
           className="strategic-map-shell strategic-map-canvas"
           elevation={3}
           sx={{
             position: 'relative',
             overflow: 'hidden',
             backgroundColor: 'background.paper',
             border: '1px solid rgba(255, 255, 255, 0.1)'
           }}
         >
           {/* Панель управления */}
           <MapCanvasControls
             isLayerFilterOpen={layerFilterOpen}
             layers={mapLayers}
             labels={{
               layers: getLocalizedText('map_layers', 'Слои карты'),
               fullscreen: getLocalizedText('map_fullscreen', 'Полноэкранный режим'),
               wars: getLocalizedText('map_layer_wars', 'Войны'),
               trade: getLocalizedText('map_layer_trade', 'Торговые пути'),
               clanIcons: getLocalizedText('map_layer_clan_icons', 'Значки кланов'),
               attackable: getLocalizedText('map_layer_attackable', 'Доступные для атаки'),
             }}
             onLayerFilterToggle={() => setLayerFilterOpen((open) => !open)}
             onLayerToggle={handleLayerToggle}
             onFullscreen={toggleFullscreen}
           />

                                               {/* Контейнер карты */}
             <Box 
               sx={{ 
                 width: '100%', 
                 height: '100%',
                 position: 'relative',
                 overflow: 'hidden'
               }}
               onClick={(e) => {
                 // Сбрасываем hover при клике на пустое место карты
                 if (!e.target.classList.contains('interactive-region')) {
                   setHoveredRegion(null);
                   setSelectedRegion(null);
                   setAdminRouteSource(null);
                 }
               }}
             >
             <Box sx={{
               width: '100%',
               height: '100%',
               display: 'flex',
               alignItems: 'center',
               justifyContent: 'center'
             }}>
                                                               <div 
                   ref={svgRef}
                   style={{ 
                     width: '100%',
                     height: '100%',
                     pointerEvents: 'auto'
                   }}
                 />
             </Box>
           </Box>
         </Paper>
       </Box>

       <section className="section grid g3 map-context-grid" aria-label={getLocalizedText('map_selected_context', 'Сведения о выбранной территории')}>
         <article className="card panel">
           <div className="eyebrow">{panelTerritory ? territoryName(panelTerritory) : getLocalizedText('map_no_selection', 'Территория не выбрана')}</div>
           <h2>{getLocalizedText('map_history_title', 'История территории')}</h2>
           {panelTerritory ? (
             <div className="map-context-list">
               <div><b>{getLocalizedText('map_owner', 'Владелец')}</b><span>{getOwnerName(panelTerritory) || getLocalizedText('map_status_neutral', 'Нейтральная')}</span></div>
               <div><b>{getLocalizedText('map_controlled_since', 'Под контролем с')}</b><span>{formatMoscowDateTime(panelTerritory.owned_since, '—', language)}</span></div>
             </div>
           ) : <p className="muted">{getLocalizedText('map_select_context_hint', 'Выберите землю на карте, чтобы увидеть её историю.')}</p>}
         </article>
         <article className="card panel">
           <div className="eyebrow">{getLocalizedText('map_bonuses_title', 'Бонусы')}</div>
           <h2>{panelTerritory ? territoryName(panelTerritory) : getLocalizedText('map_no_selection', 'Территория не выбрана')}</h2>
           {panelTerritory && !isLegacyCampaign ? <p className="muted">{cycleMessage('cycle_map_frozen_bonuses', language)}</p> : panelTerritory ? (
             <ul className="map-context-bonuses">
               <li>{getLocalizedText('map_land_bonus_value', '+{value}% к силе сухопутной атаки', { value: formatPanelNumber(panelTerritory.offense_level || 0) })}</li>
               <li>{getLocalizedText('map_defense_bonus_value', '+{value}% к защите территории', { value: formatPanelNumber(panelTerritory.fortifications || 0) })}</li>
               <li>{getLocalizedText('map_sea_bonus_value', '+{value}% к атаке через воду', { value: formatPanelNumber(panelEconomy?.sea_attack_bonus_percent ?? (Math.max(panelTerritory.port_level || 0, panelTerritory.fleet_level || 0) * 3)) })}</li>
             </ul>
           ) : <p className="muted">{getLocalizedText('map_select_bonus_hint', 'Экономические эффекты появятся после выбора территории.')}</p>}
         </article>
         <article className="card panel">
           <div className="eyebrow">{getLocalizedText('map_neighbors_title', 'Соседние земли')}</div>
           <h2>{getLocalizedText('map_available_directions', 'Доступные направления')}</h2>
           {adjacentTerritories.length ? (
             <div className="map-neighbor-list">
               {adjacentTerritories.map((territory) => {
                 const ownerClanId = Number(territory.owner_clan_id || 0);
                 const relationClass = !ownerClanId
                   ? 'is-neutral'
                   : ownerClanId === Number(myClan?.id)
                     ? 'is-own'
                     : alliedClanIds.has(ownerClanId)
                       ? 'is-allied'
                       : hostileClanIds.has(ownerClanId)
                         ? 'is-enemy'
                         : 'is-neutral';
                 const relationLabel = hostileClanIds.has(ownerClanId) ? ` · ${getLocalizedText('diplomacy_hostility', 'Вражда').toLowerCase()}` : '';
                 return <button type="button" className={`btn ${relationClass}`} key={territory.id} onClick={() => setSelectedRegion(territory)}>{territoryName(territory)}{relationLabel}</button>;
               })}
             </div>
           ) : <p className="muted">{getLocalizedText('map_select_neighbors_hint', 'Соседние земли появятся после выбора территории.')}</p>}
           <div className="map-relation-key" aria-label={getLocalizedText('map_neighbors_title', 'Соседние земли')}>
             <span className="is-own">{getLocalizedText('map_relation_own', 'Свои')}</span>
             <span className="is-allied">{getLocalizedText('map_relation_allied', 'Союзники')}</span>
             <span className="is-enemy">{getLocalizedText('map_relation_enemy', 'Противники')}</span>
             <span className="is-neutral">{getLocalizedText('map_relation_free', 'Нейтральные')}</span>
           </div>
         </article>
       </section>

       <WarDeploymentDialog
         open={deploymentDialogOpen && legacyDialogAvailable}
         interactionDisabled={!isLegacyCampaign}
         onClose={handleDeploymentClose}
         clanId={myClan?.id}
         targetTerritory={selectedRegion}
         sourceTerritory={selectedAttackSource}
         onCreated={handleWarCreated}
       />

       <Dialog
         open={adminDialogOpen && isLegacyCampaign}
         onClose={() => !adminSaving && setAdminDialogOpen(false)}
         fullWidth
         maxWidth="md"
         PaperProps={{ sx: { borderRadius: 1, backgroundImage: 'none' } }}
       >
         <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2 }}>
           <Box sx={{ minWidth: 0 }}>
             <Typography variant="h6" sx={{ overflowWrap: 'anywhere' }}>
               {getLocalizedText('map_admin_parameters_title', null, { territory: territoryName(managedTerritory) })}
             </Typography>
             <Typography variant="body2" color="text.secondary">
               {getLocalizedText('map_admin_parameters_subtitle', 'Административная настройка экономики и статуса территории')}
             </Typography>
           </Box>
           <IconButton
             onClick={() => setAdminDialogOpen(false)}
             aria-label={getLocalizedText('common_close', 'Закрыть')}
             disabled={adminSaving}
           >
             <Close />
           </IconButton>
         </DialogTitle>
         <DialogContent dividers>
           {adminForm && (
             <Box sx={{ display: 'grid', gap: 3 }}>
               <Box>
                 <Typography variant="subtitle1" fontWeight={800} gutterBottom>{getLocalizedText('map_admin_economy', 'Экономика территории')}</Typography>
                 <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' }, gap: 2 }}>
                   <TextField
                     label={getLocalizedText('map_admin_base_wealth', 'Базовый достаток')}
                     type="number"
                     value={adminForm.resource_wealth}
                     onChange={(event) => setAdminForm({ ...adminForm, resource_wealth: Math.max(0, Number(event.target.value)) })}
                     helperText={getLocalizedText('map_admin_income_preview', null, {
                       income: getDailyIncomePreview(adminForm.resource_wealth, adminForm.population),
                       bonus: getPopulationIncomeBonusPercent(adminForm.population),
                     })}
                     inputProps={{ min: 0 }}
                   />
                   <TextField
                     select
                     label={getLocalizedText('map_admin_rare_resource', 'Редкий ресурс')}
                     value={adminForm.resource_type}
                     onChange={(event) => setAdminForm({
                       ...adminForm,
                       resource_type: event.target.value,
                       secondary_resource_type: adminForm.secondary_resource_type === event.target.value
                         ? ''
                         : adminForm.secondary_resource_type,
                     })}
                   >
                     {['iron', 'wood', 'food', 'mithril'].map((resource) => (
                       <MenuItem key={resource} value={resource}>
                         {resourceName(resource)}
                       </MenuItem>
                     ))}
                   </TextField>
                   {adminForm.stronghold_power > 0 && (
                     <TextField
                       select
                       label={getLocalizedText('map_admin_second_fortress_resource', 'Второй ресурс великой крепости')}
                       value={adminForm.secondary_resource_type}
                       onChange={(event) => setAdminForm({ ...adminForm, secondary_resource_type: event.target.value })}
                       helperText={getLocalizedText('map_admin_two_resource_hint', 'Первая добыча через 48 часов, затем по 1 единице двух ресурсов в сутки')}
                     >
                       {['iron', 'wood', 'food', 'mithril']
                         .filter((resource) => resource !== adminForm.resource_type)
                         .map((resource) => (
                           <MenuItem key={resource} value={resource}>
                             {resourceName(resource)}
                           </MenuItem>
                         ))}
                     </TextField>
                   )}
                   <TextField
                     label={getLocalizedText('map_admin_resource_output', 'Ресурса в сутки')}
                     type="number"
                     value={adminForm.resource_output}
                     onChange={(event) => setAdminForm({ ...adminForm, resource_output: Math.max(0, Number(event.target.value)) })}
                     inputProps={{ min: 0 }}
                   />
                   <TextField
                     label={getLocalizedText('map_population', 'Население')}
                     type="number"
                     value={adminForm.population}
                     onChange={(event) => setAdminForm({ ...adminForm, population: Math.max(0, Number(event.target.value)) })}
                     inputProps={{ min: 0 }}
                   />
                 </Box>
               </Box>

               <Divider />

               <Box>
                 <Typography variant="subtitle1" fontWeight={800} gutterBottom>{getLocalizedText('map_admin_influence', 'Влияние территории')}</Typography>
                 <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' }, gap: 2 }}>
                   <TextField
                     label={getLocalizedText('map_admin_owner_influence', 'Даёт влияния владельцу')}
                     type="number"
                     value={adminForm.influence_value}
                     onChange={(event) => setAdminForm({ ...adminForm, influence_value: Math.max(0, Number(event.target.value)) })}
                     helperText={getLocalizedText('map_admin_owner_influence_hint', 'Постоянный бонус клана: добавляется при захвате и исчезает при потере территории')}
                     inputProps={{ min: 0 }}
                   />
                   <TextField
                     label={getLocalizedText('map_admin_attack_influence', 'Нужно влияния для атаки')}
                     type="number"
                     value={adminForm.required_influence}
                     onChange={(event) => setAdminForm({ ...adminForm, required_influence: Math.max(0, Number(event.target.value)) })}
                     helperText={getLocalizedText('map_admin_attack_influence_hint', 'Минимальное влияние клана для объявления войны; при атаке влияние не списывается')}
                     inputProps={{ min: 0 }}
                   />
                 </Box>
               </Box>

               <Divider />

               <Box>
                 <Typography variant="subtitle1" fontWeight={800} gutterBottom>{getLocalizedText('map_admin_development', 'Уровни развития')}</Typography>
                 <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                   {getLocalizedText('map_admin_value_formula', 'Ценность территории равна среднему значению доступных уровней развития.')}
                 </Typography>
                 <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, minmax(0, 1fr))' }, gap: 2 }}>
                   {[
                     ['development_level', getLocalizedText('map_upgrade_population', 'Развитие населения')],
                     ['fortifications', getLocalizedText('map_upgrade_fortifications', 'Укрепления')],
                     ['offense_level', getLocalizedText('map_upgrade_offense', 'Военный лагерь')],
                   ].map(([field, label]) => (
                     <TextField
                       key={field}
                       label={label}
                       type="number"
                       value={adminForm[field]}
                       onChange={(event) => setAdminForm({ ...adminForm, [field]: Math.min(10, Math.max(0, Number(event.target.value))) })}
                       inputProps={{ min: 0, max: 10 }}
                     />
                   ))}
                   {adminForm.has_port && (
                     <TextField
                       label={getLocalizedText('map_admin_naval_level', 'Уровень морской мощи')}
                       type="number"
                       value={Math.max(adminForm.port_level || 0, adminForm.fleet_level || 0)}
                       onChange={(event) => {
                         const navalLevel = Math.min(10, Math.max(0, Number(event.target.value)));
                         setAdminForm({ ...adminForm, port_level: navalLevel, fleet_level: navalLevel });
                       }}
                       inputProps={{ min: 0, max: 10 }}
                     />
                   )}
                 </Box>
               </Box>

               <Divider />

               <Box>
                 <Typography variant="subtitle1" fontWeight={800} gutterBottom>{getLocalizedText('map_admin_strategy', 'Стратегические свойства')}</Typography>
                 <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, minmax(0, 1fr))' }, gap: 2 }}>
                   <TextField
                     label={getLocalizedText('map_admin_required_territories', 'Нужно территорий для атаки')}
                     type="number"
                     value={adminForm.required_territories}
                     onChange={(event) => setAdminForm({ ...adminForm, required_territories: Math.max(0, Number(event.target.value)) })}
                     inputProps={{ min: 0, max: 76 }}
                   />
                   <TextField
                     label={getLocalizedText('map_admin_fortress_power', 'Сила великой крепости')}
                     type="number"
                     value={adminForm.stronghold_power}
                     onChange={(event) => setAdminForm({ ...adminForm, stronghold_power: Math.min(10, Math.max(0, Number(event.target.value))) })}
                     helperText={getLocalizedText('map_admin_regular_territory_hint', '0 — обычная территория')}
                     inputProps={{ min: 0, max: 10 }}
                   />
                 </Box>
                 <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 2 }}>
                   <FormControlLabel
                     control={<Switch checked={adminForm.is_playable} onChange={(event) => setAdminForm({ ...adminForm, is_playable: event.target.checked })} />}
                     label={getLocalizedText('map_admin_playable', 'Игровая территория')}
                   />
                   <FormControlLabel
                     control={<Switch checked={adminForm.is_coastal} onChange={(event) => setAdminForm({ ...adminForm, is_coastal: event.target.checked })} />}
                     label={getLocalizedText('map_admin_coastal', 'Прибрежная')}
                   />
                   <FormControlLabel
                     control={<Switch checked={adminForm.has_port} onChange={(event) => setAdminForm({ ...adminForm, has_port: event.target.checked })} />}
                     label={getLocalizedText('map_admin_has_port', 'Есть порт')}
                   />
                 </Box>
               </Box>
             </Box>
           )}
         </DialogContent>
         <DialogActions>
           <Button onClick={() => setAdminDialogOpen(false)} disabled={adminSaving}>{getLocalizedText('common_cancel', 'Отмена')}</Button>
           <Button
             variant="contained"
             onClick={handleAdminTerritorySave}
             disabled={adminSaving}
             startIcon={adminSaving ? <CircularProgress size={18} /> : <Settings />}
           >
             {adminSaving
               ? getLocalizedText('map_admin_saving', 'Сохранение...')
               : getLocalizedText('map_admin_save_parameters', 'Сохранить параметры')}
           </Button>
         </DialogActions>
       </Dialog>

       <Dialog
         open={territoryDialogOpen && isLegacyCampaign}
         onClose={() => setTerritoryDialogOpen(false)}
         fullWidth
         maxWidth="md"
         PaperProps={{ className: 'territory-management-dialog', sx: { borderRadius: 1, backgroundImage: 'none' } }}
       >
         <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 2, pb: 1 }}>
           <Box sx={{ minWidth: 0 }}>
             <Typography variant="h6" sx={{ overflowWrap: 'anywhere' }}>{territoryName(managedTerritory) || getLocalizedText('map_manage_territory', 'Управление территорией')}</Typography>
             <Typography variant="body2" color="text.secondary">{getLocalizedText('map_development_subtitle', 'Развитие владения клана')}</Typography>
           </Box>
           <IconButton onClick={() => setTerritoryDialogOpen(false)} aria-label={getLocalizedText('common_close', 'Закрыть')}><Close /></IconButton>
         </DialogTitle>
         <DialogContent dividers>
           {economyLoading ? (
             <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>
           ) : (
             <>
               <Typography variant="overline" color="text.secondary">{getLocalizedText('map_clan_storage', 'Общий склад клана')}</Typography>
               <Typography variant="body2" color="text.secondary">
                 {getLocalizedText('map_economy_explanation', 'Золото поступает ежедневно. Влияние действует постоянно. Первый ресурс добывается через 48 часов, затем раз в сутки.')}
               </Typography>
               <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: 1.5, mt: 0.5, mb: 3 }}>
                 {Object.entries(RESOURCE_META).map(([key, { color, Icon: icon }]) => (
                   <Box key={key} sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.5 }}>
                     {React.createElement(icon, { sx: { color, fontSize: 24 } })}
                     <Box>
                       <Typography variant="caption" color="text.secondary" display="block">{resourceName(key)}</Typography>
                       <Typography variant="subtitle2" fontWeight={800}>{myClan?.[key] || 0}</Typography>
                     </Box>
                   </Box>
                 ))}
               </Box>

               <Alert severity="info" variant="outlined" sx={{ mb: 2.5 }}>
                 {getLocalizedText('map_permanent_influence_notice', null, { value: managedEconomy?.territory_influence || 0 })}
                 {' '}{getLocalizedText('map_after_resource_ready', 'После 48 часов, затем раз в сутки:')}{' '}
                 {(managedEconomy?.daily_resource_rewards || []).map(({ resource, amount }) => (
                   <strong key={resource}>
                     +{amount} {resourceName(resource)}{' '}
                   </strong>
                 ))}
                 {' '}{getLocalizedText('map_next_yield', 'Следующая добыча')}: {formatMoscowDateTime(
                   managedEconomy?.next_resource_payout_at,
                   getLocalizedText('map_after_capture', 'после захвата'),
                   language,
                 )}.
               </Alert>

               <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: 'repeat(3, minmax(0, 1fr))' }, gap: 2 }}>
                 {Object.entries(TERRITORY_UPGRADES)
                   .filter(([key]) => managedTerritory?.has_port || key !== 'naval')
                   .map(([key, upgrade]) => {
                   const level = {
                     population: managedEconomy?.development_level || 0,
                     fortifications: managedTerritory?.fortifications || 0,
                     offense: managedEconomy?.offense_level || 0,
                     naval: managedEconomy?.naval_level || Math.max(managedEconomy?.port_level || 0, managedEconomy?.fleet_level || 0),
                   }[key];
                   const cost = managedEconomy?.upgrade_quotes?.[key] || {};
                   const isMax = level >= 10;
                   const affordable = canAffordUpgrade(cost);
                   const UpgradeIcon = upgrade.Icon;
                   const populationGrowth = Math.max(
                     0,
                     Math.floor(
                       (managedTerritory?.population || 0)
                       * (managedEconomy?.population_growth_percent_per_level || 4)
                       / 100
                     ) + (managedEconomy?.population_flat_growth_per_level || 20)
                   );
                   const effectText = {
                      population: getLocalizedText('map_next_level_population', null, {
                        value: populationGrowth.toLocaleString(language),
                        bonus: managedEconomy?.population_next_development_income_bonus_percent || 0,
                      }),
                     fortifications: getLocalizedText('map_next_level_defense', 'Следующий уровень: +2% к защите'),
                     offense: getLocalizedText('map_next_level_land', 'Следующий уровень: +2% к сухопутной атаке'),
                     naval: getLocalizedText('map_next_level_naval', 'Следующий уровень: +3% к морской атаке'),
                   }[key];
                   return (
                     <Box key={key} sx={{ display: 'flex', flexDirection: 'column', minHeight: 285, py: 1 }}>
                       <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.25, mb: 1 }}>
                         <Box sx={{ width: 40, height: 40, display: 'grid', placeItems: 'center', bgcolor: `${upgrade.color}18`, border: `1px solid ${upgrade.color}55`, borderRadius: 1 }}>
                           <UpgradeIcon sx={{ color: upgrade.color }} />
                         </Box>
                         <Box sx={{ minWidth: 0 }}>
                           <Typography variant="subtitle1" fontWeight={800} sx={{ lineHeight: 1.2 }}>{getLocalizedText(upgrade.labelKey)}</Typography>
                           <Typography variant="caption" color="text.secondary">{getLocalizedText('map_level', null, { level })}</Typography>
                         </Box>
                       </Box>
                       <LinearProgress variant="determinate" value={level * 10} sx={{ height: 6, borderRadius: 1, mb: 1.5 }} />
                       <Typography variant="body2" color="text.secondary" sx={{ minHeight: 62 }}>{getLocalizedText(upgrade.descriptionKey)}</Typography>
                       <Typography variant="body2" fontWeight={800} color="info.main" sx={{ mt: 1 }}>
                         {effectText}
                       </Typography>
                       <Typography variant="caption" fontWeight={800} color="warning.main" sx={{ mt: 1, mb: 0.75 }}>
                         {isMax
                           ? getLocalizedText('map_max_level', 'Максимальный уровень')
                           : getLocalizedText('map_next_level_cost', 'Цена следующего уровня')}
                       </Typography>
                       {!isMax && (
                         <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1.5 }}>
                           {Object.entries(cost).map(([resource, amount]) => {
                             const meta = RESOURCE_META[resource];
                             const CostIcon = meta.Icon;
                             return (
                               <Tooltip title={resourceName(resource)} key={resource} arrow>
                                 <Chip
                                   size="small"
                                   icon={<CostIcon style={{ color: meta.color }} />}
                                   label={`${amount} ${resourceName(resource)}`}
                                   color={(myClan?.[resource] || 0) >= amount ? 'default' : 'error'}
                                   variant="outlined"
                                 />
                               </Tooltip>
                             );
                           })}
                         </Box>
                       )}
                       <Button
                         variant="contained"
                         fullWidth
                         sx={{ mt: 'auto' }}
                         disabled={isMax || !affordable || Boolean(upgradingType)}
                         onClick={() => handleTerritoryUpgrade(key)}
                       >
                         {upgradingType === key
                           ? getLocalizedText('map_upgrading', 'Улучшаем...')
                           : affordable
                             ? getLocalizedText('map_buy_upgrade', 'Купить улучшение')
                             : getLocalizedText('map_not_enough_resources', 'Не хватает ресурсов')}
                       </Button>
                     </Box>
                   );
                 })}
               </Box>
             </>
           )}
         </DialogContent>
         <DialogActions sx={{ justifyContent: 'flex-end', px: 3 }}>
           <Button onClick={() => setTerritoryDialogOpen(false)}>{getLocalizedText('common_close', 'Закрыть')}</Button>
         </DialogActions>
       </Dialog>
     </Container>
   );
};

export default MapPage; 
