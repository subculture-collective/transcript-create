import { useSite } from './site';
import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';

type Theme = 'light' | 'dark';
type ThemePreference = 'auto' | 'light' | 'dark';

interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const THEME_PREFERENCE_KEY = 'themePreference';

function getSystemTheme(): Theme {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function getStoredPreference(): ThemePreference {
  const stored = localStorage.getItem(THEME_PREFERENCE_KEY) as ThemePreference | null;
  return stored || 'auto';
}

function getInitialTheme(): Theme {
  const preference = getStoredPreference();
  if (preference === 'light' || preference === 'dark') {
    return preference;
  }
  return getSystemTheme();
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const site = useSite();
  const [themePreference, setThemePreference] = useState<ThemePreference>(getStoredPreference);
  const [theme, setTheme] = useState<Theme>(getInitialTheme);

  useEffect(() => {
    // Apply theme to document
    document.documentElement.classList.remove('light', 'dark');
    document.documentElement.classList.add(theme);

    const colors = site.theme?.[theme] ?? {};
    const tokens = new Set(
      'canvas surface surface-muted surface-raised border border-strong ink muted subtle accent accent-hover accent-soft accent-contrast accent-2 accent-3 player-accent cta success success-soft warning warning-soft danger danger-soft'.split(
        ' '
      )
    );
    const applied: string[] = [];
    for (const [token, color] of Object.entries(colors)) {
      if (tokens.has(token) && /^#[0-9a-f]{6}$/i.test(color)) {
        const property = `--color-${token}`;
        document.documentElement.style.setProperty(property, color);
        applied.push(property);
      }
    }
    const fonts = {
      system: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      editorial: '"Alegreya Sans", "Segoe UI", sans-serif',
      mono: 'ui-monospace, "SFMono-Regular", Menlo, monospace',
    };
    // Without a client profile font, keep the stylesheet's typefaces.
    const font = site.theme?.font ? fonts[site.theme.font] : undefined;
    if (font) {
      for (const token of ['--font-body', '--font-display', '--font-sans']) {
        document.documentElement.style.setProperty(token, font);
        applied.push(token);
      }
    }
    // Update meta theme-color
    const metaThemeColor = document.querySelector('meta[name="theme-color"]');
    if (metaThemeColor) {
      metaThemeColor.setAttribute(
        'content',
        colors.canvas ?? (theme === 'dark' ? '#0f0f0f' : '#faf9f5')
      );
    }
    return () => {
      for (const token of applied) document.documentElement.style.removeProperty(token);
    };
  }, [theme, site.theme]);

  // Listen to system preference changes
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (e: MediaQueryListEvent) => {
      // Only auto-switch if user hasn't manually set a preference
      if (themePreference === 'auto') {
        setTheme(e.matches ? 'dark' : 'light');
      }
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [themePreference]);

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
    setThemePreference(newTheme);
    localStorage.setItem(THEME_PREFERENCE_KEY, newTheme);
  };

  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}
