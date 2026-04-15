import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  CalendarRange,
  CheckCircle2,
  Clock3,
  FileSpreadsheet,
  FolderOpen,
  Plus,
  Trash2,
  UploadCloud
} from 'lucide-react';
import { useMissionContext } from '../context/MissionContext';
import type { CreateMissionPayload } from '../types';

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

export default function HomePage() {
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
    uploadExcel,
    loadMissions
  } = useMissionContext();

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

  useEffect(() => {
    window.localStorage.setItem(PROFILE_STORAGE_KEY, JSON.stringify(profiles));
  }, [profiles]);

  const activeProfile = activeMission ? profiles[activeMission.mission_id] : undefined;
  const hasUploadedWorkbook = Boolean(activeMission?.current_file?.name);
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
      applications: activeMission.applications_count ?? fallbackApplications.size,
      controls: activeMission.control_ids_count ?? fallbackControls.size
    };
  }, [activeMission, observations]);

  const progressSteps = useMemo(() => {
    const stepStates = [
      { label: 'Create mission', done: Boolean(activeMission), current: !activeMission },
      { label: 'Upload Excel', done: hasUploadedWorkbook, current: Boolean(activeMission) && !hasUploadedWorkbook },
      { label: 'Validate observations', done: hasUploadedWorkbook && hasObservations, current: hasUploadedWorkbook && !hasObservations },
      { label: 'Generate report', done: activeMission?.status === 'Finalized', current: hasUploadedWorkbook && hasObservations && activeMission?.status !== 'Finalized' },
      { label: 'Exporter PPTX', done: activeMission?.status === 'Finalized', current: false }
    ];

    return stepStates.map((step, index) => ({ ...step, number: index + 1 }));
  }, [activeMission, hasObservations, hasUploadedWorkbook]);

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
    if (!canGoNext || !draft.manager.trim() || !draft.senior.trim()) return;

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

  const handleDeleteMission = async () => {
    if (!missionToDelete) return;

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

  return (
    <>
      <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Workspace</p>
          <h1 className="text-3xl font-semibold text-slate-900">Mission dashboard</h1>
          <p className="mt-2 max-w-3xl text-sm text-slate-500">
            Structure the mission, load the source workbook, and move the engagement forward through to the report.
          </p>
        </div>
        <button
          onClick={loadMissions}
          disabled={loadingMissions}
          className="inline-flex items-center gap-2 rounded-2xl bg-white px-4 py-2 text-sm font-semibold text-slate-700 shadow-sm ring-1 ring-slate-200 hover:bg-slate-50 disabled:opacity-50"
        >
          <FolderOpen className="h-4 w-4" /> {loadingMissions ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

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

      <section className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-card">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm uppercase tracking-[0.18em] text-slate-400">Mission setup</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">Missions</h2>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => excelInputRef.current?.click()}
              disabled={creatingFromExcel}
              className="inline-flex items-center gap-2 rounded-2xl bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-50"
            >
              <FileSpreadsheet className="h-4 w-4" />
              {creatingFromExcel ? 'Importing...' : 'Create from Excel'}
            </button>
            <button
              onClick={() => {
                setFormOpen((current) => !current);
                setFormStep(1);
              }}
              className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
            >
              <Plus className="h-4 w-4" /> New mission
            </button>
          </div>
        </div>

        {formOpen && (
          <div className="mb-8 rounded-[2rem] border border-slate-200 bg-slate-50 p-6">
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
                    placeholder="Paref"
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
              className={`rounded-[1.75rem] border p-5 text-left transition ${
                activeMissionId === mission.mission_id
                  ? 'border-red-200 bg-red-50 shadow-sm'
                  : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
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
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-sky-100 text-sky-800'
                    }`}
                  >
                    {mission.status}
                  </span>
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
                </div>
              </div>
            </div>
          ))}
        </div>

        {missions.length === 0 && !loadingMissions && (
          <div className="rounded-[1.75rem] border border-dashed border-slate-300 bg-slate-50 p-10 text-center text-slate-500">
            No missions yet. Create one manually or import the source workbook directly.
          </div>
        )}
      </section>

      {activeMission && (
        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <section className="space-y-6">
            <div className="rounded-[2rem] border border-slate-200 bg-white p-8 shadow-card">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-sm uppercase tracking-[0.2em] text-slate-400">Mission active</p>
                  <h2 className="mt-3 text-3xl font-semibold text-slate-900">{activeDisplayTitle}</h2>
                  <p className="mt-2 text-sm text-slate-500">{activeDisplayClient}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`rounded-full px-3 py-1 text-sm font-semibold ${statusStyle}`}>{activeMission.status}</span>
                  <button
                    type="button"
                    onClick={() => {
                      setDeleteError(null);
                      setMissionToDelete(activeMission.mission_id);
                    }}
                    className="inline-flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-4 py-2 text-sm font-semibold text-red-700 hover:bg-red-100"
                  >
                    <Trash2 className="h-4 w-4" /> Delete mission
                  </button>
                </div>
              </div>

              <div className="mt-8 grid gap-4 sm:grid-cols-2">
                <div className="rounded-3xl bg-slate-50 p-5">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Mission ID</p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">{activeMission.mission_id}</p>
                  <p className="mt-2 text-xs text-slate-500">Excel import now gives priority to the workbook mission identifier.</p>
                </div>
                <div className="rounded-3xl bg-slate-50 p-5">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Period</p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">
                    {activeDisplayPeriod}
                  </p>
                  <p className="mt-2 text-xs text-slate-500">{activeDisplayType}</p>
                </div>
                <div className="rounded-3xl bg-slate-50 p-5">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Participants</p>
                  <div className="mt-2 space-y-1">
                    {activeDisplayIntervenants.length > 0 ? (
                      activeDisplayIntervenants.map((intervenant) => (
                        <p key={intervenant} className="text-sm text-slate-700">
                          {intervenant}
                        </p>
                      ))
                    ) : (
                      <p className="text-sm text-slate-500">No participants recorded</p>
                    )}
                  </div>
                </div>
                <div className="rounded-3xl bg-slate-50 p-5">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Last update</p>
                  <p className="mt-2 text-sm font-semibold text-slate-900">{formatDateTime(activeMission.updated_at)}</p>
                  <p className="mt-1 text-xs text-slate-500">{loadingMission ? 'Sync in progress...' : 'Backend data is up to date'}</p>
                </div>
              </div>

              {(activeDisplayApplications.length || activeDisplayEntities.length) && (
                <div className="mt-6 grid gap-4 lg:grid-cols-3">
                 
                  <div className="rounded-3xl border border-slate-200 p-4">
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                      <CalendarRange className="h-4 w-4 text-slate-500" /> Entities
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
                      <FileSpreadsheet className="h-4 w-4 text-slate-500" /> Applications
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

            <div className="rounded-[2rem] border border-slate-200 bg-white p-8 shadow-card">
              <div className="mb-6 flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm uppercase tracking-[0.2em] text-slate-400">Workflow</p>
                  <h3 className="mt-2 text-xl font-semibold text-slate-900">Mission progress</h3>
                </div>
                <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                  Manager view
                </span>
              </div>

              <div className="flex w-full flex-wrap gap-3">
                {progressSteps.map((step) => (
                  <div
                    key={step.number}
                    className={`flex min-w-[130px] flex-1 basis-[130px] flex-col items-center rounded-3xl border px-4 py-5 text-center ${
                      step.done
                        ? 'border-emerald-200 bg-emerald-50'
                        : step.current
                        ? 'border-amber-200 bg-amber-50'
                        : 'border-slate-200 bg-slate-50'
                    }`}
                  >
                    <div className="flex w-full flex-col items-center">
                      <div
                        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${
                          step.done
                            ? 'bg-emerald-600 text-white'
                            : step.current
                            ? 'bg-amber-500 text-white'
                            : 'bg-white text-slate-500 ring-1 ring-slate-200'
                        }`}
                      >
                        {step.done ? '✓' : step.number}
                      </div>
                      <div className="mt-4 min-w-0">
                        <p className="min-h-[3.5rem] text-sm font-semibold leading-6 text-slate-900">
                          {step.label}
                        </p>
                        <p className="mt-2 text-sm text-slate-500">
                          {step.done ? 'Completed' : step.current ? 'In progress' : 'Coming next'}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="space-y-6">
            <div
              className={`rounded-[2rem] border bg-white p-8 shadow-card transition ${
                uploadHighlight ? 'border-red-300 ring-4 ring-red-100' : 'border-slate-200'
              }`}
            >
              <div className="flex items-center gap-3 text-slate-700">
                <UploadCloud className="h-5 w-5 text-slate-500" />
                <div>
                  <p className="text-sm font-semibold text-slate-900">Upload ITGC workbook</p>
                  <p className="text-sm text-slate-500">Load the source file to populate observations, controls, and the summary.</p>
                </div>
              </div>

              <div className="mt-6 rounded-[1.75rem] border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
                <p className="text-sm text-slate-500">Drop an `.xlsx` or `.xlsm` file here, or click to browse.</p>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadState.uploading}
                  className="mt-6 rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
                >
                  {uploadState.uploading ? 'Uploading...' : 'Choose file'}
                </button>
                {uploadHighlight && (
                  <p className="mt-4 text-xs font-medium text-red-600">
                    The mission is created. Next step: upload the workbook to move the mission to `Ready`.
                  </p>
                )}
              </div>

              <div className="mt-6 rounded-[1.75rem] border border-slate-200 bg-slate-50 p-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-semibold text-slate-900">Latest upload summary</p>
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
                          Parsed on {formatDateTime(activeMission.updated_at)}
                        </p>
                      </>
                    ) : (
                      <p className="mt-3 text-sm text-slate-500">No workbook has been uploaded for this mission yet.</p>
                    )}
                  </div>

                  {uploadState.uploading && (
                    <div className="flex items-center gap-2 rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                      <span className="h-2 w-2 animate-pulse rounded-full bg-slate-500" />
                      Parsing...
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
                    View observations <ArrowRight className="h-4 w-4" />
                  </button>
                )}
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-[1.75rem] bg-white p-5 shadow-card ring-1 ring-slate-200">
                <p className="text-sm text-slate-500">Observations</p>
                <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.observations}</p>
              </div>
              <div className="rounded-[1.75rem] bg-white p-5 shadow-card ring-1 ring-slate-200">
                <p className="text-sm text-slate-500">Applications</p>
                <p className="mt-3 text-3xl font-semibold text-slate-900">{stats.applications}</p>
              </div>
            
            </div>

            <div className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-card">
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Clock3 className="h-4 w-4 text-slate-500" /> Next best action
              </div>
              <p className="mt-3 text-sm leading-6 text-slate-600">
                {!hasUploadedWorkbook
                  ? 'The workspace is ready. Upload the workbook now to hydrate the observations and move the mission to Ready.'
                  : !hasObservations
                  ? 'The file is present, but the mission does not yet contain usable observations. Review the parsing and retry if needed.'
                  : 'The observations are available. The natural next step is validation review, followed by report generation.'}
              </p>
            </div>
          </section>
        </div>
      )}

      {activeMission && (
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => navigate('/observations')}
            className="rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800"
          >
            View Observations
          </button>
          <button
            onClick={() => navigate('/chat')}
            className="rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-900 hover:border-slate-300"
          >
            Open chat
          </button>
          <button
            disabled={activeMission.status === 'Draft'}
            onClick={() => navigate('/report')}
            className="rounded-2xl bg-red-600 px-5 py-3 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            Generate Report
          </button>
        </div>
      )}
      </div>

      {missionToDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-6">
          <div className="w-full max-w-xl rounded-[2rem] bg-white p-8 shadow-2xl">
            <p className="text-sm uppercase tracking-[0.2em] text-slate-400">Delete mission</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">Delete mission?</h2>
            <p className="mt-3 text-sm leading-6 text-slate-600">
              This will permanently delete the mission and its observations, feedback, and cached report data.
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
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleDeleteMission()}
                disabled={deletingMission}
                className="rounded-2xl bg-red-600 px-4 py-3 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deletingMission ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}



