import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import { authService } from '../services/authService';
import {
  AUTH_SESSION_EXPIRED_EVENT,
  clearLegacyAuthStorage,
} from '../utils/authSession';

const AuthContext = createContext();

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const bootstrapStartedRef = useRef(false);
  const bootstrappedRef = useRef(false);

  useEffect(() => {
    if (bootstrapStartedRef.current) return;
    bootstrapStartedRef.current = true;

    const checkAuth = async () => {
      clearLegacyAuthStorage();
      try {
        setUser(await authService.getSession());
      } catch (error) {
        if (error.response?.status !== 401) {
          console.error('Ошибка при проверке сессии:', error);
        }
        setUser(null);
      } finally {
        bootstrappedRef.current = true;
        setLoading(false);
      }
    };

    checkAuth();
  }, []);

  useEffect(() => {
    const handleSessionExpired = () => {
      if (!bootstrappedRef.current) return;
      setUser(null);
    };

    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, []);

  const login = async (credentials) => {
    const session = await authService.login(credentials);
    setUser(session);
    return session;
  };

  const startArenaLogin = (returnTo) => authService.startArenaLogin(returnTo);

  const completeOnboarding = async (payload) => {
    const session = await authService.completeOnboarding(payload);
    setUser(session);
    return session;
  };

  const revokeAllSessions = async () => {
    const result = await authService.revokeAllSessions();
    setUser(null);
    return result;
  };

  const impersonateUser = async (userId) => {
    const session = await authService.impersonateUser(userId);
    setUser(session);
    return session;
  };

  const returnToAdmin = async () => {
    const session = await authService.returnFromImpersonation();
    setUser(session);
    return session;
  };

  const logout = async () => {
    try {
      await authService.logout();
    } finally {
      setUser(null);
    }
  };

  const updateUser = (updatedUserData) => {
    setUser(updatedUserData);
  };

  const value = {
    user,
    loading,
    login,
    startArenaLogin,
    completeOnboarding,
    revokeAllSessions,
    impersonateUser,
    returnToAdmin,
    logout,
    updateUser,
    isAuthenticated: !!user,
    isImpersonating: Boolean(user?.is_admin_impersonation),
    impersonatingAdminUsername: user?.impersonated_by_username || null
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}; 
