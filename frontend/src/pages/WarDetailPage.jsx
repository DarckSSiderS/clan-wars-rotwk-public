import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Container,
  Divider,
  LinearProgress,
  Pagination,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Anchor,
  Assessment,
  Landscape,
  Schedule,
  Security,
  Shield,
  SportsEsports,
  PersonOutline,
  EmojiEvents,
  CheckCircleOutline,
  HighlightOff,
} from '@mui/icons-material';
import { keyframes } from '@mui/material/styles';
import { warService } from '../services/warService';
import { getTerritoryName } from '../i18n/territories';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { formatMoscowDateTime } from '../utils/dateTime';
import { getFactionIcon } from '../data/factions';
import PlayerIdentity from '../components/PlayerIdentity';
import WarSideGroups from '../components/WarSideGroups';

const MATCHES_PER_PAGE = 10;
const formatPoints = (value) => Number(value || 0).toFixed(2).replace(/\.?0+$/, '');
const formatProbability = (value, t) => (
  value == null ? t('war_no_snapshot', 'нет снимка') : `${(Number(value) * 100).toFixed(1)}%`
);
const patchLabel = (value, t) => ({
  patch_202: 'Patch 2.02',
  ennorath: 'Ennorath',
  all: t('wars_both_patches', 'Оба патча'),
}[value] || t('war_old_match', 'Данные старого матча'));
const eligibilityLabel = (code, t) => ({
  attack_squad_member: t('war_match_eligibility_attack_squad_member'),
  defending_clan_member: t('war_match_eligibility_defending_clan_member'),
  not_assigned_to_attack_squad: t('war_match_eligibility_not_assigned_to_attack_squad'),
  not_eligible_for_whole_clan_defense: t('war_match_eligibility_not_eligible_for_whole_clan_defense'),
  not_a_war_side: t('war_match_eligibility_not_a_war_side'),
}[code]);

const PointFormula = ({ side, t }) => (
  <Typography variant="body2" color="text.secondary">
    {t('war_point_formula', null, {
      base: formatPoints(side.base_points),
      power: side.power_bonus_points ? t('war_formula_power', null, { value: formatPoints(side.power_bonus_points) }) : '',
      team: side.team_bonus_points ? t('war_formula_team', null, { value: formatPoints(side.team_bonus_points) }) : '',
      relics: side.relic_bonus_points ? t('war_formula_relics', null, { value: formatPoints(side.relic_bonus_points) }) : '',
      total: formatPoints(side.total_points),
    })}
  </Typography>
);

const scoreReveal = keyframes`
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`;

const emblemPulse = keyframes`
  0%, 100% {
    transform: scale(1);
    filter: brightness(1);
  }
  50% {
    transform: scale(1.06);
    filter: brightness(1.2);
  }
`;

const progressGlint = keyframes`
  from { transform: translateX(-140%); }
  to { transform: translateX(360%); }
`;

const WarMetricTile = ({
  label,
  value,
  detail,
  detailTo,
  accent,
  icon,
}) => (
  <Box
    sx={{
      minWidth: 0,
      minHeight: 112,
      p: 2,
      display: 'flex',
      alignItems: 'center',
      gap: 1.5,
      border: '1px solid',
      borderColor: `${accent}55`,
      borderLeft: `4px solid ${accent}`,
      bgcolor: 'rgba(24, 25, 25, 0.96)',
      boxShadow: '0 8px 22px rgba(0, 0, 0, 0.18)',
    }}
  >
    <Box
      sx={{
        width: 40,
        height: 40,
        flex: '0 0 40px',
        display: 'grid',
        placeItems: 'center',
        color: accent,
        border: '1px solid',
        borderColor: `${accent}77`,
        bgcolor: `${accent}14`,
      }}
    >
      {icon}
    </Box>
    <Box minWidth={0} flex={1}>
      <Typography variant="caption" sx={{ color: accent, fontWeight: 900 }}>
        {label}
      </Typography>
      <Typography variant="h4" fontWeight={900} lineHeight={1.05}>
        {value}
      </Typography>
      {detailTo ? (
        <Typography
          component={Link}
          className="entity-link"
          to={detailTo}
          variant="body2"
          sx={{ display: 'block', mt: 0.5, overflowWrap: 'anywhere' }}
        >
          {detail}
        </Typography>
      ) : (
        <Typography variant="body2" color="text.secondary" mt={0.5}>
          {detail}
        </Typography>
      )}
    </Box>
  </Box>
);

const WarScoreSide = ({ score, war, leaderPoints, leaderCount, index, t }) => {
  const isAttacker = score.clan_id === war.attacking_clan_id;
  const isAtLead = Number(score.points || 0) === leaderPoints && leaderPoints > 0;
  const isLeader = isAtLead && leaderCount === 1;
  const isTied = isAtLead && leaderCount > 1;
  const accent = isAttacker ? '#ff5b57' : '#69aef0';
  const background = isAttacker
    ? 'rgba(255, 72, 72, 0.075)'
    : 'rgba(79, 159, 232, 0.075)';
  const maxVisiblePoints = Math.max(
    1,
    ...(war.clan_scores || []).map((item) => Number(item.points || 0)),
  );
  const progress = Math.max(3, Number(score.points || 0) / maxVisiblePoints * 100);

  return (
    <Box
      sx={{
        position: 'relative',
        overflow: 'hidden',
        minHeight: 190,
        p: { xs: 2, md: 2.5 },
        border: '1px solid',
        borderColor: `${accent}55`,
        borderLeft: `4px solid ${accent}`,
        bgcolor: background,
        animation: `${scoreReveal} 500ms ease-out ${index * 100}ms both`,
        '@media (prefers-reduced-motion: reduce)': {
          animation: 'none',
        },
      }}
    >
      <Box display="flex" alignItems="center" justifyContent="space-between" gap={2} mb={2}>
        <Box display="flex" alignItems="center" gap={1.25} minWidth={0}>
          <Box
            sx={{
              width: 42,
              height: 42,
              flex: '0 0 42px',
              display: 'grid',
              placeItems: 'center',
              color: accent,
              border: '1px solid',
              borderColor: `${accent}88`,
              bgcolor: `${accent}14`,
              animation: `${emblemPulse} 3.2s ease-in-out infinite`,
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            }}
          >
            {isAttacker ? (
              <Box component="span" sx={{ fontSize: 25, lineHeight: 1 }} aria-hidden="true">⚔</Box>
            ) : (
              <Shield sx={{ fontSize: 25 }} />
            )}
          </Box>
          <Box minWidth={0}>
            <Typography variant="caption" sx={{ color: accent, fontWeight: 800 }}>
              {isAttacker ? t('wars_attack', 'АТАКА') : t('wars_defense', 'ЗАЩИТА')}
            </Typography>
            <Typography variant="h6" noWrap>
              <Link className="entity-link" to={`/clans/${score.clan_id}`}>
                {score.clan_name}
              </Link>
            </Typography>
          </Box>
        </Box>
        {isLeader && (
          <Chip
            size="small"
            icon={<EmojiEvents />}
            label={t('war_leading', 'Лидирует')}
            sx={{
              color: '#ffd166 !important',
              borderColor: 'rgba(255, 209, 102, 0.55) !important',
              bgcolor: 'rgba(255, 209, 102, 0.08) !important',
            }}
            variant="outlined"
          />
        )}
        {isTied && (
          <Chip
            size="small"
            label={t('war_tied', 'Равный счёт')}
            sx={{
              color: 'text.secondary !important',
              borderColor: 'rgba(255, 255, 255, 0.22) !important',
              bgcolor: 'transparent !important',
            }}
            variant="outlined"
          />
        )}
      </Box>

      <Box display="flex" alignItems="baseline" justifyContent="space-between" gap={2} mb={1}>
        <Typography variant="body2" color="text.secondary">{t('wars_territory_points', 'Очки территории')}</Typography>
        <Typography variant="h4" fontWeight={900} sx={{ color: accent }}>
          {formatPoints(score.points)}
        </Typography>
      </Box>
      <LinearProgress
        variant="determinate"
        value={progress}
        sx={{
          height: 7,
          bgcolor: 'rgba(255,255,255,0.08)',
          mb: 1.5,
          overflow: 'hidden',
          '& .MuiLinearProgress-bar': {
            bgcolor: accent,
            position: 'relative',
            overflow: 'hidden',
            '&::after': {
              content: '""',
              position: 'absolute',
              inset: 0,
              width: '35%',
              bgcolor: 'rgba(255,255,255,0.3)',
              animation: `${progressGlint} 3.8s ease-in-out infinite`,
              '@media (prefers-reduced-motion: reduce)': {
                animation: 'none',
              },
            },
          },
        }}
      />
      <Box display="flex" gap={1} flexWrap="wrap" mb={0.75}>
        <Chip
          size="small"
          label={t('war_wins_count', null, { count: score.wins })}
          sx={{
            bgcolor: `${accent}14 !important`,
            borderColor: `${accent}55 !important`,
          }}
        />
        <Chip
          size="small"
          label={t('war_losses_count', null, { count: score.losses })}
          variant="outlined"
          sx={{
            bgcolor: 'transparent !important',
            borderColor: `${accent}55 !important`,
          }}
        />
        <Chip
          size="small"
          label={t('war_winrate_value', null, { value: score.win_rate })}
          variant="outlined"
          sx={{
            bgcolor: 'transparent !important',
            borderColor: `${accent}55 !important`,
          }}
        />
      </Box>
      <Typography variant="caption" color="text.secondary">
        {t('wars_score_breakdown', null, {
          base: formatPoints(score.base_points),
          power: formatPoints(score.power_bonus_points),
          relics: formatPoints(score.relic_bonus_points),
        })}
      </Typography>
    </Box>
  );
};

const WarMatchSide = ({ side, war, participants = [], patchFamily, t }) => {
  const isAttacker = side.clan_id === war.attacking_clan_id;
  const isDefender = side.clan_id === war.defending_clan_id;
  const role = isAttacker ? 'attacker' : isDefender ? 'defender' : 'outsider';
  const styles = {
    attacker: {
      color: '#ff625f',
      borderColor: '#ff4848',
      background: 'rgba(255, 72, 72, 0.08)',
      label: t('war_attacking_clan', 'Атакующий клан'),
    },
    defender: {
      color: '#74b9ff',
      borderColor: '#4f9fe8',
      background: 'rgba(79, 159, 232, 0.08)',
      label: t('war_defending_clan', 'Защищающийся клан'),
    },
    outsider: {
      color: 'text.secondary',
      borderColor: 'rgba(255, 255, 255, 0.16)',
      background: 'rgba(255, 255, 255, 0.025)',
      label: t('war_outsider', 'Внешний игрок'),
    },
  }[role];

  const marker = role === 'attacker' ? (
    <Box component="span" sx={{ fontSize: 20, lineHeight: 1 }} aria-hidden="true">⚔</Box>
  ) : role === 'defender' ? (
    <Shield sx={{ fontSize: 20 }} />
  ) : (
    <PersonOutline sx={{ fontSize: 19 }} />
  );

  return (
    <Box
      sx={{
        height: '100%',
        p: 1.5,
        borderLeft: '3px solid',
        borderColor: styles.borderColor,
        bgcolor: styles.background,
      }}
    >
      <Box display="flex" alignItems="center" gap={1} mb={0.5}>
        <Tooltip title={styles.label}>
          <Box display="inline-flex" alignItems="center" sx={{ color: styles.color }}>
            {marker}
          </Box>
        </Tooltip>
        <Typography variant="body2" fontWeight={800}>
          {side.clan_id ? (
            <Link className="entity-link" to={`/clans/${side.clan_id}`}>
              {side.clan_name}
            </Link>
          ) : <PlayerIdentity username={side.username} />}
        </Typography>
        <Typography variant="caption" sx={{ color: styles.color, ml: 'auto' }}>
          {styles.label}
        </Typography>
      </Box>
      {side.expected_probability != null ? (
        <Typography variant="body2">
          {t('war_elo_probability', null, {
            elo: side.rating ?? 1000,
            patch: patchLabel(patchFamily, t),
            probability: formatProbability(side.expected_probability, t),
          })}
        </Typography>
      ) : (
        <Typography variant="body2" color="text.secondary">
          {t('war_old_elo', 'Старый расчёт без снимка Elo')} · {patchLabel(patchFamily, t)}
        </Typography>
      )}
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
        {t('war_team_composition', null, {
          teamSize: side.team_size || participants.length || 1,
          clanMembers: side.clan_members || 0,
          bonus: side.team_bonus_percent ? t('war_team_bonus', null, { value: side.team_bonus_percent }) : '',
        })}
      </Typography>
      {side.eligibility_code && (
        <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" mt={1}>
          <Chip
            size="small"
            color={Number(side.participation_share || 0) > 0 ? 'success' : 'warning'}
            variant="outlined"
            label={eligibilityLabel(side.eligibility_code, t) || side.eligibility_code}
          />
          {side.participation_share != null && (
            <Chip size="small" variant="outlined" label={t('war_match_participation_share', null, { value: Math.round(Number(side.participation_share) * 100) })} />
          )}
        </Stack>
      )}
      {participants.length > 0 && (
        <Stack spacing={0.75} mt={1.25}>
          {participants.map((participant) => (
            <Box
              key={`${participant.username}-${participant.player_uuid || ''}`}
              sx={{
                display: 'grid',
                gridTemplateColumns: '30px minmax(0, 1fr) auto',
                alignItems: 'center',
                gap: 1,
                p: 0.75,
                bgcolor: 'rgba(0, 0, 0, 0.14)',
              }}
            >
              <Box
                component="img"
                src={getFactionIcon(participant.faction, 'small')}
                alt=""
                sx={{ width: 30, height: 30, objectFit: 'contain' }}
              />
              <PlayerIdentity
                username={participant.username}
                linkToProfile={Boolean(participant.user_id)}
                usernameClassName={participant.user_id ? 'entity-link' : ''}
              />
              <Typography variant="caption" color="text.secondary">
                Elo {participant.elo ?? '—'} · {patchLabel(patchFamily, t)}
              </Typography>
            </Box>
          ))}
        </Stack>
      )}
      <PointFormula side={side} t={t} />
    </Box>
  );
};

const WarDetailPage = () => {
  const { warId } = useParams();
  const { getLocalizedText: t, language } = useLocalizationContext();
  const [war, setWar] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [matchPage, setMatchPage] = useState(1);

  useEffect(() => {
    const loadWar = async () => {
      try {
        setWar(await warService.getWar(warId));
      } catch (loadError) {
        setError(loadError.response?.data?.detail || t('wars_load_error', 'Не удалось загрузить войну'));
      } finally {
        setLoading(false);
      }
    };
    loadWar();
  }, [t, warId]);

  const totalMatches = useMemo(
    () => (war?.tracked_matches || 0) + (war?.rejected_matches || 0),
    [war],
  );
  const matchResults = useMemo(() => war?.match_breakdown || [], [war]);
  const matchPageCount = Math.max(1, Math.ceil(matchResults.length / MATCHES_PER_PAGE));
  const visibleMatchResults = useMemo(() => {
    const pageStart = (matchPage - 1) * MATCHES_PER_PAGE;
    return matchResults.slice(pageStart, pageStart + MATCHES_PER_PAGE);
  }, [matchPage, matchResults]);

  useEffect(() => {
    setMatchPage(1);
  }, [warId, matchResults.length]);
  const leaderPoints = useMemo(
    () => Math.max(0, ...(war?.clan_scores || []).map((score) => Number(score.points || 0))),
    [war],
  );
  const leaderCount = useMemo(
    () => (war?.clan_scores || []).filter(
      (score) => Number(score.points || 0) === leaderPoints,
    ).length,
    [leaderPoints, war],
  );

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="55vh">
        <CircularProgress />
      </Box>
    );
  }

  if (error || !war) {
    return <Container sx={{ mt: 4 }}><Alert severity="error">{error || t('war_not_found', 'Война не найдена')}</Alert></Container>;
  }

  return (
    <Container maxWidth="lg" className="war-detail-page" sx={{ mt: 4, mb: 6 }}>
      <Box display="flex" alignItems="flex-start" gap={2} mb={3}>
        <Security sx={{ fontSize: 44, color: 'primary.main' }} />
        <Box>
          <Typography variant="h4" component="h1">{getTerritoryName(war.territory_name, language)}</Typography>
          <Typography color="text.secondary">
            {war.war_type === 'neutral_capture'
              ? t('wars_neutral_capture', 'Захват нейтральной территории')
              : t('wars_territory_attack', 'Война за территорию')}
          </Typography>
        </Box>
      </Box>

      <Paper sx={{ p: { xs: 2, md: 3 }, mb: 3 }}>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} justifyContent="space-between">
          <Box>
            <Typography variant="overline" color="text.secondary">{t('war_attacking_clan', 'Атакующий клан')}</Typography>
            <Typography variant="h6">
              <Link className="entity-link" to={`/clans/${war.attacking_clan_id}`}>
                {war.attacking_clan_name}
              </Link>
            </Typography>
            <Chip size="small" variant="outlined" label={patchLabel(war.attacker_patch, t)} sx={{ mt: 1 }} />
          </Box>
          <Box textAlign={{ xs: 'left', md: 'center' }}>
            <Typography variant="overline" color="text.secondary">{t('war_route_and_deadline', 'Маршрут и срок')}</Typography>
            <Box display="flex" gap={1} justifyContent={{ xs: 'flex-start', md: 'center' }} flexWrap="wrap">
              <Chip
                icon={war.attack_route === 'sea' ? <Anchor /> : <Landscape />}
                label={war.attack_route === 'sea' ? t('wars_sea_attack', 'Морская атака') : t('wars_land_attack', 'Сухопутная атака')}
              />
              <Chip
                icon={<Schedule />}
                label={war.ends_at
                  ? t('wars_until', null, { date: formatMoscowDateTime(war.ends_at, '', language) })
                  : t('war_no_deadline', 'Без срока')}
              />
            </Box>
          </Box>
          <Box textAlign={{ xs: 'left', md: 'right' }}>
            <Typography variant="overline" color="text.secondary">{t('war_defender', 'Защитник')}</Typography>
            <Typography variant="h6">
              {war.defending_clan_id ? (
                <Link className="entity-link" to={`/clans/${war.defending_clan_id}`}>
                  {war.defending_clan_name}
                </Link>
              ) : t('wars_neutral_land', 'Нейтральная земля')}
            </Typography>
            {war.defending_clan_id && (
              <Chip size="small" variant="outlined" label={patchLabel(war.defender_patch, t)} sx={{ mt: 1 }} />
            )}
          </Box>
        </Stack>
      </Paper>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: {
            xs: 'minmax(0, 1fr)',
            sm: 'repeat(2, minmax(0, 1fr))',
            lg: 'repeat(4, minmax(0, 1fr))',
          },
          alignItems: 'stretch',
          gap: 2,
          mb: 3,
        }}
      >
        <WarMetricTile
          label={t('war_counted_matches', 'ЗАЧТЁННЫЕ МАТЧИ')}
          value={war.tracked_matches || 0}
          detail={t('war_counted_detail', 'Участвуют в расчёте')}
          accent="#55c98b"
          icon={<CheckCircleOutline />}
        />
        <WarMetricTile
          label={t('war_rejected_matches', 'ОТКЛОНЁННЫЕ МАТЧИ')}
          value={war.rejected_matches || 0}
          detail={t('war_rejected_detail', 'Не прошли условия войны')}
          accent="#a8a8a8"
          icon={<HighlightOff />}
        />
        <WarMetricTile
          label={t('wars_attack', 'АТАКА')}
          value={`+${war.attacker_power || 0}%`}
          detail={war.attacking_clan_name}
          detailTo={`/clans/${war.attacking_clan_id}`}
          accent="#ff5b57"
          icon={<Box component="span" sx={{ fontSize: 23, lineHeight: 1 }}>⚔</Box>}
        />
        <WarMetricTile
          label={t('wars_defense', 'ЗАЩИТА')}
          value={`+${war.defender_power || 0}%`}
          detail={war.defending_clan_name || t('wars_neutral_land', 'Нейтральная земля')}
          detailTo={war.defending_clan_id ? `/clans/${war.defending_clan_id}` : undefined}
          accent="#69aef0"
          icon={<Shield />}
        />
      </Box>

      <Paper sx={{ p: { xs: 2, md: 3 }, mb: 3 }}>
        <Box display="flex" alignItems="center" gap={1} mb={2}>
          <Assessment color="primary" />
          <Typography variant="h6">{t('war_score_title', 'Счёт войны')}</Typography>
          <Box
            sx={{
              ml: 'auto',
              display: 'flex',
              alignItems: 'center',
              gap: 0.75,
              color: 'text.secondary',
            }}
            aria-hidden="true"
          >
            <Box component="span" sx={{ color: '#ff5b57', fontSize: 20, lineHeight: 1 }}>⚔</Box>
            <Typography variant="caption" fontWeight={800}>{t('war_against', 'ПРОТИВ')}</Typography>
            <Shield sx={{ color: '#69aef0', fontSize: 20 }} />
          </Box>
        </Box>
        <Box position="relative">
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: {
                xs: 'minmax(0, 1fr)',
                md: war.clan_scores.length > 1
                  ? 'repeat(2, minmax(0, 1fr))'
                  : 'minmax(0, 1fr)',
              },
              gap: 2,
            }}
          >
            {(war.clan_scores || []).map((score, index) => (
              <WarScoreSide
                key={score.clan_id}
                score={score}
                war={war}
                leaderPoints={leaderPoints}
                leaderCount={leaderCount}
                index={index}
                t={t}
              />
            ))}
          </Box>
          {(war.clan_scores || []).length === 2 && (
            <Box
              sx={{
                display: { xs: 'none', md: 'grid' },
                position: 'absolute',
                top: '50%',
                left: '50%',
                zIndex: 2,
                width: 36,
                height: 36,
                placeItems: 'center',
                transform: 'translate(-50%, -50%)',
                border: '1px solid rgba(255,255,255,0.22)',
                borderRadius: '50%',
                bgcolor: '#181818',
                color: 'text.secondary',
                fontSize: 11,
                fontWeight: 900,
                boxShadow: '0 0 18px rgba(0,0,0,0.65)',
                pointerEvents: 'none',
              }}
            >
              VS
            </Box>
          )}
        </Box>
      </Paper>

      <WarSideGroups
        groups={war.side_groups || []}
        deploymentTracking={war.deployment_tracking}
      />

      <Paper sx={{ p: { xs: 2, md: 3 } }}>
        <Box display="flex" alignItems="center" justifyContent="space-between" gap={2} mb={2}>
          <Box display="flex" alignItems="center" gap={1}>
            <SportsEsports color="primary" />
            <Typography variant="h6">{t('war_matches_title', 'Матчи войны')}</Typography>
          </Box>
          <Chip label={t('war_checked_total', null, { count: totalMatches })} variant="outlined" />
        </Box>

        {(war.match_breakdown || []).length === 0 ? (
          <Typography color="text.secondary">{t('war_no_matches', 'Матчи пока не обнаружены.')}</Typography>
        ) : (
          <Stack divider={<Divider flexItem />} spacing={2}>
            {visibleMatchResults.map((result) => (
              <Box key={result.id} py={0.5}>
                <Box display="flex" justifyContent="space-between" gap={2} flexWrap="wrap">
                  <Typography fontWeight={700}>
                    <PlayerIdentity username={result.winner.username} usernameClassName="entity-link" />
                    {' '}{t('war_defeated', 'победил')}{' '}
                    <PlayerIdentity username={result.loser.username} usernameClassName="entity-link" />
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {formatMoscowDateTime(result.played_at, '', language)}
                  </Typography>
                </Box>
                <Typography variant="body2" color="text.secondary" mb={1}>
                  {result.map_name || t('matches_map_unknown', 'Карта не указана')}
                  {` · ${result.game_mode || '1 versus 1'}`}
                  {` · ${patchLabel(result.patch_family, t)}`}
                  {result.duration ? ` · ${result.duration}` : ''}
                </Typography>

                {!result.is_counted ? (
                  <Chip
                    size="small"
                    color="warning"
                    variant="outlined"
                    label={t('war_rejected_reason', null, {
                      reason: result.rejection_reason || t('war_failed_check', 'матч не прошёл проверку'),
                    })}
                    sx={{ height: 'auto', maxWidth: '100%', '& .MuiChip-label': { whiteSpace: 'normal', py: 0.5 } }}
                  />
                ) : (
                  <Box
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: {
                        xs: 'minmax(0, 1fr)',
                        md: 'repeat(2, minmax(0, 1fr))',
                      },
                      alignItems: 'stretch',
                      gap: 2,
                    }}
                  >
                    <Box minWidth={0}>
                      <WarMatchSide
                        side={result.winner}
                        war={war}
                        participants={(result.participants || []).filter((item) => item.is_winner)}
                        patchFamily={result.patch_family}
                        t={t}
                      />
                    </Box>
                    <Box minWidth={0}>
                      <WarMatchSide
                        side={result.loser}
                        war={war}
                        participants={(result.participants || []).filter((item) => !item.is_winner)}
                        patchFamily={result.patch_family}
                        t={t}
                      />
                    </Box>
                  </Box>
                )}
              </Box>
            ))}
          </Stack>
        )}

        {matchPageCount > 1 && (
          <Box
            mt={3}
            display="flex"
            alignItems={{ xs: 'stretch', sm: 'center' }}
            justifyContent="space-between"
            flexDirection={{ xs: 'column', sm: 'row' }}
            gap={1.5}
          >
            <Typography variant="body2" color="text.secondary">
              {t('matches_page', null, { current: matchPage, total: matchPageCount })}
            </Typography>
            <Pagination
              aria-label={t('matches_pagination', 'Страницы матчей')}
              count={matchPageCount}
              page={matchPage}
              onChange={(_, page) => setMatchPage(page)}
              color="primary"
              size="small"
              showFirstButton
              showLastButton
            />
          </Box>
        )}
      </Paper>
    </Container>
  );
};

export default WarDetailPage;
