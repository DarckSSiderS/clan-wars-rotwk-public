import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  IconButton,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  Archive,
  CheckCircle,
  Close,
  CloudDownload,
  ErrorOutline,
  ExpandMore,
  Map,
  PauseCircle,
  PlayCircle,
  Refresh,
  SkipNext,
  Sync,
  TaskAlt,
  Tune,
} from '@mui/icons-material';
import { schedulerService } from '../services/schedulerService';
import { getFactionIcon } from '../data/factions';
import PlayerIdentity from '../components/PlayerIdentity';
import { showError, showSuccess } from '../utils/notifications';
import { formatMoscowDateTime } from '../utils/dateTime';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const STATUS_META = {
  imported: { labelKey: 'admin_sync_status_imported', color: 'success', icon: <CheckCircle fontSize="small" /> },
  known: { labelKey: 'admin_sync_status_known', color: 'info', icon: <TaskAlt fontSize="small" /> },
  skipped: { labelKey: 'admin_sync_status_skipped', color: 'warning', icon: <SkipNext fontSize="small" /> },
  error: { labelKey: 'admin_sync_status_error', color: 'error', icon: <ErrorOutline fontSize="small" /> },
};

const PATCH_LABELS = {
  patch_202: 'Patch 2.02',
  ennorath: 'Ennorath',
};

const valueOrDash = (value, t) => (
  value === null || value === undefined || value === '' ? t('admin_no_data') : String(value)
);

const formatBytes = (bytes, language, t) => {
  if (!bytes && bytes !== 0) return t('admin_no_data');
  const formatter = new Intl.NumberFormat(language, { maximumFractionDigits: 2 });
  if (bytes < 1024) return `${formatter.format(bytes)} ${t('admin_bytes_b')}`;
  if (bytes < 1024 * 1024) return `${formatter.format(bytes / 1024)} ${t('admin_bytes_kb')}`;
  return `${formatter.format(bytes / (1024 * 1024))} ${t('admin_bytes_mb')}`;
};

const DetailField = ({ label, value, mono = false }) => {
  const { getLocalizedText: t } = useLocalizationContext();

  return (
  <Box sx={{ minWidth: 0 }}>
    <Typography variant="caption" color="text.secondary">{label}</Typography>
    <Typography
      variant="body2"
      fontWeight={700}
      sx={{
        mt: 0.25,
        overflowWrap: 'anywhere',
        fontFamily: mono ? 'monospace' : 'inherit',
      }}
    >
      {valueOrDash(value, t)}
    </Typography>
  </Box>
  );
};

const DetailGrid = ({ children }) => (
  <Box
    sx={{
      display: 'grid',
      gridTemplateColumns: {
        xs: '1fr',
        sm: 'repeat(2, minmax(0, 1fr))',
        md: 'repeat(3, minmax(0, 1fr))',
      },
      gap: 2,
    }}
  >
    {children}
  </Box>
);

const TeamSide = ({ title, participants, patchLabel, winner }) => {
  const { getLocalizedText: t } = useLocalizationContext();

  return (
  <Box
    sx={{
      minWidth: 0,
      p: 2,
      borderLeft: '3px solid',
      borderLeftColor: winner ? 'success.main' : 'error.main',
      bgcolor: winner ? 'rgba(37, 160, 110, 0.08)' : 'rgba(224, 74, 74, 0.07)',
    }}
  >
    <Typography variant="overline" color={winner ? 'success.main' : 'error.main'}>
      {title}
    </Typography>
    <Stack spacing={1.25} mt={1}>
      {participants.map((participant, index) => (
        <Box
          key={`${participant.nickname}-${participant.player_uuid || index}`}
          sx={{
            display: 'grid',
            gridTemplateColumns: '48px minmax(0, 1fr) auto',
            alignItems: 'center',
            gap: 1.25,
            p: 1.25,
            bgcolor: 'rgba(0, 0, 0, 0.16)',
          }}
        >
          <Box
            component="img"
            src={getFactionIcon(participant.faction, 'large')}
            alt=""
            sx={{ width: 48, height: 48, objectFit: 'contain' }}
          />
          <Box minWidth={0}>
            <Typography fontWeight={900} sx={{ overflowWrap: 'anywhere' }}>
              {participant.nickname ? <PlayerIdentity username={participant.nickname} /> : valueOrDash(participant.nickname, t)}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {valueOrDash(participant.faction, t)}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>
              UUID: {valueOrDash(participant.player_uuid, t)}
            </Typography>
          </Box>
          <Box textAlign="right">
            <Typography fontWeight={900}>Elo · {patchLabel} {participant.elo ?? '—'}</Typography>
            <Typography variant="caption" color="text.secondary">{t("admin_ui_group_c537aea602", null, { value0: participant.old_rank ?? '—', value1: participant.new_rank ?? '—' })}
            </Typography>
          </Box>
        </Box>
      ))}
    </Stack>
  </Box>
  );
};

const ReplayDetailDialog = ({
  open,
  detail,
  loading,
  archiving,
  onClose,
  onArchive,
  onDownload,
}) => {
  const { getLocalizedText: t, language } = useLocalizationContext();
  const match = detail?.match;
  const ratingPatchLabel = PATCH_LABELS[match?.rating_patch_family]
    || match?.patch_name
    || match?.patch_version
    || t('admin_patch_unknown');
  const syncState = detail?.sync;
  const rawPayload = match?.source_payload;
  const sourcePlayers = Array.isArray(rawPayload?.Players) ? rawPayload.Players : [];
  const storedParticipants = Array.isArray(match?.participants) ? match.participants : [];
  const winnerParticipants = storedParticipants.filter((participant) => participant.is_winner);
  const loserParticipants = storedParticipants.filter((participant) => !participant.is_winner);
  const winnerTeam = winnerParticipants.length ? winnerParticipants : match ? [{
    nickname: match.winner_player,
    faction: match.winner_faction,
    player_uuid: match.winner_player_uuid,
    elo: match.winner_elo,
    old_rank: match.winner_old_rank,
    new_rank: match.winner_new_rank,
  }] : [];
  const loserTeam = loserParticipants.length ? loserParticipants : match ? [{
    nickname: match.loser_player,
    faction: match.loser_faction,
    player_uuid: match.loser_player_uuid,
    elo: match.loser_elo,
    old_rank: match.loser_old_rank,
    new_rank: match.loser_new_rank,
  }] : [];

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="lg">
      <DialogTitle sx={{ pr: 7 }}>
        <Typography variant="overline" color="primary">{t("admin_ui_66dd7ca8c9")}</Typography>
        <Typography variant="h5" fontWeight={900} sx={{ overflowWrap: 'anywhere' }}>
          {syncState?.replay_id || match?.match_id || t('common_replay')}
        </Typography>
        <IconButton
          aria-label={t("admin_ui_4ae50d3073")}
          onClick={onClose}
          sx={{ position: 'absolute', top: 12, right: 12 }}
        >
          <Close />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers>
        {loading && (
          <Box display="grid" sx={{ minHeight: 320, placeItems: 'center' }}>
            <CircularProgress />
          </Box>
        )}

        {!loading && !match && (
          <Alert severity="info">{t("admin_ui_group_dc0b640107", null, { value0: syncState?.reason || t("admin_ui_60a06350cb") })}</Alert>
        )}

        {!loading && match && (
          <Stack spacing={3}>
            <Box>
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                alignItems={{ xs: 'flex-start', sm: 'center' }}
                justifyContent="space-between"
                gap={1}
                mb={1.5}
              >
                <Typography variant="h6">{t("admin_ui_4a1e242547")}</Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  <Chip label={match.patch_name || match.patch_version || t("admin_ui_ab695e5ccd")} />
                  <Chip label={match.gamemode_name || match.game_mode || t("admin_ui_c30592999d")} />
                </Stack>
              </Stack>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', md: 'repeat(2, minmax(0, 1fr))' },
                  gap: 1,
                }}
              >
                <TeamSide title={t("admin_ui_bd3d8e9ac0")} participants={winnerTeam} patchLabel={ratingPatchLabel} winner />
                <TeamSide title={t("admin_ui_cad104632e")} participants={loserTeam} patchLabel={ratingPatchLabel} />
              </Box>
            </Box>

            <Divider />

            <Box>
              <Stack direction="row" alignItems="center" spacing={1} mb={1.5}>
                <Map color="primary" />
                <Typography variant="h6">{t("admin_ui_72a1d77610")}</Typography>
              </Stack>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: match.map_preview_url
                    ? { xs: '1fr', md: '220px minmax(0, 1fr)' }
                    : '1fr',
                  gap: 2,
                  alignItems: 'start',
                }}
              >
                {match.map_preview_url && (
                  <Box
                    component="img"
                    src={match.map_preview_url}
                    alt={match.map_name || t("admin_ui_85a9289310")}
                    sx={{ width: '100%', aspectRatio: '4 / 3', objectFit: 'cover' }}
                  />
                )}
                <DetailGrid>
                  <DetailField label={t("admin_ui_5736d0caff")} value={match.map_name} />
                  <DetailField label={t("admin_ui_c3d424a0b7")} value={match.map_id} mono />
                <DetailField label={t("admin_ui_fb95317542")} value={formatMoscowDateTime(match.match_date, '—', language)} />
                  <DetailField label={t("admin_ui_d4168ace06")} value={match.duration} />
                  <DetailField label={t("admin_ui_50df0f4d6d")} value={match.game_name} />
                  <DetailField label="Arena ID" value={match.arena_id} mono />
                  <DetailField label={t("admin_ui_ffc460764f", null, { value0: ratingPatchLabel })} value={match.elo_delta} />
                  <DetailField label={t("admin_ui_dc6c71b7bf")} value={match.downloads} />
                <DetailField label={t("admin_ui_e5c3b2e719")} value={formatMoscowDateTime(match.ratings_captured_at, '—', language)} />
                </DetailGrid>
              </Box>
            </Box>

            <Divider />

            <Box>
              <Typography variant="h6" mb={1.5}>{t("admin_ui_088936a20c")}</Typography>
              <DetailGrid>
                <DetailField label={t("admin_ui_c410bdd993")} value={t(match.is_valid ? 'common_yes' : 'common_no')} />
                <DetailField
                  label={t("admin_ui_a5d9606f7a")}
                  value={t(match.is_qualification_round ? 'common_yes' : 'common_no')}
                />
                <DetailField label={t("admin_ui_d1fe9e9ebb")} value={PATCH_LABELS[match.rating_patch_family] || match.rating_patch_family} />
                <DetailField label={t("admin_ui_1e57a1dd91", null, { value0: ratingPatchLabel })} value={match.rating_source} />
                <DetailField label={t("admin_ui_c0b7bd58c0")} value={Array.isArray(match.likes) ? match.likes.length : 0} />
                <DetailField label={t("admin_ui_aad75016a3")} value={Array.isArray(match.comments) ? match.comments.length : 0} />
              </DetailGrid>
            </Box>

            <Divider />

            <Box>
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                justifyContent="space-between"
                alignItems={{ xs: 'flex-start', sm: 'center' }}
                gap={1.5}
                mb={1.5}
              >
                <Box>
                  <Typography variant="h6">{t("admin_ui_95b7c52e12")}</Typography>
                  <Typography variant="body2" color="text.secondary">{t("admin_ui_9f0239e04c")}</Typography>
                </Box>
                <Stack direction="row" spacing={1}>
                  {!match.replay_file_exists && (
                    <Button
                      variant="outlined"
                      startIcon={archiving ? <CircularProgress size={17} /> : <Archive />}
                      disabled={archiving}
                      onClick={onArchive}
                    >{t("admin_ui_57049d752c")}</Button>
                  )}
                  {match.replay_file_exists && (
                    <Button variant="contained" startIcon={<CloudDownload />} onClick={onDownload}>{t("admin_ui_b421556bc6")}</Button>
                  )}
                </Stack>
              </Stack>
              {match.replay_download_error && (
                <Alert severity="error" variant="outlined" sx={{ mb: 1.5 }}>
                  {match.replay_download_error}
                </Alert>
              )}
              <DetailGrid>
                <DetailField label={t("admin_ui_44d5005b38")} value={match.replay_download_status || t('admin_replay_not_downloaded')} />
                <DetailField label={t("admin_ui_98713e8814")} value={formatBytes(match.replay_file_size, language, t)} />
                <DetailField label={t("admin_ui_6e21d43778")} value={formatMoscowDateTime(match.replay_downloaded_at, '—', language)} />
                <DetailField label={t("admin_ui_ad67d5a640")} value={match.replay_local_path} mono />
                <DetailField label="SHA-256" value={match.replay_sha256} mono />
                <DetailField label={t("admin_ui_d223343b9e")} value={match.replay_download_url} mono />
              </DetailGrid>
            </Box>

            <Accordion disableGutters>
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Typography fontWeight={800}>{t("admin_ui_group_4a83a38a67", null, { value0: sourcePlayers.length })}</Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Box
                  component="pre"
                  sx={{
                    m: 0,
                    p: 2,
                    maxHeight: 480,
                    overflow: 'auto',
                    whiteSpace: 'pre-wrap',
                    overflowWrap: 'anywhere',
                    bgcolor: 'rgba(0, 0, 0, 0.24)',
                    fontSize: 12,
                  }}
                >
                  {JSON.stringify(rawPayload || {}, null, 2)}
                </Box>
              </AccordionDetails>
            </Accordion>
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t("admin_ui_4ae50d3073")}</Button>
      </DialogActions>
    </Dialog>
  );
};

const AdminSyncPage = () => {
  const { getLocalizedText: t, language } = useLocalizationContext();
  const [overview, setOverview] = useState(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState(null);
  const [selectedReplayId, setSelectedReplayId] = useState('');
  const [archiving, setArchiving] = useState(false);
  const [pauseDialogOpen, setPauseDialogOpen] = useState(false);
  const [pauseReason, setPauseReason] = useState('');
  const [patches, setPatches] = useState({
    patch_202_enabled: true,
    ennorath_enabled: true,
  });

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const data = await schedulerService.getAdminOverview(statusFilter);
      setOverview(data);
      setPatches({
        patch_202_enabled: Boolean(data.campaign.patch_202_enabled),
        ennorath_enabled: Boolean(data.campaign.ennorath_enabled),
      });
    } catch (error) {
      showError(error.response?.data?.detail || t("admin_ui_a0daea3c33"));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, t]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  const savePatches = async () => {
    if (!patches.patch_202_enabled && !patches.ennorath_enabled) {
      showError(t("admin_ui_4b1d299ddb"));
      return;
    }
    setSaving(true);
    try {
      const campaign = await schedulerService.updateCampaignSettings(patches);
      setOverview((current) => ({ ...current, campaign }));
      showSuccess(t("admin_ui_c20c5b79ec"));
    } catch (error) {
      showError(error.response?.data?.detail || t("admin_ui_a0348f570b"));
    } finally {
      setSaving(false);
    }
  };

  const runSync = async () => {
    setSyncing(true);
    try {
      const result = await schedulerService.fetchMatches(15);
      showSuccess(result.message);
      await loadOverview();
    } catch (error) {
      showError(error.response?.data?.detail || t("admin_ui_3c9e856f61"));
    } finally {
      setSyncing(false);
    }
  };

  const changeCampaignPause = async () => {
    if (pauseReason.trim().length < 3) return;
    setSaving(true);
    try {
      const campaign = overview?.campaign?.is_paused
        ? await schedulerService.resumeCampaign(pauseReason.trim())
        : await schedulerService.pauseCampaign(pauseReason.trim());
      setOverview((current) => ({ ...current, campaign }));
      setPauseDialogOpen(false);
      setPauseReason('');
      showSuccess(campaign.is_paused ? t("admin_ui_33e390f0e5") : t("admin_ui_ced4dd5d95"));
    } catch (error) {
      showError(error.response?.data?.detail || t("admin_ui_d18eb76985"));
    } finally {
      setSaving(false);
    }
  };

  const openReplay = async (replayId) => {
    setSelectedReplayId(replayId);
    setDetail(null);
    setDetailOpen(true);
    setDetailLoading(true);
    try {
      setDetail(await schedulerService.getReplayDetail(replayId));
    } catch (error) {
      showError(error.response?.data?.detail || t("admin_ui_32388efdf1"));
      setDetailOpen(false);
    } finally {
      setDetailLoading(false);
    }
  };

  const archiveReplay = async () => {
    setArchiving(true);
    try {
      await schedulerService.archiveReplay(selectedReplayId);
      setDetail(await schedulerService.getReplayDetail(selectedReplayId));
      await downloadReplay();
      showSuccess(t("admin_ui_e5a7497dce"));
    } catch (error) {
      showError(error.response?.data?.detail || t("admin_ui_b51ec80b43"));
      setDetail(await schedulerService.getReplayDetail(selectedReplayId));
    } finally {
      setArchiving(false);
    }
  };

  const downloadReplay = async () => {
    try {
      const file = await schedulerService.getReplayFile(selectedReplayId);
      const url = window.URL.createObjectURL(file);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${selectedReplayId}.BfME2Replay`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      showError(error.response?.data?.detail || t("admin_ui_42e08bb0ca"));
    }
  };

  const worker = overview?.worker || {};
  const summary = overview?.summary || {};
  const replays = useMemo(() => overview?.replays || [], [overview]);

  if (loading && !overview) {
    return (
      <Box display="grid" minHeight="60vh" sx={{ placeItems: 'center' }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Container maxWidth="lg" className="admin-sync-page" sx={{ py: 4 }}>
      <Box
        display="flex"
        justifyContent="space-between"
        alignItems={{ xs: 'flex-start', md: 'center' }}
        flexDirection={{ xs: 'column', md: 'row' }}
        gap={2}
        mb={3}
      >
        <Box>
          <Typography variant="h4" fontWeight={900}>{t("admin_ui_d462988088")}</Typography>
          <Typography color="text.secondary">{t("admin_ui_4e1c97a809")}</Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Tooltip title={t("admin_ui_1fac7b539f")}>
            <IconButton onClick={loadOverview} disabled={loading || syncing}>
              <Refresh />
            </IconButton>
          </Tooltip>
          <Button
            variant="contained"
            startIcon={syncing ? <CircularProgress size={18} color="inherit" /> : <Sync />}
            onClick={runSync}
            disabled={syncing}
          >{t("admin_ui_466617a719")}</Button>
        </Stack>
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: 'minmax(0, 1.2fr) minmax(0, 1fr)' },
          gap: 2,
          mb: 2,
        }}
      >
        <Paper sx={{ p: 2.5 }}>
          <Box display="flex" alignItems="center" gap={1} mb={2}>
            <Tune color="primary" />
            <Typography variant="h6">{t("admin_ui_3849096037")}</Typography>
          </Box>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <FormControlLabel
              control={(
                <Switch
                  checked={patches.patch_202_enabled}
                  onChange={(event) => setPatches((current) => ({
                    ...current,
                    patch_202_enabled: event.target.checked,
                  }))}
                />
              )}
              label="Patch 2.02"
            />
            <FormControlLabel
              control={(
                <Switch
                  checked={patches.ennorath_enabled}
                  onChange={(event) => setPatches((current) => ({
                    ...current,
                    ennorath_enabled: event.target.checked,
                  }))}
                />
              )}
              label="Ennorath"
            />
          </Stack>
          <Button sx={{ mt: 2 }} variant="outlined" onClick={savePatches} disabled={saving}>{t("admin_ui_aff53879a0")}</Button>
          {overview?.campaign?.updated_at && (
            <Typography display="block" variant="caption" color="text.secondary" sx={{ mt: 1.5 }}>{t("admin_ui_group_e6bec077eb", null, { value0: formatMoscowDateTime(overview.campaign.updated_at, '—', language), value1: overview.campaign.updated_by ? ` · ${overview.campaign.updated_by}` : '' })}
            </Typography>
          )}
          {overview?.campaign?.is_paused && (
            <Alert severity="warning" variant="outlined" sx={{ mt: 2 }}>{t("admin_ui_group_bcd64b68dc", null, { value0: formatMoscowDateTime(overview.campaign.paused_at, '—', language), value1: overview.campaign.pause_reason ? t("admin_ui_628d37fdad", null, { value0: overview.campaign.pause_reason }) : '' })}
            </Alert>
          )}
          <Button
            sx={{ mt: 2, ml: { sm: 1 } }}
            variant="contained"
            color={overview?.campaign?.is_paused ? 'success' : 'warning'}
            startIcon={overview?.campaign?.is_paused ? <PlayCircle /> : <PauseCircle />}
            onClick={() => setPauseDialogOpen(true)}
            disabled={saving}
          >
            {overview?.campaign?.is_paused ? t("admin_ui_d92f3511ca") : t("admin_ui_57e32ddd16")}
          </Button>
        </Paper>

        <Paper sx={{ p: 2.5 }}>
          <Box display="flex" alignItems="center" justifyContent="space-between" gap={2} mb={1.5}>
            <Typography variant="h6">{t("admin_ui_4c43ebe49f")}</Typography>
            <Chip
              color={worker.is_running ? 'success' : 'error'}
              label={worker.is_running ? t("admin_ui_e6156da328") : t("admin_ui_aa0d25d0b3")}
              variant="outlined"
            />
          </Box>
          <Typography color="text.secondary" variant="body2">{t("admin_ui_group_79972006ae", null, { value0: Math.round((worker.interval_seconds || 600) / 60) })}</Typography>
          <Typography color="text.secondary" variant="body2">{t("admin_ui_group_9807b51db0", null, { value0: worker.last_success_at
              ? formatMoscowDateTime(worker.last_success_at, '—', language)
              : t("admin_ui_56e59a865a") })}
          </Typography>
          <Typography color="text.secondary" variant="body2">{t("admin_ui_group_f6eb90f0f9", null, { value0: worker.notifications_configured ? t("admin_ui_456a7abd63") : t("admin_ui_5d67da3a81"), value1: worker.last_notification_at
              ? t("admin_ui_48e585dcb9", null, { value0: formatMoscowDateTime(worker.last_notification_at, '—', language) })
              : '' })}
          </Typography>
          {worker.consecutive_failures > 0 && (
            <Alert severity="warning" variant="outlined" sx={{ mt: 1.5 }}>{t("admin_ui_group_7e5746ce26", null, { value0: worker.consecutive_failures })}
            </Alert>
          )}
          {worker.last_error && (
            <Alert severity="error" variant="outlined" sx={{ mt: 1.5 }}>
              {worker.last_error}
            </Alert>
          )}
        </Paper>
      </Box>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: 'repeat(2, minmax(0, 1fr))', md: 'repeat(4, minmax(0, 1fr))' },
          gap: 1.5,
          mb: 2,
        }}
      >
        {Object.entries(STATUS_META).map(([status, meta]) => (
          <Paper key={status} sx={{ p: 2, borderLeft: '3px solid', borderLeftColor: `${meta.color}.main` }}>
            <Typography color="text.secondary" variant="body2">{t(meta.labelKey)}</Typography>
            <Typography variant="h4" fontWeight={900}>{summary[status] || 0}</Typography>
          </Paper>
        ))}
      </Box>

      <Paper sx={{ overflow: 'hidden' }}>
        <Box
          display="flex"
          alignItems={{ xs: 'stretch', sm: 'center' }}
          justifyContent="space-between"
          flexDirection={{ xs: 'column', sm: 'row' }}
          gap={1.5}
          sx={{ p: 2 }}
        >
          <Box>
            <Typography variant="h6">{t("admin_ui_eae74a1100")}</Typography>
            <Typography variant="caption" color="text.secondary">{t("admin_ui_26aab3f4c1")}</Typography>
          </Box>
          <Select
            size="small"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            sx={{ minWidth: 190 }}
          >
            <MenuItem value="">{t("admin_ui_1a1a293895")}</MenuItem>
            {Object.entries(STATUS_META).map(([status, meta]) => (
              <MenuItem key={status} value={status}>{t(meta.labelKey)}</MenuItem>
            ))}
          </Select>
        </Box>
        <TableContainer sx={{ maxHeight: 620 }}>
          <Table stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>{t('common_replay')}</TableCell>
                <TableCell>{t("admin_ui_81e4bb361c")}</TableCell>
                <TableCell>{t("admin_ui_21d19deb0a")}</TableCell>
                <TableCell>{t("admin_ui_4a9ea52cda")}</TableCell>
                <TableCell align="center">{t("admin_ui_002dd4e666")}</TableCell>
                <TableCell>{t("admin_ui_0a2ff1a8d5")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {replays.map((replay) => {
                const meta = STATUS_META[replay.status] || STATUS_META.error;
                return (
                  <TableRow
                    key={replay.replay_id}
                    hover
                    tabIndex={0}
                    onClick={() => openReplay(replay.replay_id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        openReplay(replay.replay_id);
                      }
                    }}
                    sx={{ cursor: 'pointer' }}
                  >
                    <TableCell sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                      {replay.replay_id}
                    </TableCell>
                    <TableCell>
                      <Chip
                        size="small"
                        icon={meta.icon}
                        color={meta.color}
                        label={t(meta.labelKey)}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>
                      {PATCH_LABELS[replay.patch_family] || replay.patch_name || t("admin_ui_7f9e2cb30d")}
                    </TableCell>
                    <TableCell sx={{ minWidth: 260 }}>
                      {replay.reason || t("admin_ui_c26868825e")}
                    </TableCell>
                    <TableCell align="center">{replay.attempts}</TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>
                      {formatMoscowDateTime(replay.last_attempt_at, '—', language)}
                    </TableCell>
                  </TableRow>
                );
              })}
              {!replays.length && (
                <TableRow>
                  <TableCell colSpan={6} align="center" sx={{ py: 5, color: 'text.secondary' }}>{t("admin_ui_44bd2f7994")}</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      <Dialog open={pauseDialogOpen} onClose={() => !saving && setPauseDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{overview?.campaign?.is_paused ? t("admin_ui_d92f3511ca") : t("admin_ui_bd6131b7c9")}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            {overview?.campaign?.is_paused
              ? t("admin_ui_d143037542")
              : t("admin_ui_f49aec8800")}
          </Alert>
          <TextField
            autoFocus
            required
            fullWidth
            multiline
            minRows={2}
            label={t("admin_ui_4a9ea52cda")}
            value={pauseReason}
            inputProps={{ maxLength: 500 }}
            onChange={(event) => setPauseReason(event.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPauseDialogOpen(false)} disabled={saving}>{t("admin_ui_0ec753be8d")}</Button>
          <Button
            variant="contained"
            color={overview?.campaign?.is_paused ? 'success' : 'warning'}
            onClick={changeCampaignPause}
            disabled={saving || pauseReason.trim().length < 3}
          >{t("admin_ui_0467ae4bb8")}</Button>
        </DialogActions>
      </Dialog>

      <ReplayDetailDialog
        open={detailOpen}
        detail={detail}
        loading={detailLoading}
        archiving={archiving}
        onClose={() => setDetailOpen(false)}
        onArchive={archiveReplay}
        onDownload={downloadReplay}
      />
    </Container>
  );
};

export default AdminSyncPage;
