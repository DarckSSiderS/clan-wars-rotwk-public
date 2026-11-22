import React, { useState } from 'react';
import { CheckCircleOutline, CancelOutlined, ExpandMore, MapOutlined, Groups, Schedule } from '@mui/icons-material';
import { matchMessage, signedScore } from '../utils/cycleMatchPresentation';
import { formatMoscowDateTime } from '../utils/dateTime';
import { withAppBase } from '../utils/appBasePath';

export default function CycleMatchSummary({ match, index, language, memberName, clanLabel }) {
  const copy = key => matchMessage(key, language);
  const [broken, setBroken] = useState(false);
  return <summary>
    <span className="cycle-match-number">{String(index + 1).padStart(2, '0')}</span>
    <span className="cm-overview">
      <span className="cm-match-meta"><strong>{match.map_name || copy('mapUnknown')}</strong>
        {match.game_mode && <span><Groups aria-hidden="true" />{match.game_mode}</span>}
        {match.played_at && <span><Schedule aria-hidden="true" />{formatMoscowDateTime(match.played_at, '-', language)}</span>}
        {match.duration && <span>{match.duration}</span>}{match.patch_name && <span>{match.patch_name}</span>}
      </span>
      <span className="cm-teams">{match.teams.length ? match.teams.map(team => <span className={`cm-team${team.is_winner === true ? ' cm-team-won' : ''}`} key={team.id}>
        <span className="cm-team-outcome">{team.is_winner === true ? <CheckCircleOutline aria-hidden="true" /> : team.is_winner === false ? <CancelOutlined aria-hidden="true" /> : null}{copy(team.is_winner === true ? 'winner' : team.is_winner === false ? 'loser' : 'team')}</span>
        <span className="cycle-match-names">{team.players.map((player, playerIndex) => <span key={player.user_id || `${team.id}:${playerIndex}`}>{player.name}</span>)}</span>
      </span>) : <span className="cm-unknown-team"><span className="cycle-match-names">{match.contributions.map(row => memberName(row.user_id)).join(' · ')}</span><small>{copy('unavailable')}</small></span>}</span>
      <span className="cm-effects" aria-label={copy('contribution')}>{match.effects.map(effect => <span key={effect.clan_id}><span>{effect.clan_name || clanLabel(effect.clan_id)}</span><b className={effect.points.startsWith('-') ? 'cycle-negative' : 'cycle-positive'}>{signedScore(effect.points)}</b></span>)}</span>
    </span>
    <span className="cm-map-preview" aria-hidden="true">{match.map_preview_url && !broken ? <img src={withAppBase(match.map_preview_url)} alt="" onError={() => setBroken(true)} /> : <MapOutlined />}</span>
    <span className={`cycle-badge ${match.status === 'counted' ? 'cycle-badge--counted' : match.status === 'rejected' ? 'cycle-badge--rejected' : 'cycle-badge--active'}`}>{copy(match.status)}</span>
    <ExpandMore className="cycle-disclosure-icon" aria-hidden="true" />
  </summary>;
}
