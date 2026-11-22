import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AddCommentOutlined, BugReportOutlined, ForumOutlined, ImageOutlined, SendRounded } from '@mui/icons-material';
import { useSearchParams } from 'react-router-dom';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { useRealtimeEvent } from '../contexts/RealtimeContext';
import { feedbackService } from '../services/feedbackService';
import './FeedbackPage.css';

const EMPTY_FORM = {
  category: 'bug',
  title: '',
  description: '',
  reproduction_steps: '',
  expected_result: '',
  actual_result: '',
  image: null,
};

const statusClass = (status) => `feedback-status feedback-status--${status}`;

const FeedbackPage = () => {
  const { getLocalizedText: t, language } = useLocalizationContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const [mode, setMode] = useState(searchParams.get('ticket') ? 'history' : 'create');
  const [form, setForm] = useState(EMPTY_FORM);
  const [tickets, setTickets] = useState([]);
  const [selected, setSelected] = useState(null);
  const [reply, setReply] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const selectedId = Number(searchParams.get('ticket')) || null;
  const sourcePath = searchParams.get('from') || null;
  const formatter = useMemo(() => new Intl.DateTimeFormat(language, {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }), [language]);

  const loadTickets = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const rows = await feedbackService.listMine();
      setTickets(rows);
      if (selectedId) setSelected(rows.find((ticket) => ticket.id === selectedId) || null);
    } catch (requestError) {
      if (!quiet) setError(requestError.response?.data?.detail || t('feedback_load_error'));
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [selectedId, t]);

  useEffect(() => { loadTickets(); }, [loadTickets]);
  useRealtimeEvent((event) => {
    if (event.type?.startsWith('feedback.')) loadTickets(true);
  });

  const change = (field) => (event) => {
    setForm((current) => ({
      ...current,
      [field]: field === 'image' ? event.target.files?.[0] || null : event.target.value,
    }));
  };

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    setSuccess('');
    const data = new FormData();
    Object.entries(form).forEach(([key, value]) => {
      if (value) data.append(key, value);
    });
    if (sourcePath) data.append('source_path', sourcePath);
    data.append('user_agent', navigator.userAgent.slice(0, 500));
    try {
      const created = await feedbackService.create(data);
      setForm(EMPTY_FORM);
      setSuccess(t('feedback_created', null, { reference: created.reference }));
      setMode('history');
      setSearchParams({ ticket: String(created.id) });
      await loadTickets(true);
      setSelected(created);
    } catch (requestError) {
      const detail = requestError.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : t('feedback_submit_error'));
    } finally {
      setSaving(false);
    }
  };

  const sendReply = async (event) => {
    event.preventDefault();
    if (!selected || reply.trim().length < 2) return;
    setSaving(true);
    setError('');
    try {
      const updated = await feedbackService.reply(selected.id, reply);
      setSelected(updated);
      setReply('');
      await loadTickets(true);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t('feedback_reply_error'));
    } finally {
      setSaving(false);
    }
  };

  const openTicket = (ticket) => {
    setSelected(ticket);
    setMode('history');
    setSearchParams({ ticket: String(ticket.id) });
  };

  return (
    <main className="prototype-exact-page feedback-page">
      <header className="page-title feedback-page__header">
        <div>
          <div className="eyebrow">{t('feedback_eyebrow')}</div>
          <h1 className="serif">{t('feedback_title')}</h1>
          <p className="subtitle">{t('feedback_subtitle')}</p>
        </div>
        <div className="feedback-page__mode" role="tablist" aria-label={t('feedback_sections')}>
          <button className={mode === 'create' ? 'is-active' : ''} type="button" role="tab" aria-selected={mode === 'create'} onClick={() => setMode('create')}>
            <AddCommentOutlined />{t('feedback_new')}
          </button>
          <button className={mode === 'history' ? 'is-active' : ''} type="button" role="tab" aria-selected={mode === 'history'} onClick={() => setMode('history')}>
            <ForumOutlined />{t('feedback_mine')}<b>{tickets.length}</b>
          </button>
        </div>
      </header>

      {error && <div className="feedback-notice is-error" role="alert">{error}</div>}
      {success && <div className="feedback-notice is-success" role="status">{success}</div>}

      {mode === 'create' ? (
        <form className="card feedback-form" onSubmit={submit}>
          <div className="feedback-form__intro">
            <BugReportOutlined />
            <div><strong>{t('feedback_form_title')}</strong><span>{t('feedback_form_hint')}</span></div>
          </div>
          <div className="feedback-form__grid">
            <label><span>{t('feedback_category')}</span><select value={form.category} onChange={change('category')}>
              <option value="bug">{t('feedback_category_bug')}</option>
              <option value="suggestion">{t('feedback_category_suggestion')}</option>
              <option value="question">{t('feedback_category_question')}</option>
              <option value="other">{t('feedback_category_other')}</option>
            </select></label>
            <label className="is-wide"><span>{t('feedback_subject')}</span><input value={form.title} onChange={change('title')} minLength={5} maxLength={160} required placeholder={t('feedback_subject_placeholder')} /></label>
            <label className="is-wide"><span>{t('feedback_description')}</span><textarea value={form.description} onChange={change('description')} minLength={10} maxLength={5000} rows={5} required placeholder={t('feedback_description_placeholder')} /></label>
            {form.category === 'bug' && <>
              <label className="is-wide"><span>{t('feedback_steps')}</span><textarea value={form.reproduction_steps} onChange={change('reproduction_steps')} maxLength={3000} rows={4} placeholder={t('feedback_steps_placeholder')} /></label>
              <label><span>{t('feedback_expected')}</span><textarea value={form.expected_result} onChange={change('expected_result')} maxLength={3000} rows={3} /></label>
              <label><span>{t('feedback_actual')}</span><textarea value={form.actual_result} onChange={change('actual_result')} maxLength={3000} rows={3} /></label>
            </>}
          </div>
          <div className="feedback-form__footer">
            <label className="feedback-upload"><ImageOutlined /><span>{form.image?.name || t('feedback_attach')}</span><input type="file" accept="image/png,image/jpeg,image/webp" onChange={change('image')} /></label>
            <span>{t('feedback_context_hint')}</span>
            <button className="btn" type="submit" disabled={saving}><SendRounded />{saving ? t('feedback_sending') : t('feedback_send')}</button>
          </div>
        </form>
      ) : (
        <section className="feedback-workspace" aria-busy={loading}>
          <aside className="card feedback-ticket-list">
            <div className="feedback-ticket-list__head"><span>{t('feedback_mine')}</span><b>{tickets.length}</b></div>
            {loading && <div className="feedback-empty">{t('common_loading')}</div>}
            {!loading && tickets.length === 0 && <div className="feedback-empty"><ForumOutlined /><strong>{t('feedback_empty')}</strong><span>{t('feedback_empty_hint')}</span></div>}
            {!loading && tickets.map((ticket) => <button type="button" className={`feedback-ticket-row${selected?.id === ticket.id ? ' is-selected' : ''}`} key={ticket.id} onClick={() => openTicket(ticket)}>
              <span className="feedback-ticket-row__meta"><b>{ticket.reference}</b><time>{formatter.format(new Date(ticket.updated_at))}</time></span>
              <strong>{ticket.title}</strong>
              <span className={statusClass(ticket.status)}>{t(`feedback_status_${ticket.status}`)}</span>
            </button>)}
          </aside>
          <article className="card feedback-thread">
            {!selected ? <div className="feedback-empty"><ForumOutlined /><strong>{t('feedback_select')}</strong></div> : <>
              <header className="feedback-thread__head">
                <div><span>{selected.reference}</span><h2>{selected.title}</h2><small>{formatter.format(new Date(selected.created_at))}</small></div>
                <span className={statusClass(selected.status)}>{t(`feedback_status_${selected.status}`)}</span>
              </header>
              <div className="feedback-thread__body">
                <section className="feedback-original">
                  <p>{selected.description}</p>
                  {selected.reproduction_steps && <div><b>{t('feedback_steps')}</b><p>{selected.reproduction_steps}</p></div>}
                  {(selected.expected_result || selected.actual_result) && <div className="feedback-original__comparison">
                    {selected.expected_result && <div><b>{t('feedback_expected')}</b><p>{selected.expected_result}</p></div>}
                    {selected.actual_result && <div><b>{t('feedback_actual')}</b><p>{selected.actual_result}</p></div>}
                  </div>}
                  {selected.attachment_url && <a className="feedback-attachment" href={selected.attachment_url} target="_blank" rel="noreferrer"><img src={selected.attachment_url} alt={t('feedback_attachment_alt')} /></a>}
                </section>
                {selected.messages.map((message) => <div className={`feedback-message${message.is_admin ? ' is-admin' : ''}`} key={message.id}>
                  <div><strong>{message.author_name}</strong><time>{formatter.format(new Date(message.created_at))}</time></div><p>{message.body}</p>
                </div>)}
              </div>
              {selected.status !== 'closed' && <form className="feedback-reply" onSubmit={sendReply}><textarea value={reply} onChange={(event) => setReply(event.target.value)} minLength={2} maxLength={4000} rows={3} placeholder={t('feedback_reply_placeholder')} /><button className="btn" type="submit" disabled={saving || reply.trim().length < 2}><SendRounded />{t('feedback_reply')}</button></form>}
            </>}
          </article>
        </section>
      )}
    </main>
  );
};

export default FeedbackPage;
