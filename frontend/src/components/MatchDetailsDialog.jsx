import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
} from '@mui/material';
import {
  CloseRounded,
  DownloadRounded,
  MapRounded,
  OpenInFullRounded,
  SportsEsportsRounded,
} from '@mui/icons-material';

import { apiFetch } from '../services/apiFetch';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { getFactionIcon, getFactionName } from '../data/factions';
import { formatMoscowDateTime, asUtcIsoTime } from '../utils/dateTime';
import { withAppBase, isAdminPreview } from '../utils/appBasePath';
import PlayerIdentity from './PlayerIdentity';
import './MatchDetailsDialog.css';

const formatDuration = (value, fallback) => {
  if (value == null || value === '') return fallback;
  if (typeof value === 'string') return value;
  const seconds = Math.max(0, Math.round(Number(value) || 0));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
};

const formatFileSize = (value) => {
  const bytes = Number(value || 0);
  if (!bytes) return '';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const participantName = (participant) => participant?.username || participant?.nickname || '—';
const ratingPatchLabel = (match) => match?.patch_name || ({
  ennorath: 'Ennorath',
  patch_202: 'Patch 2.02',
}[match?.rating_patch_family]) || match?.patch_version || '—';

const MatchDetailsDialog = ({ open, matchRef, initialMatch = null, onClose, children }) => {
  const { getLocalizedText: t, language } = useLocalizationContext();
  const [match, setMatch] = useState(initialMatch);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewBroken, setPreviewBroken] = useState(false);

  useEffect(() => {
    if (!open || matchRef == null || matchRef === '') return undefined;
    const controller = new AbortController();
    setMatch(initialMatch);
    setLoading(true);
    setError('');
    setPreviewOpen(false);
    setPreviewBroken(false);

    apiFetch(`/api/v1/statistics/matches/${encodeURIComponent(String(matchRef))}`, {
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(payload.detail || t('match_details_load_error', 'Не удалось загрузить детали матча'));
        }
        return response.json();
      })
      .then(setMatch)
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') setError(requestError.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [initialMatch, matchRef, open, t]);

  const participants = useMemo(
    () => (match?.participants || []).filter((participant) => !participant.is_observer),
    [match?.participants],
  );
  const winners = participants.filter((participant) => participant.is_winner);
  const losers = participants.filter((participant) => !participant.is_winner);
  const title = match?.map_name || initialMatch?.map_name || t('match_details_title', 'Детали матча');
  const patch = ratingPatchLabel(match);
  const previewExample = isAdminPreview && String(match?.match_id || '').startsWith('demo-preview-');
  const metadata = match ? [
    [t('matches_date', 'Дата'), formatMoscowDateTime(asUtcIsoTime(match.match_date), '—', language)],
    [t('match_details_duration', 'Длительность'), formatDuration(match.duration, '—')],
    [t('matches_format', 'Формат матча'), match.game_mode || '—'],
    [t('match_details_patch', 'Патч'), patch],
    [t('match_details_game', 'Игра'), match.game_name || 'RotWK'],
    [t('match_details_arena', 'Арена'), match.arena_id || '—'],
  ] : [];

  const renderTeam = (items, winner) => (
    <section className={`match-details-team ${winner ? 'is-winner' : 'is-loser'}`}>
      <header>
        <span>{winner ? t('matches_winning_team', 'Победившая команда') : t('matches_losing_team', 'Проигравшая команда')}</span>
        <strong>{winner ? t('profile_match_win', 'Победа') : t('profile_match_loss', 'Поражение')}</strong>
      </header>
      <div className="match-details-team__players">
        {items.length ? items.map((participant, index) => (
          <article key={participant.id || `${participantName(participant)}-${index}`}>
            <img src={getFactionIcon(participant.faction, 'large')} alt="" />
            <div>
              <PlayerIdentity username={participantName(participant)} />
              <span>{getFactionName(participant.faction, language) || t('matches_faction_unknown', 'Фракция не указана')}</span>
            </div>
            <dl>
              <div><dt>Elo · {patch}</dt><dd>{participant.elo_is_verified === false ? t('match_rating_unverified') : participant.elo == null ? '—' : Math.round(Number(participant.elo))}</dd></div>
              <div>
                <dt>{t('match_details_rank', 'Ранг')}</dt>
                <dd>{participant.old_rank ?? '—'} → {participant.new_rank ?? '—'}</dd>
              </div>
            </dl>
          </article>
        )) : <p>{t('match_details_team_unknown', 'Состав команды не указан')}</p>}
      </div>
    </section>
  );

  return (
    <>
      <Dialog
        open={Boolean(open)}
        onClose={onClose}
        fullWidth
        maxWidth="lg"
        slotProps={{ paper: { className: 'match-details-dialog' } }}
      >
        <DialogTitle className="match-details-dialog__title">
          <span><SportsEsportsRounded />{title}</span>
          <IconButton aria-label={t('common_close', 'Закрыть')} onClick={onClose}><CloseRounded /></IconButton>
        </DialogTitle>
        <DialogContent dividers className="match-details-dialog__content">
          {children}
          {loading && !match ? (
            <div className="match-details-state"><CircularProgress size={36} /><span>{t('match_details_loading', 'Загружаем матч')}</span></div>
          ) : error && !match ? (
            <Alert severity="error">{error}</Alert>
          ) : match ? (
            <>
              {error && <Alert severity="warning">{error}</Alert>}
              {match.rating_warning && <Alert severity="warning">{t('match_rating_warning')}</Alert>}
              <section className="match-details-overview">
                <button
                  className="match-details-map"
                  type="button"
                  disabled={!match.map_preview_url || previewBroken}
                  onClick={() => setPreviewOpen(true)}
                  aria-label={t('matches_enlarge_map', 'Увеличить карту {map}', { map: match.map_name || '' })}
                >
                  {match.map_preview_url && !previewBroken ? (
                    <img src={withAppBase(match.map_preview_url)} alt={t('match_details_map_alt', null, { map: match.map_name || '' })} onError={() => setPreviewBroken(true)} />
                  ) : <MapRounded aria-hidden="true" />}
                  {match.map_preview_url && !previewBroken && <span><OpenInFullRounded />{t('match_details_enlarge', 'Увеличить')}</span>}
                </button>
                <div className="match-details-overview__copy">
                  <div className="match-details-chips">
                    {previewExample ? <Chip className="match-details-chip match-details-chip--neutral" size="small" label={t('match_details_preview_example')} /> : match.is_valid != null && (
                      <Chip
                        className={`match-details-chip match-details-chip--${match.is_valid ? 'valid' : 'invalid'}`}
                        size="small"
                        label={match.is_valid ? t('match_details_valid', 'Подтверждён Arena') : t('match_details_invalid', 'Не подтверждён Arena')}
                      />
                    )}
                    {match.is_qualification_round && <Chip className="match-details-chip match-details-chip--neutral" size="small" label={t('match_details_qualification', 'Квалификация')} />}
                    {match.elo_delta != null && <Chip className="match-details-chip match-details-chip--neutral" size="small" label={`Elo · ${patch} ±${Math.abs(Number(match.elo_delta))}`} />}
                  </div>
                  <dl className="match-details-metadata">
                    {metadata.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
                  </dl>
                  <div className="match-details-arena-stats">
                    <span><b>{Number(match.downloads || 0).toLocaleString(language)}</b>{t('match_details_downloads', 'скачиваний')}</span>
                    <span><b>{match.likes?.length || 0}</b>{t('match_details_likes', 'оценок')}</span>
                    <span><b>{match.comments?.length || 0}</b>{t('match_details_comments', 'комментариев')}</span>
                  </div>
                </div>
              </section>
              <div className="match-details-teams">
                {renderTeam(winners, true)}
                {renderTeam(losers, false)}
              </div>
            </>
          ) : null}
        </DialogContent>
        <DialogActions className="match-details-dialog__actions">
          {!previewExample && match?.replay_supported && match.replay_download_url ? (
            <Button component="a" href={withAppBase(match.replay_download_url)} startIcon={<DownloadRounded />} variant="contained">
              {t('match_details_download_replay', 'Скачать replay')}{formatFileSize(match.replay_file_size) ? ` · ${formatFileSize(match.replay_file_size)}` : ''}
            </Button>
          ) : <span>{match ? t('match_details_replay_unavailable', 'Replay для этого матча недоступен') : ''}</span>}
          <Button onClick={onClose}>{t('common_close', 'Закрыть')}</Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        maxWidth="lg"
        fullWidth
        slotProps={{ paper: { className: 'match-details-preview-dialog' } }}
      >
        <IconButton className="match-details-preview-dialog__close" aria-label={t('matches_close_map', 'Закрыть карту')} onClick={() => setPreviewOpen(false)}><CloseRounded /></IconButton>
        {match?.map_preview_url && <img src={withAppBase(match.map_preview_url)} alt={t('match_details_map_alt', null, { map: match.map_name || '' })} />}
      </Dialog>
    </>
  );
};

export default MatchDetailsDialog;
