import React from 'react';
import {
  Alert,
  Avatar,
  Box,
  Chip,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import { Groups, Shield, SportsMma } from '@mui/icons-material';
import { Link } from 'react-router-dom';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { formatMoscowDateTime } from '../utils/dateTime';
import PlayerIdentity from './PlayerIdentity';
import './WarSideGroups.css';

const points = (value) => Number(value || 0).toFixed(2).replace(/\.?0+$/, '');

const memberStatus = (status, t) => ({
  participating: t('war_group_status_participating'),
  left_clan: t('war_group_status_left_clan'),
  joined_during_war: t('war_group_status_joined_during_war'),
  deployment_released: t('war_group_status_deployment_released'),
}[status] || status);

const GroupCard = ({ group, t, language }) => {
  const isAttacker = group.role === 'attacker';
  const accent = group.clan_map_color || (isAttacker ? '#ff5b57' : '#69aef0');
  const ruleText = {
    whole_clan_if_challenged: t('war_group_rule_whole'),
    squad_if_challenged: t('war_group_rule_squad'),
    occupied_territory_owner: t('war_group_rule_owner'),
  }[group.defense_rule] || group.defense_rule;
  return (
    <Paper className="war-group-card" sx={{ '--war-group-accent': accent }}>
      <Box className="war-group-card__header">
        <Avatar src={group.clan_avatar_url || undefined} variant="rounded">{group.clan_name?.[0]}</Avatar>
        <Box minWidth={0}>
          <Typography variant="overline" color="text.secondary">
            {isAttacker ? t('war_group_attack') : t('war_group_defense')}
          </Typography>
          <Typography component={Link} className="entity-link" to={`/clans/${group.clan_id}`} variant="h6">
            {group.clan_name}
          </Typography>
        </Box>
        {isAttacker ? <SportsMma className="war-group-card__role-icon" /> : <Shield className="war-group-card__role-icon" />}
      </Box>
      <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
        <Chip size="small" label={group.scope === 'whole_clan' ? t('war_group_whole_clan') : t('war_group_squad')} />
        <Chip size="small" variant="outlined" label={t('war_group_members_count', null, { count: group.member_count })} />
      </Stack>
      <Typography variant="body2" color="text.secondary">{ruleText}</Typography>
      <Box component="ul" className="war-group-members">
        {group.members.map((member) => (
          <Box component="li" key={member.user_id} className="war-group-member">
            <Avatar src={member.avatar_url || undefined}>{member.display_nickname?.[0]}</Avatar>
            <Box minWidth={0}>
              <Typography fontWeight={800} sx={{ overflowWrap: 'anywhere' }}>
                <PlayerIdentity username={member.display_nickname || member.username} usernameClassName="entity-link" />
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                {t('war_group_membership_interval', null, {
                  start: formatMoscowDateTime(member.membership_started_at, '—', language),
                  end: formatMoscowDateTime(member.membership_ended_at, t('war_group_present'), language),
                })}
              </Typography>
              {member.assigned_at && <Typography variant="caption" color="text.secondary" display="block">{t('war_group_assigned_at', null, { date: formatMoscowDateTime(member.assigned_at, '', language) })}</Typography>}
              <Typography variant="caption" color="text.secondary" display="block">
                {t('war_group_metrics', null, {
                  matches: member.matches,
                  wins: member.wins,
                  losses: member.losses,
                  points: points(member.points),
                })}
              </Typography>
            </Box>
            <Chip
              size="small"
              color={member.status_code === 'participating' ? 'success' : 'default'}
              variant="outlined"
              label={memberStatus(member.status_code, t)}
            />
          </Box>
        ))}
      </Box>
    </Paper>
  );
};

const WarSideGroups = ({ groups = [], deploymentTracking = false }) => {
  const { getLocalizedText: t, language } = useLocalizationContext();
  return (
    <Box component="section" aria-labelledby="war-groups-heading" mb={3}>
      <Box display="flex" alignItems="center" gap={1} mb={2}>
        <Groups color="primary" />
        <Box>
          <Typography id="war-groups-heading" variant="h6">{t('war_groups_title')}</Typography>
          <Typography variant="body2" color="text.secondary">{t('war_groups_subtitle')}</Typography>
        </Box>
      </Box>
      {!deploymentTracking ? <Alert severity="info">{t('war_groups_legacy')}</Alert> : groups.length === 0 ? (
        <Alert severity="info">{t('war_groups_empty')}</Alert>
      ) : (
        <Box className="war-groups-grid">
          {groups.map((group, index) => <GroupCard key={`${group.clan_id}-${group.role}-${index}`} group={group} t={t} language={language} />)}
        </Box>
      )}
    </Box>
  );
};

export default WarSideGroups;
