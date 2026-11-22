import React, { useState } from 'react';
import { Box, Button, CircularProgress, Typography } from '@mui/material';
import KeyboardReturnIcon from '@mui/icons-material/KeyboardReturn';

import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';


const ImpersonationBanner = () => {
  const {
    user,
    isImpersonating,
    impersonatingAdminUsername,
    returnToAdmin,
  } = useAuth();
  const { getLocalizedText } = useLocalizationContext();
  const [returning, setReturning] = useState(false);
  const [error, setError] = useState('');

  if (!isImpersonating || !user) return null;

  const handleReturn = async () => {
    setReturning(true);
    setError('');
    try {
      await returnToAdmin();
    } catch {
      setError(getLocalizedText(
        'impersonation_return_error',
        'Не удалось вернуться в административную сессию. Повторите попытку.',
      ));
      setReturning(false);
    }
  };

  return (
    <Box
      component="section"
      role="region"
      aria-label={getLocalizedText(
        'impersonation_banner_label',
        'Режим просмотра пользователя',
      )}
      aria-busy={returning}
      sx={{
        width: '100%',
        borderBottom: '1px solid',
        borderColor: 'warning.dark',
        bgcolor: 'warning.light',
        color: 'warning.contrastText',
      }}
    >
      <Box
        sx={{
          maxWidth: 1200,
          mx: 'auto',
          px: { xs: 2, sm: 3 },
          py: 1.25,
          display: 'flex',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 1.5,
        }}
      >
        <Typography sx={{ fontWeight: 700, lineHeight: 1.4 }}>
          {getLocalizedText(
            'impersonation_banner_message',
            'Вы просматриваете сайт как {target}. Реальный администратор: {actor}.',
            {
              target: user.display_name || user.username,
              actor: impersonatingAdminUsername,
            },
          )}
        </Typography>
        <Button
          type="button"
          variant="contained"
          color="inherit"
          onClick={handleReturn}
          disabled={returning}
          startIcon={returning ? (
            <CircularProgress size={18} color="inherit" aria-hidden="true" />
          ) : (
            <KeyboardReturnIcon />
          )}
          sx={{ flex: '0 0 auto' }}
        >
          {returning
            ? getLocalizedText('impersonation_returning', 'Возвращаемся...')
            : getLocalizedText('impersonation_return', 'Вернуться к администратору')}
        </Button>
        {error && (
          <Typography
            role="alert"
            sx={{ flexBasis: '100%', fontWeight: 700 }}
          >
            {error}
          </Typography>
        )}
      </Box>
    </Box>
  );
};

export default ImpersonationBanner;
