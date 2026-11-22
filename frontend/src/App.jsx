import React, { lazy, Suspense, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { AuthProvider } from './contexts/AuthContext';
import { RealtimeProvider } from './contexts/RealtimeContext';
import { SiteThemeProvider } from './contexts/SiteThemeContext';
import { LocalizationProvider, useLocalizationContext } from './contexts/LocalizationContext';
import { PlayerIdentityProvider } from './contexts/PlayerIdentityContext';
import { PatchProvider } from './contexts/PatchContext';
import Navigation from './components/Navigation.jsx';
import PreviewScenarioSwitcher from './components/PreviewScenarioSwitcher';
import CycleWorkspace from './components/campaign/CycleWorkspace.jsx';
import ImpersonationBanner from './components/ImpersonationBanner.jsx';
import SiteFooter from './components/SiteFooter.jsx';
import ProtectedRoute from './components/ProtectedRoute';
import ProtectedAdminRoute from './components/ProtectedAdminRoute';
import HomePage from './pages/HomePage';
import { appBasePath, isAdminPreview } from './utils/appBasePath';
import './adminPreview.css';

const AuthPage = lazy(() => import('./pages/AuthPage'));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage'));
const ClansPage = lazy(() => import('./pages/ClansPage'));
const ClanViewPage = lazy(() => import('./pages/ClanViewPage'));
const ProfilePage = lazy(() => import('./pages/ProfilePage'));
const ShopPage = lazy(() => import('./pages/ShopPage'));
const WarsPage = lazy(() => import('./pages/CampaignBattlesEntry'));
const CycleBattlesPage = lazy(() => import('./pages/CycleBattlesPage'));
const CycleDiplomacyPage = lazy(() => import('./pages/CycleDiplomacyPage'));
const CycleOrdersPage = lazy(() => import('./pages/CycleOrdersPage'));
const CycleReinforcementsPage = lazy(() => import('./pages/CycleReinforcementsPage'));
const CycleEconomyPage = lazy(() => import('./pages/CycleEconomyPage'));
const CyclePreparationPage = lazy(() => import('./pages/CyclePreparationPage'));
const PreseasonPage = lazy(() => import('./pages/PreseasonPage'));
const CycleInterceptionPage = lazy(() => import('./pages/CycleInterceptionPage'));
const WarDetailPage = lazy(() => import('./pages/WarDetailPrototypePage'));
const MapPage = lazy(() => import('./pages/MapPage'));
const StatisticsPage = lazy(() => import('./pages/StatisticsPage'));
const AllMatchesPage = lazy(() => import('./pages/AllMatchesPage'));
const AdminSyncPage = lazy(() => import('./pages/AdminSyncPage'));
const AdminDashboardPage = lazy(() => import('./pages/AdminDashboardPage'));
const InfluenceHistoryPage = lazy(() => import('./pages/InfluenceHistoryPage'));
const RankingPage = lazy(() => import('./pages/RankingPage'));
const SeasonArchivePage = lazy(() => import('./pages/SeasonArchivePage'));
const AchievementsPage = lazy(() => import('./pages/AchievementsPage'));
const MessagesPage = lazy(() => import('./pages/MessagesPage'));
const FeedbackPage = lazy(() => import('./pages/FeedbackPage'));
const RulesPage = lazy(() => import('./pages/RulesPage'));
const EncyclopediaPage = lazy(() => import('./pages/EncyclopediaPage'));
const Agentation = import.meta.env.DEV && import.meta.env.VITE_AGENTATION_ENABLED === 'true'
  ? lazy(() => import('agentation').then((module) => ({ default: module.Agentation })))
  : null;

const RouteFallback = () => {
  const { getLocalizedText } = useLocalizationContext();

  return (
    <Box
      role="status"
      aria-label={getLocalizedText('common_loading', 'Загрузка...')}
      sx={{ minHeight: '45vh', display: 'grid', placeItems: 'center' }}
    >
      <CircularProgress />
    </Box>
  );
};

const AdminPreviewBanner = () => {
  const { t } = useLocalizationContext();
  return isAdminPreview && <aside className="admin-preview-banner"><strong>{t('admin_preview_mode')}</strong><PreviewScenarioSwitcher /><a href="/admin">{t('admin_preview_return')}</a></aside>;
};

const resolveRouteArt = (pathname) => {
  if (pathname === '/') return 'home';
  if (pathname.startsWith('/map')) return 'map';
  if (pathname.startsWith('/seasons')) return 'map';
  if (pathname.startsWith('/clans/')) return 'clan';
  if (pathname.startsWith('/clans')) return 'clans';
  if (pathname.startsWith('/wars') || pathname.startsWith('/battles')) return 'battles';
  if (pathname.startsWith('/campaign/cycles/')) return 'battles';
  if (pathname.startsWith('/ranking')) return 'ranking';
  if (pathname.startsWith('/rules')) return 'ranking';
  if (pathname.startsWith('/encyclopedia')) return 'ranking';
  if (pathname.startsWith('/achievements')) return 'achievements';
  if (pathname.startsWith('/feedback')) return 'profile';
  if (pathname.startsWith('/shop')) return 'shop';
  if (pathname.startsWith('/profile')) return 'profile';
  if (pathname.startsWith('/login') || pathname.startsWith('/register') || pathname.startsWith('/recover') || pathname.startsWith('/onboarding')) return 'auth';
  if (pathname.startsWith('/influence-history')) return 'chronicle';
  if (pathname.startsWith('/statistics') || pathname.startsWith('/all-matches')) return 'stats';
  if (pathname.startsWith('/admin')) return 'admin';
  return 'home';
};

const RouteArt = () => {
  const { pathname } = useLocation();

  useEffect(() => {
    const container = document.querySelector('.app-container');
    if (container) {
      container.dataset.routeArt = resolveRouteArt(pathname);
      container.dataset.adminDashboard = String(pathname === '/admin');
    }
  }, [pathname]);

  return null;
};


function App() {
  return (
    <AuthProvider>
      <RealtimeProvider>
        <SiteThemeProvider>
        <LocalizationProvider>
          <PatchProvider>
          <Router basename={appBasePath}>
            <PlayerIdentityProvider>
              <div className="app-container">
              <AdminPreviewBanner />
              <RouteArt />
              <Navigation />
              <ImpersonationBanner />
              <Suspense fallback={<RouteFallback />}>
                <Routes>
                <Route path="/" element={<HomePage />} />
                <Route path="/rules" element={<RulesPage />} />
                <Route path="/encyclopedia" element={<EncyclopediaPage />} />
                <Route path="/login" element={<AuthPage />} />
                <Route path="/register" element={<AuthPage />} />
                <Route path="/recover" element={<AuthPage />} />
                <Route
                  path="/onboarding"
                  element={(
                    <ProtectedRoute allowOnboarding>
                      <OnboardingPage />
                    </ProtectedRoute>
                  )}
                />

                <Route 
                  path="/clans" 
                  element={
                    <ProtectedRoute>
                      <ClansPage />
                    </ProtectedRoute>
                  } 
                />
                <Route 
                  path="/clans/:clanId" 
                  element={
                    <ProtectedRoute>
                      <ClanViewPage />
                    </ProtectedRoute>
                  } 
                />
                <Route 
                  path="/wars" 
                  element={
                    <ProtectedRoute>
                      <WarsPage />
                    </ProtectedRoute>
                  } 
                />
                <Route
                  path="/battles"
                  element={
                    <ProtectedRoute>
                      <WarsPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/campaign/cycles/:cycleId"
                  element={<ProtectedRoute><CycleWorkspace fallback={<RouteFallback />} /></ProtectedRoute>}
                >
                  <Route index element={<CycleBattlesPage />} />
                  <Route path="orders" element={<CycleOrdersPage />} />
                  <Route path="reinforcements" element={<CycleReinforcementsPage />} />
                  <Route path="diplomacy" element={<CycleDiplomacyPage />} />
                  <Route path="preparation" element={<CyclePreparationPage />} />
                  <Route path="interception" element={<CycleInterceptionPage />} />
                </Route>
                <Route path="/preseason" element={<ProtectedRoute><PreseasonPage /></ProtectedRoute>} />
                <Route path="/campaign/cycles/:cycleId/economy" element={<ProtectedRoute><CycleEconomyPage /></ProtectedRoute>} />
                <Route
                  path="/wars/:warId"
                  element={
                    <ProtectedRoute>
                      <WarDetailPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/battles/:warId"
                  element={
                    <ProtectedRoute>
                      <WarDetailPage />
                    </ProtectedRoute>
                  }
                />
                <Route 
                  path="/map" 
                  element={
                    <ProtectedRoute>
                      <MapPage />
                    </ProtectedRoute>
                  } 
                />
                <Route 
                  path="/profile" 
                  element={
                    <ProtectedRoute>
                      <ProfilePage />
                    </ProtectedRoute>
                  } 
                />
                <Route
                  path="/shop"
                  element={
                    <ProtectedAdminRoute>
                      <ShopPage />
                    </ProtectedAdminRoute>
                  }
                />
                <Route 
                  path="/profile/:username" 
                  element={
                    <ProtectedRoute>
                      <ProfilePage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/messages"
                  element={
                    <ProtectedRoute>
                      <MessagesPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/feedback"
                  element={
                    <ProtectedRoute>
                      <FeedbackPage />
                    </ProtectedRoute>
                  }
                />
                <Route 
                  path="/statistics" 
                  element={
                    <ProtectedRoute>
                      <StatisticsPage />
                    </ProtectedRoute>
                  } 
                />
                <Route path="/clan-statistics" element={<Navigate to="/ranking" replace />} />
                <Route
                  path="/ranking"
                  element={
                    <ProtectedRoute>
                      <RankingPage />
                    </ProtectedRoute>
                  }
                />
                <Route
                  path="/achievements"
                  element={
                    <ProtectedRoute>
                      <AchievementsPage />
                    </ProtectedRoute>
                  }
                />
                <Route 
                  path="/all-matches" 
                  element={
                    <ProtectedRoute>
                      <AllMatchesPage />
                    </ProtectedRoute>
                  } 
                />
                <Route
                  path="/influence-history"
                  element={
                    <ProtectedRoute>
                      <InfluenceHistoryPage />
                    </ProtectedRoute>
                  }
                />
                <Route path="/seasons" element={<SeasonArchivePage />} />
                <Route path="/seasons/:seasonId" element={<SeasonArchivePage />} />
                <Route
                  path="/admin"
                  element={
                    <ProtectedAdminRoute>
                      <AdminDashboardPage />
                    </ProtectedAdminRoute>
                  }
                />
                <Route
                  path="/admin/sync"
                  element={
                    <ProtectedAdminRoute>
                      <AdminSyncPage />
                    </ProtectedAdminRoute>
                  }
                />

                {/* Добавим другие защищенные маршруты позже */}
                <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Suspense>
              <SiteFooter />
              </div>
            </PlayerIdentityProvider>
          </Router>
          </PatchProvider>
        </LocalizationProvider>
        {Agentation && (
          <Suspense fallback={null}>
            <Agentation endpoint="http://localhost:4747" />
          </Suspense>
        )}
        </SiteThemeProvider>
      </RealtimeProvider>
    </AuthProvider>
  );
}

export default App;
