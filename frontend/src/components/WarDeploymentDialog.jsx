import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControl,
  InputLabel,
  List,
  ListItemAvatar,
  ListItemButton,
  ListItemText,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { Groups, MilitaryTech, Refresh, Search } from '@mui/icons-material';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { getTerritoryName } from '../i18n/territories';
import { warService } from '../services/warService';
import WarDeploymentReadiness from './WarDeploymentReadiness';
import './WarDeploymentDialog.css';

const errorMessage = (detail, fallback) => (
  typeof detail === 'string' ? detail : detail?.message || fallback
);

const validationMessage = (code, t) => ({
  campaign_rules_changed: t('war_deployment_rules_changed'),
  squad_member_busy: t('war_deployment_conflict'),
  squad_member_unverified: t('war_deployment_validation'),
  squad_member_not_in_clan: t('war_deployment_validation'),
  squad_too_small: t('war_deployment_validation'),
  warlord_not_in_squad: t('war_deployment_warlord_validation'),
  warlord_not_assigned: t('war_deployment_warlord_validation'),
  warlord_limit_exceeded: t('war_deployment_warlord_limit_error'),
  attack_points_exhausted: t('war_deployment_no_points'),
}[code]);

const WarDeploymentDialog = ({
  open,
  interactionDisabled = false,
  onClose,
  clanId,
  targetTerritory,
  sourceTerritory = null,
  onCreated,
}) => {
  const { getLocalizedText: t, language } = useLocalizationContext();
  const [readiness, setReadiness] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [warlordUserId, setWarlordUserId] = useState('');
  const [invalidIds, setInvalidIds] = useState([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const targetId = targetTerritory?.id;

  const loadReadiness = useCallback(async () => {
    if (!clanId) return;
    setLoading(true);
    try {
      const next = await warService.getWarReadiness(clanId);
      setReadiness(next);
      setWarlordUserId((current) => (
        next.candidates.some((candidate) => (
          candidate.user_id === current
          && candidate.is_warlord
          && candidate.verified
          && !candidate.busy_in_attack
        )) ? current : ''
      ));
      setSelectedIds((current) => current.filter((id) => (
        next.candidates.some((candidate) => (
          candidate.user_id === id && candidate.verified && !candidate.busy_in_attack
        ))
      )));
    } catch (loadError) {
      setError(errorMessage(loadError.response?.data?.detail, t('war_deployment_load_error')));
    } finally {
      setLoading(false);
    }
  }, [clanId, t]);

  useEffect(() => {
    if (!open) return;
    setSelectedIds([]);
    setWarlordUserId('');
    setInvalidIds([]);
    setQuery('');
    setError('');
    setReadiness(null);
    loadReadiness();
  }, [loadReadiness, open, targetId]);

  const candidates = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase(language);
    if (!normalized) return readiness?.candidates || [];
    return (readiness?.candidates || []).filter((candidate) => (
      `${candidate.nickname} ${candidate.username}`.toLocaleLowerCase(language).includes(normalized)
    ));
  }, [language, query, readiness]);

  const toggleMember = (candidate) => {
    if (!candidate.verified || candidate.busy_in_attack) return;
    if (candidate.user_id === warlordUserId && selectedIds.includes(candidate.user_id)) return;
    setInvalidIds((current) => current.filter((id) => id !== candidate.user_id));
    setSelectedIds((current) => (
      current.includes(candidate.user_id)
        ? current.filter((id) => id !== candidate.user_id)
        : [...current, candidate.user_id]
    ));
  };

  const selectWarlord = (userId) => {
    const numericId = Number(userId);
    setWarlordUserId(numericId);
    setSelectedIds((current) => (
      current.includes(numericId) ? current : [...current, numericId]
    ));
    setInvalidIds((current) => current.filter((id) => id !== numericId));
  };

  const submit = async () => {
    if (interactionDisabled || !readiness || !targetTerritory?.id) return;
    setSubmitting(true);
    setError('');
    setInvalidIds([]);
    try {
      const war = await warService.createWar({
        territoryId: Number(targetTerritory.id),
        sourceTerritoryId: sourceTerritory?.id ? Number(sourceTerritory.id) : null,
        squadMemberIds: selectedIds,
        warlordUserId,
        expectedRuleVersion: readiness.rule_version,
      });
      await onCreated(war);
    } catch (createError) {
      const detail = createError.response?.data?.detail;
      setInvalidIds(detail?.user_ids || []);
      setError(validationMessage(detail?.code, t) || errorMessage(detail, t('war_deployment_create_error')));
      if ([409, 422].includes(createError.response?.status)) await loadReadiness();
    } finally {
      setSubmitting(false);
    }
  };

  const minimum = readiness?.minimum_squad_size || 0;
  const availableWarlords = (readiness?.candidates || []).filter((candidate) => (
    candidate.is_warlord && candidate.verified && !candidate.busy_in_attack
  ));
  const hasInvalidSelected = invalidIds.some((id) => selectedIds.includes(id));
  const adjacent = Boolean(
    sourceTerritory?.adjacent_territory_ids?.some((id) => Number(id) === Number(targetId))
    || targetTerritory?.adjacent_territory_ids?.some((id) => Number(id) === Number(sourceTerritory?.id)),
  );
  const route = !sourceTerritory || adjacent ? 'land' : 'sea';
  const canSubmit = readiness
    && readiness.attack_points.available > 0
    && selectedIds.length >= minimum
    && Boolean(warlordUserId)
    && selectedIds.includes(warlordUserId)
    && !hasInvalidSelected
    && !interactionDisabled
    && !loading
    && !submitting;

  return (
    <Dialog
      open={open}
      aria-busy={interactionDisabled}
      onClose={() => !submitting && onClose()}
      fullWidth
      maxWidth="md"
      className="war-deployment-dialog"
      PaperProps={{ className: 'war-deployment-dialog__paper' }}
    >
      <DialogTitle className="war-deployment-title">
        <Groups color="error" />
        <Box>
          <Typography variant="h6">{t('war_deployment_title')}</Typography>
          <Typography variant="body2" color="text.secondary">{t('war_deployment_subtitle')}</Typography>
        </Box>
      </DialogTitle>
      <DialogContent dividers className="war-deployment-dialog__content">
        <Stack spacing={2.5}>
          <Box className="war-deployment-route">
            <Box><Typography variant="overline">{t('war_deployment_target')}</Typography><Typography fontWeight={800}>{getTerritoryName(targetTerritory?.name, language)}</Typography></Box>
            <Stack alignItems="center" spacing={0.5}>
              <MilitaryTech color="error" />
              <Chip size="small" variant="outlined" label={t(route === 'sea' ? 'war_deployment_route_sea' : 'war_deployment_route_land')} />
            </Stack>
            <Box><Typography variant="overline">{t('war_deployment_source')}</Typography><Typography fontWeight={800}>{sourceTerritory ? getTerritoryName(sourceTerritory.name, language) : t('war_deployment_no_source')}</Typography></Box>
          </Box>
          {error && <Alert severity="error" action={<Button disabled={interactionDisabled} color="inherit" size="small" startIcon={<Refresh />} onClick={loadReadiness}>{t('common_refresh', 'Обновить')}</Button>}>{error}</Alert>}
          {loading && !readiness ? <Box className="war-deployment-loading"><CircularProgress /></Box> : readiness && (
            <>
              <WarDeploymentReadiness readiness={readiness} t={t} language={language} />
              <Divider />
              <FormControl disabled={interactionDisabled} fullWidth size="small" className="war-deployment-warlord-select">
                <InputLabel id="war-deployment-warlord-label">{t('war_deployment_warlord')}</InputLabel>
                <Select
                  labelId="war-deployment-warlord-label"
                  value={warlordUserId}
                  label={t('war_deployment_warlord')}
                  onChange={(event) => selectWarlord(event.target.value)}
                  startAdornment={<MilitaryTech className="war-deployment-warlord-icon" />}
                >
                  {availableWarlords.map((candidate) => (
                    <MenuItem key={candidate.user_id} value={candidate.user_id}>
                      {candidate.nickname}
                    </MenuItem>
                  ))}
                </Select>
                {availableWarlords.length === 0 && (
                  <Typography variant="caption" color="error" className="war-deployment-warlord-help">
                    {t('war_deployment_no_warlord')}
                  </Typography>
                )}
              </FormControl>
              <Box className="war-deployment-picker__heading">
                <Typography fontWeight={800}>{t('war_deployment_selected', null, { selected: selectedIds.length, minimum })}</Typography>
                <Typography variant="caption" color="text.secondary">{t('war_deployment_rule_version', null, { version: readiness.rule_version })}</Typography>
              </Box>
              <TextField disabled={interactionDisabled} autoFocus fullWidth size="small" value={query} onChange={(event) => setQuery(event.target.value)} label={t('war_deployment_search')} InputProps={{ startAdornment: <Search color="disabled" sx={{ mr: 1 }} /> }} />
              <List className="war-deployment-list" disablePadding>
                {candidates.map((candidate) => {
                  const disabled = interactionDisabled || !candidate.verified || candidate.busy_in_attack;
                  const invalid = invalidIds.includes(candidate.user_id);
                  return (
                    <ListItemButton key={candidate.user_id} selected={selectedIds.includes(candidate.user_id)} disabled={disabled} onClick={() => toggleMember(candidate)} className={invalid ? 'war-deployment-member--invalid' : ''}>
                      <Checkbox edge="start" checked={selectedIds.includes(candidate.user_id)} disabled={disabled} tabIndex={-1} />
                      <ListItemAvatar><Avatar src={candidate.avatar_url || undefined}>{candidate.nickname?.[0]}</Avatar></ListItemAvatar>
                      <ListItemText primary={candidate.nickname} />
                      <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap" justifyContent="flex-end">
                        <Chip size="small" color={candidate.verified ? 'success' : 'default'} label={candidate.verified ? t('war_deployment_verified') : t('war_deployment_unverified')} />
                        {candidate.is_warlord && <Chip size="small" className="war-deployment-warlord-chip" icon={<MilitaryTech />} label={t('war_deployment_warlord')} />}
                        {candidate.busy_in_attack && <Chip size="small" color="error" label={t('war_deployment_busy', null, { warId: candidate.busy_war_id })} />}
                      </Stack>
                    </ListItemButton>
                  );
                })}
                {candidates.length === 0 && <Typography color="text.secondary" textAlign="center" py={3}>{t('war_deployment_no_candidates')}</Typography>}
              </List>
              <Alert severity="warning">{t('war_deployment_immutable_warning')}</Alert>
            </>
          )}
        </Stack>
      </DialogContent>
      <DialogActions className="war-deployment-dialog__actions">
        <Button onClick={onClose} disabled={submitting}>{t('common_cancel')}</Button>
        <Button variant="contained" color="error" startIcon={submitting ? <CircularProgress size={18} color="inherit" /> : <MilitaryTech />} disabled={!canSubmit} onClick={submit}>
          {submitting ? t('war_deployment_creating') : t('war_deployment_confirm')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default WarDeploymentDialog;
