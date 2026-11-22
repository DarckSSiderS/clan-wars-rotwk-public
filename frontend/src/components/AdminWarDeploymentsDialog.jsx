import React, { useEffect, useState } from 'react';
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Avatar,
  Box,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Button,
  Divider,
  Stack,
  Typography,
} from '@mui/material';
import { ExpandMore, Groups, ReceiptLong, Timeline } from '@mui/icons-material';
import { warService } from '../services/warService';
import { formatMoscowDateTime } from '../utils/dateTime';
import './AdminWarDeploymentsDialog.css';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const date = (value, language) => formatMoscowDateTime(value, '—', language);
const role = (value, t) => t(value === 'attacker' ? 'admin_deployment_role_attack' : 'admin_deployment_role_defence');
const scope = (value, t) => t(value === 'whole_clan' ? 'admin_deployment_scope_clan' : 'admin_deployment_scope_squad');

const AdminWarDeploymentsDialog = ({ warId, onClose }) => {
  const { getLocalizedText: t, language } = useLocalizationContext();
  const [war, setWar] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!warId) return;
    let active = true;
    setWar(null);
    setError('');
    setLoading(true);
    warService.getAdminWar(warId)
      .then((payload) => { if (active) setWar(payload); })
      .catch((requestError) => {
        if (!active) return;
        const detail = requestError.response?.data?.detail;
        setError(typeof detail === 'string' ? detail : detail?.message || t("admin_ui_7924bfb625"));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [t, warId]);

  const data = war?.admin_warfare;
  return (
    <Dialog open={Boolean(warId)} onClose={onClose} fullWidth maxWidth="xl">
      <DialogTitle>{t("admin_ui_group_bdc10dfd7c", null, { value0: warId })}</DialogTitle>
      <DialogContent dividers>
        {loading && <Box className="admin-inline-loading"><CircularProgress /></Box>}
        {error && <Alert severity="error">{error}</Alert>}
        {data && <Stack spacing={2}>
          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            <Chip color={war.deployment_tracking ? 'success' : 'default'} label={war.deployment_tracking ? t("admin_ui_c36d82fb5c") : t("admin_ui_5eb9a7a6ec")} />
            <Chip variant="outlined" label={t("admin_ui_a94ad0444f", null, { value0: data.campaign_rule_set_id || '—' })} />
            <Chip variant="outlined" label={t("admin_ui_ddc0bc8570", null, { value0: war.scoring_version })} />
          </Stack>

          <Box>
            <Typography variant="h6" gutterBottom><Groups fontSize="small" />{t("admin_ui_b68f2c7d05")}</Typography>
            <Stack spacing={1.5}>
              {data.deployments.map((deployment) => (
                <Accordion key={deployment.id} disableGutters>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" alignItems="center">
                      <Typography fontWeight={800}>{t("admin_ui_group_ed8b3d76e9", null, { value0: deployment.id, value1: deployment.claim_sequence, value2: deployment.clan_id })}</Typography>
                      <Chip size="small" color={deployment.current_role === 'attacker' ? 'error' : 'info'} label={role(deployment.current_role, t)} />
                      <Chip size="small" variant="outlined" label={scope(deployment.eligibility_scope, t)} />
                      <Chip size="small" variant="outlined" label={t("admin_ui_d84049b0e5", null, { value0: deployment.members.length })} />
                    </Stack>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Stack spacing={1.5}>
                      <Typography variant="body2" color="text.secondary">{t("admin_ui_group_72187c1f71", null, { value0: date(deployment.assigned_at, language), value1: deployment.assigned_by_username || t("admin_ui_646c57861a"), value2: deployment.source_territory_id || t("admin_ui_ced07fd144"), value3: deployment.territory_count_snapshot, value4: deployment.defense_rule, value5: deployment.rule_version })}
                      </Typography>
                      {deployment.members.map((member) => (
                        <Box key={member.user_id} className="admin-warfare-member">
                          <Avatar src={member.avatar_url_snapshot || undefined}>{member.nickname_snapshot?.[0]}</Avatar>
                          <Box minWidth={0}>
                            <Typography fontWeight={800}>{member.nickname_snapshot || member.username_snapshot}</Typography>
                            <Typography variant="body2">{member.username_snapshot} · user #{member.user_id}</Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ overflowWrap: 'anywhere' }}>UUID: {member.external_uuid_snapshot}</Typography>
                          </Box>
                          <Typography variant="caption" color="text.secondary">{t('admin_deployment_membership_since', null, { date: date(member.membership_started_at, language) })}<br />{t('admin_deployment_released_at', null, { date: date(member.released_at, language) })}
                          </Typography>
                        </Box>
                      ))}
                    </Stack>
                  </AccordionDetails>
                </Accordion>
              ))}
              {data.deployments.length === 0 && <Alert severity="info">{t("admin_ui_f62f0a5048")}</Alert>}
            </Stack>
          </Box>

          <Divider />
          <Box>
            <Typography variant="h6" gutterBottom><ReceiptLong fontSize="small" />{t("admin_ui_9380b73579")}</Typography>
            <Stack spacing={1}>
              {data.attack_point_spends.map((spend) => (
                <Box key={spend.id} className="admin-warfare-record">
                  <Typography fontWeight={800}>{t("admin_ui_group_73c0d4b6b9", null, { value0: spend.id, value1: spend.clan_id })}</Typography>
                  <Typography variant="body2">{t("admin_ui_group_ef32e77b51", null, { value0: date(spend.spent_at, language), value1: date(spend.recover_at, language), value2: spend.level_snapshot, value3: spend.capacity_snapshot })}</Typography>
                  <Typography variant="caption" color={spend.refunded_at ? 'warning.main' : 'text.secondary'}>
                    {spend.refunded_at ? t("admin_ui_3ae2108bb1", null, { value0: date(spend.refunded_at, language), value1: spend.refund_reason }) : t("admin_ui_f9eb0f9a69", null, { value0: spend.origin, value1: spend.rule_version })}
                  </Typography>
                </Box>
              ))}
              {data.attack_point_spends.length === 0 && <Typography color="text.secondary">{t("admin_ui_ad2984cffe")}</Typography>}
            </Stack>
          </Box>

          <Divider />
          <Box>
            <Typography variant="h6" gutterBottom><Timeline fontSize="small" />{t("admin_ui_ee140eaec4")}</Typography>
            <Stack spacing={1}>
              {data.level_events.map((event) => (
                <Box key={event.id} className="admin-warfare-record">
                  <Typography fontWeight={800}>{t("admin_ui_group_c5d2a27972", null, { value0: event.clan_id, value1: event.previous_level ?? '—', value2: event.new_level })}</Typography>
                  <Typography variant="body2">{t("admin_ui_group_800e283b8e", null, { value0: event.active_member_count, value1: event.territory_count, value2: event.influence, value3: date(event.occurred_at, language) })}</Typography>
                  <Typography variant="caption" color="text.secondary">{t("admin_ui_group_5af09a5684", null, { value0: event.reason, value1: event.rule_version })}</Typography>
                </Box>
              ))}
              {data.audit_entries.map((entry) => (
                <Accordion key={`audit-${entry.id}`} disableGutters>
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Typography fontWeight={800}>{entry.action} · {date(entry.created_at, language)}</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Typography variant="body2">{t("admin_ui_group_a3d82384a0", null, { value0: entry.actor_user_id || t("admin_ui_c2792a4424"), value1: entry.reason || t("admin_ui_1d89e230a2") })}</Typography>
                    <Box component="pre" className="admin-warfare-json">{JSON.stringify({ before: entry.before_data, after: entry.after_data }, null, 2)}</Box>
                  </AccordionDetails>
                </Accordion>
              ))}
              {data.level_events.length === 0 && data.audit_entries.length === 0 && <Typography color="text.secondary">{t("admin_ui_1995bc9024")}</Typography>}
            </Stack>
          </Box>
        </Stack>}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>{t("admin_ui_4ae50d3073")}</Button></DialogActions>
    </Dialog>
  );
};

export default AdminWarDeploymentsDialog;
