import React from 'react';
import { Box, Chip, LinearProgress, Stack, Typography } from '@mui/material';
import { formatMoscowDateTime } from '../utils/dateTime';

const WarDeploymentReadiness = ({ readiness, t, language }) => {
  const { level, attack_points: points } = readiness;
  const missing = Object.entries(level.missing || {}).filter(([, value]) => value > 0);
  const missingLabels = {
    active_members: 'war_deployment_missing_members',
    territories: 'war_deployment_missing_territories',
    influence: 'war_deployment_missing_influence',
  };
  return (
    <Box className="war-deployment-summary">
      <Box className="war-deployment-summary__tile">
        <Typography variant="overline">{t('war_deployment_level')}</Typography>
        <Typography variant="h4">{level.level}</Typography>
        <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
          <Chip size="small" label={t('war_deployment_active_members', null, { count: level.active_member_count })} />
          <Chip size="small" label={t('war_deployment_territories', null, { count: level.territory_count })} />
          <Chip size="small" label={t('war_deployment_influence', null, { count: level.influence })} />
        </Stack>
        {level.next_level && (
          <Typography variant="caption" color="text.secondary">
            {t('war_deployment_next_level', null, { level: level.next_level.level })}
            {missing.map(([key, value]) => ` · ${t(missingLabels[key], null, { count: value })}`)}
          </Typography>
        )}
      </Box>
      <Box className="war-deployment-summary__tile">
        <Typography variant="overline">{t('war_deployment_attack_points')}</Typography>
        <Typography variant="h5">
          {t('war_deployment_points_value', null, { available: points.available, capacity: points.capacity })}
        </Typography>
        <LinearProgress
          variant="determinate"
          value={points.capacity ? (points.available / points.capacity) * 100 : 0}
          color={points.available > 0 ? 'success' : 'error'}
        />
        <Stack direction="row" spacing={0.75} useFlexGap flexWrap="wrap">
          {points.recovering > 0 && <Chip size="small" label={t('war_deployment_recovering', null, { count: points.recovering })} />}
          {points.blocked > 0 && <Chip size="small" color="warning" label={t('war_deployment_blocked', null, { count: points.blocked })} />}
        </Stack>
        {points.recoveries.map((recovery) => (
          <Typography key={recovery.spend_id} variant="caption" color="text.secondary">
            {t('war_deployment_recovery_at', null, { date: formatMoscowDateTime(recovery.recover_at, '', language) })}
          </Typography>
        ))}
      </Box>
    </Box>
  );
};

export default WarDeploymentReadiness;
