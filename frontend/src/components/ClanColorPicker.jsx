import React, { useEffect, useMemo, useState } from 'react';
import { Box, CircularProgress, Tooltip, Typography } from '@mui/material';

import { useLocalization } from '../hooks/useLocalization';
import { clanService } from '../services/clanService';
import { CLAN_COLORS } from '../constants/clanColors';
import './ClanColorPicker.css';

const ClanColorPicker = ({
  value,
  onChange,
  clanId = null,
  allowAdminOverride = false,
  label,
  showPreview = true,
}) => {
  const { getTextSync } = useLocalization('clan');
  const [palette, setPalette] = useState(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    let active = true;
    setLoadError(false);
    clanService.getMapColorState(clanId)
      .then((data) => {
        if (active) setPalette(data);
      })
      .catch(() => {
        if (active) setLoadError(true);
      });
    return () => { active = false; };
  }, [clanId]);

  const blocked = useMemo(
    () => new Map((palette?.blocked_colors || []).map((item) => [item.color, item.reason])),
    [palette],
  );
  const colors = useMemo(
    () => {
      const serverColors = new Set((palette?.groups || []).flatMap((group) => group.colors));
      return CLAN_COLORS.filter((color) => serverColors.has(color));
    },
    [palette],
  );
  const normalizedValue = value?.toUpperCase() || null;
  const colorLocked = Boolean(normalizedValue)
    && !allowAdminOverride
    && palette?.can_change_existing === false;

  const statusText = () => {
    if (allowAdminOverride && normalizedValue) {
      return getTextSync('clan_color_admin_override', 'Администратор может изменить закреплённый цвет.');
    }
    if (!normalizedValue) {
      return getTextSync('clan_color_initial_hint', 'Выберите цвет владений. Первичный выбор не расходует бесплатную смену.');
    }
    if (palette?.can_change_existing) {
      return getTextSync('clan_color_change_available', 'До первого сезона доступна одна бесплатная смена цвета.');
    }
    return getTextSync('clan_color_locked', 'Цвет закреплён. Изменить его может только администратор.');
  };

  return (
    <Box className="clan-color-picker">
      <Typography className="clan-color-picker__label">
        {label || getTextSync('clan_choose_map_color', 'Выберите цвет владений')}
      </Typography>

      {showPreview && (
        <Box
          className="clan-color-picker__preview"
          style={{ '--preview-color': normalizedValue || '#626270' }}
        >
          <Box
            className="clan-color-picker__territory"
            aria-hidden="true"
          />
          <Box minWidth={0}>
            <Typography fontWeight={900}>
              {normalizedValue || getTextSync('clan_color_not_selected', 'Цвет не выбран')}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {statusText()}
            </Typography>
          </Box>
        </Box>
      )}

      {!palette && !loadError && (
        <Box className="clan-color-picker__loading" role="status">
          <CircularProgress size={20} />
          <Typography variant="caption">{getTextSync('common_loading', 'Загрузка...')}</Typography>
        </Box>
      )}

      {loadError && (
        <Typography color="error.main" variant="caption">
          {getTextSync('clan_color_loading_error', 'Не удалось загрузить палитру цветов.')}
        </Typography>
      )}

      {palette && (
        <Box className="clan-color-picker__palette">
            {colors.map((color) => {
              const selected = normalizedValue === color;
              const blockedReason = blocked.get(color);
              const disabled = !selected && (colorLocked || Boolean(blockedReason));
              const tooltip = colorLocked
                ? getTextSync('clan_color_locked', 'Цвет закреплён. Изменить его может только администратор.')
                : blockedReason
                  ? getTextSync('clan_color_occupied', 'Этот цвет уже занят другим кланом')
                  : color;
              return (
                <Tooltip title={tooltip} key={color} arrow>
                  <span>
                    <button
                      type="button"
                      aria-label={getTextSync('clan_color_choose_aria', 'Выбрать цвет {color}', { color })}
                      aria-pressed={selected}
                      className={`clan-color-picker__swatch${selected ? ' is-selected' : ''}`}
                      style={{ '--swatch-color': color }}
                      disabled={disabled}
                      onClick={() => onChange(color)}
                    />
                  </span>
                </Tooltip>
              );
            })}
        </Box>
      )}
    </Box>
  );
};

export default ClanColorPicker;
