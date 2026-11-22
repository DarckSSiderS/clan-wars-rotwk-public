import React, { useEffect, useState } from 'react';
import { IconButton } from '@mui/material';
import { Handshake, Refresh } from '@mui/icons-material';
import { Link } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { useLocalizationContext } from '../../contexts/LocalizationContext';
import useCampaignNavigation from '../../hooks/useCampaignNavigation';
import { diplomacyService } from '../../services/diplomacyService';
import { cycleDiplomacyService } from '../../services/cycleDiplomacyService';
import { warService } from '../../services/warService';
import ClanDiplomacyDialog from '../ClanDiplomacyDialog';

function Shell({ t, action, children }) {
  return <div data-section="alliances">
    <div className="section-head"><div><div className="eyebrow">{t('clans_diplomacy')}</div><h2>{t('clans_alliances_wars')}</h2></div>{action}</div>
    <div className="card diplomacy">{children}</div>
  </div>;
}

function Retry({ t, onClick }) {
  return <><p role="alert">{t('clans_diplomacy_unavailable')}</p><IconButton onClick={onClick} title={t('common_refresh')} aria-label={t('common_refresh')}><Refresh /></IconButton></>;
}

function Relations({ mode, navigation, myClan, clans, user, t, onChanged }) {
  const [state, setState] = useState({ loading: true, error: false, relations: [], wars: [] });
  const [attempt, setAttempt] = useState(0);
  const [open, setOpen] = useState(false);
  const cycleId = navigation.cycleId;
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true, error: false, relations: [], wars: [] });
    const load = mode === 'cycle_v1'
      ? cycleDiplomacyService.getRelations(cycleId, { signal: controller.signal }).then(relations => ({ relations, wars: [] }))
      : Promise.all([diplomacyService.list(null, { signal: controller.signal }), warService.getWars()])
        .then(([relations, wars]) => ({ relations, wars: wars.filter(war => war.status === 'active' && war.defending_clan_id) }));
    load.then(data => {
      if (!Array.isArray(data.relations)) throw new Error('Invalid diplomacy response');
      if (!controller.signal.aborted) setState({ ...data, loading: false, error: false });
    }).catch(() => {
      if (!controller.signal.aborted) setState({ loading: false, error: true, relations: [], wars: [] });
    });
    return () => controller.abort();
  }, [mode, cycleId, attempt]);
  const allowed = mode === 'cycle_v1' ? ['allied', 'hostile'] : ['allied', 'hostile', 'pending_alliance'];
  const rows = state.relations.filter(row => allowed.includes(row.status) && row.clan_low && row.clan_high);
  const management = mode === 'cycle_v1'
    ? <IconButton component={Link} to={navigation.diplomacyHref} title={t('clans_open_diplomacy')} aria-label={t('clans_open_diplomacy')}><Handshake /></IconButton>
    : myClan?.leader_id === user.id && <IconButton onClick={() => setOpen(true)} title={t('diplomacy_manage')} aria-label={t('diplomacy_manage')}><Handshake /></IconButton>;
  return <>
    <Shell t={t} action={!state.loading && !state.error ? management : null}>
      {state.loading ? <p role="status">{t('common_loading')}</p> : state.error ? <Retry t={t} onClick={() => setAttempt(value => value + 1)} /> : <>
        {rows.slice(0, 5).map(row => <div key={`${row.clan_low.id}-${row.clan_high.id}`}>
          <span className={`dot ${row.status === 'allied' ? 'green' : row.status === 'hostile' ? 'red' : 'gold'}`} />
          <b>{t(row.status === 'allied' ? 'diplomacy_alliance' : row.status === 'hostile' ? 'diplomacy_hostility' : 'diplomacy_pending')}</b>
          <small>{row.clan_low.name} · {row.clan_high.name}</small>
        </div>)}
        {state.wars.slice(0, 5).map(war => <div key={`war-${war.id}`}><span className="dot red" /><b>{war.territory_name}</b><small>{war.attacking_clan_name} ↔ {war.defending_clan_name}</small></div>)}
        {!rows.length && !state.wars.length && <p>{t('clans_diplomacy_empty')}</p>}
      </>}
    </Shell>
    {mode === 'legacy' && <ClanDiplomacyDialog open={open} onClose={() => setOpen(false)} myClan={myClan} clans={clans} t={t}
      onChanged={() => { setAttempt(value => value + 1); onChanged(); }} />}
  </>;
}

function SignedInSummary(props) {
  const campaign = useCampaignNavigation();
  const { t } = props;
  if (campaign.loading) return <Shell t={t}><p role="status">{t('common_loading')}</p></Shell>;
  if (campaign.error) return <Shell t={t}><Retry t={t} onClick={campaign.refresh} /></Shell>;
  const { navigation } = campaign;
  if (navigation.mode === 'interseason' || (navigation.mode === 'cycle_v1' && !navigation.cycleId)) {
    return <Shell t={t}><p role="status">{t('clans_diplomacy_interseason')}</p></Shell>;
  }
  return <Relations key={`${navigation.mode}-${navigation.cycleId || 'legacy'}`} {...props} navigation={navigation} mode={navigation.mode} />;
}

export default function ClanDiplomacySummary(props) {
  const { user } = useAuth();
  const { t } = useLocalizationContext();
  return user ? <SignedInSummary key={user.id} {...props} user={user} t={t} />
    : <Shell t={t}><p>{t('clans_diplomacy_login')}</p></Shell>;
}
