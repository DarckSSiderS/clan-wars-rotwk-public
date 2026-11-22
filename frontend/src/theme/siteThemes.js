export const SITE_THEME_ITEM_TYPE = 'site_theme';
export const DEFAULT_SITE_THEME_KEY = 'theme-default';

export const SITE_THEMES = {
  [DEFAULT_SITE_THEME_KEY]: {
    labelKey: 'theme_default',
    primary: '#bda56d',
    primarySoft: '#d3bc83',
    primaryHover: '#d3bc83',
    primaryHoverSoft: '#ddca9a',
    secondary: '#9b9d94',
    background: '#0b0d0c',
    paper: '#111411',
    cardBorder: 'rgba(210, 190, 140, 0.16)',
    primaryRgb: '189, 165, 109',
    cardRgb: '17, 20, 17',
    appBar: 'linear-gradient(180deg, rgba(17, 20, 17, 0.96), rgba(11, 13, 12, 0.92))',
    pageOverlay: 'rgba(7, 10, 8, 0.45)',
    pageImage: 'url(/backgrounds/middle-earth-clanwar.webp)',
    pageBlend: 'multiply',
    ambient: 'radial-gradient(circle at 24% 8%, rgba(189, 165, 109, 0.08) 0%, transparent 42%)',
    preview: 'linear-gradient(145deg, #23251f 0%, #0b0d0c 58%, #4e432b 100%)',
  },
  'theme-mordor': {
    labelKey: 'theme_mordor',
    primary: '#ff5a4f',
    primarySoft: '#ff8575',
    primaryHover: '#d94137',
    primaryHoverSoft: '#ff695e',
    secondary: '#c5aaa1',
    background: '#120d0c',
    paper: '#1c1412',
    cardBorder: '#5b2e27',
    primaryRgb: '255, 90, 79',
    cardRgb: '28, 20, 18',
    appBar: 'linear-gradient(135deg, #6f1d18 0%, #24100e 72%, #0b0908 100%)',
    pageOverlay: 'rgba(17, 5, 2, 0.45)',
    pageImage: 'radial-gradient(circle at 72% 78%, rgba(255, 70, 32, 0.52), transparent 28%), linear-gradient(145deg, rgba(55, 8, 3, 0.18), rgba(5, 4, 3, 0.8)), url(/backgrounds/middle-earth-clanwar.webp)',
    pageBlend: 'screen, multiply, multiply',
    ambient: 'radial-gradient(circle at 72% 82%, rgba(255, 75, 35, 0.2) 0%, transparent 38%), radial-gradient(circle at 18% 15%, rgba(139, 34, 18, 0.22) 0%, transparent 44%)',
    preview: 'radial-gradient(circle at 76% 72%, #ff5a32 0%, #6e1d13 20%, transparent 42%), linear-gradient(145deg, #32100c 0%, #100b0a 60%, #4c1712 100%)',
  },
  'theme-gondor': {
    labelKey: 'theme_gondor',
    primary: '#d6b35f',
    primarySoft: '#f0d58b',
    primaryHover: '#b38b36',
    primaryHoverSoft: '#ddba63',
    secondary: '#bdc7d2',
    background: '#0d1218',
    paper: '#141c24',
    cardBorder: '#465768',
    primaryRgb: '214, 179, 95',
    cardRgb: '20, 28, 36',
    appBar: 'linear-gradient(135deg, #344657 0%, #17212c 58%, #8d7137 140%)',
    pageOverlay: 'rgba(5, 11, 18, 0.45)',
    pageImage: 'linear-gradient(118deg, rgba(203, 218, 232, 0.18), transparent 42%), radial-gradient(circle at 78% 24%, rgba(214, 179, 95, 0.32), transparent 32%), url(/backgrounds/middle-earth-clanwar.webp)',
    pageBlend: 'screen, soft-light, multiply',
    ambient: 'radial-gradient(circle at 78% 18%, rgba(214, 179, 95, 0.18) 0%, transparent 40%), radial-gradient(circle at 15% 88%, rgba(104, 139, 171, 0.2) 0%, transparent 44%)',
    preview: 'radial-gradient(circle at 75% 25%, #e4c679 0%, #47596b 18%, transparent 42%), linear-gradient(145deg, #334454 0%, #0d131a 58%, #765f32 100%)',
  },
  'theme-rivendell': {
    labelKey: 'theme_rivendell',
    primary: '#57d1c9',
    primarySoft: '#8de9df',
    primaryHover: '#2fa9a6',
    primaryHoverSoft: '#62d8d0',
    secondary: '#c6b5e7',
    background: '#0b101b',
    paper: '#121a29',
    cardBorder: '#405070',
    primaryRgb: '87, 209, 201',
    cardRgb: '18, 26, 41',
    appBar: 'linear-gradient(135deg, #173d46 0%, #171d38 58%, #392754 100%)',
    pageOverlay: 'rgba(5, 9, 23, 0.45)',
    pageImage: 'radial-gradient(circle at 20% 18%, rgba(99, 231, 217, 0.32), transparent 28%), radial-gradient(circle at 82% 30%, rgba(151, 101, 214, 0.34), transparent 36%), url(/backgrounds/middle-earth-clanwar.webp)',
    pageBlend: 'screen, screen, multiply',
    ambient: 'radial-gradient(circle at 20% 18%, rgba(87, 209, 201, 0.2) 0%, transparent 38%), radial-gradient(circle at 80% 74%, rgba(151, 101, 214, 0.22) 0%, transparent 44%)',
    preview: 'radial-gradient(circle at 22% 24%, #6ce4d8 0%, #16464b 18%, transparent 42%), radial-gradient(circle at 78% 74%, #8051b8 0%, transparent 38%), linear-gradient(145deg, #151d36 0%, #0a101c 100%)',
  },
};

export const normalizeSiteThemeKey = (themeKey) => (
  Object.prototype.hasOwnProperty.call(SITE_THEMES, themeKey)
    ? themeKey
    : DEFAULT_SITE_THEME_KEY
);

export const getSiteTheme = (themeKey) => SITE_THEMES[normalizeSiteThemeKey(themeKey)];

export const applySiteThemeVariables = (themeKey) => {
  const normalizedKey = normalizeSiteThemeKey(themeKey);
  const theme = getSiteTheme(normalizedKey);
  const root = document.documentElement;
  root.dataset.siteTheme = normalizedKey;
  root.style.setProperty('--primary-color', theme.primary);
  root.style.setProperty('--primary-soft-color', theme.primarySoft);
  root.style.setProperty('--primary-hover-color', theme.primaryHover);
  root.style.setProperty('--primary-hover-soft-color', theme.primaryHoverSoft);
  root.style.setProperty('--primary-rgb', theme.primaryRgb);
  root.style.setProperty('--secondary-color', '#e8e4d8');
  root.style.setProperty('--accent-color', theme.secondary);
  root.style.setProperty('--dark-bg', theme.background);
  root.style.setProperty('--darker-bg', theme.background);
  root.style.setProperty('--card-bg', theme.paper);
  root.style.setProperty('--card-bg-rgb', theme.cardRgb);
  root.style.setProperty('--card-border', theme.cardBorder);
  root.style.setProperty('--text-primary', '#e8e4d8');
  root.style.setProperty('--text-secondary', theme.secondary);
  root.style.setProperty('--text-muted', '#6f746c');
  root.style.setProperty('--gradient-primary', `linear-gradient(135deg, ${theme.primary}, ${theme.primarySoft})`);
  root.style.setProperty('--page-overlay', theme.pageOverlay);
  root.style.setProperty('--page-background-image', theme.pageImage);
  root.style.setProperty('--page-background-blend', theme.pageBlend);
  root.style.setProperty('--ambient-background', theme.ambient);
};
