import React from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';
import { Refresh, MilitaryTech } from '@mui/icons-material';
import { PageShell } from '../components/ui';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import useCampaignNavigation from '../hooks/useCampaignNavigation';
import { cycleMessage } from '../utils/cycleBattleView';
import WarsPage from './WarsPage';
import './CycleBattlesPage.css';
import './CycleBattleScreen.css';

const interseasonMessages = {
  ru: ['Межсезонье', 'Сезон завершён. Итоги кампании сохранены в архиве.', 'Архив сезонов'],
  en: ['Between seasons', 'The season has ended. Campaign results are saved in the archive.', 'Season archive'],
  de: ['Saisonpause', 'Die Saison ist beendet. Die Ergebnisse sind im Archiv gespeichert.', 'Saisonarchiv'],
};

export default function CampaignBattlesEntry() {
  const { navigation, loading, error, refresh } = useCampaignNavigation();
  const { language } = useLocalizationContext();
  const location = useLocation();
  const copy = key => cycleMessage(key, language);
  if (navigation?.interseason || navigation?.mode === 'interseason') {
    const [heading, message, archiveLabel] = interseasonMessages[language] || interseasonMessages.ru;
    return <PageShell className="cycle-battles cycle-battle-screen">
      <h1>{heading}</h1>
      <div className="cycle-empty"><MilitaryTech aria-hidden="true" />
        <p role="status">{message}</p>
        <Link to="/seasons">{archiveLabel}</Link>
      </div>
    </PageShell>;
  }
  if (navigation?.mode === 'legacy') return <WarsPage />;
  if (navigation?.href) return <Navigate to={`${navigation.href}${location.search}`} replace />;
  return <PageShell className="cycle-battles cycle-battle-screen" aria-busy={loading}>
    <h1>{copy('cycle_entry_title')}</h1>
    <div className="cycle-empty"><MilitaryTech aria-hidden="true" />
    {loading ? <p role="status">{copy('common_loading')}</p> : <>
      <p role={error ? 'alert' : 'status'}>{copy(error ? 'cycle_request_failed' : 'cycle_not_open')}</p>
      <button onClick={refresh}><Refresh aria-hidden="true" />{copy(error ? 'common_retry' : 'common_refresh')}</button>
    </>}
    </div>
  </PageShell>;
}
