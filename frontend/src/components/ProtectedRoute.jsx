import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { CircularProgress, Box } from '@mui/material';
import HomePage from '../pages/HomePage';
import AuthRequiredDialog from './AuthRequiredDialog';
import OnboardingRequiredRoute from './OnboardingRequiredRoute';

const ProtectedRoute = ({ children, allowOnboarding = false }) => {
  const { isAuthenticated, loading } = useAuth();
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

  if (allowOnboarding) return children;

  return <OnboardingRequiredRoute>{children}</OnboardingRequiredRoute>;
};

export default ProtectedRoute;
