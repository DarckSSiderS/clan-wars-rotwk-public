import React from 'react';
import SiteThemePreview from './SiteThemePreview';
import { SITE_THEME_ITEM_TYPE } from '../theme/siteThemes';

const CosmeticItemPreview = ({ item, getFallbackIcon }) => {
  if (item.item_type === SITE_THEME_ITEM_TYPE) {
    return <SiteThemePreview themeKey={item.css_class} label={item.name} />;
  }

  if (item.item_type === 'avatar_frame') {
    return (
      <div className="cosmetic-preview cosmetic-preview--avatar" role="img" aria-label={item.name}>
        <div className={`cosmetic-avatar-preview ${item.css_class || ''}`}>
          <img src="/icons/profilewb.png" alt="" aria-hidden="true" />
        </div>
      </div>
    );
  }

  if (item.item_type === 'profile_background') {
    return (
      <div className={`cosmetic-preview cosmetic-preview--background ${item.css_class || ''}`} role="img" aria-label={item.name}>
        <span />
        <i />
      </div>
    );
  }

  if (item.image_url) {
    return <img src={item.image_url} alt={item.name} style={{ maxWidth: '100%', maxHeight: '100%' }} />;
  }

  if (['profile_frame', 'stat_card_style'].includes(item.item_type)) {
    const numericId = Number.parseInt(String(item.id || '').replace(/\D/g, ''), 10) || 1;
    const relicNumber = ((numericId - 1) % 12) + 1;
    return (
      <img
        src={`/design-prototype/relic_${relicNumber}.webp`}
        alt={item.name}
        className="cosmetic-preview--relic"
      />
    );
  }

  return <img src={getFallbackIcon(item.item_type)} alt={item.name} style={{ width: '40px', height: '40px' }} />;
};

export default CosmeticItemPreview;
