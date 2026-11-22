import React, { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { PageShell, Surface } from '../components/ui';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import ModelViewer from '../features/encyclopedia/ModelViewer';
import { levelStats } from '../features/encyclopedia/modelRules';
import { controlName, entityName } from '../features/encyclopedia/localizedNames';
import { encyclopediaAssetFetch } from '../services/apiFetch';
import './EncyclopediaPage.css';

function ProfilePanel({ profile }) {
  const { language, getLocalizedText: t } = useLocalizationContext();
  const [level, setLevel] = useState(1);
  const [variantId, setVariantId] = useState(profile.variants[0].id);
  const [weaponId, setWeaponId] = useState('');
  const [formation, setFormation] = useState(false);
  const variant = profile.variants.find((item) => item.id === variantId && (item.unlock || 1) <= level) || profile.variants[0];
  const weapon = variant.weapons?.find((item) => item.id === weaponId) || variant.weapons?.[0];
  const stats = levelStats(profile, level);
  const maximum = profile.maxLevel || profile.levelUps.length;
  const kind = profile.kind || 'hero';
  const statKey = profile.id === 'rohanFarm' ? 'archive_income' : kind === 'building' ? 'archive_cost' : 'archive_damage';
  const changeLevel = (nextLevel) => {
    setLevel(nextLevel);
    const levelAppearance = profile.variants.filter((item) => item.autoLevel && item.unlock <= nextLevel).at(-1);
    if (levelAppearance) setVariantId(levelAppearance.id);
    else if ((variant.unlock || 1) > nextLevel) setVariantId(profile.variants[0].id);
  };
  return <div className="encyclopedia-detail">
    <header className="encyclopedia-profile-heading">
      <img src={variant.portrait || variant.icon} alt="" />
      <div><span className="knowledge-eyebrow">Ennorath · {t(`archive_${kind}`)}</span><h2>{entityName(profile, language)}</h2></div>
    </header>
    <Surface className="encyclopedia-model-card">
      <div className="encyclopedia-model-options">
        <label>{t('archive_variant')}<select aria-label={t('archive_variant')} value={variant.id} onChange={(event) => { setVariantId(event.target.value); setWeaponId(''); }}>
          {profile.variants.map((item) => <option key={item.id} value={item.id} disabled={(item.unlock || 1) > level}>
            {controlName(item.name, language)}{(item.unlock || 1) > 1 ? ` · ${t('archive_unlock', null, { level: item.unlock })}` : ''}
          </option>)}
        </select></label>
        {variant.weapons?.length > 0 && <label>{t('archive_weapon')}<select aria-label={t('archive_weapon')} value={weapon.id} onChange={(event) => setWeaponId(event.target.value)}>
          {variant.weapons.map((item) => <option key={item.id} value={item.id}>{controlName(item.name, language)}</option>)}
        </select></label>}
        {kind === 'unit' && <label className="encyclopedia-formation"><input type="checkbox" checked={formation} onChange={(event) => setFormation(event.target.checked)} />{t('archive_formation')}</label>}
      </div>
      <ModelViewer {...{ profile, variant, weapon, formation }} />
    </Surface>
    <Surface className="encyclopedia-stats-card">
      <div className="encyclopedia-level">
        <label htmlFor="archive-level">{t('archive_level')} <strong>{level}</strong></label>
        <input id="archive-level" type="range" min="1" max={maximum} value={level} onChange={(event) => changeLevel(Number(event.target.value))} />
        <span>{maximum}</span>
      </div>
      <dl className="encyclopedia-stats" aria-live="polite">
        <div><dt>{t(kind === 'building' ? 'archive_durability' : 'archive_health')}</dt><dd data-testid="entity-health">{stats.health.toLocaleString(language)}</dd></div>
        <div><dt>{t(statKey)}</dt><dd>{stats.damage.toLocaleString(language)}{profile.id === 'rohanFarm' && <small>{t('archive_income_cycle')}</small>}</dd></div>
        <div><dt>{t('archive_armor')}</dt><dd>{stats.armor}</dd></div>
        <div><dt>{t(kind === 'building' ? 'archive_development' : 'archive_experience')}</dt><dd>{(profile.experience[level - 1] ?? 0).toLocaleString(language)}</dd></div>
      </dl>
      <details className="encyclopedia-source"><summary>{t('archive_source')}</summary><p>{t('archive_snapshot')}</p><p lang="ru">{profile.statNote}</p></details>
    </Surface>
    <section className="encyclopedia-abilities">
      <div className="knowledge-section-heading"><h3>{t('archive_abilities')}</h3><span>{t('archive_original')}</span></div>
      <div className="encyclopedia-ability-list">
        {profile.spells.map((spell, index) => <Surface as="article" key={`${spell.source}-${index}`} className={`encyclopedia-ability${spell.level > level ? ' is-locked' : ''}`}>
          <img src={spell.image} alt="" loading="lazy" />
          <div><h4 lang="ru">{spell.name}</h4><span className="encyclopedia-unlock">{spell.level > level ? t('archive_unlock', null, { level: spell.level }) : t('archive_unlocked')}</span><p lang="ru">{spell.description}</p></div>
        </Surface>)}
      </div>
    </section>
  </div>;
}

export default function EncyclopediaPage() {
  const { language, getLocalizedText: t } = useLocalizationContext();
  const [params, setParams] = useSearchParams();
  const [catalog, setCatalog] = useState(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const query = params.get('q') || '';
  const faction = params.get('faction') || 'all';
  const kind = params.get('type') || 'all';
  useEffect(() => {
    const controller = new AbortController();
    setError(false);
    encyclopediaAssetFetch('/encyclopedia/ennorath/catalog.json', { signal: controller.signal })
      .then((response) => { if (!response.ok) throw new Error('Catalogue unavailable'); return response.json(); })
      .then((data) => { if (!controller.signal.aborted) setCatalog(data); })
      .catch((failure) => { if (failure.name !== 'AbortError') setError(true); });
    return () => controller.abort();
  }, [attempt]);
  const profiles = useMemo(() => {
    const ids = catalog?.factions.find((item) => item.id === faction)?.entities;
    const search = query.trim().toLocaleLowerCase(language);
    return (catalog?.profiles || []).filter((profile) => (
      (!ids || ids.includes(profile.id)) && (kind === 'all' || (profile.kind || 'hero') === kind)
      && `${profile.name} ${entityName(profile, language)} ${profile.id}`.toLocaleLowerCase(language).includes(search)
    ));
  }, [catalog, faction, kind, query, language]);
  const selected = profiles.find((profile) => profile.id === params.get('entity')) || profiles[0];
  const update = (key, value, replace = true) => {
    const next = new URLSearchParams(params);
    if (value && value !== 'all') next.set(key, value); else next.delete(key);
    setParams(next, { replace });
  };
  return <PageShell className="knowledge-page encyclopedia-page">
    <header className="knowledge-page-heading"><div><span className="knowledge-eyebrow">ROTWK · ClanWars</span><h1>{t('archive_title')}</h1><p>{t('archive_intro')}</p></div></header>
    <div className="encyclopedia-editions" role="tablist" aria-label={t('archive_version')}>
      <button id="encyclopedia-ennorath-tab" type="button" role="tab" aria-selected="true" aria-controls="encyclopedia-ennorath-panel">Ennorath</button>
      <button type="button" role="tab" aria-label="2.02" aria-selected="false" disabled title={t('archive_202_unavailable')} aria-describedby="encyclopedia-202-note">2.02 <span>{t('archive_unavailable')}</span></button>
    </div>
    <p id="encyclopedia-202-note" className="encyclopedia-editions-note">{t('archive_202_unavailable')}</p>
    <section id="encyclopedia-ennorath-panel" role="tabpanel" aria-labelledby="encyclopedia-ennorath-tab">
    {error ? <Surface className="knowledge-message" role="alert"><p>{t('archive_load_error')}</p><button type="button" onClick={() => setAttempt((value) => value + 1)}>{t('archive_retry')}</button></Surface> : !catalog ? <p role="status">{t('common_loading')}</p> :
      <div className="encyclopedia-layout">
        <Surface as="aside" className="encyclopedia-catalog" aria-label={t('archive_catalog')}>
          <h2>{t('archive_catalog')}</h2>
          <input type="search" aria-label={t('archive_search')} placeholder={t('archive_search')} value={query} onChange={(event) => update('q', event.target.value)} />
          <div className="encyclopedia-filters">
            <label>{t('archive_faction')}<select aria-label={t('archive_faction')} value={faction} onChange={(event) => update('faction', event.target.value)}><option value="all">{t('archive_all')}</option>{catalog.factions.map((item) => <option key={item.id} value={item.id}>{t(`archive_${item.id}`)}</option>)}</select></label>
            <label>{t('archive_kind')}<select aria-label={t('archive_kind')} value={kind} onChange={(event) => update('type', event.target.value)}>{['all', 'hero', 'unit', 'building'].map((value) => <option key={value} value={value}>{t(`archive_${value}`)}</option>)}</select></label>
          </div>
          <p className="encyclopedia-count" role="status">{t('archive_count', null, { count: profiles.length })}</p>
          <div className="encyclopedia-roster">
            {profiles.map((profile) => <button type="button" key={profile.id} aria-pressed={selected?.id === profile.id} onClick={() => update('entity', profile.id, false)}>
              <img src={profile.variants[0].icon} alt="" loading="lazy" /><span><strong>{entityName(profile, language)}</strong><small>{t(`archive_${profile.kind || 'hero'}`)}</small></span>
            </button>)}
          </div>
        </Surface>
        {selected ? <ProfilePanel key={selected.id} profile={selected} /> : <Surface className="knowledge-message"><p>{t('archive_empty')}</p></Surface>}
      </div>}
    </section>
  </PageShell>;
}
