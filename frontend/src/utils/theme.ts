export type ThemePreference = 'light' | 'dark';

export const SETTINGS_STORAGE_KEY = 'audit-it-settings';

type StoredSettings = {
  theme?: ThemePreference;
};

export function readStoredTheme(): ThemePreference {
  if (typeof window === 'undefined') return 'light';

  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return 'light';
    const parsed = JSON.parse(raw) as StoredSettings;
    return parsed.theme === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export function applyThemePreference(theme: ThemePreference) {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.theme = theme;
}
