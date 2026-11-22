import React from 'react';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { getSiteTheme } from '../theme/siteThemes';

const SiteThemePreview = ({ themeKey, label }) => {
  const { getLocalizedText } = useLocalizationContext();
  const theme = getSiteTheme(themeKey);

  return (
    <div
      role="img"
      aria-label={label || getLocalizedText(theme.labelKey)}
      data-theme-preview={themeKey}
      style={{
        width: 'min(100%, 168px)',
        aspectRatio: '16 / 10',
        margin: '0 auto',
        padding: '12px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        borderRadius: '14px',
        background: theme.preview,
        border: `1px solid ${theme.cardBorder}`,
        boxShadow: `inset 0 0 32px rgba(${theme.primaryRgb}, 0.12), 0 12px 28px rgba(0, 0, 0, 0.28)`,
      }}
    >
      <span style={{ width: '58%', height: 7, borderRadius: 99, background: theme.primary }} />
      <span style={{ width: '82%', height: 24, borderRadius: 8, background: `rgba(${theme.cardRgb}, 0.82)`, border: `1px solid ${theme.cardBorder}` }} />
      <span style={{ display: 'flex', gap: 6 }}>
        <i style={{ width: 18, height: 18, borderRadius: '50%', background: theme.primary }} />
        <i style={{ width: 18, height: 18, borderRadius: '50%', background: theme.secondary }} />
        <i style={{ flex: 1, height: 18, borderRadius: 99, background: `rgba(${theme.primaryRgb}, 0.2)` }} />
      </span>
    </div>
  );
};

export default SiteThemePreview;
