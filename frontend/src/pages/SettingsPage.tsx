import { Globe2, MoonStar, Save, ShieldCheck, SunMedium, Upload, UserRound, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useAuthContext } from '../context/AuthContext';
import { useLanguage } from '../context/LanguageContext';
import { deleteMyProfileAvatar, updateMyProfile, uploadMyProfileAvatar } from '../services/api';
import { SETTINGS_STORAGE_KEY, applyThemePreference, readStoredTheme, type ThemePreference } from '../utils/theme';

type LocalSettings = {
  preferred_language: string;
  time_zone: string;
  theme: ThemePreference;
};

const defaultLocalSettings = (): LocalSettings => ({
  preferred_language: 'English',
  time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'Africa/Tunis',
  theme: readStoredTheme()
});

function readLocalSettings(): LocalSettings {
  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return defaultLocalSettings();
    return { ...defaultLocalSettings(), ...(JSON.parse(raw) as Partial<LocalSettings>) };
  } catch {
    return defaultLocalSettings();
  }
}

export default function SettingsPage() {
  const { user, refreshSession } = useAuthContext();
  const { setLanguage, text } = useLanguage();
  const [localSettings, setLocalSettings] = useState<LocalSettings>(() => readLocalSettings());
  const [organization, setOrganization] = useState(user?.organization || '');
  const [savingProfile, setSavingProfile] = useState(false);
  const [saveState, setSaveState] = useState<'idle' | 'saved' | 'error'>('idle');
  const [avatarState, setAvatarState] = useState<'idle' | 'saving' | 'saved' | 'removed' | 'error'>('idle');
  const [avatarError, setAvatarError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setOrganization(user?.organization || '');
  }, [user?.organization]);

  useEffect(() => {
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(localSettings));
    applyThemePreference(localSettings.theme);
  }, [localSettings]);

  const fullName = useMemo(() => {
    if (!user) return '';
    const combined = `${user.first_name} ${user.last_name}`.trim();
    return combined || user.display_name || user.email;
  }, [user]);

  const roleLabel = useMemo(() => {
    const role = String(user?.role || 'auditor').trim().toLowerCase();
    return role === 'manager' ? 'Manager' : 'Auditor';
  }, [user?.role]);

  const handleProfileSave = async () => {
    setSavingProfile(true);
    setSaveState('idle');
    try {
      await updateMyProfile({
        organization: organization.trim()
      });
      await refreshSession();
      setSaveState('saved');
    } catch (error) {
      console.error('Failed to save profile settings:', error);
      setSaveState('error');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleAvatarUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setAvatarState('saving');
    setAvatarError('');
    try {
      await uploadMyProfileAvatar(file);
      await refreshSession();
      setAvatarState('saved');
    } catch (error) {
      console.error('Failed to upload profile picture:', error);
      setAvatarError(error instanceof Error ? error.message : 'Profile picture could not be uploaded right now.');
      setAvatarState('error');
    } finally {
      event.target.value = '';
    }
  };

  const handleAvatarRemove = async () => {
    setAvatarState('saving');
    setAvatarError('');
    try {
      await deleteMyProfileAvatar();
      await refreshSession();
      setAvatarState('removed');
    } catch (error) {
      console.error('Failed to remove profile picture:', error);
      setAvatarError(error instanceof Error ? error.message : 'Profile picture could not be removed right now.');
      setAvatarState('error');
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="pwc-kicker">Settings</p>
          <h1 className="pwc-title mt-2 text-4xl font-semibold">{text.settings.title}</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            {text.settings.subtitle}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void handleProfileSave()}
          disabled={savingProfile}
          className="pwc-action-primary disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          {savingProfile ? text.settings.saving : text.settings.saveProfile}
        </button>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <section className="pwc-main-panel space-y-6">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#fff1e8] text-[#ef5b0c]">
              <UserRound className="h-5 w-5" />
            </div>
            <div>
              <p className="pwc-kicker">{text.settings.profile}</p>
              <h2 className="pwc-title mt-1 text-2xl font-semibold">{text.settings.personalInformation}</h2>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="md:col-span-2 rounded-[1.75rem] border border-slate-200 bg-slate-50/60 p-5">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex items-center gap-4">
                  {user?.profile_image_url ? (
                    <img
                      src={user.profile_image_url}
                      alt={`${fullName || 'User'} profile`}
                      className="h-20 w-20 rounded-[1.4rem] object-cover ring-1 ring-slate-200"
                    />
                  ) : (
                    <div className="flex h-20 w-20 items-center justify-center rounded-[1.4rem] bg-white text-slate-500 ring-1 ring-slate-200">
                      <UserRound className="h-8 w-8" />
                    </div>
                  )}

                  <div>
                    <p className="text-sm font-semibold text-slate-900">{text.settings.profilePicture}</p>
                    <p className="mt-1 text-sm text-slate-500">{text.settings.profilePictureSubtitle}</p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-3 lg:justify-end">
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    onChange={handleAvatarUpload}
                    className="hidden"
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={avatarState === 'saving'}
                    className="inline-flex min-w-[148px] items-center justify-center gap-2 rounded-2xl bg-[#ef5b0c] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#dd5308] disabled:opacity-50"
                  >
                    <Upload className="h-4 w-4" />
                    {avatarState === 'saving' ? text.settings.uploading : user?.profile_image_url ? text.settings.editPicture : text.settings.uploadPicture}
                  </button>
                  {user?.profile_image_url ? (
                    <button
                      type="button"
                      onClick={() => void handleAvatarRemove()}
                      disabled={avatarState === 'saving'}
                      className="inline-flex min-w-[148px] items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-700 transition hover:border-rose-200 hover:bg-rose-50 hover:text-rose-700 disabled:opacity-50"
                    >
                      <X className="h-4 w-4" />
                      {text.settings.remove}
                    </button>
                  ) : null}
                </div>
              </div>

              {avatarState === 'saved' ? (
                <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                  {text.settings.pictureUpdated}
                </div>
              ) : null}

              {avatarState === 'removed' ? (
                <div className="mt-4 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
                  {text.settings.pictureRemoved}
                </div>
              ) : null}

              {avatarState === 'error' ? (
                <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                  {avatarError || text.settings.pictureError}
                </div>
              ) : null}
            </div>

            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">{text.settings.fullName}</span>
              <input
                value={fullName}
                readOnly
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900"
              />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">{text.settings.email}</span>
              <input
                value={user?.email || ''}
                readOnly
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900"
              />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">{text.settings.roleTitle}</span>
              <input
                value={roleLabel}
                readOnly
                className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-900"
              />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">{text.settings.organization}</span>
              <input
                value={organization}
                onChange={(event) => setOrganization(event.target.value)}
                placeholder="PwC"
                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-[#ef5b0c]/40"
              />
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">{text.settings.preferredLanguage}</span>
              <select
                value={localSettings.preferred_language}
                onChange={(event) => {
                  const nextLanguage = event.target.value as 'English' | 'French';
                  setLocalSettings((current) => ({ ...current, preferred_language: nextLanguage }));
                  setLanguage(nextLanguage);
                }}
                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-[#ef5b0c]/40"
              >
                <option>English</option>
                <option>French</option>
              </select>
            </label>
            <label className="space-y-2">
              <span className="text-sm font-medium text-slate-700">{text.settings.timeZone}</span>
              <select
                value={localSettings.time_zone}
                onChange={(event) => setLocalSettings((current) => ({ ...current, time_zone: event.target.value }))}
                className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 outline-none transition focus:border-[#ef5b0c]/40"
              >
                <option value="Africa/Tunis">Africa/Tunis</option>
                <option value="Europe/Paris">Europe/Paris</option>
                <option value="UTC">UTC</option>
                <option value="America/New_York">America/New_York</option>
              </select>
            </label>
          </div>

          {saveState === 'saved' ? (
            <div className="rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
              {text.settings.profileSaved}
            </div>
          ) : null}

          {saveState === 'error' ? (
            <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
              {text.settings.profileError}
            </div>
          ) : null}
        </section>

        <div className="space-y-6">
          <section className="pwc-main-panel space-y-6">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#fff7d9] text-[#b77900]">
                {localSettings.theme === 'dark' ? <MoonStar className="h-5 w-5" /> : <SunMedium className="h-5 w-5" />}
              </div>
              <div>
                <p className="pwc-kicker">{text.settings.appearance}</p>
                <h2 className="pwc-title mt-1 text-2xl font-semibold">{text.settings.theme}</h2>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              {(['light', 'dark'] as ThemePreference[]).map((theme) => (
                <button
                  key={theme}
                  type="button"
                  onClick={() => setLocalSettings((current) => ({ ...current, theme }))}
                  aria-pressed={localSettings.theme === theme}
                  className={`flex items-center justify-center gap-3 rounded-xl border px-5 py-3 text-sm font-semibold transition ${
                    localSettings.theme === theme
                      ? 'border-[#ef5b0c]/30 bg-[#fff3eb] text-[#c74634] shadow-[0_10px_22px_rgba(239,91,12,0.10)]'
                      : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300 hover:text-slate-900'
                  }`}
                >
                  {theme === 'light' ? <SunMedium className="h-5 w-5" /> : <MoonStar className="h-5 w-5" />}
                  <span>{theme === 'light' ? text.settings.light : text.settings.dark}</span>
                </button>
              ))}
            </div>
          </section>

          <section className="pwc-panel p-6">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
                <Globe2 className="h-5 w-5" />
              </div>
              <div>
                <p className="pwc-kicker">{text.settings.workspace}</p>
                <h2 className="pwc-title mt-1 text-2xl font-semibold">{text.settings.preferenceSummary}</h2>
              </div>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{text.settings.language}</p>
                <p className="mt-2 text-sm font-semibold text-slate-900">{localSettings.preferred_language}</p>
              </div>
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Time zone</p>
                <p className="mt-2 text-sm font-semibold text-slate-900">{localSettings.time_zone}</p>
              </div>
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{text.settings.themePreference}</p>
                <p className="mt-2 text-sm font-semibold capitalize text-slate-900">{localSettings.theme}</p>
              </div>
              <div className="rounded-2xl bg-slate-50 p-4">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{text.settings.security}</p>
                <div className="mt-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
                  <ShieldCheck className="h-4 w-4 text-[#ef5b0c]" />
                  {text.settings.entraSession}
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
