import React from 'react';

const ICONS = {
  gold: <><circle cx="24" cy="24" r="18" fill="#8e6615" stroke="#f8d66a" strokeWidth="3" /><circle cx="24" cy="24" r="12" fill="#d99b22" stroke="#ffe59a" strokeWidth="1.5" /><path d="M27 11h-6v5c-4 .7-7 3.2-7 7 0 4.4 3.3 6.5 8.5 7.5 2.5.5 3.6 1.1 3.6 2.3 0 1.4-1.3 2.2-3.5 2.2-2.5 0-4.9-.9-6.9-2.5l-2.5 4.1c2.2 1.9 4.8 3 7.8 3.3V44h6v-4.5c4.4-.9 7-3.7 7-7.3 0-4.3-3-6.4-8.5-7.4-2.7-.5-3.9-1.2-3.9-2.4 0-1.3 1.2-2.1 3.2-2.1 2.1 0 4.1.7 6 2l2.4-4.2a15 15 0 0 0-6.2-2.3z" fill="#fff0b8" /></>,
  iron: <><path d="M7 29 15 12h21l5 17-8 8H15z" fill="#7f8994" stroke="#dce3e9" strokeWidth="2" /><path d="M15 12h21l-8 8H11z" fill="#c9d0d6" /><path d="M15 29h26l-8 8H15z" fill="#59636d" /><path d="M18 17h12" stroke="#f4f6f8" strokeWidth="2" strokeLinecap="round" /></>,
  wood: <><path d="m9 14 25 20-6 8L3 22z" fill="#76502f" stroke="#d59a5f" strokeWidth="2" /><circle cx="8" cy="18" r="6" fill="#bd7b43" stroke="#efbd79" strokeWidth="2" /><circle cx="8" cy="18" r="2.5" fill="none" stroke="#754429" strokeWidth="1.5" /><path d="m18 7 25 20-6 8L12 15z" fill="#8c5c35" stroke="#e0a363" strokeWidth="2" /><circle cx="17" cy="11" r="6" fill="#c98a4e" stroke="#ffd08b" strokeWidth="2" /></>,
  food: <><path d="M14 13c7-6 18-2 20 6 2 7-3 14-10 17-6 3-14 1-17-5-3-7 1-14 7-18z" fill="#b92f2a" stroke="#ff8170" strokeWidth="2" /><path d="M18 16c5-3 12 0 13 5 1 4-2 8-6 10-4 2-9 1-12-3-2-5 1-10 5-12z" fill="#e65346" /><path d="m32 12 6-7c2-2 5 1 3 3l-5 7m0 0 5-2c3-1 4 3 1 4l-6 2" fill="none" stroke="#f2e3cf" strokeWidth="4" strokeLinecap="round" /><circle cx="20" cy="23" r="3" fill="#8e211f" /></>,
  mithril: <><path d="M24 4 42 18 24 44 6 18z" fill="#1e8ca9" stroke="#a8f2ff" strokeWidth="2" /><path d="m24 4 7 14-7 26-7-26z" fill="#5ed9ef" /><path d="M6 18h36M17 18l7-14 7 14" fill="none" stroke="#d7fbff" strokeWidth="1.5" /><path d="m6 18 18 26 18-26" fill="none" stroke="#126d88" strokeWidth="2" /></>,
  territory_points: <><path d="M12 43V7" stroke="#d9c5ff" strokeWidth="4" strokeLinecap="round" /><path d="M14 9c9-6 14 5 26-1v20c-12 6-17-5-26 1z" fill="#7544b7" stroke="#d7b7ff" strokeWidth="2" /><path d="m27 14 2.4 4.8 5.3.8-3.8 3.7.9 5.2-4.8-2.5-4.8 2.5.9-5.2-3.8-3.7 5.3-.8z" fill="#f2e9ff" /></>,
};

const ResourceIcon = ({ resource, size = 24, className = '', style = {}, sx = {}, title, ...props }) => {
  const resolvedSize = sx.fontSize || style.fontSize || size;
  return (
    <svg
      viewBox="0 0 48 48"
      className={className}
      style={{ width: resolvedSize, height: resolvedSize, flex: sx.flex || style.flex || '0 0 auto', ...style }}
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      {...props}
    >
      {title && <title>{title}</title>}
      {ICONS[resource] || ICONS.gold}
    </svg>
  );
};

export const GoldResourceIcon = (props) => <ResourceIcon resource="gold" {...props} />;
export const IronResourceIcon = (props) => <ResourceIcon resource="iron" {...props} />;
export const WoodResourceIcon = (props) => <ResourceIcon resource="wood" {...props} />;
export const FoodResourceIcon = (props) => <ResourceIcon resource="food" {...props} />;
export const MithrilResourceIcon = (props) => <ResourceIcon resource="mithril" {...props} />;
export const TerritoryPointsResourceIcon = (props) => <ResourceIcon resource="territory_points" {...props} />;

export default ResourceIcon;
