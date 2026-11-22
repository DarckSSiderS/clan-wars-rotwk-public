import React from 'react';

const StatValue = ({ label, value, icon = null, className = '', ...props }) => (
  <div className={['cw-stat-value', className].filter(Boolean).join(' ')} {...props}>
    <p className="cw-stat-value__label">
      {icon}
      <span>{label}</span>
    </p>
    <p className="cw-stat-value__value">{value}</p>
  </div>
);

export default StatValue;
