import React, { useEffect } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import HomePage from '../pages/HomePage';
import AuthRequiredDialog from './AuthRequiredDialog';
import { showError } from '../utils/notifications';

const AccessDeniedRedirect = ({ message }) => {
  useEffect(() => {
    showError(message);
  }, [message]);

  return <Navigate to="/" replace />;
};

const ProtectedAdminRoute = ({ children }) => {
  const { user, isAuthenticated, loading } = useAuth();
  const { getLocalizedText } = useLocalizationContext();
  const navigate = useNavigate();

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  if (!isAuthenticated) {
    return (
      <>
        <HomePage />
        <AuthRequiredDialog open onClose={() => navigate('/', { replace: true })} />
      </>
    );
  }

  if (!user?.role || user.role.name !== 'admin') {
    return <AccessDeniedRedirect message={getLocalizedText('access_denied', 'Доступ запрещен. Требуется роль администратора.')} />;
  }

  return children;
};

export default ProtectedAdminRoute;
