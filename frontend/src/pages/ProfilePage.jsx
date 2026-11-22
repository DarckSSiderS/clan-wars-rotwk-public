import React, { useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { showSuccess, showError } from '../utils/notifications';
import SchedulerStatus from '../components/SchedulerStatus';
import AvatarUpload from '../components/AvatarUpload';
import QuestsSection from '../components/QuestsSection';
import StatisticsSection from '../components/StatisticsSection';
import ProfileAchievements from '../components/ProfileAchievements';
import PlayerIdentity, { PlayerTitles } from '../components/PlayerIdentity';
import { usePlayerIdentity } from '../contexts/PlayerIdentityContext';
import streamService from '../services/streamService';
import { normalizeLanguage } from '../i18n/messages';
import { useSiteTheme } from '../contexts/SiteThemeContext';
import { SITE_THEME_ITEM_TYPE } from '../theme/siteThemes';
import { getPlayerDisplayName, getPlayerProfilePath } from '../utils/playerIdentity';
import ProfileView from '../components/ProfileView';
import ProfileInventoryTab from '../components/profile/ProfileInventoryTab';
import { apiFetch } from '../services/apiFetch';
import './ProfilePage.css';

const useLatest = (value) => {
  const ref = useRef(value);
  useEffect(() => {
    ref.current = value;
  }, [value]);
  return ref;
};

const PROFILE_TABS = new Set([
  'overview', 'matches', 'statistics', 'achievements', 'relics', 'territories',
  'invitations', 'quests', 'inventory', 'settings',
]);

const ProfilePage = () => {
  const { username } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const {
    user: currentUser,
    updateUser,
    impersonateUser,
    isImpersonating
  } = useAuth();
  const { getLocalizedText, loadPageTexts, language, changeLanguage } = useLocalizationContext();
  const { getIdentity } = usePlayerIdentity();
  const { refreshSiteTheme } = useSiteTheme();
  
  const [loading, setLoading] = useState(true);
  const [user, setUser] = useState(null);
  const [userClan, setUserClan] = useState(null);
  const [invites, setInvites] = useState([]);
  const [activeTab, setActiveTab] = useState(() => {
    const requested = searchParams.get('tab');
    return PROFILE_TABS.has(requested) ? requested : 'overview';
  });
  const [playerStats, setPlayerStats] = useState(null);
  const [userInventory, setUserInventory] = useState([]);
  const [userAchievements, setUserAchievements] = useState(null);
  const [profileData, setProfileData] = useState({
    username: '',
    email: '',
    balance: 0
  });
  const [currentAvatarUrl, setCurrentAvatarUrl] = useState('');
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [verificationUpdating, setVerificationUpdating] = useState(false);
  const [impersonationStarting, setImpersonationStarting] = useState(false);
  const [settingsData, setSettingsData] = useState({
    language: 'ru',
    allow_clan_invites: true,
    telegram_url: '',
    twitch_url: '',
    youtube_url: ''
  });
  const [updatingSettings, setUpdatingSettings] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(() => !username && searchParams.get('tab') === 'settings');
  const [clanCreationOpen, setClanCreationOpen] = useState(false);
  const [balanceOpen, setBalanceOpen] = useState(false);
  const [balanceAmount, setBalanceAmount] = useState('');
  const [balanceUpdating, setBalanceUpdating] = useState(false);
  const [verificationAction, setVerificationAction] = useState(null);
  const [verificationReason, setVerificationReason] = useState('');
  const [streamStatus, setStreamStatus] = useState({
    twitch: false,
    youtube: false
  });
  
  // Определяем, является ли это профилем текущего пользователя
  const requestedProfileName = String(username || '').toLocaleLowerCase();
  const isOwnProfile = !username || Boolean(currentUser && [
    currentUser.username,
    getPlayerDisplayName(currentUser),
  ].some((name) => String(name || '').toLocaleLowerCase() === requestedProfileName));
  const isAdmin = currentUser?.role?.name === 'admin'
    || currentUser?.is_admin_impersonation
    || isImpersonating;
  const targetUsername = username || (currentUser ? currentUser.username : null);

  useEffect(() => {
    const requested = searchParams.get('tab');
    const nextTab = PROFILE_TABS.has(requested) ? requested : 'overview';
    if (!isOwnProfile && (nextTab === 'invitations' || nextTab === 'quests')) {
      setActiveTab('overview');
      return;
    }
    setActiveTab(nextTab);
  }, [isOwnProfile, searchParams]);
  
  useEffect(() => {
    loadPageTexts('profile', language);
  }, [loadPageTexts, language]);

  // Обновляем данные профиля при изменении currentUser (например, после получения награды)
  useEffect(() => {
    if (isOwnProfile && currentUser && user) {
      // Обновляем только если это собственный профиль и данные изменились
      if (currentUser.balance !== user.balance || 
          currentUser.experience !== user.experience || 
          currentUser.level !== user.level) {
        setUser(currentUser);
        setProfileData({
          username: currentUser.username || '',
          email: currentUser.email || '',
          balance: currentUser.balance || 0
        });
      }
    }
  }, [currentUser, isOwnProfile, user]);

  // Проверяем статус стримов для контентмейкеров
  useEffect(() => {
    if (user?.role?.name !== 'contentmaker') return undefined;

    let cancelled = false;
    Promise.all([
      user.twitch_url ? streamService.checkTwitchStream(user.twitch_url) : false,
      user.youtube_url ? streamService.checkYouTubeStream(user.youtube_url) : false,
    ])
      .then(([twitch, youtube]) => {
        if (!cancelled) setStreamStatus({ twitch, youtube });
      })
      .catch((error) => {
        console.error('Error checking stream status:', error);
      });

    return () => {
      cancelled = true;
    };
  }, [user?.role?.name, user?.twitch_url, user?.youtube_url]);

  const loadUserProfile = async () => {
    try {
      setLoading(true);
      // Очищаем все косметические эффекты при загрузке нового профиля
      removeAllCosmetics();
      
      // Очищаем данные при загрузке нового профиля
      setUserInventory([]);
      setUser(null);
      setUserClan(null);
      setInvites([]);
      setPlayerStats(null);
      setUserAchievements(null);
      setInventoryLoading(false);
      
      let userData;
      
      if (isOwnProfile) {
        // Для собственного профиля используем данные из AuthContext
        userData = currentUser;
        if (!userData) {
          // Если данных нет в AuthContext, загружаем из API
          const response = await apiFetch('/api/v1/users/me', {
            headers: {
            }
          });
          
          if (response.ok) {
            userData = await response.json();
          } else {
            throw new Error('Failed to load own profile');
          }
        }
      } else {
        // Загружаем профиль другого пользователя
        const response = await apiFetch(`/api/v1/users/profile/${encodeURIComponent(targetUsername)}/overview`);
        
        if (response.ok) {
          const overview = await response.json();
          userData = overview.user;
          setPlayerStats(overview.statistics || userData.player_statistics || null);
          setUserAchievements(overview.achievements || []);
        } else if (response.status === 404) {
          showError(getLocalizedText('profile_user_not_found', 'Пользователь не найден'));
          navigate('/dashboard');
          return;
        } else {
          throw new Error('Failed to load user profile');
        }
      }
      
      
      setUser(userData);
      setProfileData({
        username: userData.username || '',
        email: isOwnProfile ? (userData.email || '') : '',
        balance: isOwnProfile ? (userData.balance || 0) : 0
      });
      setCurrentAvatarUrl(userData.avatar_url || '');
      
             // Инициализируем настройки
       setSettingsData({
         language: normalizeLanguage(userData.language),
         allow_clan_invites: userData.allow_clan_invites !== undefined ? userData.allow_clan_invites : true,
         telegram_url: userData.telegram_url || '',
         twitch_url: userData.twitch_url || '',
         youtube_url: userData.youtube_url || ''
       });
      
             // Загружаем дополнительные данные
               if (isOwnProfile) {
          // Для своего профиля загружаем свой клан, приглашения и инвентарь
          await Promise.all([
            loadUserClan(),
            loadInvites(),
            loadUserInventoryWithUser(userData),
            loadPlayerStatistics(),
          ]);
          
          // Загружаем контент активной вкладки
          if (activeTab === 'achievements') {
            await loadUserAchievements();
          }
          
        } else {
          // Для чужого профиля загружаем клан этого пользователя и его инвентарь
          await Promise.all([
            loadUserClanForProfile(userData.id),
            loadUserInventoryWithUser(userData),
          ]);
        }
      
    } catch (error) {
      console.error('Error loading user profile:', error);
      showError(getLocalizedText('profile_loading_error', 'Ошибка при загрузке профиля'));
    } finally {
      setLoading(false);
    }
  };

  const loadUserProfileRef = useLatest(loadUserProfile);
  useEffect(() => {
    if (targetUsername) {
      loadUserProfileRef.current();
    }
  }, [language, loadUserProfileRef, targetUsername]);

  const loadUserClan = async () => {
    try {
      
      const response = await apiFetch('/api/v1/clans/my', {
        headers: {
        }
      });
      
      
      if (response.ok) {
        const clan = await response.json();
        setUserClan(clan);
      } else if (response.status === 404) {
        // Пользователь не состоит в клане - это нормальная ситуация
        setUserClan(null);
      } else {
        // Другие ошибки - логируем их
        console.error('❌ Error loading user clan:', response.status, response.statusText);
        setUserClan(null);
      }
      
    } catch {
      // Сетевые ошибки могут быть связаны с отсутствием клана
      setUserClan(null);
    }
  };

  const loadUserClanForProfile = async (userId) => {
    try {
      const response = await apiFetch(`/api/v1/users/${userId}/clan`, {
        headers: {
        }
      });
      if (response.ok) {
        const data = await response.json();
        // Проверяем, есть ли сообщение об ошибке
        if (data.message) {
          // Пользователь не состоит в клане - это нормальная ситуация
          setUserClan(null);
        } else {
          setUserClan(data);
        }
      } else {
        // Другие ошибки - логируем их
        console.error('Error loading user clan for profile:', response.status, response.statusText);
        setUserClan(null);
      }
    } catch (error) {
      console.error('Network error loading user clan for profile:', error);
      setUserClan(null);
    }
  };

  const loadInvites = async () => {
    try {
      const response = await apiFetch('/api/v1/clans/invites/', {
        headers: {
        }
      });
      
      if (response.ok) {
        const invitesData = await response.json();
        setInvites(invitesData);
      } else if (response.status === 404) {
        // Пустой список приглашений совместим со старым API, который отвечал 404.
        setInvites([]);
      } else {
        // Другие ошибки - логируем их
        console.error('Failed to load invites, status:', response.status);
        setInvites([]);
      }
    } catch (error) {
      console.error('Network error loading invites:', error);
      setInvites([]);
    }
  };

  const loadTabContent = async (tabId) => {
    if (!user) return;

    switch (tabId) {
      case 'overview':
      case 'matches':
      case 'statistics':
        // Загружаем статистику только если она еще не загружена
        if (!playerStats) {
          await loadPlayerStatistics();
        }
        break;
      case 'achievements':
        // Загружаем достижения только если они еще не загружены
        if (!userAchievements) {
          await loadUserAchievements();
        }
        break;
      case 'settings':
        // Настройки не требуют дополнительной загрузки
        break;
    }
  };

  // Обработчик переключения вкладок
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (tabId === 'overview') next.delete('tab');
      else next.set('tab', tabId);
      return next;
    }, { replace: true });
    loadTabContent(tabId);
  };

  // Функция для обновления настроек пользователя
  const handleUpdateSettings = async () => {
    if (!user) return;
    
    setUpdatingSettings(true);
    try {
      const response = await apiFetch(`/api/v1/users/${user.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
                 body: JSON.stringify({
           language: settingsData.language,
           allow_clan_invites: settingsData.allow_clan_invites,
           telegram_url: settingsData.telegram_url,
           twitch_url: settingsData.twitch_url,
           youtube_url: settingsData.youtube_url
         })
      });
      
             if (response.ok) {
         const updatedUser = await response.json();
         setUser(updatedUser);
         showSuccess(getLocalizedText('profile_settings_success', 'Настройки успешно обновлены'));
         // Обновляем данные в AuthContext
         if (currentUser && currentUser.id === user.id) {
           // Обновляем данные в AuthContext
           updateUser(updatedUser);
           // Обновляем язык в LocalizationContext
           changeLanguage(updatedUser.language);
         }
       } else {
        showError(getLocalizedText('profile_settings_error', 'Ошибка при обновлении настроек'));
      }
    } catch (error) {
      console.error('Error updating settings:', error);
      showError(getLocalizedText('profile_settings_error', 'Ошибка при обновлении настроек'));
    } finally {
      setUpdatingSettings(false);
    }
  };

  const loadPlayerStatistics = async () => {
    try {
      // Загружаем статистику из базы данных матчей
      const response = await apiFetch(`/api/v1/users/player-statistics/${targetUsername}`, {
        headers: {
        }
      });
      
      if (response.ok) {
        const stats = await response.json();
        setPlayerStats(stats);
      } else if (response.status === 404) {
        setPlayerStats({
          total_matches: 0,
          wins: 0,
          losses: 0,
          win_rate: 0,
          factions_used: {},
          recent_matches: []
        });
      } else {
        console.error('❌ Error loading statistics, status:', response.status);
        setPlayerStats({
          total_matches: 0,
          wins: 0,
          losses: 0,
          win_rate: 0,
          factions_used: {},
          recent_matches: []
        });
      }
    } catch (error) {
      console.error('❌ Network error loading player statistics:', error);
      setPlayerStats({
        total_matches: 0,
        wins: 0,
        losses: 0,
        win_rate: 0,
        factions_used: {},
        recent_matches: []
      });
    }
  };

  const loadUserInventory = async () => {
    if (!user || inventoryLoading) {
      return;
    }
    
    try {
      setInventoryLoading(true);
      const response = await apiFetch(`/api/v1/shop/users/${user.id}/items/`, {
        headers: {
        }
      });
      
      if (response.ok) {
        const items = await response.json();
        setUserInventory(items);
      } else {
        // Другие ошибки - логируем их
        console.error('Failed to load inventory, status:', response.status);
        setUserInventory([]);
      }
    } catch (error) {
      console.error('Network error loading inventory:', error);
      setUserInventory([]);
    } finally {
      setInventoryLoading(false);
    }
  };

  const loadUserInventoryWithUser = async (userData) => {
    if (inventoryLoading) {
      return;
    }
    
    try {
      setInventoryLoading(true);
      const response = await apiFetch(`/api/v1/shop/users/${userData.id}/items/`, {
        headers: {
        }
      });
      
      if (response.ok) {
        const items = await response.json();
        setUserInventory(items);
      } else {
        // Другие ошибки - логируем их
        console.error('Failed to load inventory, status:', response.status);
        setUserInventory([]);
      }
    } catch (error) {
      console.error('Network error loading inventory:', error);
      setUserInventory([]);
    } finally {
      setInventoryLoading(false);
    }
  };

  const loadUserAchievements = async () => {
    try {
      const response = await apiFetch(`/api/v1/achievements/users/${user.id}/achievements/`, {
        headers: {
        }
      });
      
      if (response.ok) {
        const achievements = await response.json();
        setUserAchievements(achievements);
      } else if (response.status === 404) {
        // Пустой список достижений совместим со старым API, который отвечал 404.
        setUserAchievements([]);
      } else {
        // Другие ошибки - логируем их
        console.error('Failed to load achievements, status:', response.status);
        setUserAchievements([]);
      }
    } catch (error) {
      console.error('Network error loading achievements:', error);
      setUserAchievements([]);
    }
  };

  const respondToInvite = async (inviteId, response) => {
    try {
      const result = await apiFetch(`/api/v1/clans/invites/${inviteId}?status=${response}`, {
        method: 'PUT',
        headers: {
        }
      });
      
      if (result.ok) {
        showSuccess(getLocalizedText('profile_invitation_result', null, {
          result: response === 'accepted'
            ? getLocalizedText('profile_invitation_accepted', 'принято')
            : getLocalizedText('profile_invitation_declined', 'отклонено'),
        }));
        loadInvites();
      } else {
        showError(getLocalizedText('profile_invitation_error', 'Не удалось обработать приглашение'));
      }
    } catch (error) {
      console.error('Error responding to invite:', error);
      showError(getLocalizedText('profile_invitation_error', 'Не удалось обработать приглашение'));
    }
  };

  const equipItem = async (userItemId, equip) => {
    try {
      const endpoint = equip ? '/api/v1/shop/equip/' : `/api/v1/shop/unequip/${userItemId}`;
      const method = 'POST';
      const body = equip ? JSON.stringify({ user_item_id: userItemId }) : null;
      
      const response = await apiFetch(endpoint, {
        method: method,
        headers: {
          'Content-Type': 'application/json',
        },
        ...(body && { body: body })
      });
      
      if (response.ok) {
        showSuccess(equip
          ? getLocalizedText('profile_item_equipped', 'Предмет экипирован')
          : getLocalizedText('profile_item_unequipped', 'Предмет снят'));
        await loadUserInventory();
        try {
          await refreshSiteTheme();
        } catch (error) {
          console.warn('Не удалось сразу обновить тему сайта:', error);
        }
        
        // Применяем косметику после экипировки
        setTimeout(() => {
          applyEquippedCosmetics();
        }, 200);
      } else {
        showError(getLocalizedText('profile_item_error', 'Не удалось изменить экипировку'));
      }
    } catch (error) {
      console.error('Error equipping item:', error);
      showError(getLocalizedText('profile_item_error', 'Не удалось изменить экипировку'));
    }
  };

  const updateBalance = async (amount) => {
    setBalanceUpdating(true);
    try {
      const response = await apiFetch(`/api/v1/users/${user.id}/balance`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ amount, reason: 'Ручная корректировка из профиля' })
      });
      
      if (response.ok) {
        const data = await response.json();
        setProfileData(prev => ({
          ...prev,
          balance: data.balance ?? data.new_balance ?? (Number(prev.balance || 0) + amount),
        }));
        setBalanceOpen(false);
        setBalanceAmount('');
        showSuccess(getLocalizedText('profile_balance_updated', 'Баланс успешно обновлён'));
      } else {
        showError(getLocalizedText('profile_balance_error', 'Не удалось обновить баланс'));
      }
    } catch (error) {
      console.error('Error updating balance:', error);
      showError(getLocalizedText('profile_balance_error', 'Не удалось обновить баланс'));
    } finally {
      setBalanceUpdating(false);
    }
  };

  const showBalanceModal = () => {
    setBalanceAmount('');
    setBalanceOpen(true);
  };

  const requestIdentityVerification = async () => {
    setVerificationUpdating(true);
    try {
      const response = await apiFetch('/api/v1/users/me/external-identity/verification-request', {
        method: 'POST',
        headers: {
        }
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || getLocalizedText('profile_verification_submit_error', 'Не удалось отправить профиль на проверку'));
      }
      setUser(prev => ({ ...prev, external_identity_status: data.status }));
      showSuccess(getLocalizedText('profile_verification_submitted', 'Игровой аккаунт отправлен на проверку'));
    } catch (error) {
      showError(error.message);
    } finally {
      setVerificationUpdating(false);
    }
  };

  const reviewIdentityVerification = (decision) => {
    setVerificationReason('');
    setVerificationAction(decision);
  };

  const submitIdentityVerification = async () => {
    if (!verificationAction || verificationReason.trim().length < 3) {
      return;
    }

    setVerificationUpdating(true);
    try {
      const response = await apiFetch(`/api/v1/users/${user.id}/external-identity/verification`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ decision: verificationAction, reason: verificationReason.trim() })
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || getLocalizedText('profile_verification_review_error', 'Не удалось обработать заявку'));
      }
      setUser(prev => ({ ...prev, external_identity_status: data.status }));
      showSuccess(
        verificationAction === 'approve'
          ? getLocalizedText('profile_verification_approved', 'Игровой аккаунт подтверждён')
          : getLocalizedText('profile_verification_rejected', 'Заявка отклонена')
      );
      setVerificationAction(null);
      setVerificationReason('');
    } catch (error) {
      showError(error.message);
    } finally {
      setVerificationUpdating(false);
    }
  };

  const handleImpersonateUser = async () => {
    setImpersonationStarting(true);
    try {
      await impersonateUser(user.id);
      showSuccess(getLocalizedText('profile_test_session_opened', null, { username: getPlayerDisplayName(user) }));
      navigate('/profile');
    } catch (error) {
      showError(
        error.response?.data?.detail
        || error.message
        || getLocalizedText('profile_test_session_error', 'Не удалось открыть тестовую сессию')
      );
    } finally {
      setImpersonationStarting(false);
    }
  };

  const handleAvatarUpdate = (newAvatarUrl) => {
    setCurrentAvatarUrl(newAvatarUrl);

    if (user) {
      setUser((current) => ({ ...current, avatar_url: newAvatarUrl }));
      if (currentUser?.id === user.id) {
        updateUser({ ...currentUser, avatar_url: newAvatarUrl });
      }
    }
  };

  // Функция для расчета прогресса опыта
  const calculateExperienceProgress = () => {
    if (!user) return { current: 0, max: 100, percentage: 0 };
    
    const level = user.level || 1;
    const experience = user.experience || 0;
    
    // Система уровней из QuestService
    const levelExperienceRequirements = {
      1: 0,
      2: 1000,
      3: 2500,
      4: 4500,
      5: 7000,
      6: 10000,
      7: 13500,
      8: 17500,
      9: 22000,
      10: 27000
    };
    
    // Получаем требуемый опыт для текущего уровня
    const getLevelExperienceRequirement = (level) => {
      if (level in levelExperienceRequirements) {
        return levelExperienceRequirements[level];
      }
      // Для уровней выше 10 используем формулу
      return 27000 + (level - 10) * 6000;
    };
    
    // Опыт для текущего уровня
    const currentLevelExp = getLevelExperienceRequirement(level);
    // Опыт для следующего уровня
    const nextLevelExp = getLevelExperienceRequirement(level + 1);
    // Опыт, накопленный на текущем уровне
    // Older local/demo accounts stored progress within the level while the
    // current API stores total experience. Support both shapes so the profile
    // never renders a negative XP value during a schema/data transition.
    const rawLevelProgress = experience < currentLevelExp
      ? experience
      : experience - currentLevelExp;
    // Максимальный опыт для текущего уровня
    const maxLevelProgress = nextLevelExp - currentLevelExp;
    
    const currentLevelProgress = Math.min(
      Math.max(rawLevelProgress, 0),
      maxLevelProgress,
    );
    const percentage = maxLevelProgress > 0
      ? Math.min(Math.max((currentLevelProgress / maxLevelProgress) * 100, 0), 100)
      : 0;
    
    return {
      current: currentLevelProgress,
      max: maxLevelProgress,
      percentage: Math.round(percentage)
    };
  };

  const getCategoryIcon = (category) => {
    switch (category) {
      case 'profile_frame': return '/icons/profilewb.png';
      case 'stat_card_style': return '/icons/axeswb.png';
      case 'avatar_frame': return '/icons/sauronwb.png';
      case 'profile_background': return '/icons/towerwb.png';
      case SITE_THEME_ITEM_TYPE: return '/icons/ennorathtvwb.png';
      default: return '/icons/vswb.png';
    }
  };

  // Функция для удаления всех косметических эффектов
  const removeAllCosmetics = useCallback(() => {
    const cosmeticClasses = [
      'profile-frame-gold', 'profile-frame-crystal', 'profile-frame-legendary',
      'stat-card-neon', 'stat-card-metal', 'stat-card-holographic',
      'avatar-frame-fire', 'avatar-frame-ice', 'avatar-frame-rainbow',
      'avatar-frame-palantir',
      'anime-background', 'presidents-background', 'profile-background-starlight'
    ];
    
    cosmeticClasses.forEach(className => {
      document.body.classList.remove(className);
      document.documentElement.classList.remove(className);
      document.querySelectorAll('.card').forEach(card => {
        card.classList.remove(className);
      });
      document.querySelectorAll('.main-stats-container').forEach(container => {
        container.classList.remove(className);
      });
      document.querySelectorAll('.avatar-container').forEach(container => {
        container.classList.remove(className);
      });
      document.querySelectorAll('.container-fluid').forEach(container => {
        container.classList.remove(className);
      });
      document.querySelectorAll('.app-container').forEach(container => {
        container.classList.remove(className);
      });
    });
    
    const existingVideos = document.querySelectorAll(
      '.anime-background-video, .presidents-background-video, .profile-background-starlight-video'
    );
    existingVideos.forEach(video => video.remove());
    
    // Восстанавливаем основной фон
    document.body.style.background = '';
    
    // Восстанавливаем фон app-container
    const appContainer = document.querySelector('.app-container');
    if (appContainer) {
      appContainer.style.background = '';
    }
  }, []);

  // Функция для применения конкретного косметического эффекта
  const applyCosmetic = useCallback((cssClass, itemType) => {
    switch (itemType) {
      case 'profile_frame':
        // Применяем рамку к карточке профиля
        document.querySelectorAll('.profile-header-card').forEach(card => {
          card.classList.add(cssClass);
        });
        break;
      case 'stat_card_style':
        // Применяем стиль к карточкам статистики
        document.querySelectorAll('.main-stats-container').forEach(container => {
          container.classList.add(cssClass);
        });
        document.querySelectorAll('.main-stat-card').forEach(card => {
          card.classList.add(cssClass);
        });
        break;
      case 'avatar_frame':
        // Применяем рамку к аватару
        document.querySelectorAll('.avatar-container').forEach(container => {
          container.classList.add(cssClass);
        });
        break;
      case 'profile_background':
      case 'background': {
        // Применяем фон к профилю
        document.body.classList.add(cssClass);
        document.documentElement.classList.add(cssClass);
        
        // Специальная обработка для анимированных фонов
        if (cssClass === 'anime-background') {
          const existingVideo = document.querySelector('.anime-background-video');
          if (!existingVideo) {
            const video = document.createElement('video');
            video.className = 'anime-background-video';
            video.autoplay = true;
            video.muted = true;
            video.loop = true;
            video.playsInline = true;
            video.src = '/images/anime_back.webm';
            document.body.appendChild(video);
          }
        } else if (cssClass === 'presidents-background') {
          const existingVideo = document.querySelector('.presidents-background-video');
          if (!existingVideo) {
            const video = document.createElement('video');
            video.className = 'presidents-background-video';
            video.autoplay = true;
            video.muted = true;
            video.loop = true;
            video.playsInline = true;
            video.src = '/images/presidents_back.webm';
            document.body.appendChild(video);
          }
        } else if (cssClass === 'profile-background-starlight') {
          const existingVideo = document.querySelector('.profile-background-starlight-video');
          if (!existingVideo) {
            const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
            const video = document.createElement('video');
            video.className = 'profile-background-starlight-video';
            video.autoplay = !reduceMotion;
            video.muted = true;
            video.loop = true;
            video.playsInline = true;
            video.preload = 'auto';
            video.poster = '/cosmetics/steam-profile-background-poster.jpg';
            video.setAttribute('aria-hidden', 'true');

            if (!reduceMotion) {
              const webmSource = document.createElement('source');
              webmSource.src = '/cosmetics/steam-profile-background.webm';
              webmSource.type = 'video/webm';
              video.appendChild(webmSource);

              const mp4Source = document.createElement('source');
              mp4Source.src = '/cosmetics/steam-profile-background.mp4';
              mp4Source.type = 'video/mp4';
              video.appendChild(mp4Source);
            }

            document.body.appendChild(video);
          }
        }
        
        // Также применяем к основному контейнеру профиля
        const profileContainer = document.querySelector('.container-fluid');
        if (profileContainer) {
          profileContainer.classList.add(cssClass);
        }
        
        // Также применяем к app-container
        const appContainer = document.querySelector('.app-container');
        if (appContainer) {
          appContainer.classList.add(cssClass);
          appContainer.style.background = 'none';
        }
        
        // Убираем основной фон
        document.body.style.background = 'none';
        break;
      }
      case 'profile_effects':
        // Применяем эффекты к профилю
        document.body.classList.add(cssClass);
        break;
    }
  }, []);

  // Функция для применения всех экипированных предметов
  const applyEquippedCosmetics = useCallback(() => {
    // Сначала удаляем все существующие эффекты
    removeAllCosmetics();
    
    // Применяем каждый экипированный предмет
    if (userInventory && userInventory.length > 0) {
      const equippedItems = userInventory.filter(userItem => userItem.is_equipped);
      equippedItems.forEach(userItem => {
        const cssClass = userItem.item.css_class;
        const itemType = userItem.item.item_type;
        
        if (cssClass && itemType) {
          applyCosmetic(cssClass, itemType);
        }
      });
    }
  }, [applyCosmetic, removeAllCosmetics, userInventory]);

  // Косметика меняет глобальные DOM-классы, поэтому очищаем их при смене профиля и unmount.
  useEffect(() => {
    removeAllCosmetics();
    return removeAllCosmetics;
  }, [removeAllCosmetics, targetUsername]);

  useEffect(() => {
    if (!user?.id || loading) return;
    applyEquippedCosmetics();
  }, [applyEquippedCosmetics, loading, user?.id]);

  useEffect(() => {
    if (!username || !user?.id) return;
    const canonicalPath = getPlayerProfilePath(user);
    const currentPath = `/profile/${encodeURIComponent(username)}`;
    if (canonicalPath === currentPath) return;
    const query = searchParams.toString();
    navigate(`${canonicalPath}${query ? `?${query}` : ''}`, { replace: true });
  }, [navigate, searchParams, user, username]);

  if (loading) {
    return (
      <div className="container-fluid py-4">
        <div className="text-center">
          <div className="spinner-border text-primary" role="status">
            <span className="visually-hidden">{getLocalizedText('profile_loading', 'Загрузка профиля...')}</span>
          </div>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="container-fluid py-4">
        <div className="text-center">
          <div className="alert alert-warning">
            <h5>{getLocalizedText('profile_user_not_found', 'Пользователь не найден')}</h5>
            <p>{getLocalizedText('profile_user_not_found_hint', 'Проверьте ссылку на профиль или вернитесь на главную страницу.')}</p>
          </div>
        </div>
      </div>
    );
  }

  const expProgress = calculateExperienceProgress();
  const profileIdentity = getIdentity(profileData.username) || {
    is_admin: user?.role?.name === 'admin',
    titles: user?.titles || [],
  };

  const copyProfileLink = async () => {
    try {
      const canonicalProfileUrl = new URL(
        getPlayerProfilePath(user || { username: targetUsername }),
        window.location.origin,
      ).toString();
      await navigator.clipboard.writeText(canonicalProfileUrl);
      showSuccess(getLocalizedText('profile_link_copied', 'Ссылка на профиль скопирована.'));
    } catch (error) {
      console.error('Could not copy profile link:', error);
      showError(getLocalizedText('profile_link_copy_error', 'Не удалось скопировать ссылку.'));
    }
  };

  if (user?.id) {
    return (
      <ProfileView
        t={getLocalizedText}
        language={language}
        navigate={navigate}
        user={user}
        currentUser={currentUser}
        profileData={profileData}
        profileIdentity={profileIdentity}
        currentAvatarUrl={currentAvatarUrl}
        userClan={userClan}
        invites={invites}
        activeTab={activeTab}
        playerStats={playerStats}
        userInventory={userInventory}
        userAchievements={userAchievements}
        settingsData={settingsData}
        streamStatus={streamStatus}
        expProgress={expProgress}
        targetUsername={targetUsername}
        isOwnProfile={isOwnProfile}
        isAdmin={isAdmin}
        isImpersonating={isImpersonating}
        inventoryLoading={inventoryLoading}
        verificationUpdating={verificationUpdating}
        impersonationStarting={impersonationStarting}
        updatingSettings={updatingSettings}
        settingsOpen={settingsOpen}
        clanCreationOpen={clanCreationOpen}
        balanceOpen={balanceOpen}
        balanceAmount={balanceAmount}
        balanceUpdating={balanceUpdating}
        verificationAction={verificationAction}
        verificationReason={verificationReason}
        onAvatarUpdate={handleAvatarUpdate}
        onRequestVerification={requestIdentityVerification}
        onReviewVerification={reviewIdentityVerification}
        onSubmitVerification={submitIdentityVerification}
        onImpersonate={handleImpersonateUser}
        onTabChange={handleTabChange}
        onInviteResponse={respondToInvite}
        onEquipItem={equipItem}
        onSaveSettings={handleUpdateSettings}
        onCopyProfileLink={copyProfileLink}
        onClanCreated={(clan) => {
          setUserClan(clan);
          setClanCreationOpen(false);
          showSuccess(getLocalizedText('clans_created_success', 'Клан создан'));
        }}
        onUpdateBalance={updateBalance}
        getCategoryIcon={getCategoryIcon}
        setSettingsData={setSettingsData}
        setSettingsOpen={setSettingsOpen}
        setClanCreationOpen={setClanCreationOpen}
        setBalanceOpen={setBalanceOpen}
        setBalanceAmount={setBalanceAmount}
        setVerificationAction={setVerificationAction}
        setVerificationReason={setVerificationReason}
      />
    );
  }

  return (
    <div className={`container-fluid py-4 ${isOwnProfile ? 'own-profile' : 'public-profile'}`}>
      {/* Profile Header */}
      <div className="row justify-content-center mb-5">
        <div className="col-lg-10">
          {/* Системный статус не должен запрашиваться и отображаться обычным игрокам. */}
          {isAdmin && <SchedulerStatus />}
          
          <div className="card profile-header-card glow position-relative">
            <div className="card-body text-center p-5">
              <div className="profile-avatar mb-4">
                <div className="avatar-container position-relative">
                  <img 
                    id="userAvatar" 
                    src={currentAvatarUrl || user?.avatar_url || '/icons/profilewb.png'}
                    alt="Avatar" 
                    className="user-avatar-img" 
                    style={{ 
                      display: (currentAvatarUrl || user?.avatar_url) ? 'block' : 'none',
                      width: '150px',
                      height: '150px',
                      borderRadius: '50%',
                      border: '4px solid var(--primary-color)',
                      objectFit: 'cover',
                      boxShadow: '0 0 20px rgba(var(--primary-rgb), 0.3)'
                    }}
                  />
                  <img 
                    id="defaultAvatar" 
                    src="/icons/profilewb.png" 
                    alt="Default Avatar" 
                    style={{ 
                      display: (currentAvatarUrl || user?.avatar_url) ? 'none' : 'block',
                      width: '150px',
                      height: '150px',
                      borderRadius: '50%',
                      border: '4px solid var(--primary-color)',
                      boxShadow: '0 0 20px rgba(var(--primary-rgb), 0.3)'
                    }}
                  />
                  
                </div>
                {/* Кнопка загрузки находится вне рамки и не перекрывает аватар. */}
                {isOwnProfile && (
                  <div className="avatar-upload-action">
                    <AvatarUpload
                      onAvatarUpdate={handleAvatarUpdate}
                      currentAvatarUrl={currentAvatarUrl || user?.avatar_url}
                    />
                  </div>
                )}
              </div>
              
              <h1 className="text-gradient mb-2 profile-username" id="profileUsername">
                <PlayerIdentity
                  username={profileData.username}
                  linkToProfile={false}
                  showTitles={false}
                />
              </h1>

              {isAdmin && !isOwnProfile && (
                <button
                  type="button"
                  className="btn btn-outline-warning btn-sm mb-3"
                  disabled={impersonationStarting}
                  onClick={handleImpersonateUser}
                >
                  {impersonationStarting
                    ? getLocalizedText('profile_impersonation_starting', 'Открываем тестовую сессию...')
                    : getLocalizedText('profile_impersonation_open', 'Войти для проверки')}
                </button>
              )}

              {user.external_identity_status === 'verified' && (
                <div className="mb-3">
                  <span className="badge bg-success">{getLocalizedText('profile_identity_verified', 'Игровой аккаунт подтверждён')}</span>
                </div>
              )}
              {user.external_identity_status === 'pending' && (
                <div className="mb-3 d-flex justify-content-center align-items-center gap-2 flex-wrap">
                  <span className="badge bg-warning text-dark">{getLocalizedText('profile_identity_pending', 'Привязка ожидает подтверждения')}</span>
                  {isAdmin && (!isOwnProfile || isImpersonating) && (
                    <>
                      <button
                        type="button"
                        className="btn btn-sm btn-success"
                        disabled={verificationUpdating}
                        onClick={() => reviewIdentityVerification('approve')}
                      >
                        {getLocalizedText('profile_identity_approve', 'Подтвердить')}
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-danger"
                        disabled={verificationUpdating}
                        onClick={() => reviewIdentityVerification('reject')}
                      >
                        {getLocalizedText('profile_identity_reject', 'Отклонить')}
                      </button>
                    </>
                  )}
                </div>
              )}
              {user.external_identity_status === 'unverified' && user.is_claimed && (
                <div className="mb-3 d-flex justify-content-center align-items-center gap-2 flex-wrap">
                  <span className="badge bg-danger">{getLocalizedText('profile_identity_unverified', 'Игровой аккаунт не подтверждён')}</span>
                  {isOwnProfile && (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-light"
                      disabled={verificationUpdating}
                      onClick={requestIdentityVerification}
                    >
                      {getLocalizedText('profile_identity_submit', 'Отправить на проверку')}
                    </button>
                  )}
                </div>
              )}

              {!isOwnProfile && user.is_claimed === false && (
                <div className="alert alert-info mx-auto mb-4" style={{ maxWidth: '620px' }}>
                  <div className="fw-bold mb-1">{getLocalizedText('profile_unclaimed_title', 'Игровой профиль ещё не привязан')}</div>
                  <div className="small mb-3">
                    {getLocalizedText('profile_unclaimed_description', 'Матчи, статистика и достижения уже сохраняются. Владелец ника сможет забрать весь прогресс при регистрации.')}
                  </div>
                  {!currentUser && (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-info"
                      onClick={() => navigate('/login')}
                    >
                      {getLocalizedText('profile_claim_this', 'Привязать этот профиль')}
                    </button>
                  )}
                </div>
              )}
              
              {isOwnProfile && (
                <p className="text-secondary mb-4 profile-email" id="profileEmail">
                  {profileData.email}
                </p>
              )}
              
              {/* Социальные сети для контентмейкеров */}
              {user.role && user.role.name === 'contentmaker' && (
                <div 
                  id="social-media-container" 
                  className="social-media-links"
                                     style={{
                     position: 'absolute',
                     top: '20px',
                     right: '20px',
                     zIndex: 10,
                     display: 'flex',
                     flexDirection: 'column',
                     alignItems: 'center',
                     gap: '25px',
                     filter: 'drop-shadow(0 4px 8px rgba(0, 0, 0, 0.3))'
                   }}
                >
                                                         {user.telegram_url && (
                      <a 
                        href={user.telegram_url} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="social-link telegram"
                        title="Telegram"
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: '65px',
                          height: '65px',
                          borderRadius: '50%',
                          textDecoration: 'none',
                          color: 'white',
                          fontSize: '30px',
                          transition: 'all 0.3s ease',
                          boxShadow: '0 8px 25px rgba(0, 136, 204, 0.4)',
                          position: 'relative',
                          border: '3px solid #0088cc',
                          background: 'linear-gradient(135deg, #0088cc 0%, #00a8ff 50%, #0088cc 100%)'
                        }}
                        onMouseEnter={(e) => {
                          e.target.style.transform = 'translateY(-5px) scale(1.15)';
                          e.target.style.boxShadow = '0 12px 35px rgba(0, 136, 204, 0.8)';
                          e.target.style.background = 'linear-gradient(135deg, #0077b3 0%, #0099e6 50%, #0077b3 100%)';
                        }}
                        onMouseLeave={(e) => {
                          e.target.style.transform = 'translateY(0) scale(1)';
                          e.target.style.boxShadow = '0 8px 25px rgba(0, 136, 204, 0.4)';
                          e.target.style.background = 'linear-gradient(135deg, #0088cc 0%, #00a8ff 50%, #0088cc 100%)';
                        }}
                      >
                        <i className="fab fa-telegram"></i>
                      </a>
                    )}
                                     {user.twitch_url && (
                     <a 
                       href={user.twitch_url} 
                       target="_blank" 
                       rel="noopener noreferrer"
                       className="social-link twitch"
                       title="Twitch"
                       style={{
                         display: 'inline-flex',
                         alignItems: 'center',
                         justifyContent: 'center',
                         width: '65px',
                         height: '65px',
                         borderRadius: '50%',
                         textDecoration: 'none',
                         color: 'white',
                         fontSize: '30px',
                         transition: 'all 0.3s ease',
                         boxShadow: '0 8px 25px rgba(145, 70, 255, 0.4)',
                         position: 'relative',
                         border: '3px solid #9146ff',
                         background: 'linear-gradient(135deg, #9146ff 0%, #a855f7 50%, #9146ff 100%)'
                       }}
                       onMouseEnter={(e) => {
                         e.target.style.transform = 'translateY(-5px) scale(1.15)';
                         e.target.style.boxShadow = '0 12px 35px rgba(145, 70, 255, 0.8)';
                         e.target.style.background = 'linear-gradient(135deg, #7c3aed 0%, #9333ea 50%, #7c3aed 100%)';
                       }}
                       onMouseLeave={(e) => {
                         e.target.style.transform = 'translateY(0) scale(1)';
                         e.target.style.boxShadow = '0 8px 25px rgba(145, 70, 255, 0.4)';
                         e.target.style.background = 'linear-gradient(135deg, #9146ff 0%, #a855f7 50%, #9146ff 100%)';
                       }}
                     >
                       <i className="fab fa-twitch"></i>
                       {streamStatus.twitch && (
                         <span 
                           className="live-badge"
                           style={{
                             position: 'absolute',
                             top: '-10px',
                             right: '-10px',
                             background: 'linear-gradient(135deg, #ff4444 0%, #ff6666 50%, #ff4444 100%)',
                             color: 'white',
                             fontSize: '12px',
                             fontWeight: 'bold',
                             padding: '3px 8px',
                             borderRadius: '12px',
                             border: '2px solid white',
                             boxShadow: '0 4px 12px rgba(255, 68, 68, 0.6)',
                             textTransform: 'uppercase',
                             letterSpacing: '0.5px'
                           }}
                         >
                           LIVE
                         </span>
                       )}
                     </a>
                   )}
                                     {user.youtube_url && (
                     <a 
                       href={user.youtube_url} 
                       target="_blank" 
                       rel="noopener noreferrer"
                       className="social-link youtube"
                       title="YouTube"
                       style={{
                         display: 'inline-flex',
                         alignItems: 'center',
                         justifyContent: 'center',
                         width: '65px',
                         height: '65px',
                         borderRadius: '50%',
                         textDecoration: 'none',
                         color: 'white',
                         fontSize: '30px',
                         transition: 'all 0.3s ease',
                         boxShadow: '0 8px 25px rgba(255, 0, 0, 0.4)',
                         position: 'relative',
                         border: '3px solid #ff0000',
                         background: 'linear-gradient(135deg, #ff0000 0%, #ff4444 50%, #ff0000 100%)'
                       }}
                       onMouseEnter={(e) => {
                         e.target.style.transform = 'translateY(-5px) scale(1.15)';
                         e.target.style.boxShadow = '0 12px 35px rgba(255, 0, 0, 0.8)';
                         e.target.style.background = 'linear-gradient(135deg, #cc0000 0%, #ff2222 50%, #cc0000 100%)';
                       }}
                       onMouseLeave={(e) => {
                         e.target.style.transform = 'translateY(0) scale(1)';
                         e.target.style.boxShadow = '0 8px 25px rgba(255, 0, 0, 0.4)';
                         e.target.style.background = 'linear-gradient(135deg, #ff0000 0%, #ff4444 50%, #ff0000 100%)';
                       }}
                     >
                       <i className="fab fa-youtube"></i>
                       {streamStatus.youtube && (
                         <span 
                           className="live-badge"
                           style={{
                             position: 'absolute',
                             top: '-10px',
                             right: '-10px',
                             background: 'linear-gradient(135deg, #ff4444 0%, #ff6666 50%, #ff4444 100%)',
                             color: 'white',
                             fontSize: '12px',
                             fontWeight: 'bold',
                             padding: '3px 8px',
                             borderRadius: '12px',
                             border: '2px solid white',
                             boxShadow: '0 4px 12px rgba(255, 68, 68, 0.6)',
                             textTransform: 'uppercase',
                             letterSpacing: '0.5px'
                           }}
                         >
                           LIVE
                         </span>
                       )}
                     </a>
                   )}
                </div>
              )}
              
              {/* Уровень и опыт */}
              <div className="level-info mt-4">
                <div className="level-badge mb-3">
                  <span className="level-number">{user?.level || 1}</span>
                  <span className="level-label">{getLocalizedText('profile_level', 'Уровень')}</span>
                </div>
                
                <div className="experience-bar-container">
                  <div className="experience-bar mt-3">
                    <div className="progress" style={{ 
                      height: '12px', 
                      borderRadius: '6px',
                      backgroundColor: 'rgba(255, 255, 255, 0.1)',
                      overflow: 'hidden'
                    }}>
                      <div 
                        className="progress-bar" 
                        style={{ 
                          width: `${expProgress.percentage}%`,
                          background: 'linear-gradient(90deg, #FF4848 0%, #FF6B6B 100%)',
                          transition: 'width 0.8s ease',
                          boxShadow: '0 0 10px rgba(255, 72, 72, 0.5)'
                        }}
                      ></div>
                    </div>
                    <div className="experience-text mt-2">
                      <small className="text-muted">
                        {expProgress.current} / {expProgress.max} {getLocalizedText('profile_experience', 'опыта')} 
                        ({expProgress.percentage}%)
                      </small>
                    </div>
                  </div>
                </div>
              </div>


            </div>
          </div>
        </div>
      </div>

      <div className="row justify-content-center mb-4">
        <div className="col-lg-10">
          <div className="card profile-titles-card">
            <div className="card-header">
              <h5 className="text-gradient mb-0">
                {getLocalizedText('profile_titles_heading', 'Титулы')}
              </h5>
            </div>
            <div className="card-body profile-titles-body">
              {(profileIdentity.titles || []).length > 0 ? (
                <PlayerTitles titles={profileIdentity.titles} large />
              ) : (
                <span className="text-secondary">
                  {getLocalizedText('profile_titles_empty', 'У игрока пока нет титулов')}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Basic Info Section */}
      <div className="row justify-content-center mb-4">
        <div className="col-lg-10">
          <div className="row g-4">
            {/* User Info */}
            <div className="col-md-6">
              <div className="card h-100 profile-info-card">
                <div className="card-header">
                  <h5 className="text-gradient mb-0">
                    <img src="/icons/profilewb.png" alt="User" style={{ width: '20px', height: '20px', marginRight: '8px' }} />
                    {getLocalizedText('profile_user_info_title', 'Информация о пользователе')}
                  </h5>
                </div>
                <div className="card-body">
                  <div className="user-info">
                    <div className="info-item">
                      <span className="info-label">{getLocalizedText('profile_user_info_username', 'Имя пользователя')}:</span>
                      <span className="info-value" id="userInfoUsername">
                        <PlayerIdentity username={profileData.username} linkToProfile={false} />
                      </span>
                    </div>
                    {isOwnProfile && (
                      <div className="info-item">
                        <span className="info-label">{getLocalizedText('profile_user_info_email', 'Email')}:</span>
                        <span className="info-value" id="userInfoEmail" data-private-field="email">
                          {profileData.email}
                        </span>
                      </div>
                    )}
                    <div className="info-item">
                      <span className="info-label">{getLocalizedText('profile_user_info_created', 'Дата регистрации')}:</span>
                      <span className="info-value" id="userInfoCreated">
                        {new Date(user?.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="info-item">
                      <span className="info-label">{getLocalizedText('profile_user_info_status', 'Статус')}:</span>
                      <span className="info-value">
                        <span className="badge bg-success">{getLocalizedText('profile_user_info_status_active', 'Активен')}</span>
                      </span>
                    </div>
                    {isOwnProfile && (
                      <div className="info-item">
                        <span className="info-label">{getLocalizedText('profile_user_info_balance', 'Баланс')}:</span>
                        <span className="info-value">
                          <span className="balance-amount" id="userBalance" data-private-field="balance">{profileData.balance}</span>
                          {isAdmin && (
                            <button className="btn btn-sm btn-outline-primary ms-2" onClick={showBalanceModal}>
                              <img src="/icons/sauronwb.png" alt={getLocalizedText('profile_change_balance', 'Изменить баланс')} style={{ width: '12px', height: '12px' }} />
                            </button>
                          )}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>

            {/* Clan Info */}
            <div className="col-md-6">
              <div className="card h-100 profile-info-card">
                <div className="card-header">
                  <h5 className="text-gradient mb-0">
                    <img src="/icons/towerwb.png" alt="Crown" style={{ width: '20px', height: '20px', marginRight: '8px' }} />
                    {getLocalizedText('profile_clan_info_title', 'Информация о клане')}
                  </h5>
                </div>
                <div className="card-body">
                  <div id="clanInfo">
                                         {userClan ? (
                       <div className="clan-info-item clickable" onClick={() => navigate(`/clans/${userClan.id}`)}>
                         <div>
                           <div className="clan-name">{userClan.name}</div>
                           <div className="clan-description">
                             {userClan.description || getLocalizedText('profile_no_description', 'Описание отсутствует')}
                           </div>
                         </div>
                       </div>
                    ) : (
                      <div className="no-clan">
                        <img src="/icons/towerwb.png" alt="Users" style={{ width: '60px', height: '60px', marginBottom: '1rem' }} />
                        <h6>
                          {isOwnProfile 
                            ? getLocalizedText('profile_clan_info_no_clan_title', 'Вы не состоите в клане')
                            : getLocalizedText('profile_clan_info_no_clan_title_other', 'Пользователь не состоит в клане')
                          }
                        </h6>
                        <p>
                          {isOwnProfile 
                            ? getLocalizedText('profile_clan_info_no_clan_description', 'Создайте свой клан или присоединитесь к существующему')
                            : getLocalizedText('profile_clan_info_no_clan_description_other', 'Этот пользователь пока не присоединился ни к одному клану')
                          }
                        </p>
                        {isOwnProfile && (
                          <button className="btn btn-primary" onClick={() => navigate('/clans')}>
                            <img src="/icons/towerwb.png" alt="Plus" style={{ width: '16px', height: '16px', marginRight: '8px' }} />
                            {getLocalizedText('profile_clan_info_create_clan', 'Создать клан')}
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Profile Tabs Section - только для своего профиля */}
      {user && (
        <div className="row justify-content-center">
          <div className="col-lg-10">
            <div className="card profile-tabs-card">
              <div className="card-header p-0">
                <ul className="nav nav-tabs profile-tabs" id="profileTabs" role="tablist">
                  <li className="nav-item" role="presentation">
                    <button 
                      className={`nav-link ${activeTab === 'statistics' ? 'active' : ''}`}
                      onClick={() => handleTabChange('statistics')}
                      type="button"
                    >
                      <img src="/icons/axeswb.png" alt="Chart" style={{ width: '16px', height: '16px', marginRight: '8px' }} />
                      {getLocalizedText('profile_tab_statistics', 'Статистика')}
                    </button>
                  </li>
                  <li className="nav-item" role="presentation">
                    <button 
                      className={`nav-link ${activeTab === 'achievements' ? 'active' : ''}`}
                      onClick={() => handleTabChange('achievements')}
                      type="button"
                    >
                      <img src="/icons/sauronwb.png" alt="Trophy" style={{ width: '16px', height: '16px', marginRight: '8px' }} />
                      {getLocalizedText('profile_tab_achievements', 'Достижения')}
                    </button>
                  </li>
                  <li className="nav-item" role="presentation" style={{ display: isOwnProfile ? undefined : 'none' }}>
                    <button
                      className={`nav-link ${activeTab === 'inventory' ? 'active' : ''}`}
                      onClick={() => handleTabChange('inventory')}
                      type="button"
                    >
                      <img src="/icons/vswb.png" alt="" aria-hidden="true" style={{ width: '16px', height: '16px', marginRight: '8px' }} />
                      {getLocalizedText('profile_tab_inventory', 'Инвентарь')}
                    </button>
                  </li>
                  <li className="nav-item" role="presentation" style={{ display: isOwnProfile ? undefined : 'none' }}>
                    <button 
                      className={`nav-link ${activeTab === 'quests' ? 'active' : ''}`}
                      onClick={() => handleTabChange('quests')}
                      type="button"
                    >
                      <img src="/icons/towerwb.png" alt="Quests" style={{ width: '16px', height: '16px', marginRight: '8px' }} />
                      {getLocalizedText('profile_tab_quests', 'Задания')}
                    </button>
                  </li>
                  <li className="nav-item" role="presentation" style={{ display: isOwnProfile ? undefined : 'none' }}>
                    <button 
                      className={`nav-link ${activeTab === 'settings' ? 'active' : ''}`}
                      onClick={() => handleTabChange('settings')}
                      type="button"
                    >
                                      <img src="/icons/profilewb.png" alt="Settings" style={{ width: '16px', height: '16px', marginRight: '8px' }} />
                {getLocalizedText('profile_tab_settings', 'Настройки')}
                    </button>
                  </li>
                </ul>
              </div>
              
              <div className="card-body">
                <div className="tab-content" id="profileTabsContent">
                  {/* Statistics Tab */}
                  <div className={`tab-pane fade ${activeTab === 'statistics' ? 'show active' : ''}`} id="statistics" role="tabpanel">
                    <StatisticsSection 
                      playerStats={playerStats} 
                      targetUsername={targetUsername}
                    />
                  </div>

                   {/* Inventory Tab */}
                   <div className={`tab-pane fade ${activeTab === 'inventory' ? 'show active' : ''}`} id="inventory" role="tabpanel">
                     <ProfileInventoryTab
                       inventory={userInventory}
                       getLocalizedText={getLocalizedText}
                       getCategoryIcon={getCategoryIcon}
                       onEquip={equipItem}
                       onOpenShop={() => navigate('/shop')}
                     />
                   </div>

                  {/* Achievements Tab */}
                  <div className={`tab-pane fade ${activeTab === 'achievements' ? 'show active' : ''}`} id="achievements" role="tabpanel">
                    {userAchievements ? (
                      <ProfileAchievements achievements={userAchievements} />
                    ) : (
                      <div className="text-center">
                        <div className="spinner-border text-primary" role="status">
                          <span className="visually-hidden">{getLocalizedText('profile_loading_achievements', 'Загрузка достижений...')}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Quests Tab */}
                  <div className={`tab-pane fade ${activeTab === 'quests' ? 'show active' : ''}`} id="quests" role="tabpanel">
                    <QuestsSection />
                  </div>

                  {/* Settings Tab */}
                  <div className={`tab-pane fade ${activeTab === 'settings' ? 'show active' : ''}`} id="settings" role="tabpanel">
                    <div className="settings-section">
                      
                      <div className="setting-item mb-3">
                        <label htmlFor="language-select" className="form-label">
                          {getLocalizedText('profile_settings_language_label', 'Язык интерфейса')}
                        </label>
                        <select 
                          id="language-select"
                          className="form-select"
                          value={settingsData.language}
                          onChange={(e) => setSettingsData({...settingsData, language: e.target.value})}
                        >
                          <option value="ru">{getLocalizedText('language_russian', 'Русский')}</option>
                          <option value="en">{getLocalizedText('language_english', 'Английский')}</option>
                          <option value="de">{getLocalizedText('language_german', 'Немецкий')}</option>
                        </select>
                        <div className="form-text">
                          {getLocalizedText('profile_settings_language_help', 'Выберите язык, на котором будет отображаться интерфейс')}
                        </div>
                      </div>
                      
                      <div className="setting-item mb-3">
                        <div className="form-check">
                          <input 
                            className="form-check-input" 
                            type="checkbox" 
                            id="allow-clan-invites"
                            checked={settingsData.allow_clan_invites}
                            onChange={(e) => setSettingsData({...settingsData, allow_clan_invites: e.target.checked})}
                          />
                          <label className="form-check-label" htmlFor="allow-clan-invites">
                            {getLocalizedText('profile_settings_allow_clan_invites_label', 'Разрешить приглашения в клан')}
                          </label>
                        </div>
                        <div className="form-text">
                          {getLocalizedText('profile_settings_allow_clan_invites_help', 'Если отключено, другие игроки не смогут приглашать вас в клан')}
                        </div>
                      </div>
                      
                      {/* Социальные сети для контентмейкеров */}
                      {user.role && user.role.name === 'contentmaker' && (
                        <>
                          <div className="setting-item mb-3">
                            <label htmlFor="telegram-url" className="form-label">
                              {getLocalizedText('profile_social_media_telegram_label', 'Telegram URL')}
                            </label>
                            <input 
                              type="url"
                              className="form-control"
                              id="telegram-url"
                              value={settingsData.telegram_url}
                              onChange={(e) => setSettingsData({...settingsData, telegram_url: e.target.value})}
                              placeholder="https://t.me/username"
                            />
                            <div className="form-text">
                              {getLocalizedText('profile_social_media_telegram_help', 'Ссылка на ваш Telegram канал или профиль')}
                            </div>
                          </div>
                          
                          <div className="setting-item mb-3">
                            <label htmlFor="twitch-url" className="form-label">
                              {getLocalizedText('profile_social_media_twitch_label', 'Twitch URL')}
                            </label>
                            <input 
                              type="url"
                              className="form-control"
                              id="twitch-url"
                              value={settingsData.twitch_url}
                              onChange={(e) => setSettingsData({...settingsData, twitch_url: e.target.value})}
                              placeholder="https://twitch.tv/username"
                            />
                            <div className="form-text">
                              {getLocalizedText('profile_social_media_twitch_help', 'Ссылка на ваш Twitch канал')}
                            </div>
                          </div>
                          
                          <div className="setting-item mb-3">
                            <label htmlFor="youtube-url" className="form-label">
                              {getLocalizedText('profile_social_media_youtube_label', 'YouTube URL')}
                            </label>
                            <input 
                              type="url"
                              className="form-control"
                              id="youtube-url"
                              value={settingsData.youtube_url}
                              onChange={(e) => setSettingsData({...settingsData, youtube_url: e.target.value})}
                              placeholder="https://youtube.com/@username"
                            />
                            <div className="form-text">
                              {getLocalizedText('profile_social_media_youtube_help', 'Ссылка на ваш YouTube канал')}
                            </div>
                          </div>
                        </>
                      )}
                      
                      <button 
                        className="btn btn-primary"
                        onClick={handleUpdateSettings}
                        disabled={updatingSettings}
                      >
                        {updatingSettings ? (
                          <>
                            <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                            {getLocalizedText('profile_settings_updating', 'Обновление...')}
                          </>
                        ) : (
                          getLocalizedText('profile_settings_save_button', 'Сохранить настройки')
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Invites Section - только для своего профиля */}
      {isOwnProfile && (
        <div className="row justify-content-center mt-4">
          <div className="col-lg-10">
            <div className="card profile-invites-card">
              <div className="card-header">
                <h5 className="text-gradient mb-0">
                  <img src="/icons/factorywb.png" alt="Envelope" style={{ width: '20px', height: '20px', marginRight: '8px' }} />
                  {getLocalizedText('profile_invites_title', 'Приглашения в кланы')}
                </h5>
              </div>
              <div className="card-body">
                <div id="invitesContainer">
                  {invites.length === 0 ? (
                    <div className="no-invites">
                      <img src="/icons/factorywb.png" alt="Envelope" style={{ width: '60px', height: '60px', marginBottom: '1rem' }} />
                      <h6>{getLocalizedText('profile_invites_no_invites_title', 'Приглашений нет')}</h6>
                      <p>{getLocalizedText('profile_invites_no_invites_description', 'У вас пока нет приглашений в кланы')}</p>
                    </div>
                  ) : (
                    invites.map(invite => (
                      <div key={invite.id} className="invite-card">
                        <div className="invite-header">
                          <div>
                            <div className="invite-clan-name">{invite.clan_name || getLocalizedText('profile_unknown_clan', 'Неизвестный клан')}</div>
                            <div className="invite-inviter">{getLocalizedText('profile_invites_from', 'Приглашение от')}: {getPlayerDisplayName(invite.inviter_username, getLocalizedText('profile_unknown', 'Неизвестно'))}</div>
                          </div>
                          <div className="invite-actions">
                            <button className="btn btn-accept" onClick={() => respondToInvite(invite.id, 'accepted')}>
                              <img src="/icons/sauronwb.png" alt="Check" style={{ width: '12px', height: '12px', marginRight: '4px' }} />
                              {getLocalizedText('profile_invites_accept', 'Принять')}
                            </button>
                            <button className="btn btn-decline" onClick={() => respondToInvite(invite.id, 'declined')}>
                              <img src="/icons/towerwb.png" alt="Times" style={{ width: '12px', height: '12px', marginRight: '4px' }} />
                              {getLocalizedText('profile_invites_decline', 'Отклонить')}
                            </button>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProfilePage; 
