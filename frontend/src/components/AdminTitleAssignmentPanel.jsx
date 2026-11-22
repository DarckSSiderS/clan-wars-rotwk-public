import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Paper,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import { PersonAdd, RemoveCircleOutline, Search } from '@mui/icons-material';

import api from '../services/api';
import { AdminTitleChoices, AdminTitleUserResults } from './AdminTitleAssignmentChoices';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const AdminTitleAssignmentPanel = ({ titles, onAssignmentChange }) => {
  const { getLocalizedText: t } = useLocalizationContext();
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [selectedTitleId, setSelectedTitleId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [confirmationOpen, setConfirmationOpen] = useState(false);

  useEffect(() => {
    const timeout = window.setTimeout(() => setSearch(searchInput.trim()), 350);
    return () => window.clearTimeout(timeout);
  }, [searchInput]);

  useEffect(() => {
    const controller = new AbortController();
    const loadUsers = async () => {
      setLoading(true);
      setError('');
      try {
        const response = await api.get('/admin/users', {
          params: {
            search: search || undefined,
            title_filter: filter,
            title_id: selectedTitleId || undefined,
            limit: 50,
          },
          signal: controller.signal,
        });
        setUsers(response.data.users || []);
      } catch (requestError) {
        if (requestError.code !== 'ERR_CANCELED') {
          setError(requestError.response?.data?.detail || t("admin_ui_09b2357249"));
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    loadUsers();
    return () => controller.abort();
  }, [filter, search, selectedTitleId, t]);

  const activeTitles = useMemo(() => titles.filter((title) => title.is_active), [titles]);
  const assignedTitleIds = useMemo(
    () => new Set((selectedUser?.titles || []).map((title) => title.id)),
    [selectedUser],
  );
  const selectedTitle = activeTitles.find((title) => title.id === selectedTitleId) || null;
  const isRemoval = selectedTitle ? assignedTitleIds.has(selectedTitle.id) : false;

  const selectUser = (user) => {
    setSelectedUser(user);
    setMessage('');
  };

  const confirmMutation = async () => {
    if (!selectedUser || !selectedTitle) return;
    setSaving(true);
    setError('');
    try {
      if (isRemoval) await api.delete(`/admin/titles/${selectedTitle.id}/users/${selectedUser.id}`);
      else await api.post(`/admin/titles/${selectedTitle.id}/users/${selectedUser.id}`);

      const nextTitles = isRemoval
        ? selectedUser.titles.filter((title) => title.id !== selectedTitle.id)
        : [...(selectedUser.titles || []), selectedTitle];
      const nextUser = { ...selectedUser, titles: nextTitles };
      setSelectedUser(nextUser);
      setUsers((current) => current.map((user) => (user.id === nextUser.id ? nextUser : user)));
      await onAssignmentChange({
        userId: nextUser.id,
        title: selectedTitle,
        assigned: !isRemoval,
      });
      setConfirmationOpen(false);
      setMessage(t(isRemoval ? 'admin_title_removed_from_player' : 'admin_title_assigned_to_player'));
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t("admin_ui_44f3ef7418"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Paper className="admin-section">
      <Box className="admin-section__title">
        <Box>
          <Typography variant="h6">{t("admin_ui_2beade6794")}</Typography>
          <Typography variant="body2" color="text.secondary">{t("admin_ui_e95191988f")}</Typography>
        </Box>
        <ToggleButtonGroup size="small" exclusive value={filter} onChange={(_event, value) => value && setFilter(value)} aria-label={t("admin_ui_f095343dc0")}>
          <ToggleButton value="all">{t("admin_ui_fd08da7a63")}</ToggleButton>
          <ToggleButton value="with">{t("admin_ui_72acf195af")}</ToggleButton>
          <ToggleButton value="without">{t("admin_ui_c9f7abcd46")}</ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {message && <Alert severity="success" onClose={() => setMessage('')} sx={{ mb: 2 }}>{message}</Alert>}
      {error && <Alert severity="error" onClose={() => setError('')} sx={{ mb: 2 }}>{error}</Alert>}

      <Box className="admin-title-assignment">
        <Stack spacing={1.5} minWidth={0}>
          <TextField
            size="small"
            label={t("admin_ui_68420bcf2f")}
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            InputProps={{ startAdornment: <Search fontSize="small" sx={{ mr: 1 }} /> }}
          />
          {loading ? (
            <Box className="admin-title-assignment__state"><CircularProgress size={28} /></Box>
          ) : users.length ? (
            <AdminTitleUserResults users={users} selectedUserId={selectedUser?.id} onSelect={selectUser} />
          ) : (
            <Box className="admin-title-assignment__state"><Typography color="text.secondary">{t("admin_ui_149dfe6221")}</Typography></Box>
          )}
        </Stack>

        <Stack spacing={1.5} minWidth={0}>
          {selectedUser ? (
            <>
              <Box className="admin-title-assignment__selected-user">
                <Typography variant="overline" color="text.secondary">{t("admin_ui_5a4af855f6")}</Typography>
                <Typography variant="h6">{selectedUser.username}</Typography>
                <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap mt={1}>
                  {(selectedUser.titles || []).map((title) => <Chip key={title.id} avatar={<Avatar src={title.image_url} />} label={title.name} />)}
                  {(selectedUser.titles || []).length === 0 && <Typography variant="body2" color="text.secondary">{t("admin_ui_960e5ddee7")}</Typography>}
                </Stack>
              </Box>
              <AdminTitleChoices titles={activeTitles} selectedTitleId={selectedTitleId} assignedTitleIds={assignedTitleIds} onSelect={setSelectedTitleId} />
              <Button
                variant="contained"
                color={isRemoval ? 'error' : 'primary'}
                startIcon={isRemoval ? <RemoveCircleOutline /> : <PersonAdd />}
                disabled={!selectedTitle || saving}
                onClick={() => setConfirmationOpen(true)}
              >
                {isRemoval ? t("admin_ui_584819370a") : t("admin_ui_347535888f")}
              </Button>
            </>
          ) : (
            <Box className="admin-title-assignment__state"><Typography color="text.secondary">{t("admin_ui_2642ea86a3")}</Typography></Box>
          )}
        </Stack>
      </Box>

      <Dialog open={confirmationOpen} onClose={() => !saving && setConfirmationOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>{isRemoval ? t("admin_ui_792c3da9fc") : t("admin_ui_533a1f5ad8")}</DialogTitle>
        <DialogContent>
          <Typography>
            {t("admin_ui_group_dfd3d91f04", null, { value0: isRemoval ? t("admin_ui_5fd12e7e35") : t("admin_ui_fe1285855f"), value1: selectedTitle?.name, value2: isRemoval ? t("admin_ui_68d80281ba") : t("admin_ui_63b7930d76"), value3: selectedUser?.username })}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmationOpen(false)} disabled={saving}>{t("admin_ui_0ec753be8d")}</Button>
          <Button variant="contained" color={isRemoval ? 'error' : 'primary'} onClick={confirmMutation} disabled={saving}>{t("admin_ui_0467ae4bb8")}</Button>
        </DialogActions>
      </Dialog>
    </Paper>
  );
};

export default AdminTitleAssignmentPanel;
