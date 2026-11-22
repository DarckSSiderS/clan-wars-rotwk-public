import React, { useState } from 'react';
import { Alert, Button, Stack, TextField } from '@mui/material';
import { CheckCircleOutline, HighlightOff, RestartAlt } from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import api from '../services/api';

export default function WarMatchReview({ war, result, onReviewed }) {
  const { user } = useAuth();
  const { getLocalizedText: t } = useLocalizationContext();
  const [mode, setMode] = useState(null);
  const [reason, setReason] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const admin = user?.role?.name === 'admin';
  const overridden = result.admin_override != null;
  const submit = async (event) => {
    event.preventDefault();
    if (saving || reason.trim().length < 3) return;
    setSaving(true);
    setError('');
    try {
      const response = await api.patch(`/admin/wars/${war.id}/matches/${result.id}`, { mode, reason: reason.trim() });
      onReviewed(response.data);
      setMode(null);
      setReason('');
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : t('battle_review_error'));
    } finally {
      setSaving(false);
    }
  };
  return <Stack spacing={1.5} sx={{ mb: 2 }}>
    {result.rating_warning && <Alert severity="warning">{t('match_rating_warning')}</Alert>}
    <Alert severity={result.is_counted ? 'success' : 'warning'}>
      {result.is_counted ? t('battle_review_counted') : t('war_rejected_reason', null, {
        reason: result.rejection_reason || result.admin_override_reason || t('war_failed_check'),
      })}
    </Alert>
    {overridden && result.admin_override_reason && <Alert severity="info">{t('battle_review_admin_reason', null, { reason: result.admin_override_reason })}</Alert>}
    {admin && <>
      {war.status !== 'active' && <Alert severity="info">{t('admin_war_finished_review')}</Alert>}
      <Stack direction="row" gap={1} flexWrap="wrap">
        <Button startIcon={<CheckCircleOutline />} disabled={saving || result.admin_override === true} onClick={() => { setMode('count'); setError(''); }}>{t('battle_review_count')}</Button>
        <Button startIcon={<HighlightOff />} color="error" disabled={saving || result.admin_override === false} onClick={() => { setMode('exclude'); setError(''); }}>{t('battle_review_exclude')}</Button>
        {overridden && <Button startIcon={<RestartAlt />} disabled={saving} onClick={() => { setMode('automatic'); setError(''); }}>{t('battle_review_automatic')}</Button>}
      </Stack>
      {mode && <Stack component="form" onSubmit={submit} spacing={1.5}>
        <TextField label={t('battle_review_reason')} value={reason} onChange={(event) => setReason(event.target.value)} required multiline minRows={2} fullWidth disabled={saving} slotProps={{ htmlInput: { minLength: 3, maxLength: 500 } }} />
        {error && <Alert severity="error">{error}</Alert>}
        <Stack direction="row" gap={1} flexWrap="wrap">
          <Button type="submit" variant="contained" disabled={saving || reason.trim().length < 3}>{t(mode === 'count' ? 'battle_review_count' : mode === 'exclude' ? 'battle_review_exclude' : 'battle_review_automatic')}</Button>
          <Button disabled={saving} onClick={() => { setMode(null); setError(''); }}>{t('battle_review_cancel')}</Button>
        </Stack>
      </Stack>}
    </>}
  </Stack>;
}
