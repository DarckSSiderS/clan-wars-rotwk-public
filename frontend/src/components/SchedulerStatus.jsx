import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import { showSuccess, showError } from '../utils/notifications';
import { apiFetch } from '../services/apiFetch';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const SchedulerStatus = () => {
  const { user } = useAuth();
  const { getLocalizedText: t } = useLocalizationContext();
  const [schedulerStatus, setSchedulerStatus] = useState(null);
  const [fetchingMatches, setFetchingMatches] = useState(false);

  useEffect(() => {
    if (user?.role?.name === 'admin') {
      loadSchedulerStatus();
    }
  }, [user]);

  const loadSchedulerStatus = async () => {
    try {
      const response = await apiFetch('/api/v1/scheduler/status');
      
      if (response.ok) {
        const status = await response.json();
        setSchedulerStatus(status);
      }
    } catch (error) {
      console.error('Ошибка загрузки статуса планировщика:', error);
    }
  };

  const fetchMatches = async () => {
    setFetchingMatches(true);
    try {
      const response = await apiFetch('/api/v1/scheduler/fetch-matches?limit=100', {
        method: 'POST',
      });
      
      if (response.ok) {
        const result = await response.json();
        showSuccess(result.message);
      } else {
        showError(t('scheduler_fetch_error'));
      }
    } catch (error) {
      console.error('Ошибка получения матчей:', error);
      showError(t('scheduler_fetch_error'));
    } finally {
      setFetchingMatches(false);
    }
  };

  // Показываем только администраторам
  if (user?.role?.name !== 'admin') {
    return null;
  }

  return (
    <div className="card mb-3 scheduler-status-card">
      <div className="card-header">
        <h6 className="mb-0">
          <img src="/icons/sauronwb.png" alt="Scheduler" style={{ width: '16px', height: '16px', marginRight: '8px' }} />
          {t('scheduler_title')}
        </h6>
      </div>
      <div className="card-body">
        <div className="row align-items-center">
          <div className="col-md-6">
            <div className="d-flex align-items-center mb-2">
              <span className="me-2">{t('scheduler_status')}</span>
              <span className={`badge ${schedulerStatus?.is_running ? 'bg-success' : 'bg-danger'}`}>
                {schedulerStatus?.is_running ? t('scheduler_running') : t('scheduler_stopped')}
              </span>
            </div>
            <div className="text-muted small">
              {t('scheduler_interval', null, { minutes: Math.floor((schedulerStatus?.interval_seconds || 600) / 60) })}
            </div>
          </div>
          <div className="col-md-6 text-end">
            <button 
              className={`btn btn-primary btn-sm ${fetchingMatches ? 'disabled' : ''}`}
              onClick={fetchMatches}
              disabled={fetchingMatches}
            >
              {fetchingMatches ? (
                <>
                  <span className="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                  {t('scheduler_fetching')}
                </>
              ) : (
                <>
                  <img src="/icons/towerwb.png" alt="Fetch" style={{ width: '14px', height: '14px', marginRight: '6px' }} />
                  {t('scheduler_fetch_matches')}
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SchedulerStatus; 
