import React from 'react';
import { Avatar } from '@mui/material';
import { EmojiEvents } from '@mui/icons-material';
import { Link } from 'react-router-dom';
import { SectionHeader, Surface } from '../ui';

const ClanInfluenceRanking = ({
  clans,
  loading,
  unavailable,
  title,
  emptyLabel,
  membersLabel,
  influenceLabel,
  loadingLabel,
  unavailableLabel,
}) => (
  <Surface className="home-ranking">
    <SectionHeader
      eyebrow={influenceLabel}
      title={title}
      action={<EmojiEvents aria-hidden="true" className="home-ranking__trophy" />}
    />
    {loading ? (
      <div
        className="home-page__skeleton home-page__skeleton--ranking"
        role="status"
        aria-label={loadingLabel}
      />
    ) : unavailable ? (
      <div className="home-page__panel-state" role="status">{unavailableLabel}</div>
    ) : clans.length === 0 ? (
      <div className="home-ranking__empty" role="status">{emptyLabel}</div>
    ) : (
      <ol className="home-ranking__list">
        {clans.map((clan, index) => (
          <li key={clan.id}>
            <Link to={`/clans/${clan.id}`} className="home-ranking__row">
              <span className="home-ranking__position">{index + 1}</span>
              <Avatar
                src={clan.avatar_url || '/default-clan-avatar.png'}
                alt=""
                className="home-ranking__avatar"
              />
              <span className="home-ranking__identity">
                <strong>{clan.name}</strong>
                <small>{membersLabel}: {clan.member_count || 0}</small>
              </span>
              <span className="home-ranking__influence">
                <strong>{clan.territory_points || 0}</strong>
                <small>{influenceLabel}</small>
              </span>
            </Link>
          </li>
        ))}
      </ol>
    )}
  </Surface>
);

export default ClanInfluenceRanking;
