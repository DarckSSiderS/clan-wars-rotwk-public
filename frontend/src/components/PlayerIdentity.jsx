import React from 'react';
import { Link } from 'react-router-dom';
import { AdminPanelSettings } from '@mui/icons-material';
import { Tooltip } from '@mui/material';

import { useLocalizationContext } from '../contexts/LocalizationContext';
import { usePlayerIdentity } from '../contexts/PlayerIdentityContext';
import { getPlayerDisplayName, getPlayerProfilePath } from '../utils/playerIdentity';
import './PlayerIdentity.css';

export const PlayerTitles = ({ titles = [], large = false }) => {
  const { language } = useLocalizationContext();
  const localizedTitle = (title) => ({
    name: title[`name_${language}`] || title.name,
    description: title[`description_${language}`] || title.description,
  });
  return (
    <span className={`player-titles${large ? ' player-titles--large' : ''}`}>
      {titles.map((title) => {
        const localized = localizedTitle(title);
        return (
      <Tooltip
        arrow
        key={title.id}
        title={(
          <span className="player-title-tooltip">
            <strong>{localized.name}</strong>
            <span>{localized.description}</span>
          </span>
        )}
      >
        <img className="player-title-icon" src={title.image_url} alt={localized.name} />
      </Tooltip>
        );
      })}
    </span>
  );
};

const PlayerIdentity = ({
  username,
  linkToProfile = true,
  className = '',
  usernameClassName = '',
  showAdmin = true,
  showTitles = true,
}) => {
  const { getLocalizedText } = useLocalizationContext();
  const { getIdentity } = usePlayerIdentity();
  const identity = getIdentity(username);
  const name = getPlayerDisplayName(
    identity || { username },
    getLocalizedText('player_unknown', 'Неизвестный игрок'),
  );
  const usernameNode = linkToProfile && username ? (
    <Link className={usernameClassName} to={getPlayerProfilePath(identity || { username })}>{name}</Link>
  ) : (
    <span className={usernameClassName}>{name}</span>
  );

  return (
    <span className={`player-identity ${className}`.trim()}>
      {usernameNode}
      {showAdmin && identity?.is_admin && (
        <span className="player-admin-badge" title={getLocalizedText('player_administrator', 'Администратор')}>
          <AdminPanelSettings fontSize="inherit" />
          <span>{getLocalizedText('player_administrator', 'Администратор')}</span>
        </span>
      )}
      {showTitles && <PlayerTitles titles={identity?.titles || []} />}
    </span>
  );
};

export default PlayerIdentity;
