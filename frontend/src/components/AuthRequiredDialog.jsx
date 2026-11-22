import React from 'react';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Typography,
} from '@mui/material';
import { Close, LockOutlined } from '@mui/icons-material';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import LoginForm from './LoginForm';

const AuthRequiredDialog = ({ open, onClose }) => {
  const { getLocalizedText } = useLocalizationContext();
  const title = getLocalizedText('auth_required_title', 'Войдите, чтобы продолжить');

  return (
    <Dialog
      className="auth-required-dialog"
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="xs"
      aria-labelledby="auth-required-title"
    >
      <DialogTitle
        id="auth-required-title"
        sx={{ display: 'flex', alignItems: 'center', gap: 1.25, pr: 6 }}
      >
        <LockOutlined color="primary" aria-hidden="true" />
        {title}
        <IconButton
          autoFocus
          aria-label={getLocalizedText('common_close', 'Закрыть')}
          onClick={onClose}
          sx={{ position: 'absolute', right: 10, top: 10 }}
        >
          <Close aria-hidden="true" />
        </IconButton>
      </DialogTitle>
      <DialogContent>
        <Typography color="text.secondary" sx={{ mb: 1.5 }}>
          {getLocalizedText(
            'auth_required_description',
            'Этот раздел доступен после авторизации. После входа откроется выбранная страница.',
          )}
        </Typography>
        <LoginForm />
      </DialogContent>
    </Dialog>
  );
};

export default AuthRequiredDialog;
