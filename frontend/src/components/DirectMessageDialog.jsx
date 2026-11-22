import React, { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
} from '@mui/material';
import { messagingService } from '../services/messagingService';
import { useRealtimeEvent } from '../contexts/RealtimeContext';
import { confirmAction, showSuccess } from '../utils/notifications';
import { getPlayerDisplayName } from '../utils/playerIdentity';
import './DirectMessageDialog.css';

const DirectMessageDialog = ({ open, onClose, username, currentUser, t }) => {
  const [conversation, setConversation] = useState(null);
  const [messages, setMessages] = useState([]);
  const [body, setBody] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [reportingId, setReportingId] = useState(null);
  const [reportReason, setReportReason] = useState('');
  const threadRef = useRef(null);

  const loadThread = async (conversationId, quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const thread = await messagingService.getMessages(conversationId);
      setMessages(thread.messages || []);
      setError('');
    } catch (requestError) {
      if (!quiet) setError(requestError.response?.data?.detail || t('messages_load_error', 'Не удалось загрузить диалог.'));
    } finally {
      if (!quiet) setLoading(false);
    }
  };

  useEffect(() => {
    if (!open || !username) return undefined;
    let active = true;
    setLoading(true);
    setError('');
    messagingService.open(username)
      .then(async (openedConversation) => {
        if (!active) return;
        setConversation(openedConversation);
        await loadThread(openedConversation.id);
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.response?.data?.detail || t('messages_open_error', 'Не удалось открыть диалог.'));
          setLoading(false);
        }
      });
    return () => { active = false; };
    // loadThread is scoped to this dialog and intentionally initialized per open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, username, t]);

  useRealtimeEvent((event) => {
    if (!open || Number(event.conversation_id) !== Number(conversation?.id)) return;
    if (event.type === 'message.created' && event.message) {
      setMessages((current) => current.some((message) => message.id === event.message.id)
        ? current
        : [...current, event.message]);
      if (event.message.sender_id !== currentUser?.id) {
        loadThread(conversation.id, true);
      }
    } else if (event.type === 'messages.read') {
      const messageIds = new Set(event.message_ids || []);
      setMessages((current) => current.map((message) => messageIds.has(message.id)
        ? { ...message, read_at: event.read_at }
        : message));
    }
  });

  useEffect(() => {
    if (!threadRef.current) return;
    threadRef.current.scrollTop = threadRef.current.scrollHeight;
  }, [messages]);

  const sendMessage = async (event) => {
    event.preventDefault();
    const normalized = body.trim();
    if (!conversation?.id || !normalized || sending) return;
    setSending(true);
    setError('');
    try {
      const message = await messagingService.send(conversation.id, normalized);
      setMessages((current) => current.some((item) => item.id === message.id)
        ? current
        : [...current, message]);
      setBody('');
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t('messages_send_error', 'Не удалось отправить сообщение.'));
    } finally {
      setSending(false);
    }
  };

  const blockUser = async () => {
    const confirmed = await confirmAction(
      t('messages_block_confirm', 'Заблокировать пользователя? Он больше не сможет отправлять вам сообщения.'),
      t('messages_block_title', 'Блокировка пользователя'),
    );
    if (!confirmed) return;
    setLoading(true);
    try {
      await messagingService.block(username);
      showSuccess(t('messages_blocked', 'Пользователь заблокирован.'));
      onClose();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t('messages_block_error', 'Не удалось заблокировать пользователя.'));
      setLoading(false);
    }
  };

  const reportMessage = async (messageId) => {
    if (reportReason.trim().length < 3) return;
    try {
      await messagingService.report(messageId, reportReason.trim());
      showSuccess(t('messages_reported', 'Жалоба отправлена модераторам.'));
      setReportingId(null);
      setReportReason('');
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t('messages_report_error', 'Не удалось отправить жалобу.'));
    }
  };

  return (
    <Dialog className="direct-message-dialog" open={open} onClose={() => !sending && onClose()} fullWidth maxWidth="sm">
      <DialogTitle>
        <span>{t('messages_title', 'Сообщение')}</span>
        <small>{getPlayerDisplayName(username)}</small>
      </DialogTitle>
      <DialogContent className="direct-message-dialog__content">
        {error && <Alert severity="error" sx={{ mb: 1.5 }}>{error}</Alert>}
        <div className="direct-message-thread" ref={threadRef} aria-live="polite">
          {messages.map((message) => {
            const outgoing = message.sender_id === currentUser?.id;
            return (
              <article className={`direct-message${outgoing ? ' is-outgoing' : ' is-incoming'}`} key={message.id}>
                <div>
                  <p>{message.body}</p>
                  <time>{new Date(message.created_at).toLocaleString()}</time>
                </div>
                {!outgoing && (
                  <button type="button" onClick={() => setReportingId(reportingId === message.id ? null : message.id)}>
                    {t('messages_report', 'Пожаловаться')}
                  </button>
                )}
                {reportingId === message.id && (
                  <div className="direct-message-report">
                    <TextField
                      size="small"
                      fullWidth
                      value={reportReason}
                      onChange={(event) => setReportReason(event.target.value)}
                      label={t('messages_report_reason', 'Причина жалобы')}
                    />
                    <Button size="small" disabled={reportReason.trim().length < 3} onClick={() => reportMessage(message.id)}>
                      {t('messages_report_send', 'Отправить')}
                    </Button>
                  </div>
                )}
              </article>
            );
          })}
          {!loading && !messages.length && <div className="direct-message-thread__empty">{t('messages_empty', 'Начните разговор первым.')}</div>}
          {loading && <div className="direct-message-thread__empty">{t('common_loading', 'Загрузка...')}</div>}
        </div>

        <form className="direct-message-compose" onSubmit={sendMessage}>
          <TextField
            fullWidth
            multiline
            minRows={2}
            maxRows={5}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            placeholder={t('messages_placeholder', 'Напишите сообщение...')}
            inputProps={{ maxLength: 2000 }}
          />
          <Button type="submit" variant="contained" disabled={sending || !body.trim()}>
            {sending ? t('messages_sending', 'Отправка...') : t('messages_send', 'Отправить')}
          </Button>
        </form>
      </DialogContent>
      <DialogActions className="direct-message-dialog__actions">
        <Button color="error" onClick={blockUser} disabled={loading || sending}>{t('messages_block', 'Заблокировать')}</Button>
        <Button onClick={onClose} disabled={sending}>{t('common_close', 'Закрыть')}</Button>
      </DialogActions>
    </Dialog>
  );
};

export default DirectMessageDialog;
