import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Container,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import {
  Anchor,
  EmojiEvents,
  Flag,
  Landscape,
  Schedule,
  Shield,
} from '@mui/icons-material';
import { keyframes } from '@mui/material/styles';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { Link } from 'react-router-dom';
import { getTerritoryName } from '../i18n/territories';
import { warService } from '../services/warService';
import { formatMoscowDateTime } from '../utils/dateTime';
import RulesContextLink from '../components/RulesContextLink';
import './WarsPage.css';

const getStatusColor = (status) => {
  if (status === 'active') return 'error';
  if (status === 'completed') return 'success';
  if (status === 'canceled') return 'default';
  return 'warning';
};

const getStatusText = (status, t) => {
  if (status === 'active') return t('wars_status_active', 'Активна');
  if (status === 'completed') return t('wars_status_completed', 'Завершена');
  if (status === 'canceled') return t('wars_status_canceled', 'Отменена');
  return status || t('common_unknown', 'Неизвестно');
};

const getWarTypeText = (warType, t) => (
  warType === 'neutral_capture'
    ? t('wars_neutral_capture', 'Захват нейтральной территории')
    : t('wars_territory_attack', 'Атака владения')
);

const formatPoints = (value) => {
  const number = Number(value || 0);
  return number.toFixed(2).replace(/\.?0+$/, '');
};

const warCardReveal = keyframes`
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
`;

const sideIconPulse = keyframes`
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.06); }
`;

const WarSideSummary = ({
  role,
  clanId,
  clanName,
  clanAvatarUrl,
  score,
  neutralProgress,
  isWinner = false,
  t,
}) => {
  const isAttacker = role === 'attacker';
  const sideAccent = isAttacker ? '#ff5b57' : '#69aef0';
  const accent = isWinner ? '#f5c451' : sideAccent;
  const background = isWinner
    ? 'rgba(245, 196, 81, 0.1)'
    : isAttacker
    ? 'rgba(255, 72, 72, 0.075)'
    : 'rgba(79, 159, 232, 0.075)';
  const isNeutral = !clanId;

  return (
    <Box
      sx={{
        position: 'relative',
        height: '100%',
        minHeight: 150,
        p: 2,
        border: '1px solid',
        borderColor: `${accent}55`,
        borderLeft: `4px solid ${accent}`,
        bgcolor: background,
        boxShadow: isWinner ? 'inset 0 0 28px rgba(245, 196, 81, 0.08), 0 0 18px rgba(245, 196, 81, 0.12)' : 'none',
      }}
    >
      <Box display="flex" alignItems="center" gap={1.25} mb={1.5}>
        <Box display="flex" alignItems="center" gap={1.25} minWidth={0}>
        <Box
          sx={{
            width: 38,
            height: 38,
            flex: '0 0 38px',
            display: 'grid',
            placeItems: 'center',
            color: accent,
            border: '1px solid',
            borderColor: `${accent}88`,
            bgcolor: `${accent}14`,
            animation: `${sideIconPulse} 3.2s ease-in-out infinite`,
            '@media (prefers-reduced-motion: reduce)': {
              animation: 'none',
            },
          }}
        >
          {clanAvatarUrl ? (
            <Box component="img" src={clanAvatarUrl} alt="" sx={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          ) : isAttacker ? (
            <Box component="span" sx={{ fontSize: 23, lineHeight: 1 }} aria-hidden="true">⚔</Box>
          ) : (
            <Shield sx={{ fontSize: 23 }} />
          )}
        </Box>
        <Box minWidth={0}>
          <Typography variant="caption" sx={{ color: accent, fontWeight: 900 }}>
            {isAttacker ? t('wars_attack', 'АТАКА') : t('wars_defense', 'ЗАЩИТА')}
          </Typography>
          <Typography
            variant="body1"
            fontWeight={800}
            sx={{
              lineHeight: 1.2,
              overflowWrap: 'anywhere',
            }}
          >
            {clanId ? (
              <Link className="entity-link" to={`/clans/${clanId}`}>
                {clanName}
              </Link>
            ) : (
              t('wars_neutral_land', 'Нейтральная земля')
            )}
          </Typography>
        </Box>
        </Box>
        {isWinner && (
          <Chip
            size="small"
            icon={<EmojiEvents />}
            label={t('wars_winner', 'Победитель')}
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
            variant="outlined"
          />
        )}
      </Box>

      <Box display="flex" alignItems="baseline" justifyContent="space-between" gap={1} mb={0.5}>
        <Typography variant="caption" color="text.secondary">
          {isNeutral ? t('wars_capture_progress', 'Прогресс захвата') : t('wars_territory_points', 'Очки территории')}
        </Typography>
        <Typography variant="h5" fontWeight={900} sx={{ color: accent }}>
          {isNeutral ? `${neutralProgress || 0}%` : formatPoints(score?.points)}
        </Typography>
      </Box>

      {score ? (
        <>
          <Typography variant="body2" mb={0.25}>
            {t('wars_record', null, { wins: score.wins, losses: score.losses })}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {t('wars_score_breakdown', null, {
              base: formatPoints(score.base_points),
              power: formatPoints(score.power_bonus_points),
              relics: formatPoints(score.relic_bonus_points),
            })}
          </Typography>
        </>
      ) : (
        <Typography variant="caption" color="text.secondary">
          {t('wars_no_defender', 'Территорию пока не защищает ни один клан')}
        </Typography>
      )}
    </Box>
  );
};

const FeaturedBattleSide = ({
  role,
  clanId,
  clanName,
  clanAvatarUrl,
  clanMapColor,
  score,
  t,
}) => {
  const isAttacker = role === 'attacker';
  const isNeutral = !clanId;
  const displayName = clanName || t('wars_neutral_land', 'Нейтральная земля');

  return (
    <div className={`side-score side-score--${role}${isNeutral ? ' side-score--neutral' : ''}`}>
      <span
        className={`crest-big${clanAvatarUrl ? ' crest-big--image' : ' crest-big--fallback'}`}
        style={{ '--clan-color': clanMapColor || (isAttacker ? '#526346' : '#727773') }}
      >
        {clanAvatarUrl ? (
          <img
            src={clanAvatarUrl}
            alt={t('wars_clan_logo_alt', '{clan} — логотип клана', { clan: displayName })}
          />
        ) : (
          displayName.slice(0, 1).toUpperCase() || '•'
        )}
      </span>

      <div className="side-score__body">
        <span className="side-score__role">
          {isAttacker ? t('wars_attack', 'Атака') : t('wars_defense', 'Защита')}
        </span>
        <h2 className="serif">
          {clanId ? <Link className="entity-link" to={`/clans/${clanId}`}>{displayName}</Link> : displayName}
        </h2>
        <div className="side-score__points">
          <strong>{formatPoints(score?.points)}</strong>
          <span>{t('wars_territory_points', 'Очки территории')}</span>
        </div>
        <div className="side-score__record">
          <span><strong>{score?.wins || 0}</strong>{t('profile_wins', 'Победы')}</span>
          <span><strong>{score?.losses || 0}</strong>{t('profile_losses', 'Поражения')}</span>
        </div>
      </div>
    </div>
  );
};

const WarsPage = () => {
  const { getLocalizedText: t, language } = useLocalizationContext();
  const [wars, setWars] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [warView, setWarView] = useState('active');
  const [clock, setClock] = useState(() => Date.now());

  const activeWars = useMemo(
    () => wars.filter((war) => war.status === 'active'),
    [wars],
  );
  const archivedWars = useMemo(
    () => wars.filter((war) => !['active', 'scheduled', 'pending'].includes(war.status)),
    [wars],
  );
  const displayedWars = warView === 'active' ? activeWars : archivedWars;
  const featuredWar = activeWars[0] || null;
  const featuredAttackerScore = featuredWar?.clan_scores?.find((score) => score.clan_id === featuredWar.attacking_clan_id);
  const featuredDefenderScore = featuredWar?.clan_scores?.find((score) => score.clan_id === featuredWar.defending_clan_id);
  const featuredTotal = Math.max(1, Number(featuredAttackerScore?.points || 0) + Number(featuredDefenderScore?.points || 0));
  const featuredShare = Math.round(Number(featuredAttackerScore?.points || 0) / featuredTotal * 100);
  const remainingSeconds = featuredWar?.status === 'active' && featuredWar.ends_at
    ? Math.max(0, Math.floor((new Date(featuredWar.ends_at).getTime() - clock) / 1000))
    : 0;
  const featuredTimer = [Math.floor(remainingSeconds / 3600), Math.floor(remainingSeconds % 3600 / 60), remainingSeconds % 60]
    .map((value) => String(value).padStart(2, '0')).join(':');
  const trackedMatches = wars.reduce((sum, war) => sum + Number(war.tracked_matches || 0), 0);

  const loadData = useCallback(async () => {
    setError('');
    setLoading(true);
    try {
      setWars(await warService.getWars());
    } catch (loadError) {
      setError(loadError.response?.data?.detail || t('wars_load_error', 'Не удалось загрузить войны'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    const timer = window.setInterval(() => setClock(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  if (loading) {
    return (
      <Container>
        <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth={false} className="wars-page prototype-exact-page" sx={{ mt: 0, mb: 4 }}>
      <Box className="wars-prototype-header page-title">
        <Box>
          <Typography component="p" className="wars-prototype-header__eyebrow">
            {t('wars_prototype_eyebrow', 'Военный фронт')}
          </Typography>
          <Typography variant="h4" component="h1">
            {t('wars_prototype_title', 'Битвы')}
          </Typography>
          <Typography component="p" className="wars-prototype-header__subtitle">
            {t('wars_prototype_subtitle', 'Следите за текущими сражениями, подготовкой атак и архивом результатов.')}
          </Typography>
          <RulesContextLink context="war" section="attacks" />
        </Box>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 3 }}>{error}</Alert>}

      {featuredWar ? (
        <section className="card battle-main" data-section="featured-battle">
          <div className="eyebrow">{t('wars_featured_battle', 'Главная битва')} · {getTerritoryName(featuredWar.territory_name, language)}</div>
          <div className="vs">
            <FeaturedBattleSide
              role="attacker"
              clanId={featuredWar.attacking_clan_id}
              clanName={featuredWar.attacking_clan_name}
              clanAvatarUrl={featuredWar.attacking_clan_avatar_url}
              clanMapColor={featuredWar.attacking_clan_map_color}
              score={featuredAttackerScore}
              t={t}
            />
            <div className="battle-main__center">
              <div className="vsmark">VS</div>
              <div className="warline">{getStatusText(featuredWar.status, t)}</div>
              <div className="timer">{featuredWar.status === 'active' ? featuredTimer : t('wars_status_completed', 'Завершена')}</div>
              <div className="battle-main-actions">
                <Link className="btn primary" to={`/battles/${featuredWar.id}`}>{t('wars_open_summary', 'Открыть сводку')}</Link>
                <span>#{featuredWar.id}</span>
              </div>
            </div>
            <FeaturedBattleSide
              role="defender"
              clanId={featuredWar.defending_clan_id}
              clanName={featuredWar.defending_clan_name}
              clanAvatarUrl={featuredWar.defending_clan_avatar_url}
              clanMapColor={featuredWar.defending_clan_map_color}
              score={featuredDefenderScore}
              t={t}
            />
          </div>
          <div className="battle-progress"><span style={{ background: `linear-gradient(90deg, ${featuredWar.attacking_clan_map_color || '#6f815c'} 0 ${featuredShare}%, ${featuredWar.defending_clan_map_color || '#858984'} ${featuredShare}% 100%)` }} /></div>
          <div className="battle-meta"><span>{getWarTypeText(featuredWar.war_type, t)}</span><span>{featuredWar.tracked_matches || 0} {t('profile_total_matches', 'матчей')}</span><span>{featuredWar.attack_route === 'sea' ? t('wars_sea_attack', 'Морской путь') : t('wars_land_attack', 'Сухопутный путь')}</span></div>
        </section>
      ) : (
        <section className="card battle-main battle-main--empty"><div className="eyebrow">{t('wars_featured_battle', 'Главная битва')}</div><h2>{t('homepage_no_active_battles', 'Сейчас нет активных битв')}</h2></section>
      )}

      <div className="tabs wars-tabs" role="tablist" aria-label={t('wars_journal_sections', 'Разделы журнала войн')}>
        <button type="button" role="tab" aria-selected={warView === 'active'} className={`tab${warView === 'active' ? ' active' : ''}`} onClick={() => setWarView('active')}>{t('wars_active_tab', null, { count: activeWars.length })}</button>
        <button type="button" role="tab" aria-selected={warView === 'archive'} className={`tab${warView === 'archive' ? ' active' : ''}`} onClick={() => setWarView('archive')}>{t('wars_completed_tab', null, { count: archivedWars.length })}</button>
        <Link className="tab" to="/influence-history">{t('nav_influence_history', 'История влияния')}</Link>
      </div>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: {
            xs: 'minmax(0, 1fr)',
            lg: 'repeat(2, minmax(0, 1fr))',
          },
          alignItems: 'stretch',
          gap: 3,
        }}
      >
        {displayedWars.map((war, index) => {
          const clanScores = war.clan_scores || [];
          const attackerScore = clanScores.find(
            (score) => score.clan_id === war.attacking_clan_id,
          );
          const defenderScore = clanScores.find(
            (score) => score.clan_id === war.defending_clan_id,
          );
          const attackerWon = war.status === 'completed'
            && Number(war.winner_clan_id) === Number(war.attacking_clan_id);
          const defenderWon = war.status === 'completed'
            && Number(war.winner_clan_id) === Number(war.defending_clan_id);

          return (
            <Card
              key={war.id}
              sx={{
                height: '100%',
                animation: `${warCardReveal} 500ms ease-out ${index * 90}ms both`,
                '@media (prefers-reduced-motion: reduce)': {
                  animation: 'none',
                },
              }}
            >
              <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                <Box display="flex" justifyContent="space-between" alignItems="flex-start" mb={2} gap={2}>
                  <Box>
                    <Typography variant="h6" component="h2">
                      {getTerritoryName(war.territory_name, language)}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      {getWarTypeText(war.war_type, t)}
                    </Typography>
                  </Box>
                  <Chip label={getStatusText(war.status, t)} color={getStatusColor(war.status)} size="small" />
                </Box>

                <Stack spacing={1.5} sx={{ flex: 1 }}>
                  <Box display="flex" gap={1} flexWrap="wrap">
                    <Chip
                      size="small"
                      color="secondary"
                      variant="outlined"
                      label={
                        war.attacker_patch === war.defender_patch || !war.defender_patch
                          ? (
                            war.attacker_patch === 'patch_202'
                              ? 'Patch 2.02'
                              : war.attacker_patch === 'ennorath'
                                ? 'Ennorath'
                                : t('wars_both_patches', 'Оба патча')
                          )
                          : t('wars_different_patches', 'Разные патчи кланов')
                      }
                    />
                    <Chip
                      size="small"
                      variant="outlined"
                      color={war.attack_route === 'sea' ? 'info' : 'default'}
                      icon={war.attack_route === 'sea' ? <Anchor /> : <Landscape />}
                      label={war.attack_route === 'sea' ? t('wars_sea_attack', 'Морская атака') : t('wars_land_attack', 'Сухопутная атака')}
                    />
                    <Chip
                      size="small"
                      variant="outlined"
                      label={t('wars_attack_power', null, { value: war.attacker_power || 0 })}
                    />
                    <Chip
                      size="small"
                      variant="outlined"
                      label={t('wars_defense_power', null, { value: war.defender_power || 0 })}
                    />
                  </Box>
                  {war.ends_at && (
                    <Box display="flex" alignItems="center">
                      <Schedule sx={{ fontSize: 16, mr: 1, color: 'text.secondary' }} />
                      <Typography variant="body2" color="text.secondary">
                        {t('wars_until', null, { date: formatMoscowDateTime(war.ends_at, '', language) })}
                      </Typography>
                    </Box>
                  )}

                  <Box position="relative">
                    <Box
                      sx={{
                        display: 'grid',
                        gridTemplateColumns: {
                          xs: 'minmax(0, 1fr)',
                          sm: 'repeat(2, minmax(0, 1fr))',
                        },
                        alignItems: 'stretch',
                        gap: 2,
                      }}
                    >
                      <WarSideSummary
                        role="attacker"
                        clanId={war.attacking_clan_id}
                        clanName={war.attacking_clan_name}
                        clanAvatarUrl={war.attacking_clan_avatar_url}
                        score={attackerScore}
                        isWinner={attackerWon}
                        t={t}
                      />
                      <WarSideSummary
                        role="defender"
                        clanId={war.defending_clan_id}
                        clanName={war.defending_clan_name}
                        clanAvatarUrl={war.defending_clan_avatar_url}
                        score={defenderScore}
                        neutralProgress={war.progress_percent}
                        isWinner={defenderWon}
                        t={t}
                      />
                    </Box>
                    <Box
                      sx={{
                        display: { xs: 'none', sm: 'grid' },
                        position: 'absolute',
                        top: '50%',
                        left: '50%',
                        zIndex: 2,
                        width: 32,
                        height: 32,
                        placeItems: 'center',
                        transform: 'translate(-50%, -50%)',
                        border: '1px solid rgba(255,255,255,0.22)',
                        borderRadius: '50%',
                        bgcolor: '#181818',
                        color: 'text.secondary',
                        fontSize: 10,
                        fontWeight: 900,
                        boxShadow: '0 0 16px rgba(0,0,0,0.65)',
                        pointerEvents: 'none',
                      }}
                    >
                      VS
                    </Box>
                  </Box>

                  <Button
                    component={Link}
                    to={`/battles/${war.id}`}
                    variant="outlined"
                    startIcon={<Flag />}
                    fullWidth
                  >
                    {t('wars_open', 'Открыть войну')}
                  </Button>
                </Stack>
              </CardContent>
            </Card>
          );
        })}
      </Box>

      {displayedWars.length === 0 && (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="h6" color="text.secondary" gutterBottom>
            {warView === 'active' ? t('wars_no_active', 'Активных войн нет') : t('wars_no_completed', 'Завершённых войн пока нет')}
          </Typography>
        </Paper>
      )}

      <section className="section grid g2 wars-lower-grid">
        <article className="card panel">
          <div className="eyebrow">{t('wars_chronicle_eyebrow')}</div>
          <h2>{t('wars_events_title')}</h2>
          <div className="wars-event-list">
            {wars.slice(0, 3).map((war) => (
              <Link to={`/battles/${war.id}`} key={war.id}>
                <span className={`dot ${war.status === 'completed' ? 'green' : war.status === 'active' ? 'red' : 'gold'}`} />
                <b>{getTerritoryName(war.territory_name, language)}</b>
                <small>{war.attacking_clan_name} → {war.defending_clan_name || t('wars_neutral_land', 'Нейтральная земля')}</small>
              </Link>
            ))}
            {wars.length === 0 && <p className="muted">{t('wars_events_empty')}</p>}
          </div>
        </article>
        <article className="card panel">
          <div className="eyebrow">{t('wars_summary_eyebrow')}</div>
          <h2>{t('wars_summary_title')}</h2>
          <div className="grid g2 wars-summary-grid">
            <div className="kpi"><strong>{trackedMatches}</strong><small>{t('profile_total_matches', 'Матчей')}</small></div>
            <div className="kpi"><strong>{wars.length}</strong><small>{t('wars_total_wars')}</small></div>
            <div className="kpi"><strong>{activeWars.length}</strong><small>{t('homepage_active_wars_short')}</small></div>
          </div>
        </article>
      </section>
    </Container>
  );
};

export default WarsPage;
