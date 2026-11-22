import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Avatar,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import {
  AddPhotoAlternate,
  AdminPanelSettings,
  Edit,
  Link as LinkIcon,
  RemoveCircleOutline,
  WorkspacePremium,
} from '@mui/icons-material';

import api from '../services/api';
import { useAuth } from '../contexts/AuthContext';
import { usePlayerIdentity } from '../contexts/PlayerIdentityContext';
import PlayerIdentity from './PlayerIdentity';
import AdminTitleAssignmentPanel from './AdminTitleAssignmentPanel';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const emptyTitleForm = {
  id: null,
  name: '',
  description: '',
  name_en: '',
  description_en: '',
  name_de: '',
  description_de: '',
  is_active: true,
  image: null,
  image_url: '',
};

const PRIMARY_ADMIN_USERNAME = 'darcks';

const isPrimaryAdmin = (username) => (
  username?.trim().toLocaleLowerCase() === PRIMARY_ADMIN_USERNAME
);

const AdminUsersTitlesPanel = () => {
  const { getLocalizedText: t } = useLocalizationContext();
  const { user: currentUser } = useAuth();
  const { refreshDirectory } = usePlayerIdentity();
  const [users, setUsers] = useState([]);
  const [titles, setTitles] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);
  const [roleTarget, setRoleTarget] = useState(null);
  const [roleReason, setRoleReason] = useState('');
  const [identityTarget, setIdentityTarget] = useState(null);
  const [identityForm, setIdentityForm] = useState({ arena_nickname: '', reason: '' });
  const [titleDialogOpen, setTitleDialogOpen] = useState(false);
  const [titleForm, setTitleForm] = useState(emptyTitleForm);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [userResponse, titleResponse] = await Promise.all([
        api.get('/admin/users'),
        api.get('/admin/titles'),
      ]);
      setUsers(userResponse.data.users || []);
      setTitles(titleResponse.data.titles || []);
    } catch (error) {
      setMessage({ type: 'error', text: error.response?.data?.detail || t('admin_users_load_error') });
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const filteredUsers = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return query ? users.filter((item) => item.username.toLocaleLowerCase().includes(query)) : users;
  }, [search, users]);

  const completeMutation = async (text) => {
    await Promise.all([loadData(), refreshDirectory()]);
    setMessage({ type: 'success', text });
  };

  const saveRole = async () => {
    if (!roleTarget || roleReason.trim().length < 3) return;
    setSaving(true);
    try {
      await api.patch(`/admin/users/${roleTarget.id}/role`, {
        is_admin: !roleTarget.is_admin,
        reason: roleReason.trim(),
      });
      const action = t(roleTarget.is_admin ? 'admin_role_removed' : 'admin_role_granted');
      setRoleTarget(null);
      setRoleReason('');
      await completeMutation(`${action}: ${roleTarget.username}`);
    } catch (error) {
      setMessage({ type: 'error', text: error.response?.data?.detail || t('admin_role_change_error') });
    } finally {
      setSaving(false);
    }
  };

  const openIdentityDialog = (target) => {
    setIdentityTarget(target);
    setIdentityForm({
      arena_nickname: target.display_name !== target.username ? target.display_name : '',
      reason: '',
    });
  };

  const saveArenaIdentity = async () => {
    if (!identityTarget || !identityForm.arena_nickname.trim() || identityForm.reason.trim().length < 3) return;
    setSaving(true);
    try {
      const response = await api.patch(`/admin/users/${identityTarget.id}/arena-identity`, {
        arena_nickname: identityForm.arena_nickname.trim(),
        reason: identityForm.reason.trim(),
      });
      setIdentityTarget(null);
      setIdentityForm({ arena_nickname: '', reason: '' });
      await completeMutation(t('admin_arena_identity_saved', null, { name: response.data.display_name }));
    } catch (error) {
      setMessage({ type: 'error', text: error.response?.data?.detail || t('admin_arena_identity_error') });
    } finally {
      setSaving(false);
    }
  };

  const openNewTitle = () => {
    setTitleForm(emptyTitleForm);
    setTitleDialogOpen(true);
  };

  const openEditTitle = (title) => {
    setTitleForm({ ...emptyTitleForm, ...title });
    setTitleDialogOpen(true);
  };

  const saveTitle = async () => {
    if (titleForm.name.trim().length < 2 || titleForm.description.trim().length < 3) return;
    if (!titleForm.id && !titleForm.image) return;
    setSaving(true);
    const formData = new FormData();
    formData.append('name', titleForm.name.trim());
    formData.append('description', titleForm.description.trim());
    formData.append('name_en', titleForm.name_en.trim());
    formData.append('description_en', titleForm.description_en.trim());
    formData.append('name_de', titleForm.name_de.trim());
    formData.append('description_de', titleForm.description_de.trim());
    if (titleForm.id) formData.append('is_active', String(titleForm.is_active));
    if (titleForm.image) formData.append('image', titleForm.image);
    try {
      if (titleForm.id) await api.patch(`/admin/titles/${titleForm.id}`, formData);
      else await api.post('/admin/titles', formData);
      setTitleDialogOpen(false);
      await completeMutation(t(titleForm.id ? 'admin_title_updated' : 'admin_title_created'));
    } catch (error) {
      setMessage({ type: 'error', text: error.response?.data?.detail || t('admin_title_save_error') });
    } finally {
      setSaving(false);
    }
  };

  const handleAssignmentChange = async ({ userId, title, assigned }) => {
    setUsers((current) => current.map((item) => {
      if (item.id !== userId) return item;
      const nextTitles = assigned
        ? [...(item.titles || []).filter((candidate) => candidate.id !== title.id), title]
        : (item.titles || []).filter((candidate) => candidate.id !== title.id);
      return { ...item, titles: nextTitles };
    }));
    setTitles((current) => current.map((item) => (
      item.id === title.id
        ? { ...item, assigned_count: Math.max(0, (item.assigned_count || 0) + (assigned ? 1 : -1)) }
        : item
    )));
    await refreshDirectory();
  };

  return (
    <Stack spacing={2}>
      {message && <Alert severity={message.type} onClose={() => setMessage(null)}>{message.text}</Alert>}

      <Paper className="admin-section">
        <Box className="admin-section__title">
          <Box>
            <Typography variant="h6">{t("admin_ui_154285d73c")}</Typography>
            <Typography variant="body2" color="text.secondary">{t("admin_ui_cf85fbbafb")}</Typography>
          </Box>
          <TextField size="small" label={t("admin_ui_6c94b2e1f6")} value={search} onChange={(event) => setSearch(event.target.value)} />
        </Box>
        <TableContainer className="admin-users-table">
          <Table size="small" stickyHeader>
            <TableHead><TableRow><TableCell>{t("admin_ui_5b16fcdd97")}</TableCell><TableCell>{t("admin_ui_d6dd0fd72d")}</TableCell><TableCell>{t("admin_ui_81e4bb361c")}</TableCell><TableCell>{t("admin_ui_c18d0be34a")}</TableCell><TableCell align="right">{t("admin_ui_9978ac34b2")}</TableCell></TableRow></TableHead>
            <TableBody>
              {filteredUsers.map((item) => (
                <TableRow key={item.id} hover>
                  <TableCell><PlayerIdentity username={item.username} /></TableCell>
                  <TableCell>
                    <Typography fontWeight={700}>{item.display_name || item.username}</Typography>
                    {(item.display_name || item.username) === item.username && (
                      <Typography variant="caption" color="text.secondary">{t("admin_ui_0f1e35b039")}</Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                      {isPrimaryAdmin(item.username) && (
                        <Chip size="small" color="warning" icon={<AdminPanelSettings />} label={t("admin_ui_6ea66c27ed")} />
                      )}
                      <Chip size="small" color={item.is_claimed ? 'success' : 'default'} label={item.is_claimed ? t("admin_ui_7cd5ad2c6d") : t("admin_ui_ad80c0f5f8")} />
                      {!item.is_active && <Chip size="small" color="error" label={t("admin_ui_2c998bfca0")} />}
                      {item.is_admin && !isPrimaryAdmin(item.username) && <Chip size="small" color="warning" icon={<AdminPanelSettings />} label={t("admin_ui_36d00fd77c")} />}
                    </Stack>
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                      {(item.titles || []).map((title) => (
                        <Chip
                          key={title.id}
                          size="small"
                          avatar={<Avatar src={title.image_url} />}
                          label={title.name}
                        />
                      ))}
                      {(item.titles || []).length === 0 && <Typography variant="caption" color="text.secondary">{t("admin_ui_f82a821941")}</Typography>}
                    </Stack>
                  </TableCell>
                  <TableCell align="right">
                    <Stack direction="row" spacing={1} justifyContent="flex-end">
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<LinkIcon />}
                        disabled={!item.is_claimed || saving}
                        onClick={() => openIdentityDialog(item)}
                      >{t("admin_ui_ea61e998de")}</Button>
                      <Button
                        size="small"
                        color={item.is_admin ? 'error' : 'warning'}
                        variant="outlined"
                        startIcon={item.is_admin ? <RemoveCircleOutline /> : <AdminPanelSettings />}
                        disabled={!item.is_claimed || item.id === currentUser?.id || isPrimaryAdmin(item.username) || saving}
                        onClick={() => setRoleTarget(item)}
                      >
                        {isPrimaryAdmin(item.username)
                          ? t("admin_ui_d2ba88a731")
                          : (item.is_admin ? t("admin_ui_8140b7b094") : t("admin_ui_27f4bf2ea3"))}
                      </Button>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>

      <Paper className="admin-section">
          <Box className="admin-section__title">
            <Box><Typography variant="h6">{t("admin_ui_04b414ff29")}</Typography><Typography variant="body2" color="text.secondary">{t("admin_ui_c4145f9c3a")}</Typography></Box>
            <Button variant="contained" startIcon={<AddPhotoAlternate />} onClick={openNewTitle}>{t("admin_ui_6fb6ea88be")}</Button>
          </Box>
          <Box className="admin-title-grid">
            {titles.map((title) => (
              <Box key={title.id} className={`admin-title-card${title.is_active ? '' : ' is-disabled'}`}>
                <Avatar src={title.image_url} className="admin-title-card__image" />
                <Box minWidth={0} flex={1}>
                  <Typography fontWeight={800}>{title.name}</Typography>
                  <Typography variant="body2" color="text.secondary">{title.description}</Typography>
                  <Typography variant="caption" color="text.secondary">{t("admin_ui_group_84caa747df", null, { value0: title.assigned_count || 0 })}</Typography>
                </Box>
                <Button size="small" startIcon={<Edit />} onClick={() => openEditTitle(title)}>{t("admin_ui_9d809f884b")}</Button>
              </Box>
            ))}
            {!loading && titles.length === 0 && <Typography color="text.secondary">{t("admin_ui_f93a1b8a52")}</Typography>}
          </Box>
      </Paper>

      <AdminTitleAssignmentPanel titles={titles} onAssignmentChange={handleAssignmentChange} />

      <Dialog open={Boolean(roleTarget)} onClose={() => !saving && setRoleTarget(null)} fullWidth maxWidth="sm">
        <DialogTitle>{roleTarget?.is_admin ? t("admin_ui_a37f0f5539") : t("admin_ui_885f024dda")}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>{t("admin_ui_group_bd74a8ab33", null, { value0: roleTarget?.username })}</Alert>
          <TextField autoFocus required fullWidth multiline minRows={2} label={t("admin_ui_4a9ea52cda")} value={roleReason} onChange={(event) => setRoleReason(event.target.value)} />
        </DialogContent>
        <DialogActions><Button onClick={() => setRoleTarget(null)}>{t("admin_ui_0ec753be8d")}</Button><Button variant="contained" color={roleTarget?.is_admin ? 'error' : 'warning'} disabled={saving || roleReason.trim().length < 3} onClick={saveRole}>{t("admin_ui_0467ae4bb8")}</Button></DialogActions>
      </Dialog>

      <Dialog open={Boolean(identityTarget)} onClose={() => !saving && setIdentityTarget(null)} fullWidth maxWidth="sm">
        <DialogTitle>{t("admin_ui_42e71a62d2")}</DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>{t("admin_ui_e2d97c93ec")}<strong>{identityTarget?.username}</strong>{t("admin_ui_6309bec996")}</Alert>
          <Stack spacing={2}>
            <TextField
              autoFocus
              required
              fullWidth
              label={t("admin_ui_8bab11cc8f")}
              value={identityForm.arena_nickname}
              inputProps={{ maxLength: 120 }}
              onChange={(event) => setIdentityForm((current) => ({ ...current, arena_nickname: event.target.value }))}
            />
            <TextField
              required
              fullWidth
              multiline
              minRows={2}
              label={t("admin_ui_8deb8920a7")}
              value={identityForm.reason}
              inputProps={{ maxLength: 500 }}
              onChange={(event) => setIdentityForm((current) => ({ ...current, reason: event.target.value }))}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setIdentityTarget(null)}>{t("admin_ui_0ec753be8d")}</Button>
          <Button
            variant="contained"
            startIcon={<LinkIcon />}
            disabled={saving || !identityForm.arena_nickname.trim() || identityForm.reason.trim().length < 3}
            onClick={saveArenaIdentity}
          >{t("admin_ui_a65cbdc4d1")}</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={titleDialogOpen} onClose={() => !saving && setTitleDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{titleForm.id ? t("admin_ui_98de8fdb58") : t("admin_ui_3c7f27b1e4")}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} mt={1}>
            <TextField required label={t("admin_ui_3de49828e8")} value={titleForm.name} inputProps={{ maxLength: 120 }} onChange={(event) => setTitleForm((current) => ({ ...current, name: event.target.value }))} />
            <TextField required multiline minRows={3} label={t("admin_ui_87aa1e3743")} helperText={t('admin_title_description_help')} value={titleForm.description} inputProps={{ maxLength: 1000 }} onChange={(event) => setTitleForm((current) => ({ ...current, description: event.target.value }))} />
            <TextField label={t("admin_ui_c27c1ea33a")} value={titleForm.name_en || ''} inputProps={{ maxLength: 120 }} onChange={(event) => setTitleForm((current) => ({ ...current, name_en: event.target.value }))} />
            <TextField multiline minRows={2} label={t("admin_ui_6ba8e9ea98")} value={titleForm.description_en || ''} inputProps={{ maxLength: 1000 }} onChange={(event) => setTitleForm((current) => ({ ...current, description_en: event.target.value }))} />
            <TextField label={t("admin_ui_7d3ee65ae3")} value={titleForm.name_de || ''} inputProps={{ maxLength: 120 }} onChange={(event) => setTitleForm((current) => ({ ...current, name_de: event.target.value }))} />
            <TextField multiline minRows={2} label={t("admin_ui_d5acdd0ff4")} value={titleForm.description_de || ''} inputProps={{ maxLength: 1000 }} onChange={(event) => setTitleForm((current) => ({ ...current, description_de: event.target.value }))} />
            <Button component="label" variant="outlined" startIcon={<AddPhotoAlternate />}>
              {titleForm.image ? titleForm.image.name : titleForm.image_url ? t("admin_ui_9d7c710ea6") : t("admin_ui_00a1df080f")}
              <input hidden type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={(event) => setTitleForm((current) => ({ ...current, image: event.target.files?.[0] || null }))} />
            </Button>
            {titleForm.id && <FormControlLabel control={<Switch checked={titleForm.is_active} onChange={(event) => setTitleForm((current) => ({ ...current, is_active: event.target.checked }))} />} label={t("admin_ui_08e3469188")} />}
          </Stack>
        </DialogContent>
        <DialogActions><Button onClick={() => setTitleDialogOpen(false)}>{t("admin_ui_0ec753be8d")}</Button><Button variant="contained" startIcon={<WorkspacePremium />} disabled={saving || titleForm.name.trim().length < 2 || titleForm.description.trim().length < 3 || (!titleForm.id && !titleForm.image)} onClick={saveTitle}>{t("admin_ui_4864057d62")}</Button></DialogActions>
      </Dialog>
    </Stack>
  );
};

export default AdminUsersTitlesPanel;
