import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { SETTINGS_STORAGE_KEY } from '../utils/theme';

export type AppLanguage = 'English' | 'French';

type StoredSettings = {
  preferred_language?: string;
};

const LANGUAGE_EVENT = 'audit-it-language-change';

const messages = {
  English: {
    fullScreen: {
      secureWorkspace: 'Secure Workspace',
      loadingTitle: 'Loading secure workspace',
      loadingSubtitle: 'Checking your session and preparing the audit environment.'
    },
    sidebar: {
      productName: 'Audit IT Assistant',
      workspace: 'Mission workspace',
      dashboard: 'Mission Dashboard',
      observations: 'Observations',
      chat: 'Chat',
      report: 'Report',
      feedback: 'Feedback',
      settings: 'Settings',
      selectMission: 'Select mission',
      status: 'Status',
      noMissions: 'No missions available',
      authenticatedUser: 'Authenticated user',
      workspaceMember: 'Audit workspace member',
      signOut: 'Sign out'
    },
    login: {
      internalAccess: 'Internal access',
      titleLine1: 'Professional.',
      titleLine2: 'Focused.',
      titleLine3: 'Ready for audit.',
      subtitle: 'A cleaner, sharper workspace for secure audit delivery.',
      approvedUsersOnly: 'Approved users only',
      microsoftEntra: 'Microsoft Entra',
      protectedWorkspace: 'Protected workspace',
      authentication: 'Authentication',
      welcomeBack: 'Welcome back',
      signInToContinue: 'Sign in to continue.',
      authDisabled:
        'Entra authentication is disabled in the backend environment until the required variables are added.',
      signInWithMicrosoft: 'Sign in with Microsoft',
      useApprovedAccount: 'Use your approved organization account.'
    },
    settings: {
      kicker: 'Settings',
      title: 'Workspace settings',
      subtitle:
        'Manage your profile, choose your preferred theme, and prepare notification settings for the next platform release.',
      saveProfile: 'Save profile',
      saving: 'Saving...',
      profile: 'Profile',
      personalInformation: 'Personal information',
      profilePicture: 'Profile picture',
      profilePictureSubtitle: 'Upload, change, or remove your photo.',
      uploadPicture: 'Upload picture',
      editPicture: 'Edit picture',
      uploading: 'Uploading...',
      remove: 'Remove',
      pictureUpdated: 'Profile picture updated successfully.',
      pictureRemoved: 'Profile picture removed.',
      pictureError: 'Profile picture could not be updated right now.',
      fullName: 'Full name',
      email: 'Email',
      roleTitle: 'Role / title',
      organization: 'Organization',
      preferredLanguage: 'Preferred language',
      timeZone: 'Time zone',
      profileSaved: 'Profile settings saved.',
      profileError: 'Profile settings could not be saved right now.',
      appearance: 'Appearance',
      theme: 'Theme',
      light: 'Light',
      dark: 'Dark',
      lightDescription: 'Clean, presentation-ready interface for delivery teams.',
      darkDescription: 'Saved as your preferred mode for the upcoming dark theme rollout.',
      notifications: 'Notifications',
      preferences: 'Preferences',
      notificationsInfo:
        'Email delivery will use these preferences once backend notifications are connected. In-app browser alerts can already be tested here.',
      emailNotifications: 'Email notifications',
      inAppNotifications: 'In-app notifications',
      missionUpdates: 'Notify on mission updates',
      observationChanges: 'Notify on observation status changes',
      reportExports: 'Notify when reports are generated/exported',
      channels: 'Channels',
      activityTypes: 'Activity types',
      browserAlerts: 'Browser alerts',
      browserAlertsActive: 'Active',
      browserAlertsInactive: 'Inactive',
      browserAlertsUnsupported: 'Not supported',
      browserPermissionDenied: 'Browser notifications are blocked for this site.',
      browserPermissionUnavailable: 'This browser does not support desktop notifications.',
      browserPermissionDefault: 'Allow browser notifications to receive in-app alerts here.',
      browserPermissionGranted: 'Browser notifications are enabled for this workspace.',
      testNotification: 'Send test notification',
      testNotificationTitle: 'Audit IT Assistant',
      testNotificationBody: 'Your in-app notification preferences are active.',
      notificationSettingsSaved: 'Notification preferences updated.',
      enableChannelFirst: 'Enable at least one notification channel to manage activity alerts.',
      workspace: 'Workspace',
      preferenceSummary: 'Preference summary',
      language: 'Language',
      themePreference: 'Theme preference',
      security: 'Security',
      entraSession: 'Microsoft Entra session'
    },
    home: {
      kicker: 'Workspace',
      title: 'Mission dashboard',
      subtitle:
        'Structure the mission, load the source workbook, and move the engagement forward through to the report.',
      refresh: 'Refresh',
      refreshing: 'Refreshing...',
      missionSetup: 'Mission setup',
      missions: 'Missions',
      createFromExcel: 'Create from Excel',
      importing: 'Importing...',
      newMission: 'New mission',
      noMissions: 'No missions yet. Create one manually or import the source workbook directly.',
      activeMission: 'Mission active',
      period: 'Period',
      participants: 'Participants',
      lastUpdate: 'Last update',
      entities: 'Entities',
      applications: 'Applications',
      uploadWorkbook: 'Upload ITGC workbook',
      uploadWorkbookSubtitle: 'Load the source file to populate observations, controls, and the summary.',
      dropFile: 'Drop an `.xlsx` or `.xlsm` file here, or click to browse.',
      chooseFile: 'Choose file',
      uploading: 'Uploading...',
      latestUpload: 'Latest upload summary',
      parsedOn: 'Parsed on',
      noWorkbook: 'No workbook has been uploaded for this mission yet.',
      parsing: 'Parsing...',
      viewObservations: 'View observations',
      observations: 'Observations',
      nextBestAction: 'Next best action',
      workflow: 'Workflow',
      missionProgress: 'Mission progress',
      managerView: 'Manager view',
      openChat: 'Open chat',
      generateReport: 'Generate Report',
      deleteMission: 'Delete mission',
      deleteMissionTitle: 'Delete mission?',
      deleteMissionMessage:
        'This will permanently delete the mission and its observations, feedback, and cached report data.',
      cancel: 'Cancel',
      delete: 'Delete',
      deleting: 'Deleting...',
      noParticipants: 'No participants recorded',
      syncInProgress: 'Sync in progress...',
      backendUpToDate: 'Backend data is up to date'
    }
  },
  French: {
    fullScreen: {
      secureWorkspace: 'Espace securise',
      loadingTitle: 'Chargement de l espace securise',
      loadingSubtitle: 'Verification de votre session et preparation de l environnement d audit.'
    },
    sidebar: {
      productName: 'Audit IT Assistant',
      workspace: 'Espace mission',
      dashboard: 'Tableau de bord',
      observations: 'Observations',
      chat: 'Chat',
      report: 'Rapport',
      feedback: 'Feedback',
      settings: 'Parametres',
      selectMission: 'Selectionner une mission',
      status: 'Statut',
      noMissions: 'Aucune mission disponible',
      authenticatedUser: 'Utilisateur connecte',
      workspaceMember: 'Membre de l espace audit',
      signOut: 'Se deconnecter'
    },
    login: {
      internalAccess: 'Acces interne',
      titleLine1: 'Professionnel.',
      titleLine2: 'Clair.',
      titleLine3: 'Pret pour l audit.',
      subtitle: 'Un espace plus net et plus securise pour la delivery audit.',
      approvedUsersOnly: 'Utilisateurs autorises',
      microsoftEntra: 'Microsoft Entra',
      protectedWorkspace: 'Espace protege',
      authentication: 'Authentification',
      welcomeBack: 'Bon retour',
      signInToContinue: 'Connectez-vous pour continuer.',
      authDisabled:
        'L authentification Entra est desactivee dans l environnement backend tant que les variables requises ne sont pas configurees.',
      signInWithMicrosoft: 'Se connecter avec Microsoft',
      useApprovedAccount: 'Utilisez votre compte organisationnel autorise.'
    },
    settings: {
      kicker: 'Parametres',
      title: 'Parametres de l espace',
      subtitle:
        'Gerez votre profil, choisissez votre theme prefere et preparez vos preferences de notification.',
      saveProfile: 'Enregistrer le profil',
      saving: 'Enregistrement...',
      profile: 'Profil',
      personalInformation: 'Informations personnelles',
      profilePicture: 'Photo de profil',
      profilePictureSubtitle: 'Ajouter, modifier ou supprimer votre photo.',
      uploadPicture: 'Ajouter une photo',
      editPicture: 'Modifier la photo',
      uploading: 'Telechargement...',
      remove: 'Supprimer',
      pictureUpdated: 'Photo de profil mise a jour.',
      pictureRemoved: 'Photo de profil supprimee.',
      pictureError: 'La photo de profil n a pas pu etre mise a jour.',
      fullName: 'Nom complet',
      email: 'Email',
      roleTitle: 'Role / titre',
      organization: 'Organisation',
      preferredLanguage: 'Langue preferee',
      timeZone: 'Fuseau horaire',
      profileSaved: 'Parametres du profil enregistres.',
      profileError: 'Les parametres du profil n ont pas pu etre enregistres.',
      appearance: 'Apparence',
      theme: 'Theme',
      light: 'Clair',
      dark: 'Sombre',
      lightDescription: 'Interface claire et prete pour la presentation.',
      darkDescription: 'Enregistre comme theme prefere pour le futur mode sombre.',
      notifications: 'Notifications',
      preferences: 'Preferences',
      notificationsInfo:
        'L envoi par email utilisera ces preferences une fois le backend connecte. Les alertes navigateur peuvent deja etre testees ici.',
      emailNotifications: 'Notifications email',
      inAppNotifications: 'Notifications dans l application',
      missionUpdates: 'Notifier les mises a jour de mission',
      observationChanges: 'Notifier les changements de statut des observations',
      reportExports: 'Notifier lors de la generation ou export des rapports',
      channels: 'Canaux',
      activityTypes: 'Types d activite',
      browserAlerts: 'Alertes navigateur',
      browserAlertsActive: 'Actives',
      browserAlertsInactive: 'Inactives',
      browserAlertsUnsupported: 'Non prises en charge',
      browserPermissionDenied: 'Les notifications navigateur sont bloquees pour ce site.',
      browserPermissionUnavailable: 'Ce navigateur ne prend pas en charge les notifications desktop.',
      browserPermissionDefault: 'Autorisez les notifications navigateur pour recevoir les alertes ici.',
      browserPermissionGranted: 'Les notifications navigateur sont actives pour cet espace.',
      testNotification: 'Envoyer une notification test',
      testNotificationTitle: 'Audit IT Assistant',
      testNotificationBody: 'Vos preferences de notification dans l application sont actives.',
      notificationSettingsSaved: 'Preferences de notification mises a jour.',
      enableChannelFirst: 'Activez au moins un canal de notification pour gerer les alertes d activite.',
      workspace: 'Espace',
      preferenceSummary: 'Resume des preferences',
      language: 'Langue',
      themePreference: 'Preference de theme',
      security: 'Securite',
      entraSession: 'Session Microsoft Entra'
    },
    home: {
      kicker: 'Espace',
      title: 'Tableau de bord mission',
      subtitle:
        'Structurez la mission, chargez le classeur source et faites avancer le dossier jusqu au rapport.',
      refresh: 'Actualiser',
      refreshing: 'Actualisation...',
      missionSetup: 'Configuration mission',
      missions: 'Missions',
      createFromExcel: 'Creer depuis Excel',
      importing: 'Import...',
      newMission: 'Nouvelle mission',
      noMissions: 'Aucune mission pour le moment. Creez-en une ou importez directement le fichier source.',
      activeMission: 'Mission active',
      period: 'Periode',
      participants: 'Participants',
      lastUpdate: 'Derniere mise a jour',
      entities: 'Entites',
      applications: 'Applications',
      uploadWorkbook: 'Charger le workbook ITGC',
      uploadWorkbookSubtitle: 'Chargez le fichier source pour alimenter les observations, controles et la synthese.',
      dropFile: 'Deposez un fichier `.xlsx` ou `.xlsm` ici, ou cliquez pour parcourir.',
      chooseFile: 'Choisir un fichier',
      uploading: 'Chargement...',
      latestUpload: 'Dernier resume de chargement',
      parsedOn: 'Analyse le',
      noWorkbook: 'Aucun workbook n a encore ete charge pour cette mission.',
      parsing: 'Analyse...',
      viewObservations: 'Voir les observations',
      observations: 'Observations',
      nextBestAction: 'Prochaine meilleure action',
      workflow: 'Workflow',
      missionProgress: 'Progression de la mission',
      managerView: 'Vue manager',
      openChat: 'Ouvrir le chat',
      generateReport: 'Generer le rapport',
      deleteMission: 'Supprimer la mission',
      deleteMissionTitle: 'Supprimer la mission ?',
      deleteMissionMessage:
        'Cette action supprimera definitivement la mission ainsi que ses observations, feedbacks et donnees de rapport en cache.',
      cancel: 'Annuler',
      delete: 'Supprimer',
      deleting: 'Suppression...',
      noParticipants: 'Aucun participant enregistre',
      syncInProgress: 'Synchronisation en cours...',
      backendUpToDate: 'Les donnees backend sont a jour'
    }
  }
} as const;

function readStoredLanguage(): AppLanguage {
  if (typeof window === 'undefined') return 'English';
  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return 'English';
    const parsed = JSON.parse(raw) as StoredSettings;
    return parsed.preferred_language === 'French' ? 'French' : 'English';
  } catch {
    return 'English';
  }
}

type LanguageContextValue = {
  language: AppLanguage;
  setLanguage: (language: AppLanguage) => void;
  text: (typeof messages)[AppLanguage];
};

const LanguageContext = createContext<LanguageContextValue | undefined>(undefined);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<AppLanguage>(() => readStoredLanguage());

  useEffect(() => {
    const onStorage = () => setLanguageState(readStoredLanguage());
    window.addEventListener('storage', onStorage);
    window.addEventListener(LANGUAGE_EVENT, onStorage);
    return () => {
      window.removeEventListener('storage', onStorage);
      window.removeEventListener(LANGUAGE_EVENT, onStorage);
    };
  }, []);

  const setLanguage = (nextLanguage: AppLanguage) => {
    setLanguageState(nextLanguage);
    try {
      const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
      const parsed = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
      window.localStorage.setItem(
        SETTINGS_STORAGE_KEY,
        JSON.stringify({
          ...parsed,
          preferred_language: nextLanguage
        })
      );
      window.dispatchEvent(new Event(LANGUAGE_EVENT));
    } catch {
      window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify({ preferred_language: nextLanguage }));
      window.dispatchEvent(new Event(LANGUAGE_EVENT));
    }
  };

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      text: messages[language]
    }),
    [language]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const value = useContext(LanguageContext);
  if (!value) {
    throw new Error('useLanguage must be used inside LanguageProvider');
  }
  return value;
}
