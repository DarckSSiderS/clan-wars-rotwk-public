import React, { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Container,
  FormControl,
  FormControlLabel,
  FormHelperText,
  FormLabel,
  Paper,
  Radio,
  RadioGroup,
  Select,
  TextField,
  Typography,
} from '@mui/material';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import PublicDocumentDialog from '../components/home/PublicDocumentDialog';
import { getPublicDocument } from '../content/publicDocuments';

const OnboardingPage = () => {
  const { user, completeOnboarding } = useAuth();
  const { getLocalizedText, changeLanguage } = useLocalizationContext();
  const navigate = useNavigate();
  const [historyMode, setHistoryMode] = useState('new');
  const [language, setLanguage] = useState(user?.language || 'ru');
  const [acceptedRules, setAcceptedRules] = useState(false);
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [privacyOpen, setPrivacyOpen] = useState(false);

  if (!user?.onboarding_required) {
    return <Navigate to="/profile" replace />;
  }

  const passwordInvalid = Boolean(error) && (
    password !== confirmation || (password.length > 0 && password.length < 10)
  );

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting || !acceptedRules) return;
    setError('');

    if (password !== confirmation) {
      setError(getLocalizedText('onboarding_password_mismatch', 'Пароли не совпадают.'));
      return;
    }
    if (password && password.length < 10) {
      setError(getLocalizedText(
        'onboarding_password_too_short',
        'Локальный пароль должен содержать не менее 10 символов.',
      ));
      return;
    }

    setSubmitting(true);
    try {
      const session = await completeOnboarding({
        history_mode: historyMode,
        language,
        accepted_rules: acceptedRules,
        password: password || null,
      });
      setPassword('');
      setConfirmation('');
      changeLanguage(session.language);
      navigate('/profile', { replace: true });
    } catch (requestError) {
      const code = requestError.response?.data?.detail?.code;
      setError(code === 'onboarding_invalid'
        ? getLocalizedText('onboarding_invalid', 'Проверьте выбранные настройки и попробуйте снова.')
        : getLocalizedText('onboarding_error', 'Не удалось завершить настройку. Попробуйте ещё раз.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Container maxWidth="sm">
      <Box sx={{ mt: { xs: 3, sm: 6 }, mb: 6 }}>
        <Paper elevation={3} sx={{ p: { xs: 2.5, sm: 4 } }}>
          <Typography component="h1" variant="h4" gutterBottom>
            {getLocalizedText('onboarding_title', 'Настройка профиля')}
          </Typography>
          <Typography color="text.secondary" sx={{ mb: 3 }}>
            {getLocalizedText(
              'onboarding_identity',
              'BFME Arena подтвердила профиль:',
            )}{' '}
            <Box component="strong" color="text.primary">
              {user.display_name || user.username}
            </Box>
          </Typography>

          {error && (
            <Alert id="onboarding-error" severity="error" aria-live="assertive" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}

          <Box component="form" onSubmit={handleSubmit} aria-busy={submitting}>
            <FormControl component="fieldset" fullWidth sx={{ mb: 3 }}>
              <FormLabel component="legend">
                {getLocalizedText('onboarding_history_label', 'История матчей')}
              </FormLabel>
              <RadioGroup
                name="history-mode"
                value={historyMode}
                onChange={(event) => setHistoryMode(event.target.value)}
              >
                <FormControlLabel
                  value="new"
                  control={<Radio />}
                  label={(
                    <Box>
                      <Typography fontWeight={700}>
                        {getLocalizedText('onboarding_history_new', 'Новая история')}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {getLocalizedText(
                          'onboarding_history_new_help',
                          'Статистика и прогресс начнутся после завершения настройки.',
                        )}
                      </Typography>
                    </Box>
                  )}
                />
                <FormControlLabel
                  value="full"
                  control={<Radio />}
                  label={(
                    <Box>
                      <Typography fontWeight={700}>
                        {getLocalizedText('onboarding_history_full', 'Полная история Arena')}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {getLocalizedText(
                          'onboarding_history_full_help',
                          'Доступные матчи и статистические достижения будут импортированы в фоне без клановых и экономических наград.',
                        )}
                      </Typography>
                    </Box>
                  )}
                />
              </RadioGroup>
            </FormControl>

            <FormControl fullWidth sx={{ mb: 3 }}>
              <FormLabel htmlFor="onboarding-language">
                {getLocalizedText('onboarding_language', 'Язык интерфейса')}
              </FormLabel>
              <Select
                native
                id="onboarding-language"
                value={language}
                onChange={(event) => setLanguage(event.target.value)}
                inputProps={{ 'aria-describedby': 'onboarding-language-help' }}
                sx={{ mt: 1 }}
              >
                <option value="ru">{getLocalizedText('language_russian')}</option>
                <option value="en">{getLocalizedText('language_english')}</option>
                <option value="de">{getLocalizedText('language_german')}</option>
              </Select>
              <FormHelperText id="onboarding-language-help">
                {getLocalizedText('onboarding_language_help', 'Язык можно изменить позже в меню сайта.')}
              </FormHelperText>
            </FormControl>

            <Typography component="h2" variant="h6" sx={{ mb: 0.5 }}>
              {getLocalizedText('onboarding_password_title', 'Резервный вход')}
            </Typography>
            <Typography id="onboarding-password-help" variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              {getLocalizedText(
                'onboarding_password_help',
                'Необязательно. Пароль позволит войти по текущему нику Arena, если Arena временно недоступна. Минимум 10 символов.',
              )}
            </Typography>
            <TextField
              fullWidth
              id="onboarding-password"
              label={getLocalizedText('onboarding_password', 'Локальный пароль')}
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              error={passwordInvalid}
              aria-invalid={passwordInvalid}
              aria-describedby={error ? 'onboarding-password-help onboarding-error' : 'onboarding-password-help'}
              sx={{ mb: 2 }}
            />
            <TextField
              fullWidth
              id="onboarding-password-confirmation"
              label={getLocalizedText('onboarding_password_confirmation', 'Подтвердите локальный пароль')}
              type="password"
              autoComplete="new-password"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              error={passwordInvalid}
              aria-invalid={passwordInvalid}
              aria-describedby={error ? 'onboarding-password-help onboarding-error' : 'onboarding-password-help'}
              sx={{ mb: 2.5 }}
            />

            <FormControl required error={!acceptedRules} fullWidth sx={{ mb: 1 }}>
              <FormControlLabel
                control={(
                  <Checkbox
                    checked={acceptedRules}
                    onChange={(event) => setAcceptedRules(event.target.checked)}
                    inputProps={{ 'aria-describedby': 'onboarding-rules-help' }}
                  />
                )}
                label={(
                  <span>
                    {getLocalizedText('onboarding_rules', 'Я принимаю правила проекта и правила обработки данных.')}{' '}
                    <Button variant="text" size="small" onClick={(event) => { event.preventDefault(); setPrivacyOpen(true); }}>
                      {getLocalizedText('auth_privacy_open', 'Что именно обрабатывается?')}
                    </Button>
                  </span>
                )}
              />
              <FormHelperText id="onboarding-rules-help">
                {getLocalizedText(
                  'onboarding_rules_required',
                  'Чтобы продолжить, примите правила проекта и обработки данных.',
                )}
              </FormHelperText>
            </FormControl>

            <Button
              type="submit"
              fullWidth
              variant="contained"
              disabled={!acceptedRules || submitting}
              aria-describedby={!acceptedRules ? 'onboarding-rules-help' : undefined}
              sx={{ mt: 2, minHeight: 46 }}
            >
              {submitting
                ? <CircularProgress size={24} aria-label={getLocalizedText('common_loading', 'Загрузка...')} />
                : getLocalizedText('onboarding_submit', 'Завершить настройку')}
            </Button>
          </Box>
          <PublicDocumentDialog
            documentId={privacyOpen ? 'privacy' : null}
            language={language}
            getDocument={getPublicDocument}
            onClose={() => setPrivacyOpen(false)}
            closeLabel={getLocalizedText('common_close', 'Закрыть')}
          />
        </Paper>
      </Box>
    </Container>
  );
};

export default OnboardingPage;
