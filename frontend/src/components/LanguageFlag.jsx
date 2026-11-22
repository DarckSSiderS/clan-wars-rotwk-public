import React from 'react';

const LanguageFlag = ({ language }) => {
  if (language === 'ru') {
    return (
      <svg className="cw-language-flag" viewBox="0 0 24 16" aria-hidden="true" focusable="false">
        <rect width="24" height="16" rx="1.5" fill="#fff" />
        <path d="M0 5.33h24v5.34H0z" fill="#2455a4" />
        <path d="M0 10.67h24V16H0z" fill="#c63b45" />
      </svg>
    );
  }

  if (language === 'de') {
    return (
      <svg className="cw-language-flag" viewBox="0 0 24 16" aria-hidden="true" focusable="false">
        <rect width="24" height="16" rx="1.5" fill="#161616" />
        <path d="M0 5.33h24v5.34H0z" fill="#b72f3b" />
        <path d="M0 10.67h24V16H0z" fill="#d5a93f" />
      </svg>
    );
  }

  return (
    <svg className="cw-language-flag" viewBox="0 0 24 16" aria-hidden="true" focusable="false">
      <rect width="24" height="16" rx="1.5" fill="#27456f" />
      <path d="m0 0 24 16M24 0 0 16" stroke="#f4f1e8" strokeWidth="4" />
      <path d="m0 0 24 16M24 0 0 16" stroke="#a93642" strokeWidth="1.75" />
      <path d="M12 0v16M0 8h24" stroke="#f4f1e8" strokeWidth="5" />
      <path d="M12 0v16M0 8h24" stroke="#a93642" strokeWidth="2.5" />
    </svg>
  );
};

export default LanguageFlag;
