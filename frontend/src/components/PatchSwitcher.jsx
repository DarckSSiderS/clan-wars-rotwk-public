import React from 'react';
import { usePatch } from '../contexts/PatchContext';
import { useLocalizationContext } from '../contexts/LocalizationContext';

const PatchSwitcher = ({ className = '' }) => {
  const { patches, selectedPatch, setSelectedPatch } = usePatch();
  const { getLocalizedText: t } = useLocalizationContext();

  return (
    <div
      className={`cw-patch-switch ${className}`.trim()}
      role="group"
      aria-label={t('patch_switcher_label')}
    >
      {patches.map((patch) => (
        <button
          type="button"
          key={patch.id}
          className={`cw-patch-switch__option${selectedPatch === patch.id ? ' is-active' : ''}`}
          aria-pressed={selectedPatch === patch.id}
          onClick={() => setSelectedPatch(patch.id)}
        >
          <span className="cw-patch-switch__label-long">{patch.label}</span>
          <span className="cw-patch-switch__label-short">{patch.shortLabel}</span>
        </button>
      ))}
    </div>
  );
};

export default PatchSwitcher;
