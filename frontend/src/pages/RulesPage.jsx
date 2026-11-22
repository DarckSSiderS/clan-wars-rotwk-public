import React, { useEffect, useMemo, useRef, useState } from 'react';
import useMediaQuery from '@mui/material/useMediaQuery';
import { Link, useSearchParams } from 'react-router-dom';
import { PageShell, Surface } from '../components/ui';
import { getClanWarHandbook } from '../content/clanWarHandbook';
import { useLocalizationContext } from '../contexts/LocalizationContext';
import campaignRuleService from '../services/campaignRuleService';
import './PrototypeFeaturePages.css';
import './RulesPage.css';

const RuleSection = ({ section }) => (
  <Surface as="section" className="rules-content-card">
    <h3>{section.title}</h3>
    {section.paragraphs?.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}
    {section.bullets && (
      <ul>
        {section.bullets.map((item) => <li key={item}>{item}</li>)}
      </ul>
    )}
    {section.steps && (
      <ol className="rules-step-list">
        {section.steps.map((item) => <li key={item}>{item}</li>)}
      </ol>
    )}
    {section.links && (
      <div className="rules-inline-links">
        {section.links.map((link) => <Link key={link.to} to={link.to}>{link.label}</Link>)}
      </div>
    )}
  </Surface>
);

const RejectionList = ({ items }) => (
  <ol className="rules-rejection-list">
    {items.map((item) => (
      <li key={item.title}>
        <div className="rules-rejection-list__marker" aria-hidden="true">!</div>
        <div>
          <h3>{item.title}</h3>
          <p>{item.reason}</p>
          <p className="rules-rejection-list__action">{item.action}</p>
          <Link to={item.to}>{item.title}</Link>
        </div>
      </li>
    ))}
  </ol>
);

const RulesPage = () => {
  const { language } = useLocalizationContext();
  const compactNavigation = useMediaQuery('(max-width:64rem)');
  const [searchParams, setSearchParams] = useSearchParams();
  const [rulesResponse, setRulesResponse] = useState(null);
  const [loadError, setLoadError] = useState(false);
  const tabRefs = useRef([]);
  const navigationRef = useRef(null);
  const seasonId = searchParams.get('season');
  const rulesPayload = rulesResponse?.seasonId === seasonId ? rulesResponse.payload : null;
  const requestedSection = searchParams.get('section');

  useEffect(() => {
    let active = true;
    setRulesResponse(null);
    setLoadError(false);
    campaignRuleService.getPublic(seasonId)
      .then((payload) => active && setRulesResponse({ seasonId, payload }))
      .catch(() => {
        if (active) {
          setRulesResponse(null);
          setLoadError(true);
        }
      });
    return () => { active = false; };
  }, [seasonId]);

  const handbook = useMemo(
    () => getClanWarHandbook(language, rulesPayload || {}, { seasonId, loadError }),
    [language, rulesPayload, seasonId, loadError],
  );
  const activeIndex = Math.max(
    0,
    handbook.categories.findIndex((category) => category.id === requestedSection || category.aliases?.includes(requestedSection)),
  );
  const activeCategory = handbook.categories[activeIndex] || handbook.categories[0];

  useEffect(() => {
    if (!compactNavigation) return;
    const navigation = navigationRef.current;
    const tab = tabRefs.current[activeIndex];
    if (!navigation || !tab) return;
    const revealActiveTab = () => {
      const navigationBounds = navigation.getBoundingClientRect();
      const tabBounds = tab.getBoundingClientRect();
      navigation.scrollTo({
        left: navigation.scrollLeft + tabBounds.left - navigationBounds.left
          - (navigation.clientWidth - tabBounds.width) / 2,
        behavior: 'instant',
      });
    };
    revealActiveTab();
    const observer = new ResizeObserver(revealActiveTab);
    observer.observe(navigation);
    return () => observer.disconnect();
  }, [activeIndex, activeCategory.id, compactNavigation]);

  const selectSection = (sectionId, { focus = false } = {}) => {
    const nextParams = new URLSearchParams(searchParams);
    nextParams.set('section', sectionId);
    setSearchParams(nextParams, { replace: true });
    if (focus) {
      const index = handbook.categories.findIndex((category) => category.id === sectionId);
      tabRefs.current[index]?.focus();
    }
  };

  const activateTabFromKeyboard = (event, index) => {
    const directionByKey = {
      ArrowLeft: -1,
      ArrowUp: -1,
      ArrowRight: 1,
      ArrowDown: 1,
    };
    const direction = directionByKey[event.key];
    if (!direction && event.key !== 'Home' && event.key !== 'End') return;
    event.preventDefault();
    const nextIndex = event.key === 'Home'
      ? 0
      : event.key === 'End'
        ? handbook.categories.length - 1
        : (index + direction + handbook.categories.length) % handbook.categories.length;
    selectSection(handbook.categories[nextIndex].id, { focus: true });
  };

  return (
    <PageShell className="prototype-exact-page rules-page">
      <header className="page-title rules-page__header">
        <div>
          <div className="eyebrow">{handbook.eyebrow}</div>
          <h1 className="serif">{handbook.title}</h1>
          <p className="subtitle">{handbook.intro}</p>
        </div>
      </header>

      {(loadError || rulesPayload?.rule_set?.complete === false) && (
        <div className="rules-page__notice" role="status">
          {loadError ? handbook.fallbackNotice : handbook.incompleteNotice}
        </div>
      )}

      <div className="rules-page__layout">
        <nav
          className="rules-page__index"
          aria-label={handbook.navigationLabel}
        >
          <div
            ref={navigationRef}
            className="rules-page__tabs"
            role="tablist"
            aria-orientation={compactNavigation ? 'horizontal' : 'vertical'}
          >
            {handbook.categories.map((category, index) => {
              const selected = category.id === activeCategory.id;
              return (
                <button
                  id={`rules-${category.id}-tab`}
                  key={category.id}
                  ref={(element) => { tabRefs.current[index] = element; }}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  aria-controls="rules-active-panel"
                  tabIndex={selected ? 0 : -1}
                  className={`rules-page__tab${selected ? ' is-active' : ''}`}
                  onClick={() => selectSection(category.id)}
                  onKeyDown={(event) => activateTabFromKeyboard(event, index)}
                >
                  <span className="rules-page__tab-number">{String(index + 1).padStart(2, '0')}</span>
                  <span>{category.label}</span>
                </button>
              );
            })}
          </div>
        </nav>

        <article
          id="rules-active-panel"
          className="rules-page__content"
          role="tabpanel"
          aria-labelledby={`rules-${activeCategory.id}-tab`}
        >
          <header className="rules-page__section-header">
            <span>{handbook.sectionMeta}</span>
            <h2>{activeCategory.title}</h2>
            <p>{activeCategory.summary}</p>
          </header>

          {activeCategory.sections?.map((section) => (
            <RuleSection key={section.title} section={section} />
          ))}
          {activeCategory.rejections && <RejectionList items={activeCategory.rejections} />}
        </article>
      </div>
    </PageShell>
  );
};

export default RulesPage;
