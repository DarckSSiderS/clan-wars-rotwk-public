import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  Alert, Badge, Box, Button, Checkbox, Chip, CircularProgress, Container, Dialog,
  DialogActions, DialogContent, DialogTitle, FormControlLabel, IconButton, MenuItem,
  Paper, Stack, Switch, Tab, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Tabs, TextField, Tooltip, Typography, useMediaQuery,
} from '@mui/material';
import {
  AdminPanelSettings, ArrowBack, Castle, Edit, EmojiEvents, Gavel, Groups, History, Map,
  BugReportOutlined, MilitaryTech, People, Refresh, RocketLaunch, ScienceOutlined, StopCircle, Storefront, Sync, Tune, WorkspacePremium,
} from '@mui/icons-material';
import api from '../services/api';
import AdminWarsPanel from '../components/AdminWarsPanel';
import AdminPermanentDeleteButton from '../components/AdminPermanentDeleteButton';
import AdminTerritoriesPanel from '../components/AdminTerritoriesPanel';
import AdminUsersTitlesPanel from '../components/AdminUsersTitlesPanel';
import AdminCampaignRulesPanel from '../components/AdminCampaignRulesPanel';
import AdminContentCatalogPanel from '../components/AdminContentCatalogPanel';
import AdminFeedbackPanel from '../components/AdminFeedbackPanel';
import AdminBalanceSimulatorPanel from '../components/AdminBalanceSimulatorPanel';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { formatMoscowDateTime } from '../utils/dateTime';
import { isAdminPreview } from '../utils/appBasePath';
import { treasuryDraft, treasuryCommand, readAdminCommand, rememberAdminCommand, forgetAdminCommand, recoveryCommand, canRecoverPreparation } from '../utils/adminCycleCommands';
import './AdminDashboardPage.css';

const RESOURCES = {
  gold: 'resource_gold', iron: 'resource_iron', wood: 'resource_wood',
  food: 'resource_food', mithril: 'resource_mithril', influence: 'common_influence',
};

const cycleMessages = {
  admin_cycle_diagnostics_error: ['Не удалось загрузить диагностику цикла.', 'Could not load cycle diagnostics.', 'Zyklusdiagnose konnte nicht geladen werden.'],
  admin_cycle_treasury_load_error: ['Не удалось подтвердить режим и загрузить актуальную казну.', 'Could not confirm the mode and load the current treasury.', 'Modus und aktuelle Kasse konnten nicht geladen werden.'],
  admin_cycle_treasury_conflict: ['Корректировка отклонена. Загрузите казну заново перед новой попыткой.', 'Correction rejected. Reload the treasury before trying again.', 'Korrektur abgelehnt. Lade die Kasse vor einem neuen Versuch neu.'],
  admin_cycle_command_uncertain: ['Результат запроса не подтверждён. Повторите исходную команду; её ключ сохранён.', 'The result is unconfirmed. Retry the original command; its key is saved.', 'Ergebnis unbestätigt. Wiederhole den ursprünglichen Befehl mit dem gespeicherten Schlüssel.'],
  admin_cycle_storage_error: ['Не удалось сохранить ключ команды. Запрос не отправлен.', 'Could not save the command key. No request was sent.', 'Befehlsschlüssel konnte nicht gespeichert werden. Keine Anfrage gesendet.'],
  admin_cycle_recovery_saved: ['Возобновлено полное окно подготовки: 24 часа.', 'A full 24-hour preparation window has resumed.', 'Ein vollständiges Vorbereitungsfenster von 24 Stunden wurde gestartet.'],
  admin_cycle_recovery_conflict: ['Восстановление отклонено. Обновите диагностику перед повторной проверкой.', 'Recovery rejected. Refresh diagnostics before trying again.', 'Wiederherstellung abgelehnt. Aktualisiere zuerst die Diagnose.'],
  admin_cycle_diagnostics: ['Цикл и импорт Арены', 'Cycle and Arena import', 'Zyklus und Arena-Import'],
  admin_cycle_refresh: ['Обновить диагностику', 'Refresh diagnostics', 'Diagnose aktualisieren'],
  admin_cycle_current: ['Текущий цикл', 'Current cycle', 'Aktueller Zyklus'],
  admin_cycle_mode: ['Режим', 'Mode', 'Modus'],
  admin_cycle_season: ['Сезон', 'Season', 'Saison'],
  admin_cycle_number: ['Цикл / ревизия', 'Cycle / revision', 'Zyklus / Revision'],
  admin_cycle_phase: ['Фаза', 'Phase', 'Phase'],
  admin_cycle_preparation_at: ['Начало подготовки', 'Preparation starts', 'Vorbereitungsbeginn'],
  admin_cycle_battle_at: ['Начало битвы', 'Battle starts', 'Schlachtbeginn'],
  admin_cycle_battle_ends: ['Конец битвы', 'Battle ends', 'Schlachtende'],
  admin_cycle_replay_deadline: ['Приём реплеев до', 'Replay deadline', 'Replay-Frist'],
  admin_cycle_settled: ['Расчёт завершён', 'Settlement completed', 'Abrechnung abgeschlossen'],
  admin_cycle_import_verified: ['Импорт цикла проверен', 'Cycle import verified', 'Zyklusimport geprüft'],
  admin_cycle_complete_scan: ['Последний полный обход', 'Last complete scan', 'Letzter vollständiger Scan'],
  admin_cycle_no_complete_scan: ['Полный обход не подтверждён.', 'No complete scan confirmed.', 'Kein vollständiger Scan bestätigt.'],
  admin_cycle_scan_completed: ['Завершён', 'Completed', 'Abgeschlossen'],
  admin_cycle_scan_from: ['Покрытие с', 'Coverage from', 'Abdeckung ab'],
  admin_cycle_scan_until: ['Покрытие до', 'Coverage until', 'Abdeckung bis'],
  admin_cycle_replays_count: ['Реплеев в обходе', 'Replays in scan', 'Replays im Scan'],
  admin_cycle_worker_heartbeat: ['Последний сигнал фонового процесса', 'Worker heartbeat', 'Worker-Heartbeat'],
  admin_cycle_worker_success: ['Последняя успешная проверка', 'Last successful worker run', 'Letzter erfolgreicher Worker-Durchlauf'],
  admin_cycle_worker_failures: ['Последовательные сбои', 'Worker failures', 'Worker-Fehler'],
  admin_cycle_server_time: ['Время сервера', 'Server time', 'Serverzeit'],
  admin_cycle_pending: ['Ожидают обработки', 'Awaiting processing', 'Warten auf Verarbeitung'],
  admin_cycle_pending_replays: ['Исходные реплеи', 'Source replays', 'Quell-Replays'],
  admin_cycle_pending_interceptions: ['Перехваты', 'Interceptions', 'Abfangaktionen'],
  admin_cycle_pending_contributions: ['Ожидающие личные вклады по причинам', 'Pending personal contributions by reason', 'Ausstehende persönliche Beiträge nach Grund'],
  admin_cycle_count: ['Всего', 'Count', 'Anzahl'],
  admin_cycle_no_pending: ['Ожидающих вкладов нет', 'No pending contributions', 'Keine ausstehenden Beiträge'],
  admin_cycle_recovery_warning: ['Снимок подготовки пропущен. Восстановление возобновит полные 24 часа подготовки перед раскрытием битвы. Сезон не останавливается.', 'The preparation snapshot is missing. Recovery opens a full 24-hour preparation window before battle reveal. The season continues.', 'Der Vorbereitungsschnappschuss fehlt. Die Wiederherstellung öffnet volle 24 Stunden Vorbereitung vor der Schlachtaufdeckung. Die Saison läuft weiter.'],
  admin_cycle_pending_command: ['Сохранён неподтверждённый запрос. Повтор будет отправлен с тем же ключом и исходными данными.', 'An unconfirmed request is saved. Retry uses its original key and payload.', 'Eine unbestätigte Anfrage ist gespeichert. Der erneute Versuch verwendet denselben Schlüssel und dieselben Daten.'],
  admin_cycle_recovery_reason: ['Причина восстановления', 'Recovery reason', 'Grund der Wiederherstellung'],
  admin_cycle_recovery_confirm: ['Подтверждаю возобновление полных 24 часов подготовки', 'I confirm a full 24-hour preparation window', 'Ich bestätige volle 24 Stunden Vorbereitung'],
  admin_cycle_retry: ['Повторить исходную команду', 'Retry original command', 'Ursprünglichen Befehl wiederholen'],
  admin_cycle_recover: ['Возобновить подготовку на 24 часа', 'Resume preparation for 24 hours', 'Vorbereitung für 24 Stunden fortsetzen'],
  admin_cycle_audit_action: ['Сезонная казна скорректирована', 'Seasonal treasury corrected', 'Saisonkasse korrigiert'],
  admin_cycle_audit_balances: ['Казна до и после', 'Treasury before and after', 'Kasse vorher und nachher'],
  admin_cycle_audit_scope: ['Сезон {season}, клан {clan}', 'Season {season}, clan {clan}', 'Saison {season}, Clan {clan}'],
  admin_cycle_treasury_mode: ['Сезонная казна', 'Seasonal treasury', 'Saisonkasse'],
  admin_cycle_treasury_revision: ['Сезон {season}, ревизия {revision}', 'Season {season}, revision {revision}', 'Saison {season}, Revision {revision}'],
  admin_cycle_reload_treasury: ['Загрузить актуальную казну', 'Reload current treasury', 'Aktuelle Kasse neu laden'],
  admin_cycle_personal_contributions: ['Личные вклады', 'Personal contributions', 'Persönliche Beiträge'],
  admin_cycle_registration: ['Регистрация', 'Registration', 'Registrierung'],
  admin_cycle_preparation: ['Подготовка', 'Preparation', 'Vorbereitung'],
  admin_cycle_battle: ['Битва', 'Battle', 'Schlacht'],
  admin_cycle_replay_loading: ['Загрузка реплеев', 'Replay loading', 'Replay-Import'],
  admin_cycle_settlement: ['Подведение итогов', 'Settlement', 'Abrechnung'],
  admin_cycle_rest: ['Отдых', 'Rest', 'Ruhephase'],
  admin_cycle_complete: ['Завершён', 'Completed', 'Abgeschlossen'],
  admin_cycle_season_ended: ['Сезон завершён', 'Season ended', 'Saison beendet'],
  admin_cycle_scheduled: ['Запланирован', 'Scheduled', 'Geplant'],
  admin_cycle_reason_missing_historical_elo: ['Нет Elo на момент матча', 'Historical Elo missing', 'Historisches Elo fehlt'],
  admin_cycle_reason_missing_match_times: ['Не подтверждено время матча', 'Match time unconfirmed', 'Spielzeit unbestätigt'],
  admin_cycle_reason_unknown_result: ['Не подтверждён результат', 'Result unconfirmed', 'Ergebnis unbestätigt'],
  admin_cycle_reason_interception_pending: ['Ожидается расчёт перехвата', 'Interception settlement pending', 'Abfangabrechnung ausstehend'],
  admin_cycle_reason_other: ['Требуется проверка', 'Review required', 'Prüfung erforderlich'],
};

const ACTIONS = {
  user_admin_role_updated: 'admin_action_user_admin_role_updated',
  title_created: 'admin_action_title_created',
  title_updated: 'admin_action_title_updated',
  title_assigned: 'admin_action_title_assigned',
  title_removed: 'admin_action_title_removed',
  admin_adjustment: 'admin_action_adjustment',
  clan_economy_updated: 'admin_action_clan_economy_updated',
  season_started: 'admin_action_season_started',
  season_completed: 'admin_action_season_completed',
  war_recalculated: 'admin_action_war_recalculated',
  war_match_reviewed: 'admin_action_war_match_reviewed',
  war_extended: 'admin_action_war_extended',
  war_finished_manually: 'admin_action_war_finished',
  war_canceled: 'admin_action_war_canceled',
  territory_parameters_updated: 'admin_action_territory_updated',
  territory_influence_admin_update: 'admin_action_territory_influence_updated',
  territory_influence_gained: 'admin_action_territory_influence_gained',
  territory_influence_lost: 'admin_action_territory_influence_lost',
};

const Metric = ({ icon, label, value, note }) => (
  <Box className="admin-metric">
    <Box className="admin-metric__icon">{icon}</Box>
    <Box minWidth={0}>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="h5">{value ?? 0}</Typography>
      {note && <Typography variant="caption" color="text.secondary">{note}</Typography>}
    </Box>
  </Box>
);

const AdminDashboardPage = () => {
  const { t, language } = useLocalizationContext();
  const cycleText = useCallback((key, params = {}) => (
    (cycleMessages[key]?.[language === 'en' ? 1 : language === 'de' ? 2 : 0] || key)
      .replace(/\{(\w+)\}/g, (match, name) => String(params[name] ?? match))
  ), [language]);
  const { user } = useAuth();
  const compactNavigation = useMediaQuery('(max-width:900px)');
  const [searchParams, setSearchParams] = useSearchParams();
  const initialSection = searchParams.get('section');
  const [tab, setTab] = useState(initialSection === 'feedback' ? 11 : initialSection === 'balance' ? 12 : 0);
  const [overview, setOverview] = useState(null);
  const [activeAdminWars, setActiveAdminWars] = useState([]);
  const [clans, setClans] = useState([]);
  const [seasons, setSeasons] = useState([]);
  const [ledger, setLedger] = useState([]);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(null);
  const [editingClan, setEditingClan] = useState(null);
  const [economy, setEconomy] = useState({});
  const [economyContext, setEconomyContext] = useState(null);
  const [economyLoading, setEconomyLoading] = useState(false);
  const [economyError, setEconomyError] = useState('');
  const [economyPending, setEconomyPending] = useState(null);
  const economyRequest = useRef(0);
  const [diagnostics, setDiagnostics] = useState(null);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);
  const [diagnosticsError, setDiagnosticsError] = useState('');
  const [recoveryReason, setRecoveryReason] = useState('');
  const [recoveryConfirmed, setRecoveryConfirmed] = useState(false);
  const [recoveryPending, setRecoveryPending] = useState(null);
  const [recoverySaving, setRecoverySaving] = useState(false);
  const [recoveryError, setRecoveryError] = useState('');
  const [seasonAction, setSeasonAction] = useState(null);
  const [seasonForm, setSeasonForm] = useState({ name: '' });
  const [seasonPending, setSeasonPending] = useState(null);
  useEffect(() => {
    try {
      const pending = readAdminCommand(localStorage, `season-start:${user.id}`);
      setSeasonPending(pending);
      if (pending) setSeasonForm({ name: pending.name });
    } catch { setMessage({ type: 'error', text: t('admin_cycle_start_pending') }); }
  }, [user.id, t]);
  useEffect(() => {
    if (!seasonPending || !seasons.some(season => Number(season.id) > Number(seasonPending.previous_season_id))) return;
    try {
      forgetAdminCommand(localStorage, `season-start:${user.id}`);
      setSeasonPending(null);
    } catch { setMessage({ type: 'error', text: t('admin_cycle_start_pending') }); }
  }, [seasonPending, seasons, user.id, t]);
  const [ledgerClan, setLedgerClan] = useState('');
  const [ledgerResource, setLedgerResource] = useState('');
  const [saving, setSaving] = useState(false);
  const [feedbackSummary, setFeedbackSummary] = useState({ unread: 0 });

  const loadDiagnostics = useCallback(async () => {
    setDiagnosticsLoading(true);
    setDiagnosticsError('');
    try {
      const { data } = await api.get('/campaign/cycles/admin/diagnostics');
      setDiagnostics(data);
      const pending = data.cycle && readAdminCommand(localStorage, `recovery:${user.id}:${data.cycle.id}`);
      setRecoveryPending(pending || null);
      if (pending) setRecoveryReason(pending.reason);
    } catch {
      setDiagnosticsError(cycleText('admin_cycle_diagnostics_error'));
    } finally { setDiagnosticsLoading(false); }
  }, [cycleText, user.id]);

  const loadCore = useCallback(async () => {
    const [summary, clanList, seasonList, warList, feedbackList] = await Promise.all([
      api.get('/admin/overview'),
      api.get('/admin/clans'),
      api.get('/campaign/seasons'),
      api.get('/wars/active/'),
      api.get('/admin/feedback/tickets', { params: { limit: 1 } }),
    ]);
    setOverview(summary.data);
    setClans(clanList.data.clans || []);
    setSeasons(seasonList.data.seasons || []);
    setActiveAdminWars(warList.data || []);
    setFeedbackSummary(feedbackList.data.summary || { unread: 0 });
  }, []);

  const loadLogs = useCallback(async () => {
    const params = { limit: 200 };
    if (ledgerClan) params.clan_id = ledgerClan;
    if (ledgerResource) params.resource = ledgerResource;
    const [ledgerResponse, auditResponse] = await Promise.all([
      api.get('/admin/ledger', { params }), api.get('/admin/audit', { params: { limit: 200 } }),
    ]);
    setLedger(ledgerResponse.data.entries || []);
    setAudit(auditResponse.data.entries || []);
  }, [ledgerClan, ledgerResource]);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([loadCore(), loadLogs(), loadDiagnostics()]);
    } catch (error) {
      setMessage({ type: 'error', text: error.response?.data?.detail || t('admin_dashboard_load_error') });
    } finally {
      setLoading(false);
    }
  }, [loadCore, loadLogs, loadDiagnostics, t]);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    const section = searchParams.get('section');
    if (section === 'feedback') setTab(11);
    if (section === 'balance') setTab(12);
  }, [searchParams]);

  const changeTab = (_event, value) => {
    setTab(value);
    if (value === 11) setSearchParams({ section: 'feedback' });
    else if (value === 12) setSearchParams({ section: 'balance' });
    else setSearchParams({});
  };

  const activeSeason = useMemo(() => seasons.find((item) => item.status === 'active'), [seasons]);
  const economyValid = useMemo(() => {
    if (!economyContext) return false;
    if (economyContext.mechanics_version === 'legacy') return (economy.reason || '').trim().length >= 3;
    try { treasuryCommand(economyContext, economy); return true; } catch { return false; }
  }, [economyContext, economy]);

  const openEconomy = async (clan) => {
    const request = ++economyRequest.current;
    setEditingClan(clan);
    setEconomyContext(null);
    setEconomy({});
    setEconomyPending(null);
    setEconomyError('');
    setEconomyLoading(true);
    try {
      const { data } = await api.get(`/admin/clans/${clan.id}/cycle-economy`);
      const draft = treasuryDraft(data, clan);
      const pending = data.mechanics_version === 'cycle_v1'
        ? readAdminCommand(localStorage, `treasury:${user.id}:${data.season_id}:${clan.id}`) : null;
      if (request !== economyRequest.current) return;
      setEconomyContext(data);
      setEconomyPending(pending);
      setEconomy(pending ? { ...pending.wallet, reason: pending.reason } : draft);
    } catch {
      if (request === economyRequest.current) setEconomyError(cycleText('admin_cycle_treasury_load_error'));
    } finally { if (request === economyRequest.current) setEconomyLoading(false); }
  };

  const closeEconomy = () => {
    if (saving) return;
    economyRequest.current += 1;
    setEditingClan(null);
  };

  const saveEconomy = async () => {
    if (!economyContext || economyError || economyLoading) return;
    setSaving(true);
    let scope;
    let requestStarted = false;
    try {
      if (economyContext.mechanics_version === 'cycle_v1') {
        scope = `treasury:${user.id}:${economyContext.season_id}:${editingClan.id}`;
        const payload = economyPending || rememberAdminCommand(localStorage, scope, treasuryCommand(economyContext, economy));
        setEconomyPending(payload);
        requestStarted = true;
        await api.patch(`/admin/clans/${editingClan.id}/cycle-economy`, payload);
        forgetAdminCommand(localStorage, scope);
        setEconomyPending(null);
      } else if (economyContext.mechanics_version === 'legacy') {
        requestStarted = true;
        await api.patch(`/admin/clans/${editingClan.id}/economy`, economy);
      } else return;
      setMessage({ type: 'success', text: t('admin_dashboard_economy_saved', null, { clan: editingClan.name }) });
      setEditingClan(null);
      await Promise.all([loadCore(), loadLogs()]);
    } catch (error) {
      if (scope && [400, 403, 404, 409, 422].includes(error.response?.status)) {
        forgetAdminCommand(localStorage, scope);
        setEconomyPending(null);
        setEconomyError(cycleText('admin_cycle_treasury_conflict'));
      } else {
        setMessage({ type: 'error', text: cycleText(requestStarted ? 'admin_cycle_command_uncertain' : 'admin_cycle_storage_error') });
      }
    } finally { setSaving(false); }
  };

  const recoverPreparation = async () => {
    const cycle = diagnostics?.cycle;
    if (!canRecoverPreparation(cycle, recoveryPending) || !recoveryConfirmed || diagnosticsError || diagnosticsLoading) return;
    setRecoverySaving(true);
    setRecoveryError('');
    const scope = `recovery:${user.id}:${cycle.id}`;
    let requestStarted = false;
    try {
      const payload = recoveryPending || rememberAdminCommand(localStorage, scope, recoveryCommand(cycle, recoveryReason, recoveryConfirmed));
      setRecoveryPending(payload);
      requestStarted = true;
      await api.post(`/campaign/cycles/admin/cycles/${cycle.id}/recover-preparation`, payload);
      forgetAdminCommand(localStorage, scope);
      setRecoveryPending(null);
      setRecoveryConfirmed(false);
      setRecoveryReason('');
      setMessage({ type: 'success', text: cycleText('admin_cycle_recovery_saved') });
      await loadDiagnostics();
    } catch (error) {
      if ([400, 403, 404, 409, 422].includes(error.response?.status)) {
        forgetAdminCommand(localStorage, scope);
        setRecoveryPending(null);
        setRecoveryConfirmed(false);
        setRecoveryError(cycleText('admin_cycle_recovery_conflict'));
        await loadDiagnostics();
      } else {
        setRecoveryError(cycleText(requestStarted ? 'admin_cycle_command_uncertain' : 'admin_cycle_storage_error'));
      }
    } finally { setRecoverySaving(false); }
  };

  const runSeasonAction = async () => {
    setSaving(true);
    const starting = seasonAction === 'start';
    const scope = `season-start:${user.id}`;
    try {
      if (starting) {
        const command = seasonPending || rememberAdminCommand(localStorage, scope, {
          name: seasonForm.name.trim(), previous_season_id: seasons[0]?.id || 0,
        });
        setSeasonPending(command);
        await api.post('/campaign/seasons/start', command);
        forgetAdminCommand(localStorage, scope);
        setSeasonPending(null);
      }
      else await api.post('/campaign/seasons/current/complete');
      setMessage({ type: 'success', text: t(seasonAction === 'start' ? 'admin_dashboard_campaign_started' : 'admin_dashboard_campaign_completed') });
      setSeasonAction(null);
      await Promise.all([loadCore(), loadLogs()]);
    } catch (error) {
      if (starting && [400, 403, 404, 409, 422].includes(error.response?.status)) {
        forgetAdminCommand(localStorage, scope);
        setSeasonPending(null);
      }
      setMessage({ type: 'error', text: error.response?.data?.detail || t(starting ? 'admin_cycle_start_pending' : 'admin_dashboard_operation_error') });
    } finally { setSaving(false); }
  };

  if (loading && !overview) return <Box className="admin-loading"><CircularProgress /></Box>;

  return (
    <Container maxWidth="xl" className="admin-dashboard">
      <Paper component="aside" className="admin-sidebar">
        <Link to="/" className="admin-sidebar__logo" aria-label={t("admin_ui_dbe20b8730")}>
          <img src="/brand/clanwar-logo.png" alt="Middle-earth Clan Wars" />
        </Link>
        <Box className="admin-sidebar__campaign">
          <span>{t("admin_ui_b43ed3d9f8")}</span>
          <strong>{activeSeason ? t("admin_ui_e068f944e0", null, { value0: activeSeason.number }) : t("admin_ui_f0a78606dd")}</strong>
          <small>{activeSeason?.name || t("admin_ui_532e16429e")}</small>
        </Box>
        {!isAdminPreview && (
          <a className="admin-sidebar__preview" href="/admin/preview/">
            <ScienceOutlined aria-hidden="true" />
            <span>{t('admin_preview_open', 'Предпросмотр новой версии')}</span>
          </a>
        )}
        <Tabs
          value={tab}
          onChange={changeTab}
          orientation={compactNavigation ? 'horizontal' : 'vertical'}
          variant="scrollable"
          scrollButtons={false}
          aria-label={t("admin_ui_1044de1d0e")}
          className="admin-tabs"
        >
          <Tab value={0} icon={<AdminPanelSettings />} iconPosition="start" label={t("admin_ui_39c6387206")} />
          <Tab value={2} icon={<Map />} iconPosition="start" label={t("admin_ui_2dcb633af3")} />
          <Tab value={1} icon={<Castle />} iconPosition="start" label={t("admin_ui_b829d9f79f")} />
          <Tab value={7} icon={<WorkspacePremium />} iconPosition="start" label={t("admin_ui_603b61f8f7")} />
          <Tab value={3} icon={<MilitaryTech />} iconPosition="start" label={t("admin_ui_da67844feb")} />
          <Tab value={9} icon={<Storefront />} iconPosition="start" label={t("admin_ui_4deafccab6")} />
          <Tab value={10} icon={<EmojiEvents />} iconPosition="start" label={t("admin_ui_5f16754719")} />
          <Tab value={4} icon={<RocketLaunch />} iconPosition="start" label={t("admin_ui_572dfa21aa")} />
          <Tab value={5} icon={<History />} iconPosition="start" label="Ledger" />
          <Tab value={6} icon={<Gavel />} iconPosition="start" label={t("admin_ui_39846e7f3e")} />
          <Tab
            value={8}
            icon={<Tune />}
            iconPosition="start"
            label={t('admin_campaign_rules_tab', 'Правила')}
          />
          <Tab value={11} icon={<Badge color="error" badgeContent={feedbackSummary.unread || 0} max={99}><BugReportOutlined /></Badge>} iconPosition="start" label={t("admin_ui_617371c8da")} />
          <Tab value={12} icon={<ScienceOutlined />} iconPosition="start" label={t("admin_ui_44e466613e")} />
        </Tabs>
        <Box className="admin-sidebar__footer">
          <span>{user?.username || t("admin_ui_36d00fd77c")}</span>
          <Button component={Link} to="/" startIcon={<ArrowBack />}>{t("admin_ui_25e1890278")}</Button>
        </Box>
      </Paper>

      <Box component="main" className="admin-dashboard__main">
        <Box className="admin-heading">
          <Box>
            <Typography component="span" className="admin-eyebrow">{t("admin_ui_1d68f58359")}</Typography>
            <Stack direction="row" spacing={1.25} alignItems="center">
              <AdminPanelSettings color="primary" fontSize="large" />
              <Typography variant="h4">{t("admin_ui_db79c324c1")}</Typography>
            </Stack>
            <Typography color="text.secondary">{t("admin_ui_83d7e4e093")}</Typography>
          </Box>
          <Button startIcon={<Refresh />} onClick={refresh} disabled={loading}>{t("admin_ui_c2f668e54f")}</Button>
        </Box>

        {message && <Alert severity={message.type} onClose={() => setMessage(null)} sx={{ mb: 2 }}>{message.text}</Alert>}

      {tab === 0 && overview && (
        <Box className="admin-section">
          <Box className="admin-metrics-grid">
            <Metric icon={<Map />} label={t("admin_ui_206fec9252")} value={overview.campaign.owned_territories} note={t('admin_dashboard_of_total', null, { count: overview.campaign.territories })} />
            <Metric icon={<Groups />} label={t("admin_ui_dda838a958")} value={overview.clans.total} note={t('admin_dashboard_members_count', null, { count: overview.clans.members })} />
            <Metric icon={<People />} label={t("admin_ui_b9ea664372")} value={overview.users.registered} note={t('admin_dashboard_blocked_count', null, { count: overview.users.blocked })} />
            <Metric icon={<MilitaryTech />} label={t("admin_ui_29b1e43a27")} value={overview.campaign.active_wars} />
          </Box>
          <Box component="section" className="admin-cycle-diagnostics" aria-labelledby="admin-cycle-heading" aria-busy={diagnosticsLoading}>
            <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
              <Typography id="admin-cycle-heading" component="h2" variant="h6">{cycleText('admin_cycle_diagnostics')}</Typography>
              <Tooltip title={cycleText('admin_cycle_refresh')}>
                <span><IconButton aria-label={cycleText('admin_cycle_refresh')} onClick={loadDiagnostics} disabled={diagnosticsLoading || recoverySaving}><Refresh /></IconButton></span>
              </Tooltip>
            </Stack>
            {diagnosticsError && <Alert severity="error">{diagnosticsError}</Alert>}
            {diagnosticsLoading && !diagnostics && <CircularProgress size={24} />}
            {diagnostics && <>
              <Box className="admin-cycle-diagnostics__grid">
                <Box>
                  <Typography component="h3" variant="subtitle2">{cycleText('admin_cycle_current')}</Typography>
                  <dl>
                    <dt>{cycleText('admin_cycle_mode')}</dt><dd>{diagnostics.mechanics_version}</dd>
                    <dt>{cycleText('admin_cycle_season')}</dt><dd>{diagnostics.season_id ?? '—'}</dd>
                    <dt>{cycleText('admin_cycle_number')}</dt><dd>{diagnostics.cycle ? `${diagnostics.cycle.number} / ${diagnostics.cycle.revision}` : '—'}</dd>
                    <dt>{cycleText('admin_cycle_phase')}</dt><dd>{diagnostics.cycle?.phase ? cycleText(`admin_cycle_${diagnostics.cycle.phase}`) : '—'}</dd>
                    {['preparation_at', 'battle_at', 'battle_ends_at', 'replay_deadline', 'settled_at', 'import_verified_at'].map((key) => <React.Fragment key={key}>
                      <dt>{({ preparation_at: cycleText('admin_cycle_preparation_at'), battle_at: cycleText('admin_cycle_battle_at'), battle_ends_at: cycleText('admin_cycle_battle_ends'), replay_deadline: cycleText('admin_cycle_replay_deadline'), settled_at: cycleText('admin_cycle_settled'), import_verified_at: cycleText('admin_cycle_import_verified') })[key]}</dt>
                      <dd>{formatMoscowDateTime(diagnostics.cycle?.[key], '—', language)}</dd>
                    </React.Fragment>)}
                  </dl>
                </Box>
                <Box>
                  <Typography component="h3" variant="subtitle2">{cycleText('admin_cycle_complete_scan')}</Typography>
                  {!diagnostics.arena?.last_complete_scan ? <Alert severity="warning">{cycleText('admin_cycle_no_complete_scan')}</Alert> : <dl>
                    <dt>{cycleText('admin_cycle_scan_completed')}</dt><dd>{formatMoscowDateTime(diagnostics.arena.last_complete_scan.completed_at, '—', language)}</dd>
                    <dt>{cycleText('admin_cycle_scan_from')}</dt><dd>{formatMoscowDateTime(diagnostics.arena.last_complete_scan.covered_start, '—', language)}</dd>
                    <dt>{cycleText('admin_cycle_scan_until')}</dt><dd>{formatMoscowDateTime(diagnostics.arena.last_complete_scan.covered_end, '—', language)}</dd>
                    <dt>{cycleText('admin_cycle_replays_count')}</dt><dd>{diagnostics.arena.last_complete_scan.replays_count}</dd>
                  </dl>}
                  <dl>
                    <dt>{cycleText('admin_cycle_worker_heartbeat')}</dt><dd>{formatMoscowDateTime(diagnostics.arena?.heartbeat_at, '—', language)}</dd>
                    <dt>{cycleText('admin_cycle_worker_success')}</dt><dd>{formatMoscowDateTime(diagnostics.arena?.last_worker_success_at, '—', language)}</dd>
                    <dt>{cycleText('admin_cycle_worker_failures')}</dt><dd>{diagnostics.arena?.worker_failures ?? '—'}</dd>
                    <dt>{cycleText('admin_cycle_server_time')}</dt><dd>{formatMoscowDateTime(diagnostics.server_time, '—', language)}</dd>
                  </dl>
                </Box>
                <Box>
                  <Typography component="h3" variant="subtitle2">{cycleText('admin_cycle_pending')}</Typography>
                  <dl>
                    <dt>{cycleText('admin_cycle_pending_replays')}</dt><dd>{diagnostics.arena?.pending_source_replays ?? '—'}</dd>
                    <dt>{cycleText('admin_cycle_pending_interceptions')}</dt><dd>{diagnostics.arena?.pending_interceptions ?? '—'}</dd>
                  </dl>
                  <Typography component="h4" variant="subtitle2">{cycleText('admin_cycle_personal_contributions')}</Typography>
                  <Table size="small" aria-label={cycleText('admin_cycle_pending_contributions')}>
                    <TableHead><TableRow><TableCell>{t('admin_ui_8deb8920a7')}</TableCell><TableCell align="right">{cycleText('admin_cycle_count')}</TableCell></TableRow></TableHead>
                    <TableBody>{(diagnostics.arena?.pending_contributions || []).map((item) => <TableRow key={item.reason}><TableCell>{cycleText(cycleMessages[`admin_cycle_reason_${item.reason}`] ? `admin_cycle_reason_${item.reason}` : 'admin_cycle_reason_other')}</TableCell><TableCell align="right">{item.count}</TableCell></TableRow>)}
                      {!diagnostics.arena?.pending_contributions?.length && <TableRow><TableCell colSpan={2}>{cycleText('admin_cycle_no_pending')}</TableCell></TableRow>}
                    </TableBody>
                  </Table>
                </Box>
              </Box>
              {canRecoverPreparation(diagnostics.cycle, recoveryPending) && <Box className="admin-cycle-recovery" component="form" onSubmit={(event) => { event.preventDefault(); recoverPreparation(); }}>
                {diagnostics.cycle.recovery_available && <Alert severity="warning">{cycleText('admin_cycle_recovery_warning')}</Alert>}
                {recoveryError && <Alert severity="error">{recoveryError}</Alert>}
                {recoveryPending && <Alert severity="info">{cycleText('admin_cycle_pending_command')}</Alert>}
                <TextField label={cycleText('admin_cycle_recovery_reason')} required fullWidth multiline minRows={2} value={recoveryReason} disabled={recoverySaving || Boolean(recoveryPending)} inputProps={{ maxLength: 500 }} onChange={(event) => setRecoveryReason(event.target.value)} />
                <FormControlLabel control={<Checkbox checked={recoveryConfirmed} disabled={recoverySaving} onChange={(event) => setRecoveryConfirmed(event.target.checked)} />} label={cycleText('admin_cycle_recovery_confirm')} />
                <Button type="submit" variant="outlined" color="warning" startIcon={<History />} disabled={recoverySaving || diagnosticsLoading || Boolean(diagnosticsError) || !recoveryConfirmed || recoveryReason.trim().length < 3}>
                  {recoveryPending ? cycleText('admin_cycle_retry') : cycleText('admin_cycle_recover')}
                </Button>
              </Box>}
            </>}
          </Box>
          <Box className="admin-overview-panels">
            <Paper className="admin-overview-card">
              <Typography variant="h6">{t("admin_ui_41b1e81042")}</Typography>
              {activeAdminWars.length ? (
                <Box className="admin-active-wars-table">
                  <Box className="admin-active-wars-row admin-active-wars-head"><span>{t("admin_ui_fcff2f9d30")}</span><span>{t("admin_ui_61540b9e95")}</span><span>{t("admin_ui_d386f41a4a")}</span><span>{t("admin_ui_c80d7e8172")}</span></Box>
                  {activeAdminWars.slice(0, 5).map((war) => {
                    const attacker = (war.clan_scores || []).find((score) => score.clan_id === war.attacking_clan_id);
                    const defender = (war.clan_scores || []).find((score) => score.clan_id === war.defending_clan_id);
                    return <Link className="admin-active-wars-row" to={`/battles/${war.id}`} key={war.id}><span>{war.attacking_clan_name} vs {war.defending_clan_name || t("admin_ui_a347868833")}</span><span>{war.territory_name}</span><span>{attacker?.points || 0}:{defender?.points || 0}</span><span>{war.ends_at ? formatMoscowDateTime(war.ends_at, '—', language) : '—'}</span></Link>;
                  })}
                </Box>
              ) : <Typography color="text.secondary">{t("admin_ui_b7988a3d65")}</Typography>}
            </Paper>
            <Paper className="admin-overview-card">
              <Typography variant="h6">{t("admin_ui_2698a54dd2")}</Typography>
              <Box className="admin-system-feed">
                <div><span className="admin-system-dot is-ok" /><b>{t("admin_ui_group_8215d798fc", null, { value0: overview.users.active })}</b><small>{t("admin_ui_group_53ffd95f8b", null, { value0: overview.users.blocked })}</small></div>
                <div><span className="admin-system-dot" /><b>{t("admin_ui_group_d868f7c92e", null, { value0: overview.campaign.active_caravans })}</b><small>{t("admin_ui_50d0618bf9")}</small></div>
                <div><span className={`admin-system-dot${overview.matches.sync_errors ? ' is-error' : ' is-ok'}`} /><b>{t("admin_ui_group_a3ffe7f83c", null, { value0: overview.matches.total })}</b><small>{t("admin_ui_group_e7b20fa42b", null, { value0: overview.matches.sync_errors })}</small></div>
                <div><span className={`admin-system-dot${overview.worker?.last_error ? ' is-error' : ' is-ok'}`} /><b>{t("admin_ui_e57eec02c7")}</b><small>{overview.worker ? t("admin_ui_0b21f402f3", null, { value0: formatMoscowDateTime(overview.worker.heartbeat_at, '—', language) }) : t("admin_ui_a3d08179d6")}</small></div>
              </Box>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1} className="admin-overview-actions">
                <Button component={Link} to="/map" startIcon={<Map />}>{t("admin_ui_c4a9f2172b")}</Button>
                <Button component={Link} to="/admin/sync" startIcon={<Sync />}>{t("admin_ui_7cedddad2b")}</Button>
              </Stack>
            </Paper>
          </Box>
        </Box>
      )}

      {tab === 1 && (
        <Paper className="admin-section">
          <Box className="admin-section__title"><Box><Typography variant="h6">{t("admin_ui_ef1f3a3128")}</Typography><Typography variant="body2" color="text.secondary">{t("admin_ui_fb672caa61")}</Typography></Box></Box>
          <TableContainer><Table size="small">
            <TableHead><TableRow><TableCell>{t("admin_ui_798beea33d")}</TableCell><TableCell align="right">{t("admin_ui_f3920df09c")}</TableCell><TableCell align="right">{t("admin_ui_61acc3210f")}</TableCell>{Object.values(RESOURCES).map((labelKey) => <TableCell key={labelKey} align="right">{t(labelKey)}</TableCell>)}<TableCell /></TableRow></TableHead>
            <TableBody>{clans.map((clan) => <TableRow key={clan.id} hover>
              <TableCell><Stack direction="row" alignItems="center" spacing={1}><Typography component={Link} to={`/clans/${clan.id}`} className="admin-link">{clan.name}</Typography>{clan.is_admin_clan && <Chip size="small" color="warning" label={t("admin_ui_0443a4505d")} />}</Stack></TableCell>
              <TableCell align="right">{clan.members}</TableCell><TableCell align="right">{clan.territories}</TableCell>
              {Object.keys(RESOURCES).map((key) => <TableCell key={key} align="right">{clan[key]}</TableCell>)}
              <TableCell align="right"><Button size="small" startIcon={<Edit />} onClick={() => openEconomy(clan)}>{t("admin_ui_9d809f884b")}</Button>{!clan.is_admin_clan && <AdminPermanentDeleteButton kind="clans" id={clan.id} name={clan.name} onMessage={setMessage} onDeleted={() => Promise.all([loadCore(), loadLogs()])} />}</TableCell>
            </TableRow>)}</TableBody>
          </Table></TableContainer>
        </Paper>
      )}

      {tab === 2 && (
        <AdminTerritoriesPanel
          clans={clans}
          onMessage={setMessage}
          onChanged={() => Promise.all([loadCore(), loadLogs()])}
        />
      )}

      {tab === 3 && (
        <AdminWarsPanel
          onMessage={setMessage}
          onChanged={() => Promise.all([loadCore(), loadLogs()])}
        />
      )}

      {tab === 4 && (
        <Box className="admin-campaign-layout">
          <Paper className="admin-campaign-state">
            <Typography variant="overline">{t("admin_ui_b43ed3d9f8")}</Typography>
            <Typography variant="h5">{activeSeason?.name || t("admin_ui_bd90bd46e0")}</Typography>
            <Typography color="text.secondary">{activeSeason ? t("admin_ui_9952e8a94c", null, { value0: formatMoscowDateTime(activeSeason.starts_at, '—', language) }) : t("admin_ui_2e339b2122")}</Typography>
            <Button color={activeSeason ? 'error' : 'primary'} variant={activeSeason ? 'outlined' : 'contained'} startIcon={activeSeason ? <StopCircle /> : <RocketLaunch />} onClick={() => setSeasonAction(activeSeason ? 'complete' : 'start')}>
              {activeSeason ? t("admin_ui_b7e5287b65") : t("admin_ui_7d05e52ac5")}
            </Button>
          </Paper>
          <Paper className="admin-season-history"><Typography variant="h6">{t("admin_ui_6fe520859f")}</Typography>{seasons.length === 0 ? <Typography color="text.secondary">{t("admin_ui_e335987e12")}</Typography> : seasons.map((season) => <Box className="admin-season-row" key={season.id}><Box><Typography fontWeight={700}>{season.name}</Typography><Typography variant="caption" color="text.secondary">{formatMoscowDateTime(season.starts_at, '—', language)}</Typography></Box><Chip size="small" color={season.status === 'active' ? 'success' : 'default'} label={season.status === 'active' ? t("admin_ui_3fd095aa22") : t("admin_ui_8ff17e74b3")} /></Box>)}</Paper>
        </Box>
      )}

      {tab === 5 && (
        <Paper className="admin-section">
          <Box className="admin-section__title"><Box><Typography variant="h6">{t("admin_ui_3752fc146a")}</Typography><Typography variant="body2" color="text.secondary">{t("admin_ui_145cdec188")}</Typography></Box><Stack direction={{ xs: 'column', sm: 'row' }} spacing={1}><TextField select size="small" label={t("admin_ui_798beea33d")} value={ledgerClan} onChange={(event) => setLedgerClan(event.target.value)} sx={{ minWidth: 180 }}><MenuItem value="">{t("admin_ui_fd08da7a63")}</MenuItem>{clans.map((clan) => <MenuItem key={clan.id} value={clan.id}>{clan.name}</MenuItem>)}</TextField><TextField select size="small" label={t("admin_ui_6af92380f7")} value={ledgerResource} onChange={(event) => setLedgerResource(event.target.value)} sx={{ minWidth: 150 }}><MenuItem value="">{t("admin_ui_fd08da7a63")}</MenuItem>{Object.entries(RESOURCES).map(([key, labelKey]) => <MenuItem key={key} value={key}>{t(labelKey)}</MenuItem>)}</TextField></Stack></Box>
          <TableContainer className="admin-log-table"><Table stickyHeader size="small"><TableHead><TableRow><TableCell>{t("admin_ui_3eaa09937a")}</TableCell><TableCell>{t("admin_ui_798beea33d")}</TableCell><TableCell>{t("admin_ui_6af92380f7")}</TableCell><TableCell align="right">{t("admin_ui_8ed6089103")}</TableCell><TableCell align="right">{t("admin_ui_b60bae3c3a")}</TableCell><TableCell>{t("admin_ui_4a9ea52cda")}</TableCell></TableRow></TableHead><TableBody>{ledger.map((entry) => <TableRow key={entry.id} hover><TableCell>{formatMoscowDateTime(entry.created_at, '—', language)}</TableCell><TableCell>{entry.clan_name}</TableCell><TableCell>{RESOURCES[entry.resource] ? t(RESOURCES[entry.resource]) : entry.resource}</TableCell><TableCell align="right" className={entry.amount >= 0 ? 'admin-positive' : 'admin-negative'}>{entry.amount > 0 ? '+' : ''}{entry.amount}</TableCell><TableCell align="right">{entry.balance_before} → {entry.balance_after}</TableCell><TableCell>{entry.details?.reason || (ACTIONS[entry.action] ? t(ACTIONS[entry.action]) : entry.action)}</TableCell></TableRow>)}</TableBody></Table></TableContainer>
        </Paper>
      )}

      {tab === 6 && (
        <Paper className="admin-section">
          <Box className="admin-section__title"><Box><Typography variant="h6">{t("admin_ui_5e172682fc")}</Typography><Typography variant="body2" color="text.secondary">{t("admin_ui_baf25ad865")}</Typography></Box></Box>
          <TableContainer className="admin-log-table"><Table stickyHeader size="small">
            <TableHead><TableRow><TableCell>{t("admin_ui_3eaa09937a")}</TableCell><TableCell>{t("admin_ui_36d00fd77c")}</TableCell><TableCell>{t("admin_ui_4fe9c0675c")}</TableCell><TableCell>{t("admin_ui_1f85d2038b")}</TableCell><TableCell>{t("admin_ui_4a9ea52cda")}</TableCell></TableRow></TableHead>
            <TableBody>{audit.map((entry) => <TableRow key={entry.id} hover>
              <TableCell>{formatMoscowDateTime(entry.created_at, '—', language)}</TableCell><TableCell>{entry.actor}</TableCell>
              <TableCell>{entry.action === 'cycle_clan_economy_adjusted' ? cycleText('admin_cycle_audit_action') : ACTIONS[entry.action] ? t(ACTIONS[entry.action]) : entry.action}</TableCell>
              <TableCell>{entry.entity_type} #{entry.entity_id || '—'}</TableCell>
              <TableCell>{entry.reason || '—'}{entry.action === 'cycle_clan_economy_adjusted' && <details className="admin-economy-audit">
                <summary>{cycleText('admin_cycle_audit_balances')}</summary>
                <Typography variant="caption">{cycleText('admin_cycle_audit_scope', { season: entry.after?.season_id, clan: entry.after?.clan_id })}</Typography>
                <dl>{Object.entries(RESOURCES).filter(([key]) => key !== 'influence').map(([key, labelKey]) => <React.Fragment key={key}><dt>{t(labelKey)}</dt><dd>{entry.before?.wallet?.[key] ?? '—'} → {entry.after?.wallet?.[key] ?? '—'}</dd></React.Fragment>)}</dl>
              </details>}</TableCell>
            </TableRow>)}</TableBody>
          </Table></TableContainer>
        </Paper>
      )}

      {tab === 7 && <AdminUsersTitlesPanel />}

      {tab === 8 && (
        <AdminCampaignRulesPanel
          onOpenTerritories={() => setTab(2)}
          relicEditorPath={clans[0] ? `/clans/${clans[0].id}#relics` : '/clans'}
        />
      )}

        {tab === 9 && <AdminContentCatalogPanel mode="shop" />}

        {tab === 10 && <AdminContentCatalogPanel mode="achievements" />}
        {tab === 11 && <AdminFeedbackPanel onSummaryChange={setFeedbackSummary} />}
        {tab === 12 && <AdminBalanceSimulatorPanel />}
      </Box>

      <Dialog open={Boolean(editingClan)} onClose={closeEconomy} fullWidth maxWidth="sm" aria-labelledby="admin-treasury-title">
        <DialogTitle id="admin-treasury-title">{t("admin_ui_group_572758f127", null, { value0: editingClan?.name })}</DialogTitle>
        <DialogContent aria-busy={economyLoading}>
          {economyLoading && <CircularProgress size={24} />}
          {economyError && <Alert severity="error" sx={{ mb: 2 }}>{economyError}</Alert>}
          {economyContext && <>
            <Alert severity="info" sx={{ mb: 2 }}>{economyContext.mechanics_version === 'cycle_v1'
              ? cycleText('admin_cycle_treasury_mode', { season: economyContext.season_id })
              : t("admin_ui_0bb60b0d85")}</Alert>
            {economyContext.mechanics_version === 'cycle_v1' && <Typography variant="caption" component="p" sx={{ mb: 2 }}>{cycleText('admin_cycle_treasury_revision', { season: economyContext.season_id, revision: economyPending?.expected_revision ?? economyContext.state.revision })}</Typography>}
            {economyPending && <Alert severity="warning" sx={{ mb: 2 }}>{cycleText('admin_cycle_pending_command')}</Alert>}
            <Box className="admin-economy-form">{Object.entries(RESOURCES).filter(([key]) => economyContext.mechanics_version === 'legacy' || key !== 'influence').map(([key, labelKey]) => <TextField
              key={key} label={t(labelKey)} type={economyContext.mechanics_version === 'cycle_v1' ? 'text' : 'number'}
              value={economy[key] ?? ''} disabled={saving || Boolean(economyPending) || Boolean(economyError)}
              inputProps={{ min: 0, inputMode: 'decimal', maxLength: 80 }}
              onChange={(event) => setEconomy((current) => ({ ...current, [key]: economyContext.mechanics_version === 'legacy' ? Number(event.target.value) : event.target.value }))}
            />)}</Box>
            <TextField label={t("admin_ui_8deb8920a7")} required multiline minRows={2} fullWidth sx={{ mt: 2 }} value={economy.reason || ''} disabled={saving || Boolean(economyPending) || Boolean(economyError)} inputProps={{ maxLength: 2000 }} onChange={(event) => setEconomy((current) => ({ ...current, reason: event.target.value }))} />
          </>}
        </DialogContent>
        <DialogActions>
          <Tooltip title={cycleText('admin_cycle_reload_treasury')}><span><IconButton aria-label={cycleText('admin_cycle_reload_treasury')} disabled={saving || economyLoading || Boolean(economyPending)} onClick={() => openEconomy(editingClan)}><Refresh /></IconButton></span></Tooltip>
          <Button disabled={saving} onClick={closeEconomy}>{t("admin_ui_0ec753be8d")}</Button>
          <Button variant="contained" disabled={saving || economyLoading || !economyValid || Boolean(economyError)} onClick={saveEconomy}>
            {economyPending ? cycleText('admin_cycle_retry') : t("admin_ui_4864057d62")}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={Boolean(seasonAction)} onClose={() => !saving && setSeasonAction(null)} fullWidth maxWidth="sm"><DialogTitle>{seasonAction === 'start' ? t("admin_ui_320ab87d4d") : t("admin_ui_e08f372ffa")}</DialogTitle><DialogContent>{seasonAction === 'start' ? <Stack spacing={2} mt={1}><Alert severity="info">{t('admin_cycle_start_notice')}</Alert>{seasonPending && <Alert severity="warning">{t('admin_cycle_start_pending')}</Alert>}<TextField label={t("admin_ui_3de49828e8")} value={seasonForm.name} disabled={saving || Boolean(seasonPending)} inputProps={{ maxLength: 120 }} onChange={(event) => setSeasonForm({ name: event.target.value })} /></Stack> : <Alert severity="warning">{t("admin_ui_271d847708")}</Alert>}</DialogContent><DialogActions><Button disabled={saving} onClick={() => setSeasonAction(null)}>{t("admin_ui_0ec753be8d")}</Button><Button color={seasonAction === 'start' ? 'primary' : 'error'} variant="contained" disabled={saving || (seasonAction === 'start' && !seasonForm.name.trim())} onClick={runSeasonAction}>{seasonAction === 'start' ? t("admin_ui_85ab1c5daf") : t("admin_ui_5b1713041f")}</Button></DialogActions></Dialog>
    </Container>
  );
};

export default AdminDashboardPage;
