import React, { lazy, Suspense, useEffect, useRef, useState } from 'react';
import { Dialog, DialogContent, DialogTitle, IconButton } from '@mui/material';
import { Close, Refresh } from '@mui/icons-material';
import { useLocalizationContext } from '../../contexts/LocalizationContext';
import { clanService } from '../../services/clanService';
import { cycleCampaignService as service } from '../../services/cycleCampaignService';
import CycleScouting from '../campaign/CycleScouting';
import { preparationMessage, scoutOrderAvailable } from '../../utils/cyclePreparationView';
import { mapCommandMessage } from '../../utils/cycleMapCommandView';
import CycleMapOrders from './CycleMapOrders';
import './CycleMapCommands.css';

const Reinforcements = lazy(() => import('../../pages/CycleReinforcementsPage').then(module => ({ default: module.ReinforcementsContent })));

function MapScouting({ cycleId, territoryId, onUpdate, onBusyChange }) {
  const { language } = useLocalizationContext();
  const copy = key => preparationMessage(key, language);
  const [data, setData] = useState(null), [failed, setFailed] = useState(false), [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState(null), [attempt, setAttempt] = useState(0), [clanless, setClanless] = useState(false);
  const writing = useRef(false), generation = useRef(0), mounted = useRef(false);
  useEffect(() => {
    let active = true;
    mounted.current = true;
    async function load() {
      if (writing.current) return;
      const token = ++generation.current;
      try {
        const clan = await clanService.getMyClan();
        if (!clan) { if (active && token === generation.current) setClanless(true); return; }
        const next = await service.getPreparation(cycleId, clan.id);
        if (active && token === generation.current) {
          setData(next); setFailed(false);
          setConfirmation(previous => previous && !scoutOrderAvailable(next, previous.payload) ? { ...previous, stale: true } : previous);
        }
      } catch { if (active && token === generation.current) setFailed(true); }
    }
    load();
    const timer = setInterval(load, 15000);
    return () => { active = false; mounted.current = false; clearInterval(timer); };
  }, [cycleId, attempt]);
  async function order() {
    if (failed || !confirmation || confirmation.stale || !scoutOrderAvailable(data, confirmation.payload) || writing.current) return;
    writing.current = true; generation.current++;
    setBusy(true); onBusyChange(true);
    try {
      await service.preparationCommand(cycleId, data.clan_id, 'scout', confirmation.payload);
      const next = await service.getPreparation(cycleId, data.clan_id);
      if (!mounted.current) return;
      setData(next); setFailed(false); onUpdate();
    } catch { if (mounted.current) setFailed(true); }
    finally { writing.current = false; if (mounted.current) { setBusy(false); setConfirmation(null); } onBusyChange(false); }
  }
  if (clanless) return <p>{copy('clanless')}</p>;
  return <div className="cycle-map-scouting">
    <button disabled={busy} onClick={() => setAttempt(value => value + 1)} title={copy('refresh')} aria-label={copy('refresh')}><Refresh aria-hidden="true" /></button>
    {failed && <p role="alert">{copy('failed')}</p>}
    {!data ? <p role="status">{copy('loading')}</p> : <CycleScouting data={data} territoryId={territoryId} disabled={busy || failed || Boolean(confirmation)} onOrder={(target, scoutUserId) => setConfirmation({
      payload: { territory_id: target, scout_user_id: scoutUserId, expected_revision: data.scout.wallet_revision },
      scoutName: data.scout.players.find(player => player.user_id === scoutUserId)?.name,
    })} />}
    <Dialog open={Boolean(confirmation)} onClose={() => !busy && setConfirmation(null)} aria-labelledby="map-scout-confirm"><DialogTitle id="map-scout-confirm">{copy('order')}</DialogTitle>
      <DialogContent><p>{data?.territories.find(land => land.id === confirmation?.payload.territory_id)?.name}</p><p>{copy('scoutPlayer')}: {confirmation?.scoutName}</p><p>{copy('scoutLock')}</p><p>{copy('paid')}</p>
        {confirmation && (confirmation.stale || !scoutOrderAvailable(data, confirmation.payload)) && <p role="alert">{copy('scoutStale')}</p>}
      </DialogContent>
      <div className="cycle-map-dialog-actions"><button autoFocus disabled={busy} onClick={() => setConfirmation(null)}>{copy('cancel')}</button><button disabled={busy || failed || confirmation?.stale || !scoutOrderAvailable(data, confirmation?.payload)} onClick={order}>{copy('confirm')}</button></div>
    </Dialog>
  </div>;
}

export default function CycleMapCommands({ action, onClose, cycleId, territoryId, territoryName, onUpdate }) {
  const { language } = useLocalizationContext();
  const [working, setWorking] = useState(false);
  const copy = key => mapCommandMessage(key, language);
  const titleId = React.useId();
  return <Dialog open={Boolean(action)} onClose={() => !working && onClose()} fullWidth maxWidth="md" className="cycle-map-command-dialog" aria-labelledby={titleId}>
    <DialogTitle id={titleId}><span>{copy(action?.kind || 'orders')} · {territoryName || `#${territoryId}`}</span><IconButton disabled={working} onClick={onClose} aria-label={copy('close')} title={copy('close')}><Close /></IconButton></DialogTitle>
    <DialogContent><Suspense fallback={<p role="status">{copy('loading')}</p>}>
      {action?.kind === 'orders' && <CycleMapOrders cycleId={cycleId} territoryId={territoryId} onUpdate={onUpdate} onBusyChange={setWorking} />}
      {action?.kind === 'scout' && <MapScouting key={`${cycleId}:${territoryId}`} cycleId={cycleId} territoryId={territoryId} onUpdate={onUpdate} onBusyChange={setWorking} />}
      {action?.kind === 'reinforcements' && <Reinforcements cycleId={cycleId} targetTerritoryId={territoryId} targetRecipientId={action.recipient} targetRequestId={action.request} embedded onUpdate={onUpdate} onBusyChange={setWorking} />}
    </Suspense></DialogContent>
  </Dialog>;
}
