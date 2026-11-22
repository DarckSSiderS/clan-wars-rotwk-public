import React from 'react';

const SectionHeader = ({
  as: Component = 'header',
  eyebrow,
  title,
  description,
  action,
  className = '',
  titleAs: Title = 'h2',
  ...props
}) => (
  <Component
    className={['cw-section-header', className].filter(Boolean).join(' ')}
    {...props}
  >
    <div className="cw-section-header__copy">
      {eyebrow && <p className="cw-section-header__eyebrow">{eyebrow}</p>}
      <Title className="cw-section-header__title">{title}</Title>
      {description && <p className="cw-section-header__description">{description}</p>}
    </div>
    {action && <div className="cw-section-header__action">{action}</div>}
  </Component>
);

export default SectionHeader;
