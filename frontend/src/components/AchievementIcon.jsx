import React from 'react';
import {
  Bolt,
  DarkMode,
  EmojiEvents,
  Explore,
  Groups,
  History,
  LocalFireDepartment,
  Map,
  MilitaryTech,
  Public,
  Shield,
  SportsMma,
  Timeline,
  WorkspacePremium,
} from '@mui/icons-material';

import { getFactionIcon } from '../data/factions';
import { getAchievementPresentation } from '../utils/achievementPresentation';

const GENERAL_ICONS = {
  battle: SportsMma,
  victory: EmojiEvents,
  streak: LocalFireDepartment,
  veteran: Shield,
  explore: Explore,
  factions: Public,
  duration: History,
  speed: Bolt,
  night: DarkMode,
  opponents: Groups,
  active: Timeline,
  team: Groups,
  'team-victory': WorkspacePremium,
  medal: MilitaryTech,
};

const AchievementIcon = ({ achievement }) => {
  const presentation = getAchievementPresentation(
    achievement?.achievement_type,
    achievement?.name,
  );
  const GeneralIcon = GENERAL_ICONS[presentation.symbol] || MilitaryTech;
  const MarkerIcon = presentation.symbol === 'wins' || presentation.symbol === 'winrate'
    ? EmojiEvents
    : Map;
  const factionIcon = presentation.kind === 'faction'
    ? getFactionIcon(presentation.subject, 'large')
    : null;

  return (
    <span
      className={`achievement-emblem achievement-emblem--${presentation.kind}`}
      style={{ '--achievement-accent': presentation.accent }}
      aria-hidden="true"
    >
      <span className="achievement-emblem__inner">
        {presentation.kind === 'general' && <GeneralIcon className="achievement-emblem__main-icon" />}
        {presentation.kind === 'faction' && factionIcon && (
          <img src={factionIcon} alt="" className="achievement-emblem__faction" />
        )}
        {presentation.kind === 'faction' && !factionIcon && (
          <strong className="achievement-emblem__glyph">{presentation.glyph}</strong>
        )}
        {presentation.kind === 'map' && (
          <strong className="achievement-emblem__glyph">{presentation.glyph}</strong>
        )}
        {presentation.kind === 'mode' && (
          <strong className="achievement-emblem__mode">{presentation.glyph}</strong>
        )}
      </span>
      {presentation.kind !== 'general' && <MarkerIcon className="achievement-emblem__marker" />}
    </span>
  );
};

export default AchievementIcon;
