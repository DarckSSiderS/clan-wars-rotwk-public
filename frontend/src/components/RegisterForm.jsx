import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  CircularProgress,
  Typography,
} from '@mui/material';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { authService } from '../services/authService';
import PublicDocumentDialog from './home/PublicDocumentDialog';
import { getPublicDocument } from '../content/publicDocuments';

const RegisterForm = ({ initialUsername = '', onSuccess }) => {
  const [formData, setFormData] = useState({
    username: initialUsername,
    email: '',
    password: '',
    language: localStorage.getItem('language') || 'ru',
    region: 'Europe',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [checkingUsername, setCheckingUsername] = useState(false);
  const [usernameStatus, setUsernameStatus] = useState(null);
  const [claimExistingProfile, setClaimExistingProfile] = useState(false);
  const [acceptRules, setAcceptRules] = useState(false);
  const [privacyOpen, setPrivacyOpen] = useState(false);
  const { register } = useAuth();
  const { getLocalizedText: t, language } = useLocalizationContext();

  useEffect(() => {
    const username = formData.username.trim();
    setClaimExistingProfile(false);
    if (username.length < 2) {
      setUsernameStatus(null);
      setCheckingUsername(false);
      return undefined;
    }

    let cancelled = false;
    setCheckingUsername(true);
    const timer = setTimeout(async () => {
      try {
        const status = await authService.getRegistrationStatus(username);
        if (!cancelled) setUsernameStatus(status);
      } catch (statusError) {
        if (!cancelled) {
          setUsernameStatus(null);
          setError(statusError.response?.data?.detail || t('register_check_error'));
        }
      } finally {
        if (!cancelled) setCheckingUsername(false);
      }
    }, 350);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [formData.username, t]);

  const handleChange = (event) => {
    setFormData((current) => ({
      ...current,
      [event.target.name]: event.target.value,
    }));
    setError('');
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError('');

    if (!acceptRules) {
      setError(t('auth_rules_required'));
      return;
    }
    if (usernameStatus?.status === 'taken') {
      setError(t('register_username_taken'));
      return;
    }
    if (usernameStatus?.status === 'spelling_mismatch') {
      setError(`${t('register_username_exact')} ${usernameStatus.exact_username}`);
      return;
    }
    if (usernameStatus?.status === 'claimable' && !claimExistingProfile) {
      setError(t('register_claim_required'));
      return;
    }

    setLoading(true);
    try {
      await register({
        username: formData.username,
        email: formData.email,
        password: formData.password,
        language: formData.language,
        claim_existing_profile: claimExistingProfile,
      });
      onSuccess?.({ claimExistingProfile });
    } catch (requestError) {
      setError(requestError.response?.data?.detail || t('register_error'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
    <Box component="form" onSubmit={handleSubmit} className="auth-form" aria-busy={loading} noValidate>
      {error && <Alert severity="error" role="alert">{error}</Alert>}
      <label className="field" htmlFor="register-username"><span>{t('register_nickname', 'Ник')}</span><input className="input" required id="register-username" name="username" autoComplete="username" value={formData.username} onChange={handleChange} minLength="2" maxLength="80" placeholder={t('register_player_name', 'Имя игрока')} /></label>
      {checkingUsername && (
        <Box className="auth-inline-state" role="status">
          <CircularProgress size={16} />
          <Typography variant="body2">{t('register_username_check')}</Typography>
        </Box>
      )}
      {!checkingUsername && usernameStatus?.status === 'available' && (
        <Alert severity="success">{t('register_username_available')}</Alert>
      )}
      {!checkingUsername && usernameStatus?.status === 'taken' && (
        <Alert severity="error">{t('register_username_taken')}</Alert>
      )}
      {!checkingUsername && usernameStatus?.status === 'spelling_mismatch' && (
        <Alert severity="warning">
          {t('register_username_exact')} <strong>{usernameStatus.exact_username}</strong>
        </Alert>
      )}
      {!checkingUsername && usernameStatus?.status === 'claimable' && (
        <Alert severity="info">
          <Typography variant="body2">
            {t('register_profile_found')}: {t('register_profile_stats', null, {
              matches: usernameStatus.statistics?.total_matches || 0,
              wins: usernameStatus.statistics?.wins || 0,
              achievements: usernameStatus.completed_achievements || 0,
            })}
          </Typography>
          <label className="check"><input type="checkbox" checked={claimExistingProfile} onChange={(event) => setClaimExistingProfile(event.target.checked)} /> {t('register_claim_profile')}</label>
        </Alert>
      )}
      <label className="field" htmlFor="register-email"><span>{t('register_email')}</span><input className="input" required id="register-email" name="email" type="email" autoComplete="email" value={formData.email} onChange={handleChange} /></label>
      <label className="field" htmlFor="register-password"><span>{t('login_password')}</span><input className="input" required name="password" type="password" id="register-password" autoComplete="new-password" value={formData.password} onChange={handleChange} minLength="8" /></label>
      <label className="field" htmlFor="register-region"><span>{t('register_region', 'Регион')}</span><select className="input" id="register-region" name="region" value={formData.region} onChange={handleChange}><option value="Europe">{t('register_region_europe')}</option><option value="CIS">{t('register_region_cis')}</option></select></label>
      <label className="check auth-form__consent">
        <input type="checkbox" checked={acceptRules} onChange={(event) => setAcceptRules(event.target.checked)} required />
        <span>{t('auth_rules_accept')} <button type="button" className="auth-consent-link" onClick={(event) => { event.preventDefault(); setPrivacyOpen(true); }}>{t('auth_privacy_open', 'Что именно обрабатывается?')}</button></span>
      </label>
      <button
        type="submit"
        className="btn primary full"
        disabled={loading || checkingUsername || usernameStatus?.status === 'taken'
          || usernameStatus?.status === 'spelling_mismatch'}
      >
        {loading ? <CircularProgress size={22} color="inherit" /> : t('register_submit')}
      </button>
    </Box>
    <PublicDocumentDialog
      documentId={privacyOpen ? 'privacy' : null}
      language={language}
      getDocument={getPublicDocument}
      onClose={() => setPrivacyOpen(false)}
      closeLabel={t('common_close', 'Закрыть')}
    />
    </>
  );
};

export default RegisterForm;
