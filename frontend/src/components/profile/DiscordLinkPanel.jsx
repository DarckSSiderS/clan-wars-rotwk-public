import React, { useEffect, useState } from 'react';
import { Alert, Button, Stack, TextField, Typography } from '@mui/material';
import { apiFetch } from '../../services/apiFetch';

export default function DiscordLinkPanel({ t }) {
  const [status, setStatus] = useState(null);
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    apiFetch('/api/v1/discord/link', { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error();
        setStatus(await response.json());
      })
      .catch((failure) => {
        if (failure.name !== 'AbortError') setError(t('discord_load_error', 'Не удалось загрузить привязку Discord. Откройте настройки ещё раз.'));
      });
    return () => controller.abort();
  }, [t]);

  const changeLink = async (remove) => {
    setBusy(true);
    setError('');
    setMessage('');
    try {
      const response = await apiFetch('/api/v1/discord/link', {
        method: remove ? 'DELETE' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        ...(remove ? {} : { body: JSON.stringify({ code: code.trim() }) }),
      });
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(typeof result.detail === 'string' ? result.detail : t('discord_action_error', 'Не удалось изменить привязку. Попробуйте ещё раз.'));
      }
      setStatus(remove ? { enabled: true, discord_user_id: null } : await response.json());
      setCode('');
      setMessage(remove
        ? t('discord_removed', 'Привязка отключена. Бот снимет клановый доступ при следующей синхронизации.')
        : t('discord_linked', 'Discord привязан. Бот обновит клановые роли в течение минуты.'));
    } catch (failure) {
      setError(failure.message);
    } finally {
      setBusy(false);
    }
  };

  if (status && !status.enabled) return null;
  return (
    <Stack spacing={1.5} component="section" aria-labelledby="discord-link-title" aria-busy={busy || (!status && !error)}>
      <Typography id="discord-link-title" component="h3" variant="subtitle1">Discord · {t('discord_bot_name', 'Палантир')}</Typography>
      {error && <Alert severity="error" role="alert">{error}</Alert>}
      {message && <Alert severity="success" role="status">{message}</Alert>}
      {!status && !error && <Typography role="status">{t('common_loading', 'Загрузка...')}</Typography>}
      {status?.discord_user_id ? (
        <>
          <Typography variant="body2">{t('discord_account', 'Привязанный Discord ID')}: {status.discord_user_id}</Typography>
          <Button variant="outlined" disabled={busy} onClick={() => changeLink(true)}>{t('discord_disconnect', 'Отключить Discord')}</Button>
        </>
      ) : status?.enabled ? (
        <>
          <Typography id="discord-link-help" variant="body2">{t('discord_link_help', 'Выполните /link на сервере bfmeCW и вставьте свой одноразовый код. Он действует 10 минут.')}</Typography>
          <TextField label={t('discord_code_label', 'Код от Палантира')} value={code} fullWidth
            onChange={(event) => setCode(event.target.value)} disabled={busy} autoComplete="off"
            error={Boolean(error)} inputProps={{ maxLength: 100, 'aria-describedby': 'discord-link-help', spellCheck: false }} />
          <Button variant="outlined" disabled={busy || code.trim().length < 20} onClick={() => changeLink(false)}>
            {busy ? t('discord_linking', 'Подтверждение...') : t('discord_connect', 'Привязать Discord')}
          </Button>
        </>
      ) : null}
    </Stack>
  );
}
