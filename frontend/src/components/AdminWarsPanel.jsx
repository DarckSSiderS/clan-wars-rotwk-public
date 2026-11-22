import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, Divider, MenuItem, Paper, Stack, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, TextField,
  Typography,
} from '@mui/material';
import {
  Calculate, Cancel, EmojiEvents, Groups, ManageSearch, Schedule, Shield, SportsMma,
} from '@mui/icons-material';
import api from '../services/api';
import { formatMoscowDateTime } from '../utils/dateTime';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { getTerritoryName } from '../i18n/territories';
import PlayerIdentity from './PlayerIdentity';
import AdminWarDeploymentsDialog from './AdminWarDeploymentsDialog';
import MatchDetailsDialog from './MatchDetailsDialog';
import AdminPermanentDeleteButton from './AdminPermanentDeleteButton';

const STATUS = {
  active: { labelKey: 'admin_war_status_active', color: 'error' },
  completed: { labelKey: 'admin_war_status_completed', color: 'success' },
  canceled: { labelKey: 'admin_war_status_canceled', color: 'default' },
};

const PATCHES = { patch_202: 'Patch 2.02', ennorath: 'Ennorath', all: 'admin_all_patches' };

const modeLabel = (mode, t) => String(mode || t('admin_mode_unspecified'))
  .replace(' versus ', 'v')
  .replace(' vs ', 'v');

const patchLabel = (patch, t) => (
  PATCHES[patch] ? t(PATCHES[patch], PATCHES[patch]) : patch
);

const scoreFor = (war, clanId) => (
  war?.clan_scores?.find((score) => score.clan_id === clanId)
  || { points: 0, wins: 0, losses: 0, matches: 0 }
);

const WarSide = ({ type, name, score, winner }) => {
  const { getLocalizedText: t } = useLocalizationContext();

  return (
  <Box className={`admin-war-side admin-war-side--${type} ${winner ? 'is-winner' : ''}`}>
    <Stack direction="row" spacing={1} alignItems="center">
      {type === 'attack' ? <SportsMma color="error" /> : <Shield color="info" />}
      <Box minWidth={0}>
        <Typography variant="overline">{type === 'attack' ? t("admin_ui_8ab9fa78a5") : t("admin_ui_ab7f7228f6")}</Typography>
        <Typography fontWeight={800} noWrap>{name || t("admin_ui_965444f900")}</Typography>
      </Box>
      {winner && <Chip className="admin-war-winner" size="small" icon={<EmojiEvents />} label={t("admin_ui_9db739de55")} />}
    </Stack>
    <Typography className="admin-war-side__points">{Number(score.points || 0).toFixed(2)}</Typography>
    <Typography variant="caption" color="text.secondary">
      {t("admin_ui_group_cbc825799a", null, { value0: score.wins || 0, value1: score.losses || 0, value2: score.matches || 0 })}</Typography>
  </Box>
  );
};

const AdminWarsPanel = ({ onMessage, onChanged }) => {
  const { language, getLocalizedText: t } = useLocalizationContext();
  const [wars, setWars] = useState([]);
  const [status, setStatus] = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedWar, setSelectedWar] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [action, setAction] = useState(null);
  const [form, setForm] = useState({ reason: '', hours: 24, winner_clan_id: '' });
  const [saving, setSaving] = useState(false);
  const [warfareWarId, setWarfareWarId] = useState(null);
  const [selectedMatch, setSelectedMatch] = useState(null);

  const loadWars = useCallback(async () => {
    setLoading(true);
    try {
      const params = { limit: 200 };
      if (status) params.status = status;
      const response = await api.get('/admin/wars', { params });
      setWars(response.data.wars || []);
    } catch (error) {
      onMessage({ type: 'error', text: error.response?.data?.detail || t('admin_wars_load_error') });
    } finally {
      setLoading(false);
    }
  }, [onMessage, status, t]);

  useEffect(() => { loadWars(); }, [loadWars]);

  const openWar = async (warId) => {
    setDetailLoading(true);
    try {
      const response = await api.get(`/admin/wars/${warId}`);
      setSelectedWar(response.data);
    } catch (error) {
      onMessage({ type: 'error', text: error.response?.data?.detail || t('admin_war_open_error') });
    } finally {
      setDetailLoading(false);
    }
  };

  const beginAction = (type, match = null) => {
    setAction({ type, match });
    setForm({
      points: 0,
      request_id: crypto.randomUUID(),
      reason: '',
      hours: 24,
      winner_clan_id: selectedWar?.defending_clan_id || selectedWar?.attacking_clan_id || '',
    });
  };

  const actionTitle = useMemo(() => {
    const key = ({
      recalculate: 'admin_war_action_recalculate',
      extend: 'admin_war_action_extend',
      finish: 'admin_war_action_finish',
      cancel: 'admin_war_action_cancel',
      points: 'admin_war_adjust_points',
      count: 'admin_war_action_count',
      exclude: 'admin_war_action_exclude',
      automatic: 'admin_war_action_automatic',
    })[action?.type];
    return key ? t(key) : '';
  }, [action?.type, t]);

  const runAction = async () => {
    if (!selectedWar || !action) return;
    setSaving(true);
    try {
      let response;
      const reason = form.reason.trim();
      if (['count', 'exclude', 'automatic'].includes(action.type)) {
        response = await api.patch(
          `/admin/wars/${selectedWar.id}/matches/${action.match.id}`,
          { mode: action.type, reason },
        );
      } else if (action.type === 'points') {
        response = await api.post(`/admin/wars/${selectedWar.id}/points`, { reason, points: Number(form.points), clan_id: Number(form.winner_clan_id), request_id: form.request_id });
      } else if (action.type === 'extend') {
        response = await api.post(`/admin/wars/${selectedWar.id}/extend`, { reason, hours: Number(form.hours) });
      } else if (action.type === 'finish') {
        response = await api.post(`/admin/wars/${selectedWar.id}/finish`, { reason, winner_clan_id: Number(form.winner_clan_id) });
      } else {
        response = await api.post(`/admin/wars/${selectedWar.id}/${action.type}`, { reason });
      }
      setSelectedWar(response.data);
      setAction(null);
      onMessage({ type: 'success', text: t('admin_war_action_success', null, { action: actionTitle }) });
      await loadWars();
      if (onChanged) await onChanged();
    } catch (error) {
      onMessage({ type: 'error', text: error.response?.data?.detail || t('admin_dashboard_operation_error') });
    } finally {
      setSaving(false);
    }
  };

  const attackerScore = scoreFor(selectedWar, selectedWar?.attacking_clan_id);
  const defenderScore = scoreFor(selectedWar, selectedWar?.defending_clan_id);
  const active = selectedWar?.status === 'active';

  return (
    <Paper className="admin-section">
      <Box className="admin-section__title">
        <Box>
          <Typography variant="h6">{t("admin_ui_929e33035d")}</Typography>
          <Typography variant="body2" color="text.secondary">{t("admin_ui_99e92ae392")}</Typography>
        </Box>
        <TextField select size="small" label={t("admin_ui_f7f293b5c5")} value={status} onChange={(event) => setStatus(event.target.value)} sx={{ minWidth: 170 }}>
          <MenuItem value="">{t("admin_ui_134c2463ea")}</MenuItem>
          <MenuItem value="active">{t("admin_ui_6009f6cb7c")}</MenuItem>
          <MenuItem value="completed">{t("admin_ui_52b1d415f2")}</MenuItem>
          <MenuItem value="canceled">{t("admin_ui_05f0405be7")}</MenuItem>
        </TextField>
      </Box>

      {loading ? <Box className="admin-inline-loading"><CircularProgress size={30} /></Box> : (
        <TableContainer className="admin-war-table"><Table size="small">
          <TableHead><TableRow>
            <TableCell>{t("admin_ui_61540b9e95")}</TableCell><TableCell>{t("admin_ui_919af63e42")}</TableCell><TableCell>{t("admin_ui_f7f293b5c5")}</TableCell>
            <TableCell>{t("admin_ui_f812ebf899")}</TableCell><TableCell>{t("admin_ui_7a298f5165")}</TableCell><TableCell />
          </TableRow></TableHead>
          <TableBody>
            {wars.map((war) => <TableRow key={war.id} hover>
              <TableCell><Typography fontWeight={800}>{getTerritoryName(war.territory_name, language)}</Typography><Typography variant="caption" color="text.secondary">{t("admin_ui_group_2368f77c34", null, { value0: war.id })}</Typography></TableCell>
              <TableCell><Typography variant="body2"><b>{war.attacking_clan_name}</b> → {war.defending_clan_name || t("admin_ui_1d4763018f")}</Typography>{war.winner_clan_name && <Typography variant="caption" color="warning.main">{t("admin_ui_group_a853b97388", null, { value0: war.winner_clan_name })}</Typography>}</TableCell>
              <TableCell><Chip size="small" color={STATUS[war.status]?.color} label={STATUS[war.status]?.labelKey ? t(STATUS[war.status].labelKey) : war.status} /></TableCell>
              <TableCell><Typography variant="body2">{t("admin_ui_group_b6c316dbfd", null, { value0: war.tracked_matches })}</Typography><Typography variant="caption" color="text.secondary">{t("admin_ui_group_1a40b5215b", null, { value0: war.rejected_matches })}</Typography></TableCell>
              <TableCell>{formatMoscowDateTime(war.status === 'active' ? war.ends_at : war.ended_at, '—', language)}</TableCell>
              <TableCell align="right"><Button size="small" startIcon={<ManageSearch />} onClick={() => openWar(war.id)}>{t("admin_ui_1259571a15")}</Button></TableCell>
            </TableRow>)}
            {wars.length === 0 && <TableRow><TableCell colSpan={6} align="center">{t("admin_ui_fd490c15c3")}</TableCell></TableRow>}
          </TableBody>
        </Table></TableContainer>
      )}

      <Dialog open={Boolean(selectedWar) || detailLoading} onClose={() => !saving && setSelectedWar(null)} fullWidth maxWidth="lg">
        <DialogTitle>{selectedWar ? t("admin_ui_ceaf7a09d1", null, { value0: getTerritoryName(selectedWar.territory_name, language), value1: selectedWar.id }) : t("admin_ui_c32257d1a3")}</DialogTitle>
        <DialogContent dividers>
          {!selectedWar ? <Box className="admin-inline-loading"><CircularProgress /></Box> : <Stack spacing={2}>
            <Box className="admin-war-score">
              <WarSide type="attack" name={selectedWar.attacking_clan_name} score={attackerScore} winner={selectedWar.winner_clan_id === selectedWar.attacking_clan_id} />
              <Box className="admin-war-score__versus">VS</Box>
              <WarSide type="defense" name={selectedWar.defending_clan_name} score={defenderScore} winner={selectedWar.winner_clan_id === selectedWar.defending_clan_id} />
            </Box>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }} justifyContent="space-between">
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Chip label={STATUS[selectedWar.status]?.labelKey ? t(STATUS[selectedWar.status].labelKey) : selectedWar.status} color={STATUS[selectedWar.status]?.color} />
                <Chip label={t("admin_ui_b6c316dbfd", null, { value0: selectedWar.tracked_matches })} color="success" variant="outlined" />
                <Chip label={t("admin_ui_1a40b5215b", null, { value0: selectedWar.rejected_matches })} variant="outlined" />
                <Chip label={patchLabel(selectedWar.attacker_patch, t)} variant="outlined" />
              </Stack>
              {active && <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                <Button size="small" startIcon={<Schedule />} onClick={() => beginAction('extend')}>{t("admin_ui_d354e301cb")}</Button>
                <Button size="small" color="success" startIcon={<EmojiEvents />} onClick={() => beginAction('finish')}>{t("admin_ui_5b1713041f")}</Button>
                <Button size="small" color="error" startIcon={<Cancel />} onClick={() => beginAction('cancel')}>{t("admin_ui_555ad1c0c3")}</Button>
              </Stack>}
              <Button size="small" startIcon={<Groups />} onClick={() => setWarfareWarId(selectedWar.id)}>{t("admin_ui_17b3d88b67")}</Button>
              <Button size="small" startIcon={<Calculate />} onClick={() => beginAction('points')}>{t('admin_war_adjust_points')}</Button>
              <Button size="small" startIcon={<Calculate />} onClick={() => beginAction('recalculate')}>{t("admin_ui_0c50d415ae")}</Button>
              <AdminPermanentDeleteButton kind="wars" id={selectedWar.id} onMessage={onMessage} onDeleted={async () => { setSelectedWar(null); await loadWars(); if (onChanged) await onChanged(); }} />
            </Stack>
            {!active && <Alert severity="info">{t('admin_war_finished_review')}</Alert>}
            {(selectedWar.score_adjustments || []).map((row) => <Alert key={row.id} severity="info">{selectedWar.clan_scores.find((score) => score.clan_id === row.clan_id)?.clan_name}: {row.points > 0 ? '+' : ''}{row.points} · {row.reason}</Alert>)}
            <Divider />
            <Typography variant="h6">{t("admin_ui_fd1e39a418")}</Typography>
            <TableContainer className="admin-war-matches"><Table size="small" stickyHeader>
              <TableHead><TableRow><TableCell>{t("admin_ui_3eaa09937a")}</TableCell><TableCell>{t("admin_ui_d5f9e29f80")}</TableCell><TableCell>{t("admin_ui_9fa227c53f")}</TableCell><TableCell>{t("admin_ui_457969b009")}</TableCell><TableCell /></TableRow></TableHead>
              <TableBody>{selectedWar.match_breakdown.map((match) => <TableRow
                key={match.id}
                hover
                className="match-clickable-row"
                role="button"
                tabIndex={0}
                onClick={(event) => {
                  if (!event.target.closest('a, button')) setSelectedMatch(match);
                }}
                onKeyDown={(event) => {
                  if (event.target.closest('a, button')) return;
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    setSelectedMatch(match);
                  }
                }}
              >
                <TableCell>{formatMoscowDateTime(match.played_at, '—', language)}</TableCell>
                <TableCell><Typography variant="body2" fontWeight={700}>{match.map_name || t("admin_ui_098e705ea7")}</Typography><Typography variant="caption" color="text.secondary">{modeLabel(match.game_mode, t)} · {patchLabel(match.patch_family, t) || t("admin_ui_8336a4f611")}</Typography></TableCell>
                <TableCell><Typography variant="body2"><PlayerIdentity username={match.winner.username} />{t("admin_ui_18d7dde9d7")}<PlayerIdentity username={match.loser.username} /></Typography><Typography variant="caption" color="text.secondary">{t("admin_ui_group_105b486388", null, { value0: Number(match.winner.total_points || 0).toFixed(2) })}</Typography></TableCell>
                <TableCell><Chip size="small" color={match.is_counted ? 'success' : 'default'} label={match.is_counted ? t("admin_ui_eb578281fe") : t("admin_ui_4909c5ca0e")} /><Typography variant="caption" display="block" color="text.secondary" sx={{ mt: .5 }}>{match.admin_override === null ? (match.rejection_reason || t("admin_ui_5ed8fe81c9")) : t("admin_ui_73cd824358", null, { value0: t(match.admin_override ? 'admin_war_counted' : 'admin_war_excluded'), value1: match.admin_override_reason })}</Typography></TableCell>
                <TableCell align="right">{<Stack direction="row" spacing={.5} justifyContent="flex-end">
                  <Button size="small" disabled={match.admin_override === true} onClick={() => beginAction('count', match)}>{t("admin_ui_efcfdecf1d")}</Button>
                  <Button size="small" color="error" disabled={match.admin_override === false} onClick={() => beginAction('exclude', match)}>{t("admin_ui_85961c9f03")}</Button>
                  {match.admin_override !== null && <Button size="small" onClick={() => beginAction('automatic', match)}>{t("admin_ui_5695330ffb")}</Button>}
                </Stack>}</TableCell>
              </TableRow>)}
              {selectedWar.match_breakdown.length === 0 && <TableRow><TableCell colSpan={5} align="center">{t("admin_ui_d6a70541ca")}</TableCell></TableRow>}
              </TableBody>
            </Table></TableContainer>
          </Stack>}
        </DialogContent>
        <DialogActions><Button onClick={() => setSelectedWar(null)}>{t("admin_ui_4ae50d3073")}</Button></DialogActions>
      </Dialog>

      <Dialog open={Boolean(action)} onClose={() => !saving && setAction(null)} fullWidth maxWidth="sm">
        <DialogTitle>{actionTitle}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} mt={1}>
            {action?.type === 'extend' && <TextField label={t("admin_ui_e6a5a264b5")} type="number" value={form.hours} inputProps={{ min: 1, max: 168 }} onChange={(event) => setForm((current) => ({ ...current, hours: event.target.value }))} />}
            {action?.type === 'points' && <TextField type="number" label={t('admin_war_points_delta')} value={form.points} inputProps={{ min: -1000000, max: 1000000, step: 0.01 }} onChange={(event) => setForm((current) => ({ ...current, points: event.target.value }))} />}
            {['finish', 'points'].includes(action?.type) && <TextField select label={t('admin_war_side')} value={form.winner_clan_id} onChange={(event) => setForm((current) => ({ ...current, winner_clan_id: event.target.value }))}>
              <MenuItem value={selectedWar?.attacking_clan_id}>{selectedWar?.attacking_clan_name}</MenuItem>
              {selectedWar?.defending_clan_id && <MenuItem value={selectedWar.defending_clan_id}>{selectedWar.defending_clan_name}</MenuItem>}
            </TextField>}
            {action?.type === 'cancel' && <Alert severity="warning">{t("admin_ui_518370862a")}</Alert>}
            <TextField autoFocus required multiline minRows={3} label={t("admin_ui_4a9ea52cda")} value={form.reason} onChange={(event) => setForm((current) => ({ ...current, reason: event.target.value }))} helperText={t('admin_war_audit_reason_help')} />
          </Stack>
        </DialogContent>
        <DialogActions><Button onClick={() => setAction(null)}>{t("admin_ui_f6dab074d7")}</Button><Button variant="contained" color={action?.type === 'cancel' || action?.type === 'exclude' ? 'error' : 'primary'} disabled={saving || form.reason.trim().length < 3} onClick={runAction}>{saving ? t("admin_ui_632fd0d93d") : t("admin_ui_0467ae4bb8")}</Button></DialogActions>
      </Dialog>
      <MatchDetailsDialog
        open={Boolean(selectedMatch)}
        matchRef={selectedMatch?.match_id || selectedMatch?.id}
        initialMatch={selectedMatch}
        onClose={() => setSelectedMatch(null)}
      />
      <AdminWarDeploymentsDialog warId={warfareWarId} onClose={() => setWarfareWarId(null)} />
    </Paper>
  );
};

export default AdminWarsPanel;
