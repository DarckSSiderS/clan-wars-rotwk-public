import React from 'react';
import { FeedbackOutlined, FavoriteBorderRounded } from '@mui/icons-material';
import { Link, useLocation } from 'react-router-dom';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import './SiteFooter.css';

const SUPPORT_URL = 'https://pay.cloudtips.ru/p/711c6d95';

const SiteFooter = () => {
  const { getLocalizedText: t } = useLocalizationContext();
  const location = useLocation();
  const feedbackUrl = `/feedback?from=${encodeURIComponent(location.pathname)}`;

  return (
    <footer className="site-footer">
      <div className="site-footer__inner">
        <div className="site-footer__studio">
          <span>{t('footer_development_team', 'Команда разработки')}</span>
          <strong>triple D</strong>
        </div>
        <div className="site-footer__actions">
          <Link className="site-footer__feedback" to={feedbackUrl}>
            <FeedbackOutlined aria-hidden="true" />
            <span>{t('footer_feedback', 'Сообщить о проблеме')}</span>
          </Link>
          <a className="site-footer__support" href={SUPPORT_URL} target="_blank" rel="noopener noreferrer">
            <FavoriteBorderRounded aria-hidden="true" />
            <span>{t('footer_support_project', 'Поддержать проект')}</span>
          </a>
        </div>
      </div>
    </footer>
  );
};

export default SiteFooter;
