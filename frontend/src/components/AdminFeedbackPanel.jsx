import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert, Box, Button, Chip, CircularProgress, MenuItem, Paper, Stack, TextField, Typography,
} from '@mui/material';
import {
  AssignmentIndOutlined, BugReportOutlined, ForumOutlined, Refresh, SendRounded,
} from '@mui/icons-material';
import { useSearchParams } from 'react-router-dom';
import { useRealtimeEvent } from '../contexts/RealtimeContext';
import { feedbackService } from '../services/feedbackService';
import { formatMoscowDateTime } from '../utils/dateTime';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const CATEGORY = { bug: 'admin_feedback_category_bug', suggestion: 'admin_feedback_category_suggestion', question: 'admin_feedback_category_question', other: 'admin_feedback_category_other' };
const STATUS = { new: 'admin_feedback_status_new', in_progress: 'admin_feedback_status_progress', waiting_user: 'admin_feedback_status_waiting', resolved: 'admin_feedback_status_resolved', closed: 'admin_feedback_status_closed' };
const PRIORITY = { low: 'admin_feedback_priority_low', normal: 'admin_feedback_priority_normal', high: 'admin_feedback_priority_high', critical: 'admin_feedback_priority_critical' };
const SUMMARY_METRICS = [
  ['admin_feedback_metric_unread', 'unread', 'unread'],
  ['admin_feedback_metric_new', 'new', 'new'],
  ['admin_feedback_metric_progress', 'in_progress', 'progress'],
  ['admin_feedback_metric_critical', 'critical', 'critical'],
];

const AdminFeedbackPanel = ({ onSummaryChange }) => {
  const { getLocalizedText: t, language } = useLocalizationContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTicketId = Number(searchParams.get('ticket')) || null;
  const [tickets, setTickets] = useState([]);
  const [summary, setSummary] = useState({ total: 0, unread: 0, new: 0, in_progress: 0, critical: 0 });
  const [selected, setSelected] = useState(null);
  const [filters, setFilters] = useState({ status: 'all', category: 'all', priority: 'all', search: '' });
  const [reply, setReply] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    if (!quiet) setError('');
    try {
      const data = await feedbackService.listAdmin(filters);
      setTickets(data.items || []);
      setSummary(data.summary || {});
      onSummaryChange?.(data.summary || {});
      const desiredId = selected?.id || requestedTicketId;
      const desired = (data.items || []).find((ticket) => ticket.id === desiredId);
      if (desired) setSelected(desired);
      else if (!desiredId && data.items?.length) setSelected(data.items[0]);
    } catch (requestError) {
      if (!quiet) setError(requestError.response?.data?.detail || t("admin_ui_eb819a865f"));
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [filters, onSummaryChange, requestedTicketId, selected?.id, t]);

  useEffect(() => {
    const timer = window.setTimeout(() => load(), filters.search ? 250 : 0);
    return () => window.clearTimeout(timer);
  }, [load, filters.search]);
  useRealtimeEvent((event) => {
    if (event.type?.startsWith('feedback.')) load(true);
  });

  const selectTicket = async (ticket) => {
    setSelected(ticket);
    setSearchParams({ section: 'feedback', ticket: String(ticket.id) });
    if (ticket.admin_unread) {
      try {
        const updated = await feedbackService.markAdminRead(ticket.id);
        setSelected(updated);
        await load(true);
      } catch {
        // Reading is advisory; the queue remains usable if this request fails.
      }
    }
  };

  const update = async (payload) => {
    if (!selected) return;
    setSaving(true);
    setError('');
    try {
      const updated = await feedbackService.updateAdmin(selected.id, payload);
      setSelected(updated);
      await load(true);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t("admin_ui_7740327975"));
    } finally { setSaving(false); }
  };

  const sendReply = async () => {
    if (!selected || reply.trim().length < 2) return;
    setSaving(true);
    setError('');
    try {
      const updated = await feedbackService.replyAdmin(selected.id, reply);
      setSelected(updated);
      setReply('');
      await load(true);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t("admin_ui_549f8a4c78"));
    } finally { setSaving(false); }
  };

  const visibleMessages = useMemo(() => selected?.messages || [], [selected]);

  return (
    <Box className="admin-feedback">
      <Box className="admin-content-title">
        <Box><Typography variant="h4">{t("admin_ui_22b9a1eb70")}</Typography><Typography color="text.secondary">{t("admin_ui_9e0dda873a")}</Typography></Box>
        <Button startIcon={<Refresh />} onClick={() => load()} disabled={loading}>{t("admin_ui_c2f668e54f")}</Button>
      </Box>
      {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}
      <Box className="admin-feedback__metrics">
        {SUMMARY_METRICS.map(([labelKey, valueKey, tone]) => <Paper key={labelKey} className={`admin-feedback-metric is-${tone}`}><strong>{summary[valueKey] || 0}</strong><span>{t(labelKey)}</span></Paper>)}
      </Box>
      <Paper className="admin-feedback__filters">
        <TextField size="small" label={t("admin_ui_6433b522a1")} value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} />
        <TextField size="small" select label={t("admin_ui_f7f293b5c5")} value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}><MenuItem value="all">{t("admin_ui_dad15ae690")}</MenuItem>{Object.entries(STATUS).map(([value, labelKey]) => <MenuItem value={value} key={value}>{t(labelKey)}</MenuItem>)}</TextField>
        <TextField size="small" select label={t("admin_ui_d25691ca40")} value={filters.category} onChange={(event) => setFilters({ ...filters, category: event.target.value })}><MenuItem value="all">{t("admin_ui_c21a23a52f")}</MenuItem>{Object.entries(CATEGORY).map(([value, labelKey]) => <MenuItem value={value} key={value}>{t(labelKey)}</MenuItem>)}</TextField>
        <TextField size="small" select label={t("admin_ui_b5b6ddbf62")} value={filters.priority} onChange={(event) => setFilters({ ...filters, priority: event.target.value })}><MenuItem value="all">{t("admin_ui_3bb6b48110")}</MenuItem>{Object.entries(PRIORITY).map(([value, labelKey]) => <MenuItem value={value} key={value}>{t(labelKey)}</MenuItem>)}</TextField>
      </Paper>
      <Box className="admin-feedback__workspace">
        <Paper className="admin-feedback__queue">
          {loading && <Box className="admin-feedback__empty"><CircularProgress size={28} /></Box>}
          {!loading && !tickets.length && <Box className="admin-feedback__empty"><ForumOutlined /><b>{t("admin_ui_6e1a1d08e3")}</b><span>{t("admin_ui_faf6920588")}</span></Box>}
          {!loading && tickets.map((ticket) => <button type="button" key={ticket.id} className={`admin-feedback-row${selected?.id === ticket.id ? ' is-selected' : ''}${ticket.admin_unread ? ' is-unread' : ''}`} onClick={() => selectTicket(ticket)}>
            <span className="admin-feedback-row__top"><b>{ticket.reference}</b><time>{formatMoscowDateTime(ticket.updated_at, '—', language)}</time></span>
            <strong>{ticket.title}</strong>
            <span className="admin-feedback-row__author">{ticket.reporter_name}</span>
            <span className="admin-feedback-row__chips"><Chip size="small" label={t(CATEGORY[ticket.category])} /><Chip size="small" className={`priority-${ticket.priority}`} label={t(PRIORITY[ticket.priority])} /></span>
          </button>)}
        </Paper>
        <Paper className="admin-feedback__detail">
          {!selected ? <Box className="admin-feedback__empty"><BugReportOutlined /><b>{t("admin_ui_747d564a2e")}</b></Box> : <>
            <Box className="admin-feedback__detail-head">
              <Box><Typography variant="overline">{selected.reference} · {t(CATEGORY[selected.category])}</Typography><Typography variant="h5">{selected.title}</Typography><Typography variant="caption" color="text.secondary">{selected.reporter_name} · {formatMoscowDateTime(selected.created_at, '—', language)}</Typography></Box>
              <Stack direction="row" spacing={1} flexWrap="wrap" justifyContent="flex-end">
                <TextField size="small" select label={t("admin_ui_f7f293b5c5")} value={selected.status} onChange={(event) => update({ status: event.target.value })}>{Object.entries(STATUS).map(([value, labelKey]) => <MenuItem value={value} key={value}>{t(labelKey)}</MenuItem>)}</TextField>
                <TextField size="small" select label={t("admin_ui_b5b6ddbf62")} value={selected.priority} onChange={(event) => update({ priority: event.target.value })}>{Object.entries(PRIORITY).map(([value, labelKey]) => <MenuItem value={value} key={value}>{t(labelKey)}</MenuItem>)}</TextField>
                <Button variant="outlined" startIcon={<AssignmentIndOutlined />} onClick={() => update({ assign_to_me: !selected.assigned_admin_id })}>{selected.assigned_admin_name || t("admin_ui_13ded02b4f")}</Button>
              </Stack>
            </Box>
            <Box className="admin-feedback__context">
              {selected.source_path && <span><b>{t("admin_ui_97e20f8391")}</b>{selected.source_path}</span>}
              {selected.user_agent && <span><b>{t("admin_ui_1b4034547a")}</b>{selected.user_agent}</span>}
            </Box>
            <Box className="admin-feedback__thread">
              <section className="admin-feedback__original"><p>{selected.description}</p>{selected.reproduction_steps && <div><b>{t("admin_ui_53e28d350c")}</b><p>{selected.reproduction_steps}</p></div>}{(selected.expected_result || selected.actual_result) && <div className="admin-feedback__comparison">{selected.expected_result && <div><b>{t("admin_ui_dcd2690bed")}</b><p>{selected.expected_result}</p></div>}{selected.actual_result && <div><b>{t("admin_ui_58d861817e")}</b><p>{selected.actual_result}</p></div>}</div>}{selected.attachment_url && <a href={selected.attachment_url} target="_blank" rel="noreferrer"><img src={selected.attachment_url} alt={t("admin_ui_63088c5791")} /></a>}</section>
              {visibleMessages.map((message) => <section key={message.id} className={`admin-feedback-message${message.is_admin ? ' is-admin' : ''}`}><div><b>{message.author_name}</b><time>{formatMoscowDateTime(message.created_at, '—', language)}</time></div><p>{message.body}</p></section>)}
            </Box>
            <Box className="admin-feedback__reply"><TextField multiline minRows={3} maxRows={8} value={reply} onChange={(event) => setReply(event.target.value)} placeholder={t("admin_ui_a041b86257")} /><Button variant="contained" startIcon={<SendRounded />} onClick={sendReply} disabled={saving || reply.trim().length < 2}>{t("admin_ui_76dcf737a6")}</Button></Box>
          </>}
        </Paper>
      </Box>
    </Box>
  );
};

export default AdminFeedbackPanel;
