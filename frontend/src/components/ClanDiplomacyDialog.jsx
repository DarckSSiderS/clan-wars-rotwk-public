import React, { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  TextField,
} from '@mui/material';
import { diplomacyService } from '../services/diplomacyService';

const STATUS_LABELS = {
  pending_alliance: 'diplomacy_status_pending_alliance',
  allied: 'diplomacy_status_allied',
  hostile: 'diplomacy_status_hostile',
  neutral: 'diplomacy_status_neutral',
};

const ClanDiplomacyDialog = ({ open, onClose, myClan, clans, t, onChanged }) => {
  const [relations, setRelations] = useState([]);
  const [targetClanId, setTargetClanId] = useState('');
  const [action, setAction] = useState('propose_alliance');
  const [note, setNote] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const availableClans = useMemo(
    () => clans.filter((clan) => clan.id !== myClan?.id && !clan.is_admin_clan),
    [clans, myClan?.id],
  );

  const loadRelations = async () => {
    if (!myClan?.id) return;
    setLoading(true);
    setError('');
    try {
      setRelations(await diplomacyService.list(myClan.id));
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t('diplomacy_load_error', 'Не удалось загрузить дипломатические отношения.'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) loadRelations();
    // loadRelations intentionally runs only when the modal opens or the clan changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, myClan?.id]);

  const otherClan = (relation) => (
    relation.clan_low.id === myClan?.id ? relation.clan_high : relation.clan_low
  );

  const runAction = async (otherId, nextAction = action) => {
    if (!myClan?.id || !otherId) return;
    setLoading(true);
    setError('');
    try {
      await diplomacyService.act(myClan.id, otherId, nextAction, note);
      setNote('');
      await loadRelations();
      onChanged?.();
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t('diplomacy_action_error', 'Не удалось изменить дипломатический статус.'));
      setLoading(false);
    }
  };

  return (
    <Dialog className="diplomacy-dialog" open={open} onClose={() => !loading && onClose()} fullWidth maxWidth="md">
      <DialogTitle>{t('diplomacy_dialog_title', 'Дипломатия клана')}</DialogTitle>
      <DialogContent>
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <section className="diplomacy-dialog__form">
          <TextField
            select
            fullWidth
            label={t('diplomacy_target_clan', 'Клан')}
            value={targetClanId}
            onChange={(event) => setTargetClanId(event.target.value)}
          >
            {availableClans.map((clan) => <MenuItem key={clan.id} value={clan.id}>{clan.name}</MenuItem>)}
          </TextField>
          <TextField
            select
            fullWidth
            label={t('diplomacy_action', 'Действие')}
            value={action}
            onChange={(event) => setAction(event.target.value)}
          >
            <MenuItem value="propose_alliance">{t('diplomacy_propose_alliance', 'Предложить союз')}</MenuItem>
            <MenuItem value="declare_hostility">{t('diplomacy_declare_hostility', 'Объявить вражду')}</MenuItem>
            <MenuItem value="set_neutral">{t('diplomacy_set_neutral', 'Установить нейтралитет')}</MenuItem>
          </TextField>
          <TextField
            fullWidth
            label={t('diplomacy_note', 'Послание')}
            value={note}
            onChange={(event) => setNote(event.target.value)}
            inputProps={{ maxLength: 500 }}
          />
          <Button variant="contained" disabled={loading || !targetClanId} onClick={() => runAction(Number(targetClanId))}>
            {t('diplomacy_send', 'Отправить')}
          </Button>
        </section>

        <section className="diplomacy-dialog__relations">
          <h3>{t('diplomacy_current_relations', 'Текущие отношения')}</h3>
          {relations.map((relation) => {
            const counterpart = otherClan(relation);
            const incoming = relation.status === 'pending_alliance'
              && relation.requested_by_clan_id !== myClan.id;
            return (
              <article className={`diplomacy-relation is-${relation.status}`} key={relation.id}>
                <span className="diplomacy-relation__crest" style={{ '--relation-color': counterpart.map_color || '#74633e' }}>
                  {counterpart.name.slice(0, 1).toUpperCase()}
                </span>
                <div><b>{counterpart.name}</b><small>{STATUS_LABELS[relation.status] ? t(STATUS_LABELS[relation.status]) : relation.status}</small></div>
                <div className="diplomacy-relation__actions">
                  {incoming && <Button size="small" variant="contained" onClick={() => runAction(counterpart.id, 'accept_alliance')}>{t('diplomacy_accept', 'Принять')}</Button>}
                  {incoming && <Button size="small" color="error" onClick={() => runAction(counterpart.id, 'reject_alliance')}>{t('diplomacy_reject', 'Отклонить')}</Button>}
                  {(relation.status === 'allied' || relation.status === 'hostile') && <Button size="small" onClick={() => runAction(counterpart.id, 'set_neutral')}>{t('diplomacy_set_neutral', 'Нейтралитет')}</Button>}
                </div>
              </article>
            );
          })}
          {!loading && !relations.length && <p className="diplomacy-dialog__empty">{t('diplomacy_empty', 'Дипломатических соглашений пока нет.')}</p>}
        </section>
      </DialogContent>
      <DialogActions><Button onClick={onClose} disabled={loading}>{t('common_close', 'Закрыть')}</Button></DialogActions>
    </Dialog>
  );
};

export default ClanDiplomacyDialog;
