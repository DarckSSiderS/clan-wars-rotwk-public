import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';

export const GAME_PATCHES = Object.freeze({
  ennorath: { id: 'ennorath', label: 'Ennorath', shortLabel: 'ENN' },
  patch_202: { id: 'patch_202', label: 'Patch 2.02', shortLabel: '2.02' },
});

const STORAGE_KEY = 'clanwars:selected-patch';
const PatchContext = createContext(null);

const normalizePatch = (value) => (GAME_PATCHES[value] ? value : 'ennorath');

export const PatchProvider = ({ children }) => {
  const [selectedPatch, setSelectedPatchState] = useState(() => {
    try {
      return normalizePatch(window.localStorage.getItem(STORAGE_KEY));
    } catch {
      return 'ennorath';
    }
  });

  const setSelectedPatch = (nextPatch) => {
    const normalized = normalizePatch(nextPatch);
    setSelectedPatchState(normalized);
    try {
      window.localStorage.setItem(STORAGE_KEY, normalized);
    } catch {
      // The in-memory preference still works when storage is unavailable.
    }
  };

  useEffect(() => {
    const syncPatch = (event) => {
      if (event.key === STORAGE_KEY) {
        setSelectedPatchState(normalizePatch(event.newValue));
      }
    };
    window.addEventListener('storage', syncPatch);
    return () => window.removeEventListener('storage', syncPatch);
  }, []);

  const value = useMemo(() => ({
    selectedPatch,
    selectedPatchData: GAME_PATCHES[selectedPatch],
    setSelectedPatch,
    patches: Object.values(GAME_PATCHES),
  }), [selectedPatch]);

  return <PatchContext.Provider value={value}>{children}</PatchContext.Provider>;
};

export const usePatch = () => {
  const context = useContext(PatchContext);
  if (!context) throw new Error('usePatch must be used inside PatchProvider');
  return context;
};
