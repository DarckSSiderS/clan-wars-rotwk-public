import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, CircularProgress } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { clanService } from '../services/clanService';
import { useAuth } from '../contexts/AuthContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import { showSuccess, showError, confirmAction } from '../utils/notifications';
import ClanCreationDialog from '../components/ClanCreationDialog';
import ClanDiplomacySummary from '../components/clan/ClanDiplomacySummary';
import { PageShell } from '../components/ui';
import './ClansPage.css';

const ClansPage = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { getLocalizedText: t, language, loadPageTexts } = useLocalizationContext();
  const locale = language === 'de' ? 'de-DE' : language === 'en' ? 'en-US' : 'ru-RU';
  const [clans, setClans] = useState([]);
  const [myClan, setMyClan] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [sortBy, setSortBy] = useState('rating');
  const [recruitingOnly, setRecruitingOnly] = useState(false);
  const [createClanOpen, setCreateClanOpen] = useState(false);

  useEffect(() => {
    loadPageTexts('clans', language);
  }, [language, loadPageTexts]);

  const fetchClans = useCallback(async () => {
    try {
      const [clansData, currentClan] = await Promise.all([
        clanService.getClans(),
        user
          ? clanService.getMyClan().catch(() => null)
          : Promise.resolve(null),
      ]);
      setClans(Array.isArray(clansData) ? clansData : []);
      setMyClan(currentClan);
      setError('');
    } catch {
      setError(t('clans_error_loading', 'Ошибка при загрузке кланов'));
    } finally {
      setLoading(false);
    }
  }, [t, user]);

  useEffect(() => {
    fetchClans();
  }, [fetchClans]);

  const filteredClans = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    return clans
      .filter((clan) => !query
        || clan.name.toLowerCase().includes(query)
        || clan.description?.toLowerCase().includes(query)
        || clan.motto?.toLowerCase().includes(query))
      .filter((clan) => !recruitingOnly || clan.is_recruiting)
      .sort((left, right) => {
        if (sortBy === 'members') return (right.member_count || 0) - (left.member_count || 0);
        if (sortBy === 'territories') return (right.territory_count || 0) - (left.territory_count || 0);
        if (sortBy === 'name') return left.name.localeCompare(right.name, locale);
        return (right.territory_points || 0) - (left.territory_points || 0);
      });
  }, [clans, locale, recruitingOnly, searchTerm, sortBy]);

  const handleClanCreated = (createdClan) => {
    showSuccess(t('clans_created_success', 'Клан успешно создан'));
    setCreateClanOpen(false);
    setMyClan(createdClan);
    fetchClans();
  };


  const handleDeleteClan = async (clanId) => {
    const confirmed = await confirmAction(
      t('clan_delete_confirm_message', 'Расформировать клан? История, очки и владения останутся в архиве.'),
      t('clan_delete_confirm_title', 'Расформирование клана'),
    );
    if (!confirmed) return;

    try {
      await clanService.deleteClan(clanId);
      showSuccess(t('clan_delete_success', 'Клан расформирован и перенесён в архив.'));
      fetchClans();
    } catch (requestError) {
      showError(requestError.response?.data?.detail || t('clans_delete_error', 'Ошибка при удалении клана'));
    }
  };

  if (loading) {
    return (
      <PageShell className="clans-prototype-page prototype-exact-page clans-prototype-page--loading">
        <CircularProgress aria-label={t('common_loading', 'Загрузка...')} />
      </PageShell>
    );
  }

  return (
    <PageShell className="clans-prototype-page prototype-exact-page clans-page">
      <header className="clans-prototype-hero page-title">
        <div>
          <span className="eyebrow">{t('clans_prototype_eyebrow', 'Союзы Средиземья')}</span>
          <h1 className="serif">{t('clans_page_title', 'Кланы')}</h1>
          <p className="subtitle">{t('clans_prototype_subtitle', 'Сравнивайте составы, владения, форму и историю противников.')}</p>
        </div>
        {!myClan ? (
          <button className="clans-primary-action btn primary" type="button" onClick={() => setCreateClanOpen(true)}>
            {t('clans_create_button', 'Создать клан')}
          </button>
        ) : (
          <button className="clans-secondary-action btn" type="button" onClick={() => navigate(`/clans/${myClan.id}`)}>
            {t('clans_my_clan', 'Мой клан')}
          </button>
        )}
      </header>

      {error && <Alert severity="error" className="clans-prototype-alert">{error}</Alert>}

      <section className="clans-filterbar card filterbar" aria-label={t('clans_filters', 'Фильтры кланов')}>
        <label className="clans-search">
          <span className="sr-only">{t('clans_search_placeholder', 'Поиск клана')}</span>
          <input
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder={t('clans_search_placeholder', 'Поиск клана')}
          />
        </label>
        <select value={sortBy} onChange={(event) => setSortBy(event.target.value)} aria-label={t('clans_sort', 'Сортировка')}>
          <option value="rating">{t('clans_sort_rating', 'Сортировка: рейтинг')}</option>
          <option value="territories">{t('clans_sort_territories', 'Территории')}</option>
          <option value="members">{t('clans_sort_members', 'Участники')}</option>
          <option value="name">{t('clans_sort_name', 'Название')}</option>
        </select>
        <label className="clans-recruiting-filter">
          <input
            type="checkbox"
            checked={recruitingOnly}
            onChange={(event) => setRecruitingOnly(event.target.checked)}
          />
          <span>{t('clans_recruiting_only', 'Идёт набор')}</span>
        </label>
      </section>

      {filteredClans.length ? (
        <section className="clans-prototype-grid section grid" aria-label={t('clans_page_title', 'Кланы')}>
          {filteredClans.map((clan, index) => {
            const isOwner = user?.id === clan.leader_id && !clan.is_admin_clan;
            const mapColor = clan.map_color || '#74633e';
            return (
              <article
                className="clans-prototype-card clans-page__card card clan-card hover"
                style={{ '--clan-accent': mapColor, '--accent': mapColor }}
                key={clan.id}
                onClick={() => navigate(`/clans/${clan.id}`)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') navigate(`/clans/${clan.id}`);
                }}
                role="link"
                tabIndex={0}
              >
                <div className="clans-prototype-card__head">
                  {clan.avatar_url
                    ? <img className="clans-prototype-card__avatar" src={clan.avatar_url} alt="" />
                    : <span className="clans-prototype-card__avatar crest-mini" aria-hidden="true">{clan.name.slice(0, 1).toUpperCase()}</span>}
                  <div>
                    <h2>{clan.name}</h2>
                    <span className="clans-prototype-card__level">{t('clan_level_badge', null, { level: clan.level ?? 1 })}</span>
                    <p>{clan.motto || clan.description || t('clans_no_description', 'Описание отсутствует')}</p>
                  </div>
                </div>
                <div className="clans-prototype-card__meta">
                  <span><b>#{index + 1}</b><small>{t('clans_place', 'Место')}</small></span>
                  <span><b>{Number(clan.territory_points || 0).toLocaleString(locale)}</b><small>{t('clans_points', 'Очков')}</small></span>
                  <span><b>{clan.territory_count || 0}</b><small>{t('clans_territories', 'Земель')}</small></span>
                  <span><b>{clan.member_count || 0}</b><small>{t('clan_members_short', 'Участников')}</small></span>
                </div>
                <footer>
                  <span>{clan.created_at ? new Date(clan.created_at).toLocaleDateString(locale) : t('common_unknown', 'Неизвестно')}</span>
                  {clan.is_recruiting && <b>{t('clans_recruiting', 'Набор открыт')}</b>}
                  {isOwner && (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        handleDeleteClan(clan.id);
                      }}
                    >
                      {t('clans_delete_button', 'Удалить клан')}
                    </button>
                  )}
                </footer>
              </article>
            );
          })}
        </section>
      ) : (
        <section className="clans-prototype-empty" role="status">
          <strong>{t('clans_no_clans_found', 'Кланы не найдены')}</strong>
          <p>{t('clans_be_first', 'Измените фильтры или создайте новый клан.')}</p>
        </section>
      )}

      <section className="section grid g2 clans-lower-grid">
        <div data-section="clan-standings">
          <div className="section-head">
            <div><div className="eyebrow">{t('ranking_season_tab', 'Текущий сезон')}</div><h2>{t('clans_influence_table', 'Таблица влияния')}</h2></div>
          </div>
          <div className="card table-wrap clans-influence-table-wrap">
            <table className="table clans-influence-table">
              <thead><tr><th>#</th><th>{t('clans_page_title', 'Клан')}</th><th>{t('clan_statistics_influence', 'Влияние')}</th><th>{t('clans_territories', 'Земли')}</th><th>{t('clans_members', 'Участники')}</th></tr></thead>
              <tbody>
                {filteredClans.slice(0, 8).map((clan, index) => (
                  <tr key={clan.id}>
                    <td>{index + 1}</td>
                    <td><button type="button" className="clans-table-link" onClick={() => navigate(`/clans/${clan.id}`)}>{clan.name}</button></td>
                    <td>{Number(clan.territory_points || 0).toLocaleString(locale)}</td>
                    <td>{clan.territory_count || 0}</td>
                    <td>{clan.member_count || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
        <ClanDiplomacySummary myClan={myClan} clans={clans} onChanged={fetchClans} />
      </section>

      <ClanCreationDialog
        open={createClanOpen && !myClan}
        onClose={() => setCreateClanOpen(false)}
        onCreated={handleClanCreated}
      />
    </PageShell>
  );
};

export default ClansPage;
