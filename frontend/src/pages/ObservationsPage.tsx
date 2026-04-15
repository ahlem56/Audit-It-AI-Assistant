import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MessageSquare, Plus, Trash2, X } from 'lucide-react';
import PriorityBadge from '../components/PriorityBadge';
import { useMissionContext } from '../context/MissionContext';
import type { Observation, PriorityLevel } from '../types';

const priorityOptions: PriorityLevel[] = ['Critical', 'High', 'Medium', 'Low'];
const validationStatusOptions = ['', 'Draft', 'Validated'] as const;

export default function ObservationsPage() {
  const navigate = useNavigate();
  const { activeMission, observations, updateObservations, recalculatePriorities } = useMissionContext();
  const [selectedObservationId, setSelectedObservationId] = useState<string | null>(null);
  const [localObservations, setLocalObservations] = useState<Observation[]>(observations);
  const [saving, setSaving] = useState(false);
  const [recalculating, setRecalculating] = useState(false);
  const [search, setSearch] = useState('');
  const [priorityFilter, setPriorityFilter] = useState<'All' | PriorityLevel>('All');
  const [statusFilter, setStatusFilter] = useState<string>('All');

  useEffect(() => {
    setLocalObservations(observations);
  }, [observations]);

  const selectedObservation = useMemo(
    () => localObservations.find((observation) => observation.id === selectedObservationId) ?? null,
    [localObservations, selectedObservationId]
  );

  const updateObservation = (id: string, updater: (observation: Observation) => Observation) => {
    setLocalObservations((current) => current.map((observation) => (observation.id === id ? updater(observation) : observation)));
  };

  const filteredObservations = useMemo(() => {
    const normalizedSearch = search.trim().toLowerCase();

    return localObservations.filter((observation) => {
      const matchesSearch =
        !normalizedSearch ||
        [
          observation.observation_id,
          observation.control_id,
          observation.application,
          observation.title,
          observation.finding,
          observation.comments,
          observation.owners
        ]
          .join(' ')
          .toLowerCase()
          .includes(normalizedSearch);

      const matchesPriority = priorityFilter === 'All' || observation.priority === priorityFilter;
      const matchesStatus = statusFilter === 'All' || observation.status === statusFilter;

      return matchesSearch && matchesPriority && matchesStatus;
    });
  }, [localObservations, priorityFilter, search, statusFilter]);

  const totalSummary = `${localObservations.length} observations - ${localObservations.filter((o) => o.priority === 'Critical').length} Critical - ${localObservations.filter((o) => o.priority === 'High').length} High - ${localObservations.filter((o) => o.priority === 'Medium').length} Medium - ${localObservations.filter((o) => o.priority === 'Low').length} Low`;

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateObservations(localObservations);
    } catch (error) {
      console.error('Failed to save observations:', error);
    } finally {
      setSaving(false);
    }
  };

  const handleRecalculate = async () => {
    setRecalculating(true);
    try {
      await recalculatePriorities();
    } catch (error) {
      console.error('Failed to recalculate priorities:', error);
    } finally {
      setRecalculating(false);
    }
  };

  const handleAddRow = () => {
    const id = `OBS-${Date.now()}`;
    const newRow: Observation = {
      id,
      observation_id: id,
      domain: '',
      domaine_controle: '',
      category: '',
      categorie_controle: '',
      control_id: '',
      controle_ref: '',
      application: '',
      layer: '',
      couche: '',
      title: '',
      titre_observation: '',
      expected_control: '',
      controle_attendu: '',
      finding: '',
      constat: '',
      risk: '',
      risque_associe: '',
      compensating_procedure: '',
      procedure_compensatoire: '',
      impact: '',
      impact_potentiel: '',
      root_cause: '',
      cause_racine: '',
      comments: '',
      commentaire_auditeur: '',
      population: '',
      sample_size: '',
      taille_echantillon: '',
      exception_count: '',
      nombre_exceptions: '',
      owners: '',
      responsables: '',
      evidence_references: '',
      references_probantes: '',
      control_status: '',
      statut_controle: '',
      status: '',
      statut_validation: '',
      priority: null,
      priority_justification: '',
      priority_reason: '',
      priority_source: '',
      recommendation: '',
      recommandation_proposee: '',
      included_in_report: true
    };

    setLocalObservations((current) => [newRow, ...current]);
    setSelectedObservationId(id);
  };

  const deleteObservation = (id: string) => {
    setLocalObservations((current) => current.filter((observation) => observation.id !== id));
    if (selectedObservationId === id) {
      setSelectedObservationId(null);
    }
  };

  if (!activeMission) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <p className="text-slate-500">Please select a mission from the workspace first.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Observations</p>
          <h1 className="text-3xl font-semibold text-slate-900">Observation register</h1>
          <p className="mt-2 text-sm text-slate-500">{activeMission.name}</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button onClick={() => navigate('/chat')} className="rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800">
            Open mission chat
          </button>
          <button
            type="button"
            onClick={handleRecalculate}
            disabled={recalculating}
            className="rounded-2xl bg-red-600 px-5 py-3 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
          >
            {recalculating ? 'Recalculating...' : 'Recalculate Priorities'}
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="rounded-2xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>

      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
        <div className="grid gap-4 lg:grid-cols-[1.2fr_0.8fr_0.8fr_auto]">
          <label className="space-y-2 text-sm text-slate-700">
            Search
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900"
              placeholder="Search observations"
            />
          </label>
          <label className="space-y-2 text-sm text-slate-700">
            Priority
            <select
              value={priorityFilter}
              onChange={(event) => setPriorityFilter(event.target.value as 'All' | PriorityLevel)}
              className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900"
            >
              <option value="All">All</option>
              {priorityOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-2 text-sm text-slate-700">
            Validation
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900"
            >
              <option value="All">All</option>
              {validationStatusOptions.map((status) => (
                <option key={status || 'blank'} value={status}>
                  {status || 'Blank'}
                </option>
              ))}
            </select>
          </label>
          <div className="flex items-end">
            <button
              type="button"
              className="inline-flex items-center gap-2 rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800"
              onClick={handleAddRow}
            >
              <Plus className="h-4 w-4" /> Add new row
            </button>
          </div>
        </div>
      </section>

      <div className="flex items-center justify-between px-1">
        <p className="text-sm text-slate-600">{totalSummary}</p>
        <p className="text-sm text-slate-500">{filteredObservations.length} visible</p>
      </div>

      <section className="space-y-4">
        {filteredObservations.map((observation) => (
          <article
            key={observation.id}
            onClick={() => setSelectedObservationId(observation.id)}
            className="group cursor-pointer rounded-[2rem] border border-slate-200 bg-white p-6 shadow-card transition hover:-translate-y-0.5 hover:border-slate-300"
          >
            <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="rounded-full bg-red-50 px-3 py-1 text-xs font-semibold text-red-700">
                    {observation.observation_id || observation.id}
                  </span>
                  <p className="text-sm font-semibold text-slate-900">
                    {observation.control_id || 'No control ref'} - {observation.application || 'No application'}
                  </p>
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-600">
                    {observation.layer || 'No layer'}
                  </span>
                </div>
                <h2 className="mt-4 max-w-4xl text-xl font-semibold leading-8 text-slate-900">
                  {observation.title || 'Untitled observation'}
                </h2>
                <p className="mt-4 max-w-5xl text-sm leading-7 text-slate-600">
                  {observation.finding || 'No finding provided.'}
                </p>
              </div>

              <div className="flex min-w-[220px] flex-col items-start gap-3 xl:items-end">
                <PriorityBadge priority={observation.priority} overridden={observation.priority_source === 'manual_override'} />
                <div className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
                  <p>
                    Status: <span className="font-semibold text-slate-900">{observation.status || 'Blank'}</span>
                  </p>
                  <p className="mt-1">
                    In report: <span className="font-semibold text-slate-900">{observation.included_in_report ? 'Yes' : 'No'}</span>
                  </p>
                </div>
              </div>
            </div>
          </article>
        ))}

        {filteredObservations.length === 0 ? (
          <div className="rounded-[2rem] border border-dashed border-slate-300 bg-white px-6 py-12 text-center text-sm text-slate-500">
            No observations match the current filters.
          </div>
        ) : null}
      </section>

      <div
        className={`fixed inset-0 z-40 transition ${selectedObservation ? 'pointer-events-auto bg-slate-900/30' : 'pointer-events-none bg-transparent'}`}
        onClick={() => setSelectedObservationId(null)}
      />

      <aside
        className={`fixed right-0 top-0 z-50 h-screen w-full max-w-[480px] overflow-y-auto border-l border-slate-200 bg-white shadow-2xl transition-transform duration-300 ${
          selectedObservation ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {selectedObservation ? (
          <div className="min-h-full p-6" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 pb-5">
              <div>
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                  Observation ID: <span className="font-semibold text-slate-900">{selectedObservation.observation_id || selectedObservation.id}</span>
                </p>
                <p className="text-sm font-semibold text-slate-900">
                  {selectedObservation.control_id || 'No control ref'} - {selectedObservation.application || 'No application'}
                </p>
                <p className="mt-2 text-sm text-slate-500">{selectedObservation.title || 'Untitled observation'}</p>
              </div>
              <button type="button" onClick={() => setSelectedObservationId(null)} className="rounded-full bg-slate-100 p-2 text-slate-600 hover:bg-slate-200">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-6 py-6">
              <section className="border-b border-slate-200 pb-6">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Priority</p>
                <div className="mt-4 flex items-start gap-3">
                  <div className="flex-1">
                    <select
                      value={selectedObservation.priority ?? ''}
                      onChange={(event) =>
                        updateObservation(selectedObservation.id, (observation) => ({
                          ...observation,
                          priority: (event.target.value || null) as PriorityLevel | null,
                          priority_source: event.target.value ? 'manual_override' : '',
                          priority_reason: event.target.value ? 'manual override by user' : '',
                          priority_justification: event.target.value ? observation.priority_justification : ''
                        }))
                      }
                      className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900"
                    >
                      <option value="">Not set</option>
                      {priorityOptions.map((option) => (
                        <option key={option} value={option}>
                          {option}
                        </option>
                      ))}
                    </select>
                  </div>
                  {selectedObservation.priority_source === 'manual_override' ? (
                    <span className="rounded-full bg-orange-100 px-3 py-2 text-xs font-semibold text-orange-800">overridden manually</span>
                  ) : null}
                </div>

                <div className="mt-5 space-y-3 rounded-3xl bg-slate-50 p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Why {selectedObservation.priority || 'this priority'}?</p>
                  <p className="text-sm text-slate-700">{selectedObservation.priority_reason || 'No priority reason available yet.'}</p>
                  <p className="text-sm text-slate-600">{selectedObservation.priority_justification || 'No justification generated yet.'}</p>
                </div>
              </section>

              <section className="border-b border-slate-200 pb-6">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Title</p>
                <input
                  value={selectedObservation.title}
                  onChange={(event) =>
                    updateObservation(selectedObservation.id, (observation) => ({
                      ...observation,
                      title: event.target.value,
                      titre_observation: event.target.value
                    }))
                  }
                  className="mt-4 w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900"
                />
              </section>

              <section className="border-b border-slate-200 pb-6">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Finding / Constat</p>
                <textarea
                  value={selectedObservation.finding}
                  onChange={(event) =>
                    updateObservation(selectedObservation.id, (observation) => ({
                      ...observation,
                      finding: event.target.value,
                      constat: event.target.value
                    }))
                  }
                  className="mt-4 min-h-[220px] w-full rounded-3xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-900"
                />
              </section>

              <section className="border-b border-slate-200 pb-6">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Recommendation</p>
                <textarea
                  value={selectedObservation.recommendation}
                  onChange={(event) =>
                    updateObservation(selectedObservation.id, (observation) => ({
                      ...observation,
                      recommendation: event.target.value,
                      recommandation_proposee: event.target.value
                    }))
                  }
                  className="mt-4 min-h-[160px] w-full rounded-3xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-900"
                />
              </section>

              <section className="border-b border-slate-200 pb-6">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Compensating procedure</p>
                <textarea
                  value={selectedObservation.compensating_procedure}
                  onChange={(event) =>
                    updateObservation(selectedObservation.id, (observation) => ({
                      ...observation,
                      compensating_procedure: event.target.value,
                      procedure_compensatoire: event.target.value
                    }))
                  }
                  className="mt-4 min-h-[140px] w-full rounded-3xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-900"
                />
              </section>

              <section className="border-b border-slate-200 pb-6">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">Comments</p>
                <textarea
                  value={selectedObservation.comments}
                  onChange={(event) =>
                    updateObservation(selectedObservation.id, (observation) => ({
                      ...observation,
                      comments: event.target.value,
                      commentaire_auditeur: event.target.value
                    }))
                  }
                  className="mt-4 min-h-[140px] w-full rounded-3xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-900"
                />
              </section>

              <section className="grid gap-4 border-b border-slate-200 pb-6 sm:grid-cols-2">
                <label className="text-sm font-semibold text-slate-900">
                  Status
                  <select
                    value={selectedObservation.status}
                    onChange={(event) =>
                      updateObservation(selectedObservation.id, (observation) => ({
                        ...observation,
                        status: event.target.value,
                        statut_validation: event.target.value
                      }))
                    }
                    className="mt-3 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900"
                  >
                    {validationStatusOptions.map((status) => (
                      <option key={status || 'blank'} value={status}>
                        {status || 'Blank'}
                      </option>
                    ))}
                  </select>
                </label>

                <div>
                  <p className="text-sm font-semibold text-slate-900">In report</p>
                  <label className="mt-3 inline-flex items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={selectedObservation.included_in_report}
                      onChange={(event) =>
                        updateObservation(selectedObservation.id, (observation) => ({
                          ...observation,
                          included_in_report: event.target.checked
                        }))
                      }
                    />
                    {selectedObservation.included_in_report ? 'Included' : 'Excluded'}
                  </label>
                </div>
              </section>

              <button
                type="button"
                onClick={() => {
                  navigate('/chat');
                }}
                className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-900 hover:bg-slate-50"
              >
                <MessageSquare className="h-4 w-4" /> Ask assistant about this obs
              </button>

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={saving}
                  className="flex-1 rounded-2xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  {saving ? 'Saving...' : 'Save changes'}
                </button>
                <button
                  type="button"
                  onClick={() => deleteObservation(selectedObservation.id)}
                  className="rounded-2xl border border-red-200 bg-red-50 px-5 py-3 text-sm font-semibold text-red-700 hover:bg-red-100"
                >
                  Delete obs
                </button>
              </div>
            </div>
          </div>
        ) : null}
      </aside>
    </div>
  );
}

