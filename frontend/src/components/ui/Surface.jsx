import React from 'react';

const Surface = ({
  as: Component = 'section',
  interactive = false,
  className = '',
  ...props
}) => (
  <Component
    className={[
      'cw-surface',
      interactive && 'cw-surface--interactive',
      className,
    ].filter(Boolean).join(' ')}
    {...props}
  />
);

export default Surface;
