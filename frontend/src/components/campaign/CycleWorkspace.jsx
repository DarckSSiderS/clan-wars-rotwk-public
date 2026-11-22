import React, { Suspense, useLayoutEffect, useRef } from 'react';
import { Outlet, useParams } from 'react-router-dom';
import { useLocalizationContext } from '../../contexts/LocalizationContext';
import CycleNavigation from './CycleNavigation';
import './CycleWorkspace.css';

export default function CycleWorkspace({ fallback }) {
  const { cycleId } = useParams();
  const { language } = useLocalizationContext();
  const workspace = useRef(null);

  useLayoutEffect(() => {
    const chrome = [...document.querySelectorAll('.cw-navigation, .admin-preview-banner')];
    const measure = () => {
      // The preview banner currently scrolls away; only pinned chrome reserves space.
      const bottom = chrome.reduce((offset, element) => {
        const style = getComputedStyle(element);
        if (!['sticky', 'fixed'].includes(style.position)) return offset;
        return Math.max(offset, element.getBoundingClientRect().height + (parseFloat(style.top) || 0));
      }, 0);
      workspace.current?.style.setProperty('--cycle-workspace-top', `${bottom}px`);
    };
    const observer = new ResizeObserver(measure);
    chrome.forEach(element => observer.observe(element));
    window.addEventListener('resize', measure);
    measure();
    return () => {
      observer.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, []);

  return <div className="cycle-workspace" ref={workspace}>
    <div className="cycle-workspace__navigation">
      <CycleNavigation cycleId={cycleId} language={language} />
    </div>
    <div className="cycle-workspace__content">
      <Suspense fallback={fallback}><Outlet /></Suspense>
    </div>
  </div>;
}
