import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { CssBaseline } from '@mui/material';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import { useAuth } from './AuthContext';
import { apiFetch } from '../services/apiFetch';
import {
  applySiteThemeVariables,
  DEFAULT_SITE_THEME_KEY,
  getSiteTheme,
  normalizeSiteThemeKey,
  SITE_THEME_ITEM_TYPE,
} from '../theme/siteThemes';

const THEME_STORAGE_KEY = 'rotwk-site-theme';
const SiteThemeContext = createContext(null);

const readCachedTheme = () => normalizeSiteThemeKey(
  window.localStorage.getItem(THEME_STORAGE_KEY),
);

export const useSiteTheme = () => {
  const context = useContext(SiteThemeContext);
  if (!context) {
    throw new Error('useSiteTheme must be used within a SiteThemeProvider');
  }
  return context;
};

export const SiteThemeProvider = ({ children }) => {
  const { user, loading } = useAuth();
  const [themeKey, setThemeKey] = useState(readCachedTheme);

  const refreshSiteTheme = useCallback(async () => {
    if (!user?.id) {
      setThemeKey(DEFAULT_SITE_THEME_KEY);
      window.localStorage.removeItem(THEME_STORAGE_KEY);
      return DEFAULT_SITE_THEME_KEY;
    }

    const response = await apiFetch('/api/v1/shop/my-items/equipped/');
    if (!response.ok) {
      throw new Error(`Unable to load equipped theme: ${response.status}`);
    }

    const payload = await response.json();
    const equippedItems = Array.isArray(payload) ? payload : [];
    const activeTheme = equippedItems.find(
      (userItem) => userItem.item?.item_type === SITE_THEME_ITEM_TYPE,
    );
    const nextThemeKey = normalizeSiteThemeKey(activeTheme?.item?.css_class);
    setThemeKey(nextThemeKey);
    window.localStorage.setItem(THEME_STORAGE_KEY, nextThemeKey);
    return nextThemeKey;
  }, [user?.id]);

  useEffect(() => {
    if (loading) return;
    refreshSiteTheme().catch((error) => {
      console.warn('Не удалось обновить тему сайта:', error);
    });
  }, [loading, refreshSiteTheme]);

  useEffect(() => {
    applySiteThemeVariables(themeKey);
  }, [themeKey]);

  const siteTheme = useMemo(() => getSiteTheme(themeKey), [themeKey]);
  const muiTheme = useMemo(() => createTheme({
    palette: {
      mode: 'dark',
      primary: { main: siteTheme.primary },
      secondary: { main: siteTheme.secondary },
      background: {
        default: siteTheme.background,
        paper: siteTheme.paper,
      },
      text: {
        primary: '#e8e4d8',
        secondary: '#9b9d94',
      },
      warning: { main: '#bda56d' },
      success: { main: '#68765c' },
      error: { main: '#87453c' },
      divider: 'rgba(210, 190, 140, 0.16)',
    },
    typography: {
      fontFamily: 'var(--cw-font-ui)',
      h1: { fontFamily: 'var(--cw-font-display)', fontWeight: 700, lineHeight: 1.1 },
      h2: { fontFamily: 'var(--cw-font-display)', fontWeight: 700, lineHeight: 1.15 },
      h3: { fontWeight: 700, lineHeight: 1.2 },
      h4: { fontWeight: 700, lineHeight: 1.2 },
      h5: { fontWeight: 700, lineHeight: 1.25 },
      h6: { fontWeight: 700, lineHeight: 1.3 },
    },
    shape: { borderRadius: 8 },
    components: {
      MuiAppBar: {
        styleOverrides: {
          root: {
            backgroundColor: 'rgba(11, 13, 12, 0.9)',
            backgroundImage: 'none',
            borderBottom: '1px solid rgba(210, 190, 140, 0.16)',
            boxShadow: 'none',
          },
        },
      },
      MuiButton: {
        defaultProps: { disableElevation: true },
        styleOverrides: {
          root: {
            minHeight: 40,
            borderRadius: 6,
            fontWeight: 700,
            letterSpacing: 0,
            textTransform: 'none',
            transition: 'background-color 220ms, border-color 220ms, color 220ms, transform 220ms',
            '&:active': { transform: 'translateY(1px)' },
          },
          containedPrimary: {
            color: '#0b0d0c',
            backgroundColor: siteTheme.primary,
            '&:hover': { backgroundColor: siteTheme.primarySoft },
          },
          outlined: {
            borderColor: 'rgba(210, 190, 140, 0.32)',
          },
        },
      },
      MuiCard: {
        styleOverrides: {
          root: {
            background: `rgba(${siteTheme.cardRgb}, 0.9)`,
            backgroundImage: 'none',
            backdropFilter: 'blur(10px)',
            border: `1px solid ${siteTheme.cardBorder}`,
            borderRadius: 8,
            boxShadow: '0 10px 30px rgba(2, 4, 3, 0.2)',
          },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: {
            background: `rgba(${siteTheme.cardRgb}, 0.92)`,
            backgroundImage: 'none',
            backdropFilter: 'blur(10px)',
            borderColor: siteTheme.cardBorder,
          },
        },
      },
      MuiDialog: {
        styleOverrides: {
          paper: {
            background: 'rgba(17, 20, 17, 0.98)',
            border: '1px solid rgba(210, 190, 140, 0.24)',
            borderRadius: 10,
            boxShadow: '0 18px 48px rgba(2, 4, 3, 0.42)',
          },
        },
      },
      MuiMenu: {
        styleOverrides: {
          paper: {
            background: 'rgba(17, 20, 17, 0.98)',
            border: '1px solid rgba(210, 190, 140, 0.2)',
            borderRadius: 8,
            boxShadow: '0 16px 36px rgba(2, 4, 3, 0.42)',
          },
          list: { padding: 6 },
        },
      },
      MuiMenuItem: {
        styleOverrides: {
          root: {
            minHeight: 40,
            margin: '2px 0',
            borderRadius: 5,
            color: '#c4c2b8',
            fontSize: '0.82rem',
            '&:hover': { color: '#e8e4d8', backgroundColor: 'rgba(189, 165, 109, 0.08)' },
            '&.Mui-selected': { color: '#d3bc83', backgroundColor: 'rgba(189, 165, 109, 0.12)' },
            '&.Mui-selected:hover': { backgroundColor: 'rgba(189, 165, 109, 0.16)' },
          },
        },
      },
      MuiSelect: {
        styleOverrides: {
          icon: { color: '#9b9d94' },
          select: { minHeight: '1.35em' },
        },
      },
      MuiAutocomplete: {
        styleOverrides: {
          paper: {
            color: '#c4c2b8',
            background: 'rgba(17, 20, 17, 0.99)',
            border: '1px solid rgba(210, 190, 140, 0.2)',
            boxShadow: '0 16px 36px rgba(2, 4, 3, 0.42)',
          },
          option: {
            minHeight: 40,
            '&[aria-selected="true"]': { color: '#d3bc83', backgroundColor: 'rgba(189, 165, 109, 0.12)' },
            '&.Mui-focused': { backgroundColor: 'rgba(189, 165, 109, 0.08)' },
          },
        },
      },
      MuiTextField: {
        defaultProps: { variant: 'outlined' },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          root: {
            backgroundColor: 'rgba(11, 13, 12, 0.72)',
            '& .MuiOutlinedInput-notchedOutline': {
              borderColor: 'rgba(210, 190, 140, 0.2)',
            },
            '&:hover .MuiOutlinedInput-notchedOutline': {
              borderColor: 'rgba(210, 190, 140, 0.42)',
            },
          },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: {
            borderColor: 'rgba(210, 190, 140, 0.12)',
            fontVariantNumeric: 'tabular-nums',
          },
          head: {
            color: '#d3bc83',
            fontWeight: 700,
          },
        },
      },
      MuiTooltip: {
        styleOverrides: {
          tooltip: {
            color: '#e8e4d8',
            backgroundColor: '#171a17',
            border: '1px solid rgba(210, 190, 140, 0.18)',
            fontSize: '0.78rem',
          },
        },
      },
    },
  }), [siteTheme]);

  const value = useMemo(() => ({
    themeKey,
    siteTheme,
    refreshSiteTheme,
  }), [refreshSiteTheme, siteTheme, themeKey]);

  return (
    <SiteThemeContext.Provider value={value}>
      <ThemeProvider theme={muiTheme}>
        <CssBaseline />
        {children}
      </ThemeProvider>
    </SiteThemeContext.Provider>
  );
};
