import React, { useState } from 'react';
import { useLocation } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Collapse,
  Divider,
  TextField,
  Typography,
} from '@mui/material';
import { ExpandLess, ExpandMore, LoginOutlined } from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const locationPath = (location) => (
  `${location.pathname}${location.search || ''}${location.hash || ''}`
);

const LoginForm = ({ onSuccess, autoFocus = false }) => {
  const [formData, setFormData] = useState({ nickname: '', password: '' });
  const [error, setError] = useState('');
  const [fallbackOpen, setFallbackOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const { login, startArenaLogin } = useAuth();
  const { getLocalizedText } = useLocalizationContext();
  const location = useLocation();

  const requestedLocation = location.state?.from || location;
  const returnTo = requestedLocation.pathname === '/login'
    ? '/'
    : locationPath(requestedLocation);

  const handleChange = (event) => {
    setFormData((current) => ({
      ...current,
      [event.target.name]: event.target.value,
    }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setError('');
    setSubmitting(true);

    try {
      await login(formData);
      await onSuccess?.();
    } catch (requestError) {
      const code = requestError.response?.data?.detail?.code;
      setError(code === 'invalid_credentials'
        ? getLocalizedText('login_invalid_credentials', 'Неверный ник Arena или пароль.')
        : getLocalizedText('login_error', 'Не удалось войти. Попробуйте ещё раз.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box sx={{ width: '100%' }}>
      <Typography color="text.secondary" sx={{ mb: 2 }}>
        {getLocalizedText(
          'login_arena_description',
          'Вход через Arena подтверждает ваш игровой профиль и сохраняет привязку при смене ника.',
        )}
      </Typography>
      <Button
        type="button"
        fullWidth
        variant="contained"
        size="large"
        startIcon={<LoginOutlined aria-hidden="true" />}
        onClick={() => startArenaLogin(returnTo)}
        sx={{ minHeight: 48 }}
      >
        {getLocalizedText('login_arena_submit', 'Войти через BFME Arena')}
      </Button>

      <Divider sx={{ my: 2.5 }} />
      <Button
        type="button"
        fullWidth
        variant="text"
        aria-expanded={fallbackOpen}
        aria-controls="password-login-form"
        endIcon={fallbackOpen
          ? <ExpandLess aria-hidden="true" />
          : <ExpandMore aria-hidden="true" />}
        onClick={() => {
          setFallbackOpen((current) => !current);
          setError('');
        }}
      >
        {getLocalizedText('login_password_fallback', 'Войти по паролю')}
      </Button>

      <Collapse in={fallbackOpen} unmountOnExit>
        <Box
          id="password-login-form"
          component="form"
          onSubmit={handleSubmit}
          sx={{ pt: 1 }}
          aria-busy={submitting}
        >
          <Typography id="password-login-help" variant="body2" color="text.secondary">
            {getLocalizedText(
              'login_password_help',
              'Используйте текущий ник BFME Arena и ранее заданный локальный пароль.',
            )}
          </Typography>
          {error && (
            <Alert id="login-form-error" severity="error" aria-live="assertive" sx={{ mt: 1.5 }}>
              {error}
            </Alert>
          )}
          <TextField
            margin="normal"
            required
            fullWidth
            id="arena-nickname"
            label={getLocalizedText('login_arena_nickname', 'Ник BFME Arena')}
            name="nickname"
            autoComplete="username"
            autoFocus={autoFocus}
            value={formData.nickname}
            onChange={handleChange}
            error={Boolean(error)}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'password-login-help login-form-error' : 'password-login-help'}
          />
          <TextField
            margin="normal"
            required
            fullWidth
            name="password"
            label={getLocalizedText('login_password', 'Пароль')}
            type="password"
            id="password"
            autoComplete="current-password"
            value={formData.password}
            onChange={handleChange}
            error={Boolean(error)}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'password-login-help login-form-error' : 'password-login-help'}
          />
          <Button
            type="submit"
            fullWidth
            variant="outlined"
            sx={{ mt: 2, minHeight: 42 }}
            disabled={submitting}
          >
            {submitting
              ? <CircularProgress size={24} aria-label={getLocalizedText('common_loading', 'Загрузка...')} />
              : getLocalizedText('login_submit', 'Войти')}
          </Button>
        </Box>
      </Collapse>
    </Box>
  );
};

export default LoginForm;
