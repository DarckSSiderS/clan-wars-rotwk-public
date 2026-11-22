import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Button, CircularProgress } from '@mui/material';
import { NotificationsActiveOutlined } from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import { presenceService } from '../services/presenceService';
import './PlayerPresence.css';

const relativeLastSeen = (value, language) => {
  const timestamp = Date.parse(value || '');
  if (!Number.isFinite(timestamp)) return null;
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  const locale = language === 'de' ? 'de-DE' : language === 'en' ? 'en-GB' : 'ru-RU';
  const formatter = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  if (seconds < 60) return formatter.format(-seconds, 'second');
  if (seconds < 3600) return formatter.format(-Math.round(seconds / 60), 'minute');
  if (seconds < 86400) return formatter.format(-Math.round(seconds / 3600), 'hour');
  return formatter.format(-Math.round(seconds / 86400), 'day');
};

export const PresenceBadge = ({ presence, language = 'ru', showLastSeen = true }) => {
  if (!presence) {
    const checking = language === 'de' ? 'Status wird geprüft' : language === 'en' ? 'Checking status' : 'Проверяем статус';
    return (
      <span className="player-presence-badge is-checking">
        <i aria-hidden="true" />
        {checking}
      </span>
    );
  }
  const isOnline = Boolean(presence?.is_online);
  const lastSeen = showLastSeen ? relativeLastSeen(presence?.last_seen_at, language) : null;
  const lastSeenPrefix = language === 'de' ? 'Zuletzt' : language === 'en' ? 'Seen' : 'Был(а)';
  const label = isOnline
    ? 'Online'
    : lastSeen
      ? `${lastSeenPrefix} ${lastSeen}`
      : 'Offline';

  return (
    <span className={`player-presence-badge ${isOnline ? 'is-online' : 'is-offline'}`}>
      <i aria-hidden="true" />
      {label}
    </span>
  );
};

const PlayerPresence = ({ userId, isClaimed = true, language = 'ru', t }) => {
  const { isAuthenticated, user: currentUser } = useAuth();
  const [presence, setPresence] = useState(null);
  const [requestState, setRequestState] = useState('idle');
  const [message, setMessage] = useState('');
  const cooldownRef = useRef(null);
  const isOwnProfile = Number(currentUser?.id) === Number(userId);

  const loadPresence = useCallback(async () => {
    if (!userId) return;
    try {
      const [nextPresence] = await presenceService.getMany([userId]);
      if (nextPresence) setPresence(nextPresence);
    } catch {
      // A failed background check must not replace a previously known state.
    }
  }, [userId]);

  useEffect(() => {
    loadPresence();
    const interval = window.setInterval(loadPresence, 30_000);
    window.addEventListener('focus', loadPresence);
    return () => {
      window.clearInterval(interval);
      window.removeEventListener('focus', loadPresence);
    };
  }, [loadPresence]);

  useEffect(() => () => window.clearTimeout(cooldownRef.current), []);

  const requestOnline = async () => {
    setRequestState('loading');
    setMessage('');
    try {
      const result = await presenceService.requestOnline(userId);
      if (result.status === 'already_online') {
        setPresence(result);
        setMessage(t('presence_already_online', 'Игрок уже online.'));
      } else {
        setMessage(t('presence_request_sent', 'Запрос отправлен.'));
      }
      setRequestState('sent');
      window.clearTimeout(cooldownRef.current);
      cooldownRef.current = window.setTimeout(() => {
        setRequestState('idle');
        setMessage('');
      }, Number(result.cooldown_seconds || 60) * 1000);
    } catch (error) {
      setMessage(error.response?.data?.detail || t('presence_request_error', 'Не удалось отправить запрос online.'));
      setRequestState('error');
    }
  };

  return (
    <div className="player-presence">
      <PresenceBadge presence={presence} language={language} />
      {isAuthenticated && !isOwnProfile && isClaimed && presence && !presence.is_online && (
        <Button
          size="small"
          variant="text"
          startIcon={requestState === 'loading' ? <CircularProgress size={14} /> : <NotificationsActiveOutlined />}
          disabled={requestState === 'loading' || requestState === 'sent'}
          onClick={requestOnline}
        >
          {requestState === 'sent'
            ? t('presence_requested', 'Запрос отправлен')
            : t('presence_request_online', 'Запросить online')}
        </Button>
      )}
      {message && (
        <span
          className={`player-presence__message${requestState === 'error' ? ' is-error' : ''}`}
          role="status"
        >
          {message}
        </span>
      )}
    </div>
  );
};

export default PlayerPresence;
