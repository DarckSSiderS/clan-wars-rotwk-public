import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { MailOutlineRounded, RefreshRounded } from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import DirectMessageDialog from '../components/DirectMessageDialog';
import { messagingService } from '../services/messagingService';
import { useRealtimeEvent } from '../contexts/RealtimeContext';
import { getPlayerDisplayName } from '../utils/playerIdentity';
import './MessagesPage.css';

const MessagesPage = () => {
  const { user } = useAuth();
  const { getLocalizedText: t, language } = useLocalizationContext();
  const [searchParams, setSearchParams] = useSearchParams();
  const [conversations, setConversations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const selectedUsername = searchParams.get('with') || '';
  const dateFormatter = useMemo(() => new Intl.DateTimeFormat(language, {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }), [language]);

  const loadConversations = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    if (!quiet) setError('');
    try {
      setConversations(await messagingService.list());
    } catch (requestError) {
      if (!quiet) setError(requestError.response?.data?.detail || t('messages_list_error', 'Не удалось загрузить сообщения.'));
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [t]);

  useEffect(() => { loadConversations(); }, [loadConversations]);

  useRealtimeEvent((event) => {
    if (event.type === 'message.created' || event.type === 'messages.read') {
      loadConversations(true);
    }
  });

  const openConversation = (username) => {
    setSearchParams({ with: username });
  };

  const closeConversation = () => {
    setSearchParams({});
    loadConversations();
  };

  return (
    <main className="prototype-exact-page messages-page">
      <header className="page-title messages-page__header">
        <div>
          <div className="eyebrow">{t('messages_eyebrow', 'Личная связь')}</div>
          <h1 className="serif">{t('messages_page_title', 'Сообщения')}</h1>
          <p className="subtitle">{t('messages_page_subtitle', 'Здесь можно читать личные сообщения и продолжать разговоры с игроками.')}</p>
        </div>
        <button className="btn" type="button" onClick={loadConversations} disabled={loading}>
          <RefreshRounded />
          {t('messages_refresh', 'Обновить')}
        </button>
      </header>

      <section className="card messages-inbox" aria-busy={loading}>
        <div className="messages-inbox__heading">
          <span>{t('messages_dialogs', 'Диалоги')}</span>
          <b>{conversations.length}</b>
        </div>

        {error && <div className="messages-inbox__state is-error" role="alert">{error}</div>}
        {!error && loading && <div className="messages-inbox__state" role="status">{t('common_loading', 'Загрузка...')}</div>}
        {!error && !loading && conversations.length === 0 && (
          <div className="messages-inbox__state">
            <MailOutlineRounded />
            <strong>{t('messages_no_dialogs', 'Диалогов пока нет')}</strong>
            <span>{t('messages_no_dialogs_copy', 'Откройте профиль игрока и нажмите «Написать», чтобы начать разговор.')}</span>
            <Link className="btn" to="/ranking">{t('messages_find_player', 'Найти игрока')}</Link>
          </div>
        )}

        {!error && !loading && conversations.map((conversation) => {
          const counterpart = conversation.counterpart;
          const counterpartName = getPlayerDisplayName(counterpart);
          const lastMessage = conversation.last_message;
          return (
            <button
              className={`messages-inbox__row${conversation.unread_count ? ' is-unread' : ''}`}
              type="button"
              key={conversation.id}
              onClick={() => openConversation(counterpartName)}
            >
              <span className="messages-inbox__avatar">
                {counterpart.avatar_url
                  ? <img src={counterpart.avatar_url} alt="" />
                  : counterpartName.slice(0, 1).toUpperCase()}
              </span>
              <span className="messages-inbox__copy">
                <strong>{counterpartName}</strong>
                <span>{lastMessage?.body || t('messages_empty', 'Начните разговор первым.')}</span>
              </span>
              <span className="messages-inbox__meta">
                {lastMessage?.created_at && <time dateTime={lastMessage.created_at}>{dateFormatter.format(new Date(lastMessage.created_at))}</time>}
                {conversation.unread_count > 0 && <b>{conversation.unread_count > 99 ? '99+' : conversation.unread_count}</b>}
              </span>
            </button>
          );
        })}
      </section>

      <DirectMessageDialog
        open={Boolean(selectedUsername)}
        onClose={closeConversation}
        username={selectedUsername}
        currentUser={user}
        t={t}
      />
    </main>
  );
};

export default MessagesPage;
