import React from 'react';
import { Link } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  InputAdornment,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { History, Map, Refresh, Save, Search, WorkspacePremium } from '@mui/icons-material';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import useCampaignRulesEditor from '../hooks/useCampaignRulesEditor';
import CampaignRuleCategorySection from './CampaignRuleCategorySection';
import CampaignRuleHistoryDialog from './CampaignRuleHistoryDialog';
import './AdminCampaignRulesPanel.css';

const AdminCampaignRulesPanel = ({ onOpenTerritories, relicEditorPath = '/clans' }) => {
  const { t } = useLocalizationContext();
  const editor = useCampaignRulesEditor(t);
  const {
    active, categories, changes, conflict, fieldErrors, history, historyLoading,
    historyOpen, loading, message, openHistory, originalValues, reason, restore,
    save, saving, search, setHistoryOpen, setReason, setSearch, values,
    changeValue, loadCurrent,
  } = editor;

  if (loading && !active) return <Box className="campaign-rules-loading"><CircularProgress /></Box>;

  return (
    <Stack spacing={2}>
      <Paper className="campaign-rules-toolbar">
        <Box>
          <Typography variant="h5">{t('admin_campaign_rules_title', 'Правила кампании')}</Typography>
          <Typography color="text.secondary">
            {t('admin_campaign_rules_subtitle', 'Числовой баланс применяется версиями только к новым операциям')}
          </Typography>
        </Box>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}>
          <Button startIcon={<Map />} onClick={onOpenTerritories}>
            {t('admin_campaign_rules_territories_link', 'Территории')}
          </Button>
          <Button component={Link} to={relicEditorPath} startIcon={<WorkspacePremium />}>
            {t('admin_campaign_rules_relics_link', 'Реликвии')}
          </Button>
          <Button startIcon={<History />} onClick={openHistory}>
            {t('admin_campaign_rules_history', 'История версий')}
          </Button>
        </Stack>
      </Paper>

      {message && <Alert severity={message.type}>{String(message.text)}</Alert>}
      {conflict && (
        <Alert severity="warning" action={<Button onClick={loadCurrent} startIcon={<Refresh />}>
          {t('admin_campaign_rules_reload', 'Загрузить актуальную')}
        </Button>}>
          {t('admin_campaign_rules_conflict', 'Правила уже изменены: активна версия {version}. Ввод сохранён до перезагрузки.', {
            version: conflict.active_version,
          })}
        </Alert>
      )}

      <Paper className="campaign-rules-editor">
        <Box className="campaign-rules-editor__controls">
          <Typography fontWeight={800}>
            {t('admin_campaign_rules_version', 'Активная версия: {version}', { version: active?.version })}
          </Typography>
          <TextField
            size="small"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder={t('admin_campaign_rules_search', 'Поиск по названию или ключу')}
            slotProps={{ input: { startAdornment: <InputAdornment position="start"><Search /></InputAdornment> } }}
          />
        </Box>
        {Object.entries(categories).map(([category, rules], index) => (
          <CampaignRuleCategorySection
            key={category}
            category={category}
            rules={rules}
            values={values}
            originalValues={originalValues}
            fieldErrors={fieldErrors}
            onChange={changeValue}
            t={t}
            defaultExpanded={index === 0 || Boolean(search)}
          />
        ))}
        {Object.keys(categories).length === 0 && (
          <Typography className="campaign-rules-empty" color="text.secondary">
            {t('admin_campaign_rules_empty', 'Подходящих правил нет')}
          </Typography>
        )}
      </Paper>

      <Paper className="campaign-rules-savebar">
        <TextField
          required
          multiline
          minRows={2}
          label={t('admin_campaign_rules_reason', 'Причина изменения')}
          value={reason}
          onChange={(event) => setReason(event.target.value)}
        />
        <Button
          variant="contained"
          startIcon={saving ? <CircularProgress size={18} /> : <Save />}
          disabled={saving || Object.keys(changes).length === 0 || reason.trim().length < 3}
          onClick={save}
        >
          {t('admin_campaign_rules_save', 'Активировать новую версию')} ({Object.keys(changes).length})
        </Button>
      </Paper>

      <CampaignRuleHistoryDialog
        open={historyOpen}
        items={history}
        currentVersion={active?.version}
        loading={historyLoading}
        saving={saving}
        error={message?.type === 'error' ? message.text : conflict ? t(
          'admin_campaign_rules_conflict',
          'Правила уже изменены: активна версия {version}. Ввод сохранён до перезагрузки.',
          { version: conflict.active_version },
        ) : null}
        onClose={() => setHistoryOpen(false)}
        onRestore={restore}
        t={t}
      />
    </Stack>
  );
};

export default AdminCampaignRulesPanel;
