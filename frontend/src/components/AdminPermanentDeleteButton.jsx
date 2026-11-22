import React, { useState } from 'react';
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, TextField } from '@mui/material';
import { DeleteForever } from '@mui/icons-material';
import api from '../services/api';
import { useLocalizationContext } from '../contexts/LocalizationContext';

export default function AdminPermanentDeleteButton({ kind, id, name, onDeleted, onMessage }) {
  const { getLocalizedText: t } = useLocalizationContext();
  const [open, setOpen] = useState(false);
  const [confirmation, setConfirmation] = useState('');
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const remove = async () => {
    setSaving(true);
    try {
      await api.delete(`/admin/${kind}/${id}`, { data: { confirmation_id: Number(confirmation), reason: reason.trim() } });
      setOpen(false);
      onMessage({ type: 'success', text: t('admin_purge_done') });
      await onDeleted();
    } catch (error) {
      onMessage({ type: 'error', text: error.response?.data?.detail || t('admin_dashboard_operation_error') });
    } finally {
      setSaving(false);
    }
  };
  return <>
    <Button size="small" color="error" startIcon={<DeleteForever />} onClick={() => { setConfirmation(''); setReason(''); setOpen(true); }}>{t('admin_purge_title')}</Button>
    <Dialog open={open} onClose={() => !saving && setOpen(false)} fullWidth maxWidth="sm">
      <DialogTitle>{t('admin_purge_title')}: {name || `#${id}`}</DialogTitle>
      <DialogContent>
        <Alert severity="warning">{t(kind === 'clans' ? 'admin_purge_clan_warning' : 'admin_purge_war_warning')}</Alert>
        <TextField fullWidth margin="normal" label={t('admin_purge_confirm', null, { id })} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={saving} />
        <TextField fullWidth margin="normal" label={t('admin_purge_reason')} value={reason} onChange={(event) => setReason(event.target.value)} disabled={saving} multiline minRows={2} />
      </DialogContent>
      <DialogActions>
        <Button disabled={saving} onClick={() => setOpen(false)}>{t('admin_ui_f6dab074d7')}</Button>
        <Button color="error" variant="contained" disabled={saving || confirmation.trim() !== String(id) || reason.trim().length < 3} onClick={remove}>{t('admin_purge_title')}</Button>
      </DialogActions>
    </Dialog>
  </>;
}
