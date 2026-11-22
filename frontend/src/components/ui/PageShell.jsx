import React from 'react';

const PageShell = ({ as: Component = 'main', className = '', ...props }) => (
  <Component
    className={['cw-page-shell', className].filter(Boolean).join(' ')}
    {...props}
  />
);

export default PageShell;
