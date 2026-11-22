import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { MilitaryTech, Groups, Route, Handshake, MapOutlined, Flag } from '@mui/icons-material';
import { cycleMessage } from '../../utils/cycleBattleView';

const destinations = [
  ['battles', '', MilitaryTech], ['orders', '/orders', Groups],
  ['reinforcements', '/reinforcements', Route], ['diplomacy', '/diplomacy', Handshake],
  ['preparation', '/preparation', Flag],
];

export default function CycleNavigation({ cycleId, language }) {
  const { pathname } = useLocation();
  const section = pathname.replace(/\/$/, '').split('/').at(-1);
  const active = section === 'interception' ? 'reinforcements'
    : destinations.find(([key]) => key === section)?.[0] || 'battles';
  return <nav className="cycle-navigation" aria-label={cycleMessage('cycle_navigation', language)}>
    {destinations.map(([key, path, Icon]) => <Link key={key} to={`/campaign/cycles/${cycleId}${path}`}
      aria-current={active === key ? 'page' : undefined}>
      <Icon aria-hidden="true" /><span>{cycleMessage(`cycle_nav_${key}`, language)}</span>
    </Link>)}
    <Link className="cycle-navigation__map" to="/map">
      <MapOutlined aria-hidden="true" /><span>{cycleMessage('cycle_map', language)}</span>
    </Link>
  </nav>;
}
