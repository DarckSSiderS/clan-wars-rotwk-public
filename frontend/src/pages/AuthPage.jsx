import React, { useState } from 'react';
import { Alert, Box, CircularProgress, Paper, Tab, Tabs, Typography } from '@mui/material';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import LoginForm from '../components/LoginForm';
import RegisterForm from '../components/RegisterForm';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { authService } from '../services/authService';
import './AuthPage.css';

const tabFromPath = (pathname) => {
  if (pathname.startsWith('/register')) return 'register';
  if (pathname.startsWith('/recover')) return 'recover';
  return 'login';
};

const OAUTH_ERROR_MESSAGES = {
  access_denied: 'oauth_error_access_denied',
  arena_rejected: 'oauth_error_arena_rejected',
  oauth_not_configured: 'oauth_error_not_configured',
  invalid_callback: 'oauth_error_invalid_callback',
  invalid_state: 'oauth_error_invalid_state',
  inactive_account: 'oauth_error_inactive_account',
  arena_unavailable: 'oauth_error_arena_unavailable',
  invalid_identity: 'oauth_error_invalid_identity',
  account_conflict: 'oauth_error_account_conflict',
  oauth_failed: 'oauth_error_failed',
};

const AuthPage = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { getLocalizedText: t } = useLocalizationContext();
  const [recoveryEmail, setRecoveryEmail] = useState('');
  const [recoveryPassword, setRecoveryPassword] = useState('');
  const [recoveryPasswordConfirm, setRecoveryPasswordConfirm] = useState('');
  const [recoveryNotice, setRecoveryNotice] = useState('');
  const [recoveryError, setRecoveryError] = useState('');
  const [recoverySubmitting, setRecoverySubmitting] = useState(false);
  const activeTab = tabFromPath(location.pathname);
  const recoveryToken = searchParams.get('token') || '';
  const oauthError = searchParams.get('oauth_error');
  const oauthMessageKey = OAUTH_ERROR_MESSAGES[oauthError] || (oauthError ? 'oauth_error_failed' : null);

  const switchTab = (_, value) => {
    navigate(value === 'login' ? '/login' : `/${value}`);
  };

  const handleLoginSuccess = () => {
    const requestedPath = location.state?.from;
    const destination = requestedPath?.pathname
      ? `${requestedPath.pathname}${requestedPath.search || ''}${requestedPath.hash || ''}`
      : '/';
    navigate(destination, { replace: true });
  };

  const handleRegisterSuccess = ({ claimExistingProfile }) => {
    navigate('/login', {
      replace: true,
      state: {
        message: claimExistingProfile ? t('register_claim_success') : t('register_success'),
      },
    });
  };

  const handleRecovery = async (event) => {
    event.preventDefault();
    setRecoveryNotice('');
    setRecoveryError('');

    if (recoveryToken && recoveryPassword !== recoveryPasswordConfirm) {
      setRecoveryError(t('register_password_mismatch'));
      return;
    }

    setRecoverySubmitting(true);
    try {
      const result = recoveryToken
        ? await authService.confirmPasswordRecovery(recoveryToken, recoveryPassword)
        : await authService.requestPasswordRecovery(recoveryEmail);
      setRecoveryNotice(result.message);
      if (recoveryToken) {
        setRecoveryPassword('');
        setRecoveryPasswordConfirm('');
      }
    } catch (requestError) {
      setRecoveryError(requestError.response?.data?.detail || t('auth_recover_error'));
    } finally {
      setRecoverySubmitting(false);
    }
  };

  return (
    <main className="auth-page" data-section="auth-shell">
      <Paper className="auth-card" elevation={0}>
        <header className="auth-card__header">
          <img src="/brand/clanwar-logo.png" alt="Middle-earth Clan Wars" className="auth-card__logo" />
          <span className="auth-card__eyebrow">{t('auth_eyebrow')}</span>
        </header>

        <Tabs
          value={activeTab}
          onChange={switchTab}
          variant="fullWidth"
          aria-label={t('auth_eyebrow')}
          className="auth-tabs"
        >
          <Tab value="login" label={t('login_title')} />
          <Tab value="register" label={t('register_title')} />
          <Tab value="recover" label={t('auth_recover_tab')} />
        </Tabs>

        <Box className="auth-card__body">
          {activeTab === 'login' && (
            <section role="tabpanel" aria-labelledby="auth-login-heading">
              <Typography component="h1" variant="h4" id="auth-login-heading">
                {t('auth_login_heading')}
              </Typography>
              <Typography className="auth-card__description">{t('auth_login_description')}</Typography>
              {location.state?.message && <Alert severity="success">{location.state.message}</Alert>}
              {oauthMessageKey && <Alert severity="error" role="alert">{t(oauthMessageKey)}</Alert>}
              <LoginForm onSuccess={handleLoginSuccess} />
            </section>
          )}

          {activeTab === 'register' && (
            <section role="tabpanel" aria-labelledby="auth-register-heading">
              <Typography component="h1" variant="h4" id="auth-register-heading">
                {t('auth_register_heading')}
              </Typography>
              <Typography className="auth-card__description">{t('auth_register_description')}</Typography>
              <RegisterForm
                initialUsername={searchParams.get('username') || ''}
                onSuccess={handleRegisterSuccess}
              />
            </section>
          )}

          {activeTab === 'recover' && (
            <section role="tabpanel" aria-labelledby="auth-recover-heading">
              <Typography component="h1" variant="h4" id="auth-recover-heading">
                {t('auth_recover_heading')}
              </Typography>
              <Typography className="auth-card__description">
                {recoveryToken ? t('auth_recover_new_password_description') : t('auth_recover_description')}
              </Typography>
              <Box
                component="form"
                className="auth-form"
                onSubmit={handleRecovery}
                aria-busy={recoverySubmitting}
              >
                {recoveryToken ? (
                  <>
                    <label className="field" htmlFor="recovery-password"><span>{t('auth_recover_new_password')}</span><input className="input" required id="recovery-password" type="password" autoComplete="new-password" value={recoveryPassword} onChange={(event) => setRecoveryPassword(event.target.value)} minLength="8" maxLength="128" /></label>
                    <label className="field" htmlFor="recovery-password-confirm"><span>{t('register_confirm_password')}</span><input className="input" required id="recovery-password-confirm" type="password" autoComplete="new-password" value={recoveryPasswordConfirm} onChange={(event) => setRecoveryPasswordConfirm(event.target.value)} minLength="8" maxLength="128" /></label>
                  </>
                ) : (
                  <label className="field" htmlFor="recovery-email"><span>{t('register_email')}</span><input className="input" required id="recovery-email" type="email" autoComplete="email" value={recoveryEmail} onChange={(event) => setRecoveryEmail(event.target.value)} placeholder="you@example.com" /></label>
                )}
                {recoveryNotice && <Alert severity="success">{recoveryNotice}</Alert>}
                {recoveryError && <Alert severity="error">{recoveryError}</Alert>}
                <button type="submit" className="btn primary full" disabled={recoverySubmitting}>
                  {recoverySubmitting
                    ? <CircularProgress size={22} color="inherit" />
                    : recoveryToken ? t('auth_recover_save_password') : t('auth_recover_action')}
                </button>
                <Link className="text-btn full auth-back-link" to="/login">{t('auth_back_to_login', 'Вернуться ко входу')}</Link>
              </Box>
            </section>
          )}
        </Box>
      </Paper>
    </main>
  );
};

export default AuthPage;
