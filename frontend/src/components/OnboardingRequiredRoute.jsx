import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const OnboardingRequiredRoute = ({ children }) => {
  const { user } = useAuth();
  const location = useLocation();

  if (user?.onboarding_required) {
    return <Navigate to="/onboarding" state={{ from: location }} replace />;
  }

  return children;
};

export default OnboardingRequiredRoute;
