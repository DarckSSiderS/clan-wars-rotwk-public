import React, { useState } from 'react';
import { Search } from '@mui/icons-material';
import { useLocalizationContext } from '../../contexts/LocalizationContext';
import { preparationMessage, scoutOrderAvailable } from '../../utils/cyclePreparationView';
import { mapCommandMessage } from '../../utils/cycleMapCommandView';
import { formatMoscowDateTime } from '../../utils/dateTime';

export default function CycleScouting(props) {
  const { data, territoryId } = props;
  const scope = JSON.stringify([data.cycle_id, data.clan_id, territoryId, data.scout.wallet_revision,
    data.scout.players?.map(player => player.user_id)]);
  return <ScoutingContent key={scope} {...props} />;
}

function ScoutingContent({ data, territoryId, disabled, onOrder }) {
  const { language } = useLocalizationContext();
  const [selection, setSelection] = useState('');
  const [scoutUserId, setScoutUserId] = useState('');
  const lockId = React.useId();
  const copy = key => preparationMessage(key, language);
  const target = territoryId ?? selection;
  const name = id => data.territories.find(land => land.id === id)?.name || `#${id}`;
  const players = data.scout.players || [];
  const unavailableKey = {
    no_free_players: 'noFreeScout', no_permission: 'scoutNoPermission', outside_preparation: 'scoutOutsidePreparation',
    cutoff_passed: 'scoutCutoffPassed', already_requested: 'scoutAlreadyRequested', economy_missing: 'scoutEconomyMissing',
  }[data.scout.unavailable_reason];
  const payload = { territory_id: Number(target), scout_user_id: Number(scoutUserId), expected_revision: data.scout.wallet_revision };
  const canOrder = !disabled && scoutOrderAvailable(data, payload);
  return <section className="cycle-scouting">
    <h2>{copy('scout')}</h2>
    <p>{copy('reportAt')}: {formatMoscowDateTime(data.scout.cutoff, '-', language)}</p>
    {data.scout.request ? <><h3>{name(data.scout.request.territory_id)}</h3>
      {data.scout.request.scout_user_id ? <><p><strong>{copy('scoutPlayer')}: {data.scout.request.scout_name || `#${data.scout.request.scout_user_id}`}</strong></p>
        <p>{copy('scoutLock')}</p></> : <p>{copy('scoutUnassigned')}</p>}
      {data.scout.report ? <div className="cp-report"><h3>{copy('report')}</h3>{data.scout.report.enemy_squads.length ? <ul>{data.scout.report.enemy_squads.map((count, index) => <li key={index}><span>{copy('squad')}</span><strong>{count}</strong></li>)}</ul> : <p>{copy('noSquads')}</p>}</div> : <p role="status">{copy('waiting')}</p>}
    </> : data.scout.can_request ? <form onSubmit={event => { event.preventDefault(); if (canOrder) onOrder(payload.territory_id, payload.scout_user_id); }}>
      {territoryId != null ? <h3>{name(territoryId)}</h3> : <label>{copy('target')}<select required value={selection} disabled={disabled} onChange={event => setSelection(event.target.value)}><option value="">{copy('choose')}</option>{data.territories.map(land => <option key={land.id} value={land.id}>{land.name}</option>)}</select></label>}
      <label>{copy('scoutPlayer')}<select required value={scoutUserId} disabled={disabled || !players.length} aria-describedby={lockId} onChange={event => setScoutUserId(event.target.value)}>
        <option value="">{copy('chooseScout')}</option>{players.map(player => <option key={player.user_id} value={player.user_id}>{player.name}</option>)}
      </select></label>
      {!players.length && <p role="status">{copy('noScoutPlayers')}</p>}
      <p id={lockId}>{copy('scoutLock')}</p>
      <p>{copy('paid')}</p><button type="submit" disabled={!canOrder}><Search aria-hidden="true" />{copy('order')}</button>
    </form> : <p role="status">{unavailableKey ? copy(unavailableKey) : mapCommandMessage('scoutingUnavailable', language)}</p>}
  </section>;
}
