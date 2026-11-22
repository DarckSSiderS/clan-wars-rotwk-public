import React, { useCallback, useEffect, useState } from 'react';
import { NavLink, useLocation, useNavigate } from 'react-router-dom';
import {
  AppBar,
  Avatar,
  Box,
  Button,
  CircularProgress,
  Container,
  IconButton,
  Menu,
  MenuItem,
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material';
import {
  AdminPanelSettings,
  EmojiEvents,
  FeedbackOutlined,
  ExitToApp,
  GroupAdd,
  Language as LanguageIcon,
  Login,
  Lock,
  MailOutline,
  MenuBookRounded,
  Menu as MenuIcon,
  MilitaryTech,
  NotificationsNone,
  Person,
  ShoppingBag,
  TaskAlt,
  Timeline,
} from '@mui/icons-material';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { LANGUAGES } from '../i18n/messages';
import { notificationService } from '../services/notificationService';
import { messagingService } from '../services/messagingService';
import { useRealtimeEvent } from '../contexts/RealtimeContext';
import { getPlayerDisplayName } from '../utils/playerIdentity';
import { getNotificationPresentation } from '../utils/notificationPresentation';
import LanguageFlag from './LanguageFlag';
import PatchSwitcher from './PatchSwitcher';
import './Navigation.css';

const STATISTICS_ROUTES = [
  '/statistics',
  '/all-matches',
  '/influence-history',
];

const notificationIcon = (type) => {
  if (type === 'direct_message') return <MailOutline />;
  if (type === 'online_request') return <Person />;
  if (type === 'clan_invite' || type === 'clan_application') return <GroupAdd />;
  if (type === 'shop_purchase' || type?.startsWith('clan_relic_') || type?.startsWith('clan_trade_')) return <ShoppingBag />;
  if (type?.startsWith('clan_')) return <GroupAdd />;
  if (type === 'achievement_completed') return <EmojiEvents />;
  if (type === 'war_started' || type === 'war_completed') return <MilitaryTech />;
  if (type?.endsWith('_response')) return <TaskAlt />;
  return <NotificationsNone />;
};

const Navigation = () => {
  const {
    user,
    logout,
    returnToAdmin,
    isAuthenticated,
    isImpersonating,
    impersonatingAdminUsername,
  } = useAuth();
  const { language, changeLanguage, getLocalizedText: t } = useLocalizationContext();
  const location = useLocation();
  const navigate = useNavigate();
  const [accountAnchor, setAccountAnchor] = useState(null);
  const [mobileAnchor, setMobileAnchor] = useState(null);
  const [languageAnchor, setLanguageAnchor] = useState(null);
  const [notificationsAnchor, setNotificationsAnchor] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [unreadMessageCount, setUnreadMessageCount] = useState(0);
  const statisticsActive = STATISTICS_ROUTES.includes(location.pathname);
  const isAdmin = user?.role?.name === 'admin';
  const accountDisplayName = getPlayerDisplayName(user, '?');
  const shopLockedMessage = t(
    'shop_locked_message',
    'Караван с припасами в пути, магазин недоступен',
  );

  const loadUnreadCount = useCallback(async () => {
    try {
      setUnreadCount(await notificationService.getUnreadCount());
    } catch {
      setUnreadCount(0);
    }
  }, []);

  const loadNotifications = useCallback(async () => {
    setNotificationsLoading(true);
    setNotificationsError(false);
    try {
      const data = await notificationService.getNotifications({ limit: 30, unread_only: true });
      setNotifications(data.items || []);
      setUnreadCount(data.unread_count || 0);
    } catch {
      setNotificationsError(true);
    } finally {
      setNotificationsLoading(false);
    }
  }, []);

  const loadUnreadMessages = useCallback(async () => {
    try {
      const conversations = await messagingService.list();
      setUnreadMessageCount(conversations.reduce(
        (total, conversation) => total + Number(conversation.unread_count || 0),
        0,
      ));
    } catch {
      setUnreadMessageCount(0);
    }
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      loadUnreadCount();
      loadUnreadMessages();
    } else {
      setNotifications([]);
      setUnreadCount(0);
      setUnreadMessageCount(0);
      setNotificationsAnchor(null);
    }
  }, [isAuthenticated, loadUnreadCount, loadUnreadMessages, user?.id]);

  useEffect(() => {
    if (!isAuthenticated) return undefined;

    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') {
        loadUnreadCount();
        loadUnreadMessages();
      }
    };
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);

    return () => {
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [isAuthenticated, loadUnreadCount, loadUnreadMessages, user?.id]);

  useRealtimeEvent((event) => {
    if (!isAuthenticated) return;
    if (event.type === 'notification.created') {
      setUnreadCount((count) => count + 1);
      setNotifications((items) => {
        const notification = event.notification;
        if (!notification || items.some((item) => item.id === notification.id)) return items;
        return [notification, ...items].slice(0, 30);
      });
    } else if (event.type === 'notification.read') {
      setNotifications((items) => items.filter((item) => item.id !== event.notification_id));
      setUnreadCount((count) => Math.max(0, count - 1));
    } else if (event.type === 'notifications.read_all') {
      setNotifications([]);
      setUnreadCount(0);
    }
    if (event.type === 'message.created' || event.type === 'messages.read') {
      loadUnreadMessages();
    }
  });

  const closeAccount = () => setAccountAnchor(null);
  const closeMobile = () => setMobileAnchor(null);

  const openNotifications = (event) => {
    setNotificationsAnchor(event.currentTarget);
    loadNotifications();
  };

  const openNotification = async (notification) => {
    if (!notification.read_at) {
      try {
        await notificationService.markRead(notification.id);
        setNotifications((items) => items.filter((item) => item.id !== notification.id));
        setUnreadCount((count) => Math.max(0, count - 1));
      } catch {
        // Переход к связанному экрану остаётся доступным даже при сбое отметки.
      }
    }
    setNotificationsAnchor(null);
    if (notification.link_url) navigate(notification.link_url);
  };

  const markAllNotificationsRead = async () => {
    try {
      await notificationService.markAllRead();
      setNotifications([]);
      setUnreadCount(0);
    } catch {
      setNotificationsError(true);
    }
  };

  const formatNotificationTime = (value) => {
    if (!value) return '';
    const locale = language === 'en' ? 'en-GB' : language === 'de' ? 'de-DE' : 'ru-RU';
    return new Intl.DateTimeFormat(locale, {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(value));
  };

  const navigateFromMenu = (path, closeMenu) => {
    closeMenu();
    navigate(path);
  };

  const handleLogout = () => {
    logout();
    closeAccount();
    navigate('/');
  };

  const handleReturnToAdmin = async () => {
    await returnToAdmin();
    closeAccount();
    navigate('/profile');
  };

  const mainLinks = [
    ['/map', t('nav_map', 'Карта')],
    ['/clans', t('nav_clans', 'Кланы')],
    ['/battles', t('nav_wars', 'Битвы')],
    ['/ranking', t('nav_rating', 'Рейтинг')],
    ['/statistics', t('nav_statistics', 'Статистика')],
    ['/encyclopedia', t('nav_encyclopedia')],
    ['/seasons', t('season_archive_title')],
    ['/shop', t('nav_relics', 'Магазин'), true],
  ];
  const mobileLinks = [['/', t('nav_home', 'Главная')], ...mainLinks];

  const statisticsLinks = [
    ['/statistics', t('nav_statistics_overall', 'Общая статистика'), '/icons/axeswb.png'],
    ['/clan-statistics', t('nav_statistics_clans', 'Статистика кланов'), '/icons/towerwb.png'],
    ['/all-matches', t('nav_statistics_matches', 'Все матчи'), '/icons/sauronwb.png'],
    ['/influence-history', t('nav_influence_history', 'История влияния'), Timeline],
  ];

  return (
    <AppBar component="header" position="sticky" elevation={0} className="cw-navigation">
      <Container maxWidth={false} className="cw-navigation__container">
        <Toolbar disableGutters className="cw-navigation__toolbar">
          <Typography
            component={NavLink}
            to="/"
            aria-label="BFME ClanWars"
            className="cw-navigation__brand"
          >
            <img src="/brand/clanwar-logo.png" alt="" aria-hidden="true" />
          </Typography>

          <Box component="nav" aria-label={t('nav_primary', 'Основная навигация')} className="cw-navigation__desktop">
            {mainLinks.map(([path, label, locked]) => (
              locked && !isAdmin ? (
                <Tooltip title={shopLockedMessage} arrow key={path}>
                  <span className="cw-navigation__link cw-navigation__link--locked" aria-disabled="true">
                    {label}<Lock />
                  </span>
                </Tooltip>
              ) : (
                <NavLink
                  key={path}
                  to={path}
                  end={path === '/'}
                  className={({ isActive }) => [
                    'cw-navigation__link',
                    (isActive || (path === '/statistics' && statisticsActive)) && 'cw-navigation__link--active',
                  ].filter(Boolean).join(' ')}
                >
                  {label}
                </NavLink>
              )
            ))}

          </Box>

          <PatchSwitcher className="cw-navigation__patch-switch" />

          <IconButton
            size="large"
            aria-label={t('nav_open_menu', 'Открыть меню')}
            aria-controls={mobileAnchor ? 'mobile-navigation-menu' : undefined}
            aria-haspopup="true"
            aria-expanded={Boolean(mobileAnchor)}
            onClick={(event) => setMobileAnchor(event.currentTarget)}
            color="inherit"
            className="cw-navigation__mobile-trigger"
          >
            <MenuIcon />
          </IconButton>

          <IconButton
            size="large"
            aria-label={t('nav_language', 'Язык')}
            aria-controls={languageAnchor ? 'language-menu' : undefined}
            aria-haspopup="true"
            aria-expanded={Boolean(languageAnchor)}
            onClick={(event) => setLanguageAnchor(event.currentTarget)}
            color="inherit"
            className="cw-navigation__language-trigger"
          >
            <LanguageIcon />
            <span className="cw-navigation__language-code">{language.toUpperCase()}</span>
          </IconButton>

          {isAuthenticated && (
            <IconButton
              size="large"
              aria-label={unreadMessageCount
                ? t('nav_messages_unread_count', 'Сообщения: {count} непрочитанных', { count: unreadMessageCount })
                : t('nav_messages', 'Сообщения')}
              onClick={() => navigate('/messages')}
              color="inherit"
              className="cw-navigation__messages-trigger"
            >
              <MailOutline />
              {unreadMessageCount > 0 && <span className="cw-navigation__message-dot" aria-hidden="true" />}
            </IconButton>
          )}

          {isAuthenticated && (
            <IconButton
              size="large"
              aria-label={unreadCount
                ? t('nav_notifications_unread_count', 'Уведомления: {count} непрочитанных', { count: unreadCount })
                : t('nav_notifications', 'Уведомления')}
              aria-controls={notificationsAnchor ? 'notifications-menu' : undefined}
              aria-haspopup="true"
              aria-expanded={Boolean(notificationsAnchor)}
              onClick={openNotifications}
              color="inherit"
              className="cw-navigation__notifications-trigger"
            >
              <NotificationsNone />
              {unreadCount > 0 && (
                <span className="cw-navigation__notification-dot" aria-hidden="true">
                  {unreadCount > 99 ? '99+' : unreadCount}
                </span>
              )}
            </IconButton>
          )}

          {isAuthenticated ? (
            <IconButton
              size="large"
              aria-label={t('nav_profile', 'Профиль')}
              aria-controls={accountAnchor ? 'account-navigation-menu' : undefined}
              aria-haspopup="true"
              aria-expanded={Boolean(accountAnchor)}
              onClick={(event) => setAccountAnchor(event.currentTarget)}
              color="inherit"
              className="cw-navigation__account-trigger"
            >
              {user?.avatar_url ? (
                <Avatar src={user.avatar_url} alt="" className="cw-navigation__avatar" />
              ) : (
                <Avatar aria-hidden="true" className="cw-navigation__avatar cw-navigation__avatar--fallback">
                  {accountDisplayName.slice(0, 1).toUpperCase()}
                </Avatar>
              )}
              <span className="cw-navigation__account-copy">
                <strong>{accountDisplayName}</strong>
              </span>
            </IconButton>
          ) : (
            <Button
              component={NavLink}
              to="/login"
              color="inherit"
              aria-label={t('nav_login', 'Войти')}
              startIcon={<Login />}
              className="cw-navigation__login"
            >
              <span>{t('nav_login', 'Войти')}</span>
            </Button>
          )}

          <Menu
            id="mobile-navigation-menu"
            anchorEl={mobileAnchor}
            open={Boolean(mobileAnchor)}
            onClose={closeMobile}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
            slotProps={{ paper: { className: 'cw-navigation__mobile-menu' } }}
          >
            {mobileLinks.map(([path, label, locked]) => (
              <MenuItem
                key={path}
                selected={location.pathname === path}
                disabled={locked && !isAdmin}
                title={locked && !isAdmin ? shopLockedMessage : undefined}
                onClick={() => !(locked && !isAdmin) && navigateFromMenu(path, closeMobile)}
              >
                {label}
                {locked && !isAdmin && <Lock className="cw-navigation__menu-lock" />}
              </MenuItem>
            ))}
            <MenuItem disabled className="cw-navigation__menu-heading">
              {t('nav_statistics', 'Статистика')}
            </MenuItem>
            {statisticsLinks.map(([path, label]) => (
              <MenuItem
                key={path}
                selected={location.pathname === path}
                onClick={() => navigateFromMenu(path, closeMobile)}
              >
                {label}
              </MenuItem>
            ))}
            {!isAuthenticated && (
              <MenuItem onClick={() => navigateFromMenu('/login', closeMobile)}>
                {t('nav_login', 'Войти')}
              </MenuItem>
            )}
            {isAuthenticated && (
              <MenuItem onClick={() => navigateFromMenu('/profile', closeMobile)}>
                <Person className="cw-navigation__menu-icon" />
                {t('nav_profile', 'Профиль')}
              </MenuItem>
            )}
            {isAuthenticated && (
              <MenuItem onClick={() => navigateFromMenu('/messages', closeMobile)}>
                <MailOutline className="cw-navigation__menu-icon" />
                {t('nav_messages', 'Сообщения')}
                {unreadMessageCount > 0 && <b className="cw-navigation__menu-count">{unreadMessageCount}</b>}
              </MenuItem>
            )}
            {isAuthenticated && (
              <MenuItem onClick={() => navigateFromMenu('/achievements', closeMobile)}>
                <EmojiEvents className="cw-navigation__menu-icon" />
                {t('achievements_page_title', 'Достижения')}
              </MenuItem>
            )}
            {isAuthenticated && (
              <MenuItem onClick={() => navigateFromMenu('/rules', closeMobile)}>
                <MenuBookRounded className="cw-navigation__menu-icon" />
                {t('nav_rules', 'Правила ClanWar')}
              </MenuItem>
            )}
            {isAuthenticated && (
              <MenuItem onClick={() => navigateFromMenu(`/feedback?from=${encodeURIComponent(location.pathname)}`, closeMobile)}>
                <FeedbackOutlined className="cw-navigation__menu-icon" />
                {t('nav_feedback', 'Обратная связь')}
              </MenuItem>
            )}
            {isAuthenticated && (
              <MenuItem onClick={() => navigateFromMenu('/profile?tab=invitations', closeMobile)}>
                <GroupAdd className="cw-navigation__menu-icon" />
                {t('profile_invites_title', 'Приглашения')}
              </MenuItem>
            )}
            {isAuthenticated && (
              <MenuItem onClick={() => navigateFromMenu('/profile?tab=quests', closeMobile)}>
                <TaskAlt className="cw-navigation__menu-icon" />
                {t('profile_tab_quests', 'Задания')}
              </MenuItem>
            )}
            {user?.role?.name === 'admin' && (
              <MenuItem onClick={() => navigateFromMenu('/admin', closeMobile)}>
                <AdminPanelSettings className="cw-navigation__menu-icon" />
                {t('nav_admin', 'Админ-панель')}
              </MenuItem>
            )}
            {isAuthenticated && (
              <MenuItem onClick={() => { closeMobile(); handleLogout(); }}>
                <ExitToApp className="cw-navigation__menu-icon" />
                {t('nav_logout', 'Выйти')}
              </MenuItem>
            )}
          </Menu>

          <Menu
            id="language-menu"
            anchorEl={languageAnchor}
            open={Boolean(languageAnchor)}
            onClose={() => setLanguageAnchor(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
            slotProps={{ paper: { className: 'cw-navigation__menu-paper' } }}
          >
            {LANGUAGES.map((item) => (
              <MenuItem
                key={item.code}
                selected={language === item.code}
                onClick={() => {
                  changeLanguage(item.code);
                  setLanguageAnchor(null);
                }}
                className="cw-navigation__language-option"
              >
                <LanguageFlag language={item.code} />
                <strong>{item.shortLabel}</strong>
                <span>{item.label}</span>
              </MenuItem>
            ))}
          </Menu>

          <Menu
            id="notifications-menu"
            anchorEl={notificationsAnchor}
            open={Boolean(notificationsAnchor)}
            onClose={() => setNotificationsAnchor(null)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
            slotProps={{
              paper: { className: 'cw-navigation__notification-menu' },
              list: { 'aria-label': t('nav_notifications', 'Уведомления') },
            }}
          >
            <li className="cw-navigation__notification-header" role="presentation">
              <span className="cw-navigation__notification-eyebrow">
                {t('nav_notifications', 'Уведомления')}
              </span>
              {unreadCount > 0 && (
                <Button size="small" onClick={markAllNotificationsRead}>
                  {t('nav_notifications_mark_all', 'Прочитать все')}
                </Button>
              )}
            </li>
            {notificationsLoading ? (
              <li className="cw-navigation__notification-state" role="status">
                <CircularProgress size={24} />
                <span>{t('common_loading', 'Загрузка...')}</span>
              </li>
            ) : notificationsError ? (
              <li className="cw-navigation__notification-state" role="alert">
                <strong>{t('nav_notifications_load_error', 'Не удалось загрузить события')}</strong>
                <Button size="small" onClick={loadNotifications}>
                  {t('nav_notifications_retry', 'Повторить')}
                </Button>
              </li>
            ) : notifications.length ? notifications.map((notification) => {
              const copy = getNotificationPresentation(notification, language, t);
              return (
                <MenuItem
                  key={notification.id}
                  className={`cw-navigation__notification-item${notification.read_at ? '' : ' is-unread'}`}
                  onClick={() => openNotification(notification)}
                >
                  <span className="cw-navigation__notification-icon" aria-hidden="true">
                    {notificationIcon(notification.notification_type)}
                  </span>
                  <span className="cw-navigation__notification-copy">
                    <strong>{copy.title}</strong>
                    <span>{copy.message}</span>
                    <time dateTime={notification.created_at}>{formatNotificationTime(notification.created_at)}</time>
                  </span>
                </MenuItem>
              );
            }) : (
              <li className="cw-navigation__notification-panel">
                <strong>{t('nav_notifications_empty', 'Новых событий пока нет')}</strong>
                <p>{t('nav_notifications_empty_copy', 'Здесь появятся приглашения, решения по заявкам, покупки и награды.')}</p>
              </li>
            )}
          </Menu>

          <Menu
            id="account-navigation-menu"
            anchorEl={accountAnchor}
            open={Boolean(accountAnchor)}
            onClose={closeAccount}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
            slotProps={{ paper: { className: 'cw-navigation__menu-paper' } }}
          >
            <MenuItem onClick={() => navigateFromMenu('/profile', closeAccount)}>
              <Person className="cw-navigation__menu-icon" />
              {t('nav_profile', 'Профиль')}
            </MenuItem>
            <MenuItem onClick={() => navigateFromMenu('/messages', closeAccount)}>
              <MailOutline className="cw-navigation__menu-icon" />
              {t('nav_messages', 'Сообщения')}
              {unreadMessageCount > 0 && <b className="cw-navigation__menu-count">{unreadMessageCount}</b>}
            </MenuItem>
            <MenuItem onClick={() => navigateFromMenu('/rules', closeAccount)}>
              <MenuBookRounded className="cw-navigation__menu-icon" />
              {t('nav_rules', 'Правила ClanWar')}
            </MenuItem>
            <MenuItem onClick={() => navigateFromMenu('/profile?tab=invitations', closeAccount)}>
              <GroupAdd className="cw-navigation__menu-icon" />
              {t('profile_invites_title', 'Приглашения')}
            </MenuItem>
            {user?.role?.name === 'admin' && (
              <MenuItem onClick={() => navigateFromMenu('/admin', closeAccount)}>
                <AdminPanelSettings className="cw-navigation__menu-icon" />
                {t('nav_admin', 'Админ-панель')}
              </MenuItem>
            )}
            {isImpersonating && (
              <MenuItem onClick={handleReturnToAdmin}>
                <AdminPanelSettings className="cw-navigation__menu-icon" />
                {t('nav_return_to_admin', 'Вернуться в {username}', {
                  username: impersonatingAdminUsername || 'администратора',
                })}
              </MenuItem>
            )}
            <MenuItem onClick={handleLogout}>
              <ExitToApp className="cw-navigation__menu-icon" />
              {t('nav_logout', 'Выйти')}
            </MenuItem>
          </Menu>
        </Toolbar>
      </Container>
    </AppBar>
  );
};

export default Navigation;
