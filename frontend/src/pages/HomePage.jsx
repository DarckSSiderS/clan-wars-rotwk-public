import React, { useEffect, useState } from 'react';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { statisticsService } from '../services/statisticsService';
import { PageShell } from '../components/ui';
import HomeHero from '../components/home/HomeHero';
import './HomePage.css';

const HomePage = () => {
  const { getLocalizedText: t } = useLocalizationContext();
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let mounted = true;

    statisticsService.getHomeSummary()
      .then((data) => {
        if (!mounted) return;
        setSummary(data);
        setError(false);
      })
      .catch(() => {
        if (!mounted) return;
        setSummary(null);
        setError(true);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, []);

  return (
    <PageShell className="home-page">
      <HomeHero summary={summary} loading={loading} />

      {error && (
        <div className="home-page__summary-error" role="alert">
          {t(
            'homepage_summary_error',
            'Не удалось загрузить сводку кампании. Остальные разделы доступны.',
          )}
        </div>
      )}
    </PageShell>
  );
};

export default HomePage;
