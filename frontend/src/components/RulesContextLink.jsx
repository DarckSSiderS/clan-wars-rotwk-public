import React from 'react';
import { HelpOutlineRounded } from '@mui/icons-material';
import { Link } from 'react-router-dom';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import './RulesContextLink.css';

const LABEL_KEYS = {
  map: 'rules_context_map',
  war: 'rules_context_war',
  clan: 'rules_context_clan',
  market: 'rules_context_market',
};

const RulesContextLink = ({ context, section, className = '' }) => {
  const { getLocalizedText: t } = useLocalizationContext();
  const labelKey = LABEL_KEYS[context] || LABEL_KEYS.clan;

  return (
    <Link
      className={`rules-context-link ${className}`.trim()}
      to={`/rules?section=${section}`}
    >
      <HelpOutlineRounded aria-hidden="true" fontSize="small" />
      <span>{t(labelKey)}</span>
    </Link>
  );
};

export default RulesContextLink;
