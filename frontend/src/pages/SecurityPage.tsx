import {
  CheckCircle2,
  ChevronDown,
  Clock,
  Copy,
  Fingerprint,
  LockKeyhole,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  TriangleAlert,
  X
} from 'lucide-react';
import { Fragment, useEffect, useMemo, useState } from 'react';
import { getSecurityAuditEvents } from '../services/api';
import type { SecurityAuditEvent, SecurityAuditEventsResponse } from '../types';

const actionLabels: Record<string, string> = {
  LOGIN_SUCCESS: 'Login success',
  LOGIN_FAILED: 'Login failed',
  MISSION_CREATED: 'Mission created',
  MISSION_VIEWED: 'Mission viewed',
  FILE_UPLOADED: 'File uploaded',
  OBSERVATION_UPDATED: 'Observation updated',
  PRIORITY_RECALCULATED: 'Priority recalculated',
  REPORT_GENERATED: 'Report generated',
  REPORT_EXPORTED: 'Report exported',
  USER_INVITED: 'User invited',
  CHAT_QUESTION_ASKED: 'Chat question asked',
  AI_ANSWER_GENERATED: 'AI answer generated',
  SECURITY_VALIDATION_BLOCKED: 'Security validation blocked'
};

const ALL = 'all';

function formatDate(value: string) {
  if (!value) return 'Unknown time';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date);
}

function shortHash(value: string) {
  return value ? `${value.slice(0, 12)}...${value.slice(-8)}` : 'Unavailable';
}

function eventTitle(event: SecurityAuditEvent) {
  return actionLabels[event.action] || event.action.replace(/_/g, ' ').toLowerCase();
}

function includesText(value: unknown, query: string) {
  return String(value ?? '').toLowerCase().includes(query);
}

function metadataSummary(event: SecurityAuditEvent) {
  const entries = Object.entries(event.metadata_json || {});
  if (!entries.length) return 'No metadata';
  return entries
    .slice(0, 3)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(' · ');
}

function uniqueOptions(events: SecurityAuditEvent[], key: keyof SecurityAuditEvent) {
  return Array.from(new Set(events.map((event) => String(event[key] || '')).filter(Boolean))).sort();
}

export default function SecurityPage() {
  const [data, setData] = useState<SecurityAuditEventsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [userFilter, setUserFilter] = useState(ALL);
  const [actionFilter, setActionFilter] = useState(ALL);
  const [statusFilter, setStatusFilter] = useState(ALL);
  const [missionFilter, setMissionFilter] = useState(ALL);
  const [expandedEventId, setExpandedEventId] = useState<string | null>(null);

  const loadEvents = async () => {
    setLoading(true);
    setError('');
    try {
      setData(await getSecurityAuditEvents(300));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Security activity could not be loaded.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadEvents();
  }, []);

  const events = data?.events ?? [];

  const filterOptions = useMemo(
    () => ({
      users: uniqueOptions(events, 'user_email'),
      actions: uniqueOptions(events, 'action'),
      statuses: uniqueOptions(events, 'status'),
      missions: uniqueOptions(events, 'mission_id')
    }),
    [events]
  );

  const filteredEvents = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return events.filter((event) => {
      const matchesUser = userFilter === ALL || event.user_email === userFilter;
      const matchesAction = actionFilter === ALL || event.action === actionFilter;
      const matchesStatus = statusFilter === ALL || event.status === statusFilter;
      const matchesMission = missionFilter === ALL || event.mission_id === missionFilter;
      const matchesQuery =
        !normalizedQuery ||
        includesText(event.event_id, normalizedQuery) ||
        includesText(event.user_email, normalizedQuery) ||
        includesText(event.action, normalizedQuery) ||
        includesText(event.mission_id, normalizedQuery) ||
        includesText(event.resource_type, normalizedQuery) ||
        includesText(event.resource_id, normalizedQuery) ||
        includesText(JSON.stringify(event.metadata_json || {}), normalizedQuery);

      return matchesUser && matchesAction && matchesStatus && matchesMission && matchesQuery;
    });
  }, [actionFilter, events, missionFilter, query, statusFilter, userFilter]);

  const stats = useMemo(
    () => ({
      total: events.length,
      filtered: filteredEvents.length,
      failed: events.filter((event) => event.status === 'failure').length,
      ai: events.filter((event) => event.action.includes('AI') || event.action.includes('CHAT')).length
    }),
    [events, filteredEvents.length]
  );

  const resetFilters = () => {
    setQuery('');
    setUserFilter(ALL);
    setActionFilter(ALL);
    setStatusFilter(ALL);
    setMissionFilter(ALL);
    setExpandedEventId(null);
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="pwc-kicker">Security</p>
          <h1 className="pwc-title mt-2 text-4xl font-semibold">Security Activity</h1>
          <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
            Sensitive platform actions are recorded in an append-only, hash-chained audit trail.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadEvents()}
          disabled={loading}
          className="pwc-action-primary disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <section className="pwc-panel p-5">
          <div className="flex items-center gap-3">
            <ShieldCheck className="h-5 w-5 text-[#ef5b0c]" />
            <p className="text-sm font-semibold text-slate-900">Chain status</p>
          </div>
          <p className={`mt-4 text-2xl font-semibold ${data?.chain.valid ? 'text-emerald-700' : 'text-rose-700'}`}>
            {data?.chain.valid ? 'Intact' : 'Review'}
          </p>
          <p className="mt-1 text-xs text-slate-500">{data?.chain.reason || 'Waiting for audit data.'}</p>
        </section>

        <section className="pwc-panel p-5">
          <div className="flex items-center gap-3">
            <Clock className="h-5 w-5 text-[#ef5b0c]" />
            <p className="text-sm font-semibold text-slate-900">Visible events</p>
          </div>
          <p className="mt-4 text-2xl font-semibold text-slate-950">{stats.total}</p>
          <p className="mt-1 text-xs text-slate-500">{stats.filtered} shown after filters.</p>
        </section>

        <section className="pwc-panel p-5">
          <div className="flex items-center gap-3">
            <TriangleAlert className="h-5 w-5 text-[#ef5b0c]" />
            <p className="text-sm font-semibold text-slate-900">Failed events</p>
          </div>
          <p className="mt-4 text-2xl font-semibold text-slate-950">{stats.failed}</p>
          <p className="mt-1 text-xs text-slate-500">Failed logins or blocked operations.</p>
        </section>

        <section className="pwc-panel p-5">
          <div className="flex items-center gap-3">
            <LockKeyhole className="h-5 w-5 text-[#ef5b0c]" />
            <p className="text-sm font-semibold text-slate-900">AI events</p>
          </div>
          <p className="mt-4 text-2xl font-semibold text-slate-950">{stats.ai}</p>
          <p className="mt-1 text-xs text-slate-500">Chat and answer generation activity.</p>
        </section>
      </div>

      <section className="pwc-main-panel">
        <div className="mb-5 flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <p className="pwc-kicker">Audit Trail</p>
            <h2 className="pwc-title mt-1 text-2xl font-semibold">Tamper-Evident Events</h2>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            {data?.chain.valid ? (
              <div className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-semibold text-emerald-700">
                <CheckCircle2 className="h-4 w-4" />
                Hash chain verified
              </div>
            ) : null}
            <button
              type="button"
              onClick={resetFilters}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 transition hover:border-slate-300"
            >
              <X className="h-4 w-4" />
              Clear filters
            </button>
          </div>
        </div>

        <div className="mb-5 rounded-2xl border border-slate-200 bg-slate-50/70 p-5">
          <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <SlidersHorizontal className="h-4 w-4 text-[#ef5b0c]" />
              Filters
            </div>
            <p className="text-xs font-medium text-slate-500">
              Showing {stats.filtered} of {stats.total} visible events
            </p>
          </div>

          <div className="grid gap-4">
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Search</span>
              <div className="relative">
                <Search className="pointer-events-none absolute left-4 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search user, action, mission, resource, metadata..."
                  className="h-11 w-full rounded-xl border border-slate-200 bg-white pl-11 pr-4 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-[#ef5b0c]/50 focus:ring-2 focus:ring-[#ef5b0c]/10"
                />
              </div>
            </label>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <label className="block">
                <span className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">User</span>
                <select
                  value={userFilter}
                  onChange={(event) => setUserFilter(event.target.value)}
                  className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-[#ef5b0c]/50 focus:ring-2 focus:ring-[#ef5b0c]/10"
                >
                  <option value={ALL}>All users</option>
                  {filterOptions.users.map((user) => (
                    <option key={user} value={user}>{user}</option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Action</span>
                <select
                  value={actionFilter}
                  onChange={(event) => setActionFilter(event.target.value)}
                  className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-[#ef5b0c]/50 focus:ring-2 focus:ring-[#ef5b0c]/10"
                >
                  <option value={ALL}>All actions</option>
                  {filterOptions.actions.map((action) => (
                    <option key={action} value={action}>{actionLabels[action] || action}</option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Status</span>
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                  className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-[#ef5b0c]/50 focus:ring-2 focus:ring-[#ef5b0c]/10"
                >
                  <option value={ALL}>All status</option>
                  {filterOptions.statuses.map((status) => (
                    <option key={status} value={status}>{status}</option>
                  ))}
                </select>
              </label>

              <label className="block">
                <span className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Mission</span>
                <select
                  value={missionFilter}
                  onChange={(event) => setMissionFilter(event.target.value)}
                  className="h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-[#ef5b0c]/50 focus:ring-2 focus:ring-[#ef5b0c]/10"
                >
                  <option value={ALL}>All missions</option>
                  {filterOptions.missions.map((mission) => (
                    <option key={mission} value={mission}>{mission}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        </div>

        {error ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
        ) : null}

        {loading ? (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600">
            Loading security activity...
          </div>
        ) : null}

        {!loading && !error && filteredEvents.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-600">
            No events match the current filters.
          </div>
        ) : null}

        {!loading && !error && filteredEvents.length > 0 ? (
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <div className="max-h-[620px] overflow-auto">
              <table className="min-w-[1120px] text-left text-sm">
                <colgroup>
                  <col className="w-[150px]" />
                  <col className="w-[260px]" />
                  <col className="w-[210px]" />
                  <col className="w-[230px]" />
                  <col className="w-[110px]" />
                  <col className="w-[190px]" />
                  <col className="w-[100px]" />
                </colgroup>
                <thead className="sticky top-0 z-[1] bg-slate-50 text-xs uppercase tracking-[0.14em] text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Time</th>
                    <th className="px-4 py-3 font-semibold">User</th>
                    <th className="px-4 py-3 font-semibold">Action</th>
                    <th className="px-4 py-3 font-semibold">Resource</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold">Hash</th>
                    <th className="px-4 py-3 font-semibold" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredEvents.map((event) => {
                    const expanded = expandedEventId === event.event_id;
                    return (
                      <Fragment key={event.event_id}>
                        <tr className={expanded ? 'bg-[#fffaf6]' : 'bg-white hover:bg-slate-50'}>
                          <td className="px-4 py-4 text-slate-700">{formatDate(event.timestamp)}</td>
                          <td className="px-4 py-4">
                            <p className="truncate font-semibold text-slate-950">{event.user_email || 'System'}</p>
                            <p className="truncate text-xs text-slate-500">{event.organization_id || 'Organization not set'}</p>
                          </td>
                          <td className="px-4 py-4">
                            <p className="font-semibold text-slate-950">{eventTitle(event)}</p>
                            <p className="text-xs text-slate-500">{event.action}</p>
                          </td>
                          <td className="px-4 py-4">
                            <p className="truncate text-slate-700">{event.mission_id || 'No mission'}</p>
                            <p className="truncate text-xs text-slate-500">{event.resource_type || 'resource'} · {event.resource_id || 'n/a'}</p>
                          </td>
                          <td className="px-4 py-4">
                            <span className={`rounded-xl px-3 py-1 text-xs font-semibold ${event.status === 'failure' ? 'bg-rose-50 text-rose-700' : 'bg-emerald-50 text-emerald-700'}`}>
                              {event.status}
                            </span>
                          </td>
                          <td className="px-4 py-4 font-mono text-xs text-slate-600">{shortHash(event.hash)}</td>
                          <td className="px-4 py-4 text-right">
                            <button
                              type="button"
                              onClick={() => setExpandedEventId(expanded ? null : event.event_id)}
                              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition hover:border-[#ef5b0c]/40 hover:text-[#c74634]"
                            >
                              Details
                              <ChevronDown className={`h-4 w-4 transition ${expanded ? 'rotate-180' : ''}`} />
                            </button>
                          </td>
                        </tr>
                        {expanded ? (
                          <tr className="bg-[#fffaf6]">
                            <td colSpan={7} className="px-4 pb-5">
                              <div className="grid gap-4 rounded-2xl border border-[#ffd8c2] bg-white p-4 lg:grid-cols-[1fr_1fr]">
                                <div>
                                  <p className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
                                    <Fingerprint className="h-4 w-4 text-[#ef5b0c]" />
                                    Integrity details
                                  </p>
                                  <div className="space-y-2 text-xs text-slate-600">
                                    <p><span className="font-semibold text-slate-800">Event ID:</span> {event.event_id}</p>
                                    <p><span className="font-semibold text-slate-800">Hash:</span> <span className="font-mono">{event.hash}</span></p>
                                    <p><span className="font-semibold text-slate-800">Previous:</span> <span className="font-mono">{event.previous_hash}</span></p>
                                    <p><span className="font-semibold text-slate-800">IP:</span> {event.ip_address || 'Not captured'}</p>
                                    <p><span className="font-semibold text-slate-800">User agent:</span> {event.user_agent || 'Not captured'}</p>
                                  </div>
                                </div>
                                <div>
                                  <div className="mb-2 flex items-center justify-between gap-3">
                                    <p className="text-sm font-semibold text-slate-900">Metadata</p>
                                    <button
                                      type="button"
                                      onClick={() => void navigator.clipboard?.writeText(JSON.stringify(event, null, 2))}
                                      className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:border-slate-300"
                                    >
                                      <Copy className="h-3.5 w-3.5" />
                                      Copy event
                                    </button>
                                  </div>
                                  <p className="mb-2 text-xs text-slate-500">{metadataSummary(event)}</p>
                                  <pre className="max-h-44 overflow-auto rounded-xl bg-slate-950 p-3 text-xs text-slate-100">
                                    {JSON.stringify(event.metadata_json || {}, null, 2)}
                                  </pre>
                                </div>
                              </div>
                            </td>
                          </tr>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}
      </section>
    </div>
  );
}
