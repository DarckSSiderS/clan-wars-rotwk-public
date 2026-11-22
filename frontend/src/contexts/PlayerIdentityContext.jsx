import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../services/apiFetch';

const PlayerIdentityContext = createContext(null);

export const usePlayerIdentity = () => {
  const context = useContext(PlayerIdentityContext);
  if (!context) throw new Error('usePlayerIdentity должен использоваться внутри PlayerIdentityProvider');
  return context;
};

export const PlayerIdentityProvider = ({ children }) => {
  const [directory, setDirectory] = useState({});

  const refreshDirectory = useCallback(async () => {
    try {
      const response = await apiFetch('/api/v1/users/identity-directory');
      if (!response.ok) return;
      const payload = await response.json();
      const nextDirectory = {};
      (payload.players || []).forEach((player) => {
        const names = [player.username, player.display_name, ...(player.aliases || [])];
        names.forEach((name) => {
          if (name) nextDirectory[String(name).toLocaleLowerCase()] = player;
        });
      });
      setDirectory(nextDirectory);
    } catch (error) {
      console.error('Не удалось загрузить статусы и титулы игроков:', error);
    }
  }, []);

  useEffect(() => {
    refreshDirectory();
  }, [refreshDirectory]);

  const value = useMemo(() => ({
    getIdentity: (username) => directory[String(username || '').toLocaleLowerCase()] || null,
    refreshDirectory,
  }), [directory, refreshDirectory]);

  return (
    <PlayerIdentityContext.Provider value={value}>
      {children}
    </PlayerIdentityContext.Provider>
  );
};
