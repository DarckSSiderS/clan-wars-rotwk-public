import React, { useCallback, useEffect, useState } from 'react';
import {
  AccessTimeRounded,
  AutoAwesomeRounded,
  CalendarMonthOutlined,
  DateRangeOutlined,
  TodayOutlined,
} from '@mui/icons-material';
import { CircularProgress } from '@mui/material';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { showSuccess, showError } from '../utils/notifications';
import { apiFetch } from '../services/apiFetch';
import { GoldResourceIcon } from './ResourceIcon';
import './QuestsSection.css';

const QuestsSection = () => {
  const { user, updateUser } = useAuth();
  const { getLocalizedText, loadPageTexts, language } = useLocalizationContext();
  
  const [dailyQuests, setDailyQuests] = useState([]);
  const [weeklyQuests, setWeeklyQuests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('daily');

  const loadQuests = useCallback(async () => {
    setLoading(true);
    try {
      // Загружаем ежедневные задания
      const dailyResponse = await apiFetch(`/api/v1/quests/daily?language=${language}`);
      
      if (dailyResponse.ok) {
        const dailyData = await dailyResponse.json();
        setDailyQuests(dailyData);
      }

      // Загружаем еженедельные задания
      const weeklyResponse = await apiFetch(`/api/v1/quests/weekly?language=${language}`);
      
      if (weeklyResponse.ok) {
        const weeklyData = await weeklyResponse.json();
        setWeeklyQuests(weeklyData);
      }
    } catch (error) {
      console.error('Ошибка загрузки заданий:', error);
    } finally {
      setLoading(false);
    }
  }, [language]);

  useEffect(() => {
    loadPageTexts('quests', language);
    loadQuests();
  }, [loadPageTexts, language, loadQuests]);



  const claimReward = async (questId) => {
    try {
      const response = await apiFetch(`/api/v1/quests/claim/${questId}`, {
        method: 'POST',
      });
      
      if (response.ok) {
        const result = await response.json();
        showSuccess(getLocalizedText('quest_reward_received', null, {
          coins: result.coins_earned,
          experience: result.experience_earned,
        }));
        
        // Обновляем данные пользователя только в текущем состоянии приложения.
        if (updateUser) {
          const updatedUserData = {
            ...user,
            balance: result.new_balance,
            experience: result.new_experience,
            level: result.new_level
          };
          updateUser(updatedUserData);
        }
        
        // Перезагружаем задания
        loadQuests();
      } else {
        showError(getLocalizedText('quest_reward_error', 'Не удалось получить награду'));
      }
    } catch (error) {
      console.error('Ошибка получения награды:', error);
      showError(getLocalizedText('quest_reward_error', 'Не удалось получить награду'));
    }
  };

  const getProgressTone = (percentage) => {
    if (percentage >= 100) return 'is-complete';
    if (percentage >= 75) return 'is-high';
    if (percentage >= 50) return 'is-mid';
    return 'is-low';
  };

  const formatTimeUntilReset = (expiresAt) => {
    const expires = new Date(expiresAt);
    const seconds = Math.round((expires.getTime() - Date.now()) / 1000);
    if (!Number.isFinite(seconds) || seconds <= 0) {
      return getLocalizedText('quest_expired', 'Истекло');
    }
    const formatter = new Intl.RelativeTimeFormat(language, { numeric: 'always' });
    if (seconds >= 86400) return formatter.format(Math.ceil(seconds / 86400), 'day');
    if (seconds >= 3600) return formatter.format(Math.ceil(seconds / 3600), 'hour');
    return formatter.format(Math.max(1, Math.ceil(seconds / 60)), 'minute');
  };

  const getQuestStatus = (userQuest) => {
    if (userQuest.is_completed) {
      return getLocalizedText('quest_completed', 'Завершено');
    }
    
    const expiresAt = new Date(userQuest.expires_at);
    const now = new Date();
    if (expiresAt <= now) {
      return getLocalizedText('quest_expired', 'Истекло');
    }
    
    return getLocalizedText('quest_in_progress', 'В процессе');
  };

  const renderQuestCard = (questData) => {
    const { quest, user_quest, progress_percentage } = questData;
    const isCompleted = user_quest.is_completed;
    const isClaimed = user_quest.is_claimed;
    const canClaim = isCompleted && !isClaimed;
    const isExpired = new Date(user_quest.expires_at) <= new Date();

    return (
      <article
        key={quest.id}
        className={`quest-card${isCompleted ? ' is-completed' : ''}${isClaimed ? ' is-claimed' : ''}${isExpired ? ' is-expired' : ''}`}
      >
        <div className="quest-header">
          <div className="quest-title">
            <h3>{getLocalizedText(quest.title_key, quest.title)}</h3>
            <p className="quest-description">
              {getLocalizedText(quest.description_key, quest.description)}
            </p>
          </div>
          <div className="quest-rewards">
            <div className="reward-item reward-item--coins">
              <GoldResourceIcon className="quest-reward-icon" size={16} />
              <span>{quest.reward_coins}</span>
            </div>
            <div className="reward-item reward-item--experience">
              <AutoAwesomeRounded className="quest-reward-icon" aria-hidden="true" />
              <span>{quest.reward_experience}</span>
            </div>
          </div>
        </div>
        
        <div className="quest-progress">
          <div className="progress-info">
            <span className="progress-text">
              {user_quest.current_progress} / {quest.target_value}
            </span>
            <span className="quest-timer">
              <AccessTimeRounded aria-hidden="true" />
              <strong>{formatTimeUntilReset(user_quest.expires_at)}</strong>
            </span>
          </div>
          <div className="quest-progress__track" aria-hidden="true">
            <div
              className={`quest-progress__fill ${getProgressTone(progress_percentage)}`}
              style={{ width: `${Math.min(progress_percentage, 100)}%` }}
            />
          </div>
        </div>
        
        <div className="quest-actions">
          {canClaim ? (
            <button 
              type="button"
              className="quest-claim-button"
              onClick={() => claimReward(quest.id)}
            >
              {getLocalizedText('quest_claim_reward', 'Получить награду')}
            </button>
          ) : isClaimed ? (
            <span className="quest-status is-claimed">{getLocalizedText('quest_claimed', 'Награда получена')}</span>
          ) : (
            <span className={`quest-status${isExpired ? ' is-expired' : ' is-progress'}`}>
              {getQuestStatus(user_quest)}
            </span>
          )}
        </div>
      </article>
    );
  };

  if (loading) {
    return (
      <div className="quests-section quests-section--loading" role="status">
        <CircularProgress size={28} />
        <span className="visually-hidden">{getLocalizedText('common_loading', 'Загрузка...')}</span>
      </div>
    );
  }

  return (
    <section className="quests-section">
      <ul className="quest-tabs" role="tablist">
        <li role="presentation">
          <button
            id="quests-daily-tab"
            type="button"
            role="tab"
            aria-selected={activeTab === 'daily'}
            aria-controls="quests-daily-panel"
            className={`quest-tab${activeTab === 'daily' ? ' is-active' : ''}`}
            onClick={() => setActiveTab('daily')}
          >
            <TodayOutlined className="quest-tab__icon" aria-hidden="true" />
            {getLocalizedText('quests_daily', 'Ежедневные')}
          </button>
        </li>
        <li role="presentation">
          <button
            id="quests-weekly-tab"
            type="button"
            role="tab"
            aria-selected={activeTab === 'weekly'}
            aria-controls="quests-weekly-panel"
            className={`quest-tab${activeTab === 'weekly' ? ' is-active' : ''}`}
            onClick={() => setActiveTab('weekly')}
          >
            <DateRangeOutlined className="quest-tab__icon" aria-hidden="true" />
            {getLocalizedText('quests_weekly', 'Еженедельные')}
          </button>
        </li>
      </ul>

      <div className="quest-tab-content">
        <div
          id="quests-daily-panel"
          role="tabpanel"
          aria-labelledby="quests-daily-tab"
          hidden={activeTab !== 'daily'}
        >
          {dailyQuests.length > 0 ? (
            <div className="quests-grid">
              {dailyQuests.map(renderQuestCard)}
            </div>
          ) : (
            <div className="quests-empty">
              <CalendarMonthOutlined className="quests-empty__icon" aria-hidden="true" />
              <h3>{getLocalizedText('quests_no_daily', 'Нет ежедневных заданий')}</h3>
              <p>{getLocalizedText('quests_no_daily_description', 'Ежедневные задания появятся завтра')}</p>
            </div>
          )}
        </div>

        <div
          id="quests-weekly-panel"
          role="tabpanel"
          aria-labelledby="quests-weekly-tab"
          hidden={activeTab !== 'weekly'}
        >
          {weeklyQuests.length > 0 ? (
            <div className="quests-grid">
              {weeklyQuests.map(renderQuestCard)}
            </div>
          ) : (
            <div className="quests-empty">
              <DateRangeOutlined className="quests-empty__icon" aria-hidden="true" />
              <h3>{getLocalizedText('quests_no_weekly', 'Нет еженедельных заданий')}</h3>
              <p>{getLocalizedText('quests_no_weekly_description', 'Еженедельные задания появятся в следующую неделю')}</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
};

export default QuestsSection; 
