import React from 'react';
import { Box, Tooltip, Typography } from '@mui/material';
import { CLAN_RESOURCES } from './clanResources';

const ClanResourceSummary = ({ economy, getResourceLabel, ariaLabel }) => (
  <Box
    aria-label={ariaLabel}
    sx={{
      display: 'grid',
      gridTemplateColumns: 'repeat(auto-fit, minmax(112px, 1fr))',
      gap: 1,
      mt: 2,
      width: '100%',
    }}
  >
    {CLAN_RESOURCES.map(({ key, color, Icon }) => (
      <Tooltip title={getResourceLabel(key)} key={key} arrow>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0, py: 0.75 }}>
          <Icon sx={{ color, fontSize: 24, flex: '0 0 auto' }} />
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="caption" color="text.secondary" display="block" sx={{ lineHeight: 1.2 }}>
              {getResourceLabel(key)}
            </Typography>
            <Typography variant="subtitle2" fontWeight={800}>{economy?.[key] || 0}</Typography>
          </Box>
        </Box>
      </Tooltip>
    ))}
  </Box>
);

export default ClanResourceSummary;
