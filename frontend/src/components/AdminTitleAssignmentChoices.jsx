import React from 'react';
import { Avatar, Box, ButtonBase, Chip, Stack, Typography } from '@mui/material';
import { CheckCircle, PersonOutline } from '@mui/icons-material';
import { useLocalizationContext } from '../contexts/LocalizationContext';

export const AdminTitleUserResults = ({ users, selectedUserId, onSelect }) => {
  const { getLocalizedText: t } = useLocalizationContext();

  return (
  <Box className="admin-title-assignment__results" role="listbox" aria-label={t("admin_ui_7dd4c5392d")}>
    {users.map((user) => (
      <ButtonBase
        key={user.id}
        className={`admin-title-assignment__user${selectedUserId === user.id ? ' is-selected' : ''}`}
        onClick={() => onSelect(user)}
        role="option"
        aria-selected={selectedUserId === user.id}
      >
        <PersonOutline />
        <Box minWidth={0} textAlign="left">
          <Typography fontWeight={800} noWrap>{user.username}</Typography>
          <Typography variant="caption" color="text.secondary">{t("admin_ui_group_ae461e01b9", null, { value0: (user.titles || []).length })}
          </Typography>
        </Box>
        {selectedUserId === user.id && <CheckCircle color="success" />}
      </ButtonBase>
    ))}
  </Box>
  );
};

export const AdminTitleChoices = ({ titles, selectedTitleId, assignedTitleIds, onSelect }) => {
  const { getLocalizedText: t } = useLocalizationContext();

  return (
  <Box className="admin-title-assignment__titles" role="listbox" aria-label={t("admin_ui_59c51ffcbe")}>
    {titles.map((title) => {
      const assigned = assignedTitleIds.has(title.id);
      const selected = selectedTitleId === title.id;
      return (
        <ButtonBase
          key={title.id}
          className={`admin-title-assignment__title${selected ? ' is-selected' : ''}`}
          onClick={() => onSelect(title.id)}
          role="option"
          aria-selected={selected}
        >
          <Avatar src={title.image_url} alt="" />
          <Box minWidth={0} textAlign="left">
            <Stack direction="row" alignItems="center" spacing={0.75} mb={0.25}>
              <Typography fontWeight={800} noWrap>{title.name}</Typography>
              {assigned && <Chip size="small" color="success" label={t("admin_ui_97a775e1ee")} />}
            </Stack>
            <Typography variant="caption" color="text.secondary" className="admin-title-assignment__description">
              {title.description}
            </Typography>
          </Box>
        </ButtonBase>
      );
    })}
  </Box>
  );
};
