import React from 'react';
import {
  Box,
  FormControlLabel,
  IconButton,
  Paper,
  Switch,
  Tooltip,
  Typography,
} from '@mui/material';
import { Fullscreen, Layers } from '@mui/icons-material';

const MapCanvasControls = ({
  isLayerFilterOpen,
  layers,
  labels,
  onLayerFilterToggle,
  onLayerToggle,
  onFullscreen,
}) => (
  <Box className="map-control-panel">
    <Tooltip title={labels.layers}>
      <IconButton
        aria-label={labels.layers}
        aria-expanded={isLayerFilterOpen}
        onClick={onLayerFilterToggle}
        size="small"
        className={`map-control-button${isLayerFilterOpen ? ' map-control-button--selected' : ''}`}
      >
        <Layers />
      </IconButton>
    </Tooltip>
    <Tooltip title={labels.fullscreen}>
      <IconButton
        aria-label={labels.fullscreen}
        onClick={onFullscreen}
        size="small"
        className="map-control-button"
      >
        <Fullscreen />
      </IconButton>
    </Tooltip>
    {isLayerFilterOpen && (
      <Paper className="map-layer-filter" elevation={8}>
        <Typography className="map-layer-filter__title">{labels.layers}</Typography>
        {[
          ['wars', labels.wars],
          ['trade', labels.trade],
          ['clanIcons', labels.clanIcons],
          ['attackable', labels.attackable],
        ].map(([key, label]) => (
          <FormControlLabel
            key={key}
            className="map-layer-filter__option"
            control={(
              <Switch
                size="small"
                checked={Boolean(layers[key])}
                onChange={(event) => onLayerToggle(key, event.target.checked)}
              />
            )}
            label={<span className="map-layer-filter__label">{label}</span>}
          />
        ))}
      </Paper>
    )}
  </Box>
);

export default MapCanvasControls;
