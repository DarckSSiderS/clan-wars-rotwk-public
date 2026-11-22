import React, { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { Restore } from '@mui/icons-material';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { formatMoscowDateTime } from '../utils/dateTime';

const CampaignRuleHistoryDialog = ({
  open,
  items,
  currentVersion,
  loading,
  saving,
  error,
  onClose,
  onRestore,
  t,
}) => {
  const { language } = useLocalizationContext();
  const [selectedVersion, setSelectedVersion] = useState(null);
  const [reason, setReason] = useState('');

  const close = () => {
    if (saving) return;
    setSelectedVersion(null);
    setReason('');
    onClose();
  };

  const restore = async () => {
    const restored = await onRestore(selectedVersion, reason.trim());
    if (restored) close();
  };

  return (
    <Dialog open={open} onClose={close} fullWidth maxWidth="md">
      <DialogTitle>{t('admin_campaign_rules_history', 'История версий')}</DialogTitle>
      <DialogContent dividers>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{String(error)}</Alert>}
        {selectedVersion ? (
          <Stack spacing={2}>
            <Alert severity="warning">
              {t('admin_campaign_rules_restore_confirm', 'Создать новую версию на основе версии {version}?', {
                version: selectedVersion,
              })}
            </Alert>
            <TextField
              autoFocus
              required
              multiline
              minRows={3}
              label={t('admin_campaign_rules_reason', 'Причина изменения')}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </Stack>
        ) : loading ? (
          <Box className="campaign-rules-history__loading"><CircularProgress /></Box>
        ) : items.length === 0 ? (
          <Typography color="text.secondary">
            {t('admin_campaign_rules_history_empty', 'История пока пуста')}
          </Typography>
        ) : (
          <Stack divider={<Divider flexItem />}>
            {items.map((item) => (
              <Box className="campaign-rules-history__row" key={item.id}>
                <Box minWidth={0}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Typography fontWeight={800}>v{item.version}</Typography>
                    {item.version === currentVersion && (
                      <Chip
                        size="small"
                        color="success"
                        label={t('admin_campaign_rules_active', 'Активна')}
                      />
                    )}
                  </Stack>
                  <Typography variant="body2">{item.reason}</Typography>
                  <Typography variant="caption" color="text.secondary">
                    {formatMoscowDateTime(item.created_at, '', language)}
                  </Typography>
                </Box>
                <Button
                  startIcon={<Restore />}
                  disabled={item.version === currentVersion}
                  onClick={() => setSelectedVersion(item.version)}
                >
                  {t('admin_campaign_rules_restore', 'Восстановить')}
                </Button>
              </Box>
            ))}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        {selectedVersion && (
          <Button onClick={() => setSelectedVersion(null)} disabled={saving}>
            {t('admin_campaign_rules_back', 'Назад')}
          </Button>
        )}
        <Button onClick={close} disabled={saving}>
          {t('common_close', 'Закрыть')}
        </Button>
        {selectedVersion && (
          <Button
            variant="contained"
            color="warning"
            startIcon={saving ? <CircularProgress size={18} /> : <Restore />}
            disabled={saving || reason.trim().length < 3}
            onClick={restore}
          >
            {t('admin_campaign_rules_restore', 'Восстановить')}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
};

export default CampaignRuleHistoryDialog;
