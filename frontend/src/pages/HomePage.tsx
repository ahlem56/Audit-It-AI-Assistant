import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  CalendarRange,
  CheckCircle2,
  ChevronDown,
  Clock3,
  FileSpreadsheet,
  FolderOpen,
  Plus,
  Trash2,
  UploadCloud,
  UserPlus
} from 'lucide-react';
import { useAuthContext } from '../context/AuthContext';
import { useMissionContext } from '../context/MissionContext';
import { useLanguage } from '../context/LanguageContext';
import { downloadM365DriveItem, getM365DriveChildren, getM365MyDriveRoot } from '../services/api';
import type { CreateMissionPayload, M365DriveItem, MissionWorkflowStep } from '../types';

type MissionSetupProfile = {
  periodStart: string;
  periodEnd: string;
  missionType: string;
  manager: string;
  senior: string;
  teamMembers: string[];
  entities: string[];
  applications: string[];
};

type MissionSetupDraft = CreateMissionPayload & {
  periodStart: string;
  periodEnd: string;
  missionType: string;
  manager: string;
  senior: string;
  teamMembers: string[];
  teamMemberInput: string;
  entitiesInput: string;
  applicationsInput: string;
};

const PROFILE_STORAGE_KEY = 'mission-setup-profiles';

const emptyDraft = (): MissionSetupDraft => ({
  name: '',
  client: '',
  fiscal_year: '',
  periodStart: '',
  periodEnd: '',
  missionType: 'ITGC',
  manager: '',
  senior: '',
  teamMembers: [],
  teamMemberInput: '',
  entitiesInput: '',
  applicationsInput: ''
});

const readProfiles = (): Record<string, MissionSetupProfile> => {
  try {
    const raw = window.localStorage.getItem(PROFILE_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Record<string, MissionSetupProfile>) : {};
  } catch {
    return {};
  }
};

const toList = (value: string) =>
  value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);

const formatDateTime = (value?: string) => {
  if (!value) return 'Not available';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-US', {
    dateStyle: 'short',
    timeStyle: 'short'
  }).format(date);
};

const formatMissionPeriod = (start?: string, end?: string) => {
  if (!start && !end) return 'To be defined';
  if (start && end) return `${start} -> ${end}`;
  return start || end || 'To be defined';
};

const isSupportedM365Workbook = (item: M365DriveItem) => {
  const name = item.name.toLowerCase();
  return Boolean(item.file) && (name.endsWith('.xlsx') || name.endsWith('.xlsm'));
};

const formatFileSize = (size?: number) => {
  if (!size || size <= 0) return 'Size unavailable';
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
};

export default function HomePage() {
  const { text } = useLanguage();
  const { user } = useAuthContext();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const excelInputRef = useRef<HTMLInputElement>(null);
  const {
    missions,
    activeMissionId,
    activeMission,
    loadingMissions,
    loadingMission,
    uploadState,
    observations,
    parsedMission,
    setActiveMissionId,
    createNewMission,
    createMissionFromExcel,
    deleteExistingMission,
    inviteAuditor,
    uploadExcel,
    importM365DriveItem,
    regenerateReportPreview,
    loadMissions
  } = useMissionContext();
  const canManageMissions = user?.role === 'manager';

  const [formOpen, setFormOpen] = useState(false);
  const [formStep, setFormStep] = useState(1);
  const [submittingMission, setSubmittingMission] = useState(false);
  const [creatingFromExcel, setCreatingFromExcel] = useState(false);
  const [uploadHighlight, setUploadHighlight] = useState(false);
  const [profiles, setProfiles] = useState<Record<string, MissionSetupProfile>>(() => readProfiles());
  const [draft, setDraft] = useState<MissionSetupDraft>(() => emptyDraft());
  const [missionToDelete, setMissionToDelete] = useState<string | null>(null);
  const [deletingMission, setDeletingMission] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [inviteEmail, setInviteEmail] = useState('');
  const [invitingAuditor, setInvitingAuditor] = useState(false);
  const [generatingReport, setGeneratingReport] = useState(false);
  const [inviteMessage, setInviteMessage] = useState<string | null>(null);
  const [m365Open, setM365Open] = useState(false);
  const [m365Loading, setM365Loading] = useState(false);
  const [m365ImportingId, setM365ImportingId] = useState<string | null>(null);
  const [m365Items, setM365Items] = useState<M365DriveItem[]>([]);
  const [m365Error, setM365Error] = useState<string | null>(null);
  const [m365Mode, setM365Mode] = useState<'create' | 'upload'>('upload');
  const [m365FolderStack, setM365FolderStack] = useState<M365DriveItem[]>([]);
  const [createExcelMenuOpen, setCreateExcelMenuOpen] = useState(false);

  useEffect(() => {
    window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profiles));
  }, [profiles]);

  useEffect(() => {
    if (!createExcelMenuOpen) return;

    const closeMenu = () => setCreateExcelMenuOpen(false);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeMenu();
    };

    window.addEventListener('click', closeMenu);
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('click', closeMenu);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [createExcelMenuOpen]);

  const activeProfile = activeMission ? profiles[activeMission.mission_id] : undefined;
  const hasUploadedWorkbook = Boolean(
    activeMission?.current_file?.name ||
      (activeMission?.parsing_status === 'parsed' && ((activeMission?.observations_count ?? 0) > 0 || observations.length > 0))
  );
  const hasObservations = (activeMission?.observations_count ?? observations.length) > 0;
  const activeDisplayTitle = parsedMission?.titre_mission || activeMission?.name || '';
  const activeDisplayClient = parsedMission?.entite_auditee || activeMission?.client || '';
  const activeDisplayPeriod = parsedMission?.periode || formatMissionPeriod(activeProfile?.periodStart, activeProfile?.periodEnd);
  const activeDisplayType = parsedMission?.type_mission || activeProfile?.missionType || 'Type to be confirmed by the workbook';
  const activeDisplayIntervenants = useMemo(() => {
    const profileIntervenants = [activeProfile?.manager, activeProfile?.senior, ...(activeProfile?.teamMembers ?? [])]
      .map((value) => value?.trim())
      .filter((value): value is string => Boolean(value));

    if (profileIntervenants.length > 0) return profileIntervenants;
    return (parsedMission?.intervenants ?? []).filter(Boolean);
  }, [activeProfile?.manager, activeProfile?.senior, activeProfile?.teamMembers, parsedMission?.intervenants]);
  const activeDisplayEntities =
    activeProfile?.entities.length
      ? activeProfile.entities
      : parsedMission?.entite_auditee
      ? [parsedMission.entite_auditee]
      : [];
  const activeDisplayApplications =
    activeProfile?.applications.length ? activeProfile.applications : parsedMission?.applications ?? [];

  const stats = useMemo(() => {
    if (!activeMission) {
      return { observations: 0, applications: 0, controls: 0 };
    }

    const scopedApplications = new Set(
      activeDisplayApplications
        .map((application) => application.trim())
        .filter((application): application is string => Boolean(application))
    );

    const fallbackApplications = new Set(
      observations
        .map((observation) => observation.application?.trim())
        .filter((application): application is string => Boolean(application))
    );

    const fallbackControls = new Set(
      observations
        .map((observation) => (observation.controle_ref || observation.control_id)?.trim())
        .filter((controlId): controlId is string => Boolean(controlId))
    );

    return {
      observations: activeMission.observations_count ?? observations.length,
      applications: scopedApplications.size || activeMission.applications_count || fallbackApplications.size,
      controls: activeMission.control_ids_count ?? fallbackControls.size
    };
  }, [activeDisplayApplications, activeMission, observations]);

  const progressSteps = useMemo<MissionWorkflowStep[]>(() => {
    if (activeMission?.workflow?.steps?.length) {
      return activeMission.workflow.steps;
    }

    return [
      {
        key: 'mission_created',
        label: 'Create mission',
        state: activeMission ? 'completed' : 'in_progress',
        status_label: activeMission ? 'Completed' : 'In progress',
        description: activeMission
          ? 'Mission workspace is created and ready for source documents.'
          : 'Create a mission to begin the workflow.'
      },
      {
        key: 'workbook_uploaded',
        label: 'Upload Excel',
        state: hasUploadedWorkbook ? 'completed' : 'coming_next',
        status_label: hasUploadedWorkbook ? 'Completed' : 'Coming next',
        description: hasUploadedWorkbook
          ? 'Workbook uploaded and parsed successfully.'
          : 'Upload the ITGC workbook to populate the mission data.'
      },
      {
        key: 'observations_validated',
        label: 'Validate observations',
        state: hasObservations ? 'in_progress' : 'coming_next',
        status_label: hasObservations ? 'In progress' : 'Coming next',
        description: hasObservations
          ? 'Review the observations and validate them before report generation.'
          : 'Validation starts once observations are loaded from the workbook.'
      },
      {
        key: 'report_generated',
        label: 'Generate report',
        state: 'coming_next',
        status_label: 'Coming next',
        description: 'Generate the report draft after reviewing observations.'
      },
      {
        key: 'pptx_exported',
        label: 'Export PPTX',
        state: 'coming_next',
        status_label: 'Coming next',
        description: 'Export the final PowerPoint deliverable.'
      }
    ];
  }, [activeMission, hasObservations, hasUploadedWorkbook]);

  const nextBestAction = activeMission?.workflow?.next_best_action
    ? activeMission.workflow.next_best_action
    : !hasUploadedWorkbook
    ? 'The workspace is ready. Upload the workbook now to hydrate the observations and move the mission to Ready.'
    : !hasObservations
    ? 'The file is present, but the mission does not yet contain usable observations. Review the parsing and retry if needed.'
    : 'The observations are available. The natural next step is validation review, followed by report generation.';

  const statusStyle = useMemo(() => {
    if (!activeMission) return 'bg-slate-100 text-slate-700';
    if (activeMission.status === 'Draft') return 'bg-slate-100 text-slate-700';
    if (activeMission.status === 'Ready') return 'bg-emerald-100 text-emerald-800';
    return 'bg-sky-100 text-sky-800';
  }, [activeMission]);

  const canGoNext =
    draft.name.trim() &&
    draft.client.trim() &&
    draft.fiscal_year.trim() &&
    draft.periodStart &&
    draft.periodEnd &&
    draft.missionType.trim();

  const handleAddTeamMember = () => {
    const member = draft.teamMemberInput.trim();
    if (!member) return;
    setDraft((current) => ({
      ...current,
      teamMembers: [...current.teamMembers, member],
      teamMemberInput: ''
    }));
  };

  const handleRemoveTeamMember = (index: number) => {
    setDraft((current) => ({
      ...current,
      teamMembers: current.teamMembers.filter((_, memberIndex) => memberIndex !== index)
    }));
  };

  const resetForm = () => {
    setDraft(emptyDraft());
    setFormStep(1);
    setFormOpen(false);
  };

  const handleCreateMission = async () => {
    if (!canManageMissions || !canGoNext || !draft.manager.trim() || !draft.senior.trim()) return;

    setSubmittingMission(true);
    try {
      const mission = await createNewMission({
        name: draft.name.trim(),
        client: draft.client.trim(),
        fiscal_year: draft.fiscal_year.trim()
      });

      setProfiles((current) => ({
        ...current,
        [mission.mission_id]: {
          periodStart: draft.periodStart,
          periodEnd: draft.periodEnd,
          missionType: draft.missionType,
          manager: draft.manager.trim(),
          senior: draft.senior.trim(),
          teamMembers: draft.teamMembers,
          entities: toList(draft.entitiesInput),
          applications: toList(draft.applicationsInput)
        }
      }));

      setActiveMissionId(mission.mission_id);
      resetForm();
      setUploadHighlight(true);
    } catch (error) {
      console.error('Failed to create mission:', error);
    } finally {
      setSubmittingMission(false);
    }
  };

  const handleCreateFromExcel = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!canManageMissions) {
      event.target.value = '';
      return;
    }

    setCreatingFromExcel(true);
    try {
      const mission = await createMissionFromExcel(file);
      setActiveMissionId(mission.mission_id);
      setUploadHighlight(false);
    } catch (error) {
      console.error('Failed to create mission from Excel:', error);
      alert(error instanceof Error ? error.message : 'Failed to create mission from Excel');
    } finally {
      setCreatingFromExcel(false);
      event.target.value = '';
    }
  };

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      await uploadExcel(file);
      setUploadHighlight(false);
    } catch (error) {
      console.error('Upload failed:', error);
    } finally {
      event.target.value = '';
    }
  };

  const openM365Picker = async (mode: 'create' | 'upload') => {
    if (!canManageMissions) return;
    if (mode === 'upload' && !activeMission) return;
    setM365Mode(mode);
    setM365Open(true);
    setM365Loading(true);
    setM365Error(null);
    setM365FolderStack([]);
    try {
      const items = await getM365MyDriveRoot();
      setM365Items(items);
    } catch (error) {
      setM365Error(error instanceof Error ? error.message : 'Unable to load Microsoft 365 files.');
      setM365Items([]);
    } finally {
      setM365Loading(false);
    }
  };

  const loadM365Root = async () => {
    setM365Loading(true);
    setM365Error(null);
    try {
      const items = await getM365MyDriveRoot();
      setM365FolderStack([]);
      setM365Items(items);
    } catch (error) {
      setM365Error(error instanceof Error ? error.message : 'Unable to load Microsoft 365 files.');
    } finally {
      setM365Loading(false);
    }
  };

  const openM365Folder = async (folder: M365DriveItem) => {
    const driveId = folder.parentReference?.driveId;
    if (!driveId || !folder.folder) return;
    setM365Loading(true);
    setM365Error(null);
    try {
      const items = await getM365DriveChildren(driveId, folder.id);
      setM365FolderStack((current) => [...current, folder]);
      setM365Items(items);
    } catch (error) {
      setM365Error(error instanceof Error ? error.message : 'Unable to open this Microsoft 365 folder.');
    } finally {
      setM365Loading(false);
    }
  };

  const goBackM365Folder = async () => {
    if (m365FolderStack.length <= 1) {
      await loadM365Root();
      return;
    }

    const parentStack = m365FolderStack.slice(0, -1);
    const parent = parentStack[parentStack.length - 1];
    const driveId = parent.parentReference?.driveId;
    if (!driveId) return;

    setM365Loading(true);
    setM365Error(null);
    try {
      const items = await getM365DriveChildren(driveId, parent.id);
      setM365FolderStack(parentStack);
      setM365Items(items);
    } catch (error) {
      setM365Error(error instanceof Error ? error.message : 'Unable to go back in Microsoft 365 folders.');
    } finally {
      setM365Loading(false);
    }
  };

  const handleM365Import = async (item: M365DriveItem) => {
    if (!isSupportedM365Workbook(item)) return;
    setM365ImportingId(item.id);
    setM365Error(null);
    try {
      if (m365Mode === 'create') {
        const file = await downloadM365DriveItem(item);
        const mission = await createMissionFromExcel(file);
        setActiveMissionId(mission.mission_id);
      } else {
        await importM365DriveItem(item);
      }
      setUploadHighlight(false);
      setM365Open(false);
    } catch (error) {
      setM365Error(error instanceof Error ? error.message : 'Microsoft 365 import failed.');
    } finally {
      setM365ImportingId(null);
    }
  };

  const handleDeleteMission = async () => {
    if (!missionToDelete || !canManageMissions) return;

    setDeletingMission(true);
    setDeleteError(null);
    try {
      await deleteExistingMission(missionToDelete);
      setProfiles((current) => {
        const next = { ...current };
        delete next[missionToDelete];
        return next;
      });
      setMissionToDelete(null);
      setUploadHighlight(false);
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : 'Failed to delete mission.');
    } finally {
      setDeletingMission(false);
    }
  };

  const handleInviteAuditor = async () => {
    const email = inviteEmail.trim();
    if (!activeMission || !email || !canManageMissions) return;

    setInvitingAuditor(true);
    setInviteMessage(null);
    try {
      await inviteAuditor(activeMission.mission_id, email);
      setInviteEmail('');
      setInviteMessage(`Auditor invited: ${email.toLowerCase()}`);
    } catch (error) {
      setInviteMessage(error instanceof Error ? error.message : 'Failed to invite auditor.');
    } finally {
      setInvitingAuditor(false);
    }
  };

  const handleGenerateReport = async () => {
    if (!activeMission || generatingReport) return;

    setGeneratingReport(true);
    try {
      await regenerateReportPreview();
      navigate('/report');
    } catch (error) {
      console.error('Failed to generate report:', error);
      alert(error instanceof Error ? error.message : 'Failed to generate report.');
    } finally {
      setGeneratingReport(false);
    }
  };

  return (
    <>
      <div className="mission-studio space-y-6">
      <section className="mission-studio-hero">
        <div className="mission-studio-brand">
          <span>{text.home.kicker}</span>
          <strong>{activeMission?.client || 'Mission workspace'} / {activeMission?.fiscal_year || 'FY setup'}</strong>
        </div>

        <div className="mission-studio-command">
          <div>
            <h1>{text.home.title}</h1>
            <p>{text.home.subtitle}</p>
          </div>
        </div>

        <div className="mission-studio-hero-footer">
          <span>Active mission: {activeMission?.name || 'none selected'}</span>
          <button
            onClick={loadMissions}
            disabled={loadingMissions}
          >
            <FolderOpen className="h-4 w-4" /> {loadingMissions ? text.home.refreshing : text.home.refresh}
          </button>
        </div>
      </section>

      <input
        ref={excelInputRef}
        type="file"
        accept=".xlsx,.xlsm"
        onChange={handleCreateFromExcel}
        className="hidden"
      />
      <input
        ref={fileInputRef}
        type="file"
        accept=".xlsx,.xlsm"
        onChange={handleFileUpload}
        className="hidden"
      />

      <section className="pwc-main-panel">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="pwc-kicker">{text.home.missionSetup}</p>
            <h2 className="pwc-title mt-3 text-3xl font-semibold">{text.home.missions}</h2>
          </div>
          {canManageMissions ? (
          <div className="mission-toolbar-actions flex flex-wrap gap-2">
            <div className="relative">
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  setCreateExcelMenuOpen((current) => !current);
                }}
                disabled={creatingFromExcel}
                className="mission-toolbar-button mission-toolbar-button-secondary disabled:opacity-50"
              >
                <FileSpreadsheet className="h-4 w-4" />
                {creatingFromExcel ? text.home.importing : text.home.createFromExcel}
                <ChevronDown className="mission-toolbar-chevron h-4 w-4" />
              </button>
              {createExcelMenuOpen && (
                <div className="mission-create-menu absolute right-0 z-30 mt-2 w-72 overflow-hidden border bg-white p-1.5">
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      setCreateExcelMenuOpen(false);
                      excelInputRef.current?.click();
                    }}
                    className="mission-create-menu-item flex w-full items-start gap-3 px-3 py-3 text-left"
                  >
                    <FileSpreadsheet className="mt-0.5 h-4 w-4 text-slate-600" />
                    <span>
                      <span className="block text-sm font-semibold text-slate-900">Local workbook</span>
                      <span className="mt-1 block text-xs leading-5 text-slate-500">Select an Excel file from this computer.</span>
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.stopPropagation();
                      setCreateExcelMenuOpen(false);
                      void openM365Picker('create');
                    }}
                    className="mission-create-menu-item flex w-full items-start gap-3 px-3 py-3 text-left"
                  >
                    <FolderOpen className="mt-0.5 h-4 w-4 text-slate-600" />
                    <span>
                      <span className="block text-sm font-semibold text-slate-900">Microsoft 365</span>
                      <span className="mt-1 block text-xs leading-5 text-slate-500">Choose a workbook from OneDrive.</span>
                    </span>
                  </button>
                </div>
              )}
            </div>
            <button
              onClick={() => {
                setCreateExcelMenuOpen(false);
                setFormOpen((current) => !current);
                setFormStep(1);
              }}
              className="mission-toolbar-button mission-toolbar-button-primary"
            >
              <Plus className="h-4 w-4" /> {text.home.newMission}
            </button>
          </div>
          ) : (
            <p className="max-w-md rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
              Auditor access: you can work on missions where a manager invited you, but mission creation and deletion are reserved for managers.
            </p>
          )}
        </div>

        {formOpen && canManageMissions && (
          <div className="mb-8 rounded-[2rem] border border-white/70 bg-white/60 p-6 backdrop-blur">
            <div className="mb-6 flex items-center gap-3">
              {[1, 2].map((step) => (
                <div key={step} className="flex items-center gap-3">
                  <div
                    className={`flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold ${
                      formStep === step ? 'bg-slate-900 text-white' : 'bg-white text-slate-500 ring-1 ring-slate-200'
                    }`}
                  >
                    {step}
                  </div>
                  <span className={`text-sm ${formStep === step ? 'font-semibold text-slate-900' : 'text-slate-500'}`}>
                    {step === 1 ? 'General information' : 'Participants and scope'}
                  </span>
                </div>
              ))}
            </div>

            {formStep === 1 ? (
              <div className="grid gap-4 lg:grid-cols-2">
                <label className="space-y-2">
                  <span className="text-sm font-medium text-slate-700">Mission name</span>
                  <input
                    value={draft.name}
                    onChange={(event) => setDraft((current) => ({ ...current, name: event.target.value }))}
                    placeholder="Audit ITGC - Revue FY2025"
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-slate-400"
                  />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-medium text-slate-700">Client name</span>
                  <input
                    value={draft.client}
                    onChange={(event) => setDraft((current) => ({ ...current, client: event.target.value }))}
                    placeholder="Zitouna Banque"
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-slate-400"
                  />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-medium text-slate-700">Fiscal year</span>
                  <input
                    value={draft.fiscal_year}
                    onChange={(event) => setDraft((current) => ({ ...current, fiscal_year: event.target.value }))}
                    placeholder="FY25"
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-slate-400"
                  />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-medium text-slate-700">Mission type</span>
                  <select
                    value={draft.missionType}
                    onChange={(event) => setDraft((current) => ({ ...current, missionType: event.target.value }))}
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-slate-400"
                  >
                    <option value="ITGC">ITGC</option>
                    <option value="IT General Controls">IT General Controls</option>
                  </select>
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-medium text-slate-700">Audit period - start</span>
                  <input
                    type="date"
                    value={draft.periodStart}
                    onChange={(event) => setDraft((current) => ({ ...current, periodStart: event.target.value }))}
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-slate-400"
                  />
                </label>
                <label className="space-y-2">
                  <span className="text-sm font-medium text-slate-700">Audit period - end</span>
                  <input
                    type="date"
                    value={draft.periodEnd}
                    onChange={(event) => setDraft((current) => ({ ...current, periodEnd: event.target.value }))}
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-slate-400"
                  />
                </label>
              </div>
            ) : (
              <div className="grid gap-6 lg:grid-cols-2">
                <div className="space-y-4">
                  <label className="space-y-2">
                    <span className="text-sm font-medium text-slate-700">Manager</span>
                    <input
                      value={draft.manager}
                      onChange={(event) => setDraft((current) => ({ ...current, manager: event.target.value }))}
                      placeholder="Manager name"
                      className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-slate-400"
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-sm font-medium text-slate-700">Senior</span>
                    <input
                      value={draft.senior}
                      onChange={(event) => setDraft((current) => ({ ...current, senior: event.target.value }))}
                      placeholder="Senior name"
                      className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-slate-400"
                    />
                  </label>
                  <div className="space-y-2">
                    <span className="text-sm font-medium text-slate-700">Team</span>
                    <div className="flex gap-3">
                      <input
                        value={draft.teamMemberInput}
                        onChange={(event) => setDraft((current) => ({ ...current, teamMemberInput: event.target.value }))}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault();
                            handleAddTeamMember();
                          }
                        }}
                        placeholder="Add a team member"
                        className="flex-1 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-slate-400"
                      />
                      <button
                        type="button"
                        onClick={handleAddTeamMember}
                        className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                      >
                        + Add
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {draft.teamMembers.map((member, index) => (
                        <button
                          key={`${member}-${index}`}
                          type="button"
                          onClick={() => handleRemoveTeamMember(index)}
                          className="rounded-full bg-slate-900 px-3 py-1 text-xs font-medium text-white"
                        >
                          {member} x
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  <label className="space-y-2">
                    <span className="text-sm font-medium text-slate-700">Audited entities</span>
                    <textarea
                      rows={4}
                      value={draft.entitiesInput}
                      onChange={(event) => setDraft((current) => ({ ...current, entitiesInput: event.target.value }))}
                      placeholder="One entity per line"
                      className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-slate-400"
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-sm font-medium text-slate-700">Applications in scope</span>
                    <textarea
                      rows={4}
                      value={draft.applicationsInput}
                      onChange={(event) => setDraft((current) => ({ ...current, applicationsInput: event.target.value }))}
                      placeholder="One application per line"
                      className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm outline-none transition focus:border-slate-400"
                    />
                  </label>
                  <p className="rounded-2xl bg-white px-4 py-3 text-xs leading-6 text-slate-500 ring-1 ring-slate-200">
                    These advanced fields help structure the frontend workspace. Today the backend mainly saves
                    `name`, `client_name`, and `fiscal_year`, then completes the rest through Excel upload.
                  </p>
                </div>
              </div>
            )}

            <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
              <button
                onClick={resetForm}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <div className="flex gap-3">
                {formStep === 2 && (
                  <button
                    onClick={() => setFormStep(1)}
                    className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    Back
                  </button>
                )}
                {formStep === 1 ? (
                  <button
                    onClick={() => setFormStep(2)}
                    disabled={!canGoNext}
                    className="rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                  >
                    Next step
                  </button>
                ) : (
                  <button
                    onClick={handleCreateMission}
                    disabled={submittingMission}
                    className="rounded-2xl bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-red-300"
                  >
                    {submittingMission ? 'Creating...' : 'Create mission'}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        <div className="grid gap-4 xl:grid-cols-2">
          {missions.map((mission) => (
            <div
              key={mission.mission_id}
              className={`mission-studio-mission-card rounded-[1.75rem] border p-5 text-left transition ${
                    activeMissionId === mission.mission_id
                  ? 'border-[#ef5b0c]/25 bg-[#fff3eb] shadow-[0_16px_30px_rgba(239,91,12,0.10)]'
                  : 'border-slate-200 bg-white/88 hover:border-[#ef5b0c]/25 hover:bg-white'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <button
                    type="button"
                    onClick={() => {
                      setActiveMissionId(mission.mission_id);
                      setUploadHighlight(false);
                    }}
                    className="text-left"
                  >
                    <p className="text-lg font-semibold text-slate-900">{mission.name}</p>
                  </button>
                  <p className="mt-1 text-sm text-slate-500">
                    {mission.client} - {mission.fiscal_year}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${
                      mission.status === 'Draft'
                        ? 'bg-slate-100 text-slate-700'
                        : mission.status === 'Ready'
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-rose-100 text-rose-700'
                    }`}
                  >
                    {mission.status}
                  </span>
                  {canManageMissions && (
                  <button
                    type="button"
                    onClick={() => {
                      setDeleteError(null);
                      setMissionToDelete(mission.mission_id);
                    }}
                    className="rounded-2xl border border-red-200 bg-red-50 p-2 text-red-700 hover:bg-red-100"
                    aria-label={`Delete mission ${mission.name}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>

        {missions.length === 0 && !loadingMissions && (
          <div className="rounded-[1.75rem] border border-dashed border-slate-300 bg-slate-50 p-10 text-center text-slate-500">
            {text.home.noMissions}
          </div>
        )}
      </section>

      {activeMission && (
        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <section className="space-y-6">
            <div className="pwc-main-panel">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="pwc-kicker">{text.home.activeMission}</p>
                  <h2 className="pwc-title mt-3 text-4xl font-semibold">{activeDisplayTitle}</h2>
                  <p className="mt-2 text-sm text-slate-500">{activeDisplayClient}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`rounded-full px-3 py-1 text-sm font-semibold ${statusStyle}`}>{activeMission.status}</span>
                  {canManageMissions && (
                  <button
                    type="button"
                    onClick={() => {
                      setDeleteError(null);
                      setMissionToDelete(activeMission.mission_id);
                    }}
                    className="inline-flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-100"
                  >
                      <Trash2 className="h-4 w-4" /> {text.home.deleteMission}
                    </button>
                  )}
                </div>
              </div>

              {canManageMissions && (
                <div className="mt-6 rounded-3xl bg-slate-50 p-5">
                  <div className="flex flex-wrap items-end gap-3">
                    <label className="min-w-[260px] flex-1 space-y-2">
                      <span className="text-sm font-semibold text-slate-700">Invite auditor to this mission</span>
                      <input
                        type="email"
                        value={inviteEmail}
                        onChange={(event) => setInviteEmail(event.target.value)}
                        placeholder="auditor@example.com"
                        className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => void handleInviteAuditor()}
                      disabled={invitingAuditor || !inviteEmail.trim()}
                      className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                    >
                      <UserPlus className="h-4 w-4" />
                      {invitingAuditor ? 'Inviting...' : 'Invite'}
                    </button>
                  </div>
                  {activeMission.invited_auditor_emails.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-2">
                      {activeMission.invited_auditor_emails.map((email) => (
                        <span key={email} className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600 ring-1 ring-slate-200">
                          {email}
                        </span>
                      ))}
                    </div>
                  )}
                  {inviteMessage && <p className="mt-3 text-sm text-slate-600">{inviteMessage}</p>}
                </div>
              )}

              <div className="mt-8 grid gap-4 sm:grid-cols-2">
                <div className="rounded-3xl bg-slate-50 p-5">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Mission ID</p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">{activeMission.mission_id}</p>
                </div>
                <div className="rounded-3xl bg-slate-50 p-5">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{text.home.period}</p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">
                    {activeDisplayPeriod}
                  </p>
                </div>
                <div className="rounded-3xl bg-slate-50 p-5">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{text.home.participants}</p>
                  <div className="mt-2 space-y-1">
                    {activeDisplayIntervenants.length > 0 ? (
                      activeDisplayIntervenants.map((intervenant) => (
                        <p key={intervenant} className="text-sm text-slate-700">
                          {intervenant}
                        </p>
                      ))
                    ) : (
                      <p className="text-sm text-slate-500">{text.home.noParticipants}</p>
                    )}
                  </div>
                </div>
                <div className="rounded-3xl bg-slate-50 p-5">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-400">{text.home.lastUpdate}</p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">{formatDateTime(activeMission.updated_at)}</p>
                  <p className="mt-1 text-xs text-slate-500">{loadingMission ? text.home.syncInProgress : text.home.backendUpToDate}</p>
                </div>
              </div>

              {(activeDisplayApplications.length || activeDisplayEntities.length) && (
                <div className="mt-6 grid gap-4 lg:grid-cols-3">
                 
                  <div className="rounded-3xl border border-slate-200 p-4">
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                      <CalendarRange className="h-4 w-4 text-slate-500" /> {text.home.entities}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {activeDisplayEntities.map((entity) => (
                        <span key={entity} className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">
                          {entity}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-3xl border border-slate-200 p-4">
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                      <FileSpreadsheet className="h-4 w-4 text-slate-500" /> {text.home.applications}
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {activeDisplayApplications.map((application) => (
                        <span key={application} className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">
                          {application}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </div>

          </section>

          <section className="space-y-6">
            <div
              className={`pwc-main-panel transition ${
                uploadHighlight ? 'border-red-300 ring-4 ring-red-100' : 'border-slate-200'
              }`}
            >
              <div className="flex items-center gap-3 text-slate-700">
                <UploadCloud className="h-5 w-5 text-slate-500" />
                <div>
                  <p className="text-sm font-semibold text-slate-900">{text.home.uploadWorkbook}</p>
                  <p className="text-sm text-slate-500">{text.home.uploadWorkbookSubtitle}</p>
                </div>
              </div>

              <div className="mt-6 rounded-[1.75rem] border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
                <p className="text-sm text-slate-500">{text.home.dropFile}</p>
                <div className="mt-6 flex flex-wrap justify-center gap-3">
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadState.uploading}
                    className="pwc-action-dark disabled:opacity-50"
                  >
                    {uploadState.uploading ? text.home.uploading : text.home.chooseFile}
                  </button>
                  <button
                    type="button"
                    onClick={() => void openM365Picker('upload')}
                    disabled={uploadState.uploading}
                    className="pwc-action-primary disabled:opacity-50"
                  >
                    <FolderOpen className="h-4 w-4" />
                    Import from Microsoft 365
                  </button>
                </div>
                {uploadHighlight && (
                  <p className="mt-4 text-xs font-medium text-red-600">
                    The mission is created. Next step: upload the workbook to move the mission to `Ready`.
                  </p>
                )}
              </div>

              <div className="mt-6 rounded-[1.75rem] border border-slate-200 bg-slate-50 p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">{text.home.latestUpload}</p>
                    {activeMission.current_file ? (
                      <>
                        <div className="mt-3 flex items-center gap-2 text-sm font-medium text-slate-900">
                          <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                          <span>{activeMission.current_file.name}</span>
                        </div>
                        <p className="mt-2 text-sm text-slate-600">
                          {stats.observations} observations - {stats.applications} applications - {stats.controls} controls
                        </p>
                        <p className="mt-1 text-sm text-slate-500">
                          {text.home.parsedOn} {formatDateTime(activeMission.updated_at)}
                        </p>
                      </>
                    ) : (
                      <p className="mt-3 text-sm text-slate-500">{text.home.noWorkbook}</p>
                    )}
                  </div>

                  {uploadState.uploading && (
                    <div className="flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                      <span className="h-2 w-2 animate-pulse rounded-full bg-slate-500" />
                      {text.home.parsing}
                    </div>
                  )}
                </div>

                {uploadState.error && (
                  <div className="mt-4 flex items-center gap-2 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">
                    <AlertTriangle className="h-4 w-4" />
                    {uploadState.error}
                  </div>
                )}

                {activeMission.current_file && (
                  <button
                    type="button"
                    onClick={() => navigate('/observations')}
                    className="mt-5 inline-flex items-center gap-2 rounded-2xl bg-white px-4 py-3 text-sm font-semibold text-slate-900 ring-1 ring-slate-200 hover:bg-slate-100"
                  >
                    {text.home.viewObservations} <ArrowRight className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="pwc-panel p-5">
                <p className="text-sm text-slate-500">{text.home.observations}</p>
                <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.observations}</p>
              </div>
              <div className="pwc-panel p-5">
                <p className="text-sm text-slate-500">{text.home.applications}</p>
                <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.applications}</p>
              </div>
            
            </div>

            <div className="pwc-panel p-6">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Clock3 className="h-4 w-4 text-slate-500" /> {text.home.nextBestAction}
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">{nextBestAction}</p>
            </div>
          </section>
        </div>
      )}

      {activeMission && (
        <section className="pwc-main-panel">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm uppercase tracking-[0.2em] text-slate-400">{text.home.workflow}</p>
              <h3 className="mt-2 text-xl font-semibold text-slate-900">{text.home.missionProgress}</h3>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
              {text.home.managerView}
            </span>
          </div>

          <div className="rounded-[1.5rem] border border-slate-200 bg-white/70 px-5 py-6">
            <div className="grid gap-4 lg:grid-cols-5">
            {progressSteps.map((step, index) => {
              const isCompleted = step.state === 'completed';
              const isCurrent = step.state === 'in_progress';
              const stepStateLabel = step.status_label;

              return (
                <div key={step.key} className="relative">
                  {index < progressSteps.length - 1 && (
                    <div
                      className={`absolute left-[1.125rem] top-[1.125rem] hidden h-px w-[calc(100%+1rem)] lg:block ${
                        isCompleted ? 'bg-slate-300' : 'bg-slate-200'
                      }`}
                    />
                  )}

                  <div className="relative z-[1] flex gap-4 lg:block">
                    <div className="flex shrink-0 flex-col items-center lg:items-start">
                      <div
                        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-xs font-semibold ring-4 ring-white ${
                          isCompleted
                            ? 'bg-[#0f8f61] text-white'
                            : isCurrent
                            ? 'bg-[#ef5b0c] text-white'
                            : 'bg-white text-slate-500 ring-1 ring-slate-200'
                        }`}
                      >
                        {isCompleted ? <CheckCircle2 className="h-3.5 w-3.5" /> : index + 1}
                      </div>
                      {index < progressSteps.length - 1 && (
                        <div className="mt-2 h-full w-px bg-slate-200 lg:hidden" />
                      )}
                    </div>

                    <div className="min-w-0 pb-5 lg:mt-4 lg:pb-0">
                      <p className="text-sm font-semibold leading-5 text-slate-950">{step.label}</p>
                      <span
                        className={`mt-2 inline-flex rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${
                          isCompleted
                            ? 'bg-emerald-50 text-[#0f8f61] ring-1 ring-emerald-100'
                            : isCurrent
                            ? 'bg-orange-50 text-[#c74634] ring-1 ring-orange-100'
                            : 'bg-slate-50 text-slate-500 ring-1 ring-slate-200'
                        }`}
                      >
                        {stepStateLabel}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
            </div>
          </div>
        </section>
      )}

      {activeMission && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => navigate('/observations')}
            className="pwc-action-dark"
          >
            {text.home.viewObservations}
          </button>
          <button
            onClick={() => navigate('/chat')}
            className="pwc-action-muted"
          >
            {text.home.openChat}
          </button>
          <button
            disabled={activeMission.status === 'Draft'}
            onClick={() => void handleGenerateReport()}
            className="pwc-action-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {generatingReport ? 'Generating...' : text.home.generateReport}
          </button>
        </div>
      )}
      </div>

      {m365Open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-4 backdrop-blur-sm sm:p-6">
          <div className="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-[1.75rem] bg-white shadow-2xl ring-1 ring-slate-900/10">
            <div className="border-b border-slate-200 bg-slate-50/80 px-6 py-5 sm:px-7">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="flex min-w-0 items-start gap-4">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-white text-slate-700 shadow-sm ring-1 ring-slate-200">
                    <FolderOpen className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-400">Microsoft 365</p>
                    <h2 className="mt-1 text-2xl font-semibold leading-tight text-slate-950">
                      {m365Mode === 'create' ? 'Create mission from workbook' : 'Import workbook'}
                    </h2>
                    <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">
                      {m365Mode === 'create'
                        ? 'Choose an Excel workbook from OneDrive. The file must include a Mission sheet so the workspace can be created and parsed.'
                        : 'Choose an Excel workbook from OneDrive to load observations into the active mission.'}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setM365Open(false)}
                  disabled={Boolean(m365ImportingId)}
                  className="rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-50"
                >
                  Close
                </button>
              </div>
            </div>

            <div className="space-y-4 px-6 py-5 sm:px-7">
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Source</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">OneDrive</p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Accepted</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">.xlsx, .xlsm</p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-400">Mode</p>
                  <p className="mt-1 text-sm font-semibold text-slate-900">
                    {m365Mode === 'create' ? 'Create mission' : 'Import to mission'}
                  </p>
                </div>
              </div>

              {m365Error && (
                <div className="flex items-center gap-2 rounded-2xl bg-red-50 px-4 py-3 text-sm font-medium text-red-700 ring-1 ring-red-100">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  {m365Error}
                </div>
              )}

              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-3">
                <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
                  <button
                    type="button"
                    onClick={() => void loadM365Root()}
                    disabled={m365Loading || Boolean(m365ImportingId)}
                    className="inline-flex items-center gap-2 rounded-xl bg-white px-3 py-2 font-semibold text-slate-800 ring-1 ring-slate-200 hover:bg-slate-100 disabled:opacity-50"
                  >
                    <FolderOpen className="h-4 w-4" />
                    OneDrive
                  </button>
                  {m365FolderStack.map((folder, index) => (
                    <span key={folder.id} className="flex min-w-0 items-center gap-2">
                      <span className="text-slate-400">/</span>
                      <span className="max-w-[180px] truncate rounded-xl bg-white px-3 py-2 font-medium text-slate-700 ring-1 ring-slate-200">
                        {folder.name}
                      </span>
                      {index === m365FolderStack.length - 1 && (
                        <button
                          type="button"
                          onClick={() => void goBackM365Folder()}
                          disabled={m365Loading || Boolean(m365ImportingId)}
                          className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100 disabled:opacity-50"
                        >
                          Back
                        </button>
                      )}
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto border-t border-slate-100 px-6 py-5 sm:px-7">
              {m365Loading ? (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-10 text-center">
                  <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
                  <p className="mt-4 text-sm font-medium text-slate-600">Loading Microsoft 365 files...</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {m365Items.map((item) => {
                    const supported = isSupportedM365Workbook(item);
                    const isFolder = Boolean(item.folder);
                    return (
                      <div
                        key={item.id}
                        className={`grid gap-3 rounded-2xl border px-4 py-3 transition sm:grid-cols-[minmax(0,1fr)_150px] sm:items-center ${
                          supported || isFolder
                            ? 'border-slate-200 bg-white hover:border-slate-300'
                            : 'border-slate-100 bg-slate-50'
                        }`}
                      >
                        <div className="flex min-w-0 items-center gap-3">
                          <div
                            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${
                              supported
                                ? 'bg-emerald-50 text-emerald-700'
                                : isFolder
                                ? 'bg-amber-50 text-amber-700'
                                : 'bg-slate-100 text-slate-400'
                            }`}
                          >
                            {isFolder ? <FolderOpen className="h-5 w-5" /> : <FileSpreadsheet className="h-5 w-5" />}
                          </div>
                          <div className="min-w-0">
                            <p className="truncate text-sm font-semibold text-slate-950">{item.name}</p>
                            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                              <span>{item.folder ? `${item.folder.childCount ?? 0} item(s)` : formatFileSize(item.size)}</span>
                              {item.lastModifiedDateTime && <span>Modified {formatDateTime(item.lastModifiedDateTime)}</span>}
                            </div>
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => isFolder ? void openM365Folder(item) : void handleM365Import(item)}
                          disabled={(!supported && !isFolder) || Boolean(m365ImportingId) || m365Loading}
                          className={`rounded-xl px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-45 ${
                            isFolder
                              ? 'bg-white text-slate-900 ring-1 ring-slate-200 hover:bg-slate-50'
                              : supported
                              ? 'bg-slate-950 text-white hover:bg-slate-800'
                              : 'bg-slate-200 text-slate-500'
                          }`}
                        >
                          {m365ImportingId === item.id
                            ? 'Importing...'
                            : isFolder
                            ? 'Open folder'
                            : supported
                            ? (m365Mode === 'create' ? 'Create mission' : 'Import file')
                            : 'Unsupported'}
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}

              {!m365Loading && m365Items.length === 0 && !m365Error && (
                <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-10 text-center text-sm text-slate-500">
                  No files were returned by Microsoft 365.
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {missionToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-6">
          <div className="w-full max-w-xl rounded-[2rem] bg-white p-8 shadow-2xl">
            <p className="text-sm uppercase tracking-[0.2em] text-slate-400">{text.home.deleteMission}</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">{text.home.deleteMissionTitle}</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              {text.home.deleteMissionMessage}
            </p>
            {deleteError && (
              <div className="mt-4 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">
                {deleteError}
              </div>
            )}
            <div className="mt-6 flex flex-wrap items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  if (deletingMission) return;
                  setMissionToDelete(null);
                  setDeleteError(null);
                }}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700"
              >
                {text.home.cancel}
              </button>
              <button
                type="button"
                onClick={() => void handleDeleteMission()}
                disabled={deletingMission}
                className="rounded-2xl bg-red-600 px-4 py-3 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deletingMission ? text.home.deleting : text.home.delete}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}



