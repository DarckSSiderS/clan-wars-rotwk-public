import React from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Alert,
  Container,
  Paper,
  Typography,
  Box,
} from '@mui/material';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import LoginForm from '../components/LoginForm';

const LoginPage = () => {
  const { getLocalizedText } = useLocalizationContext();
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const oauthError = searchParams.get('oauth_error');

  const oauthMessages = {
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
  const oauthMessageKey = oauthMessages[oauthError] || (oauthError ? 'oauth_error_failed' : null);

  const handleSuccess = () => {
    const requestedPath = location.state?.from;
    const destination = requestedPath?.pathname
      ? `${requestedPath.pathname}${requestedPath.search || ''}${requestedPath.hash || ''}`
      : '/';
    navigate(destination, { replace: true });
  };

  return (
    <Container maxWidth="sm">
      <Box
        sx={{
          marginTop: 8,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
        }}
      >
        <Paper
          elevation={3}
          sx={{
            padding: 4,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            width: '100%',
          }}
        >
          <Typography component="h1" variant="h4" gutterBottom>
            {getLocalizedText('login_title', 'Вход')}
          </Typography>

          {oauthMessageKey && (
            <Alert severity="error" aria-live="polite" sx={{ width: '100%', mb: 2 }}>
              {getLocalizedText(oauthMessageKey, 'Не удалось войти через BFME Arena. Попробуйте ещё раз.')}
            </Alert>
          )}

          <LoginForm onSuccess={handleSuccess} />
        </Paper>
      </Box>
    </Container>
  );
};

export default LoginPage;
