import { useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileCheck2,
  FileSpreadsheet,
  Flag,
  ListChecks,
  Loader2,
  MessageSquareText,
  RefreshCcw,
  ShieldAlert,
  Star,
  Target,
  TrendingUp
} from 'lucide-react';
import { getMissionFeedbacks, getMissionObservations, getMissionQualityGate } from '../services/api';
import { useAuthContext } from '../context/AuthContext';
import { useMissionContext } from '../context/MissionContext';
import type { AuditorFeedback, Mission, MissionQualityGateResult, Observation, PriorityLevel } from '../types';

type MissionDashboardData = {
  mission: Mission;
  observations: Observation[];
  feedbacks: AuditorFeedback[];
  qualityGate: MissionQualityGateResult | null;
};

type WorkflowStep = {
  key: string;
  label: string;
  count: number;
  total: number;
  icon: typeof CheckCircle2;
};

type ActionCenterItem = {
  key: string;
  title: string;
  detail: string;
  severity: 'critical' | 'warning' | 'info' | 'success';
};

const priorityColors: Record<PriorityLevel, string> = {
  Critical: '#c74634',
  High: '#ef5b0c',
  Medium: '#ffb600',
  Low: '#d6d3d1'
};

const feedbackCategoryLabels: Record<string, string> = {
  report_quality: 'Report quality',
  priority_logic: 'Priority logic',
  recommendations: 'Recommendations',
  ppt_design: 'PPT design',
  data_accuracy: 'Data accuracy',
  missing_content: 'Missing content',
  usability: 'Usability'
};

function percent(value: number, total: number) {
  if (total <= 0) return 0;
  return Math.round((value / total) * 100);
}

function formatNumber(value: number) {
  return new Intl.NumberFormat().format(value);
}

function isObservationValidated(observation: Observation) {
  return String(observation.status || observation.statut_validation || '').trim().toLowerCase() === 'validated';
}

function hasExcelUploaded(mission: Mission) {
  return Boolean(mission.current_file?.name || mission.parsing_status === 'parsed' || mission.parsing_status === 'parsing');
}

function hasObservationsParsed(mission: Mission, observations: Observation[]) {
  return mission.parsing_status === 'parsed' || observations.length > 0 || Number(mission.observations_count || 0) > 0;
}

function hasReportGenerated(mission: Mission) {
  return Boolean(mission.report_generated_at || mission.workflow?.report_generated);
}

function hasReportExported(mission: Mission) {
  return Boolean(mission.exported_at);
}

function average(values: number[]) {
  if (!values.length) return 0;
  return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
}

function mostCommon(values: string[], limit = 2) {
  const counts = new Map<string, number>();
  values
    .map((value) => value.trim())
    .filter(Boolean)
    .forEach((value) => counts.set(value, (counts.get(value) || 0) + 1));

  return Array.from(counts.entries())
    .sort((left, right) => right[1] - left[1])
    .slice(0, limit)
    .map(([value]) => value);
}

function joinReadable(values: string[]) {
  if (values.length === 0) return '';
  if (values.length === 1) return values[0];
  return `${values.slice(0, -1).join(', ')} and ${values[values.length - 1]}`;
}

function KpiCard({
  label,
  value,
  helper,
  icon: Icon,
  tone = 'default'
}: {
  label: string;
  value: string;
  helper: string;
  icon: typeof Target;
  tone?: 'default' | 'warning' | 'danger' | 'success';
}) {
  const toneClass =
    tone === 'danger'
      ? 'bg-red-50 text-red-700 ring-red-100'
      : tone === 'warning'
      ? 'bg-amber-50 text-amber-700 ring-amber-100'
      : tone === 'success'
      ? 'bg-emerald-50 text-emerald-700 ring-emerald-100'
      : 'bg-[#fff3eb] text-[#ef5b0c] ring-orange-100';

  return (
    <div className="dashboard-studio-kpi">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm text-slate-500">{label}</p>
          <p className="mt-3 text-3xl font-semibold text-slate-950">{value}</p>
        </div>
        <span className={`inline-flex h-11 w-11 items-center justify-center rounded-2xl ring-1 ${toneClass}`}>
          <Icon className="h-5 w-5" />
        </span>
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-500">{helper}</p>
    </div>
  );
}

function EmptyPanel({ title, message }: { title: string; message: string }) {
  return (
    <div className="dashboard-studio-empty">
      <div>
        <p className="text-sm font-semibold text-slate-800">{title}</p>
        <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">{message}</p>
      </div>
    </div>
  );
}

function actionSeverityClass(severity: ActionCenterItem['severity']) {
  if (severity === 'critical') return 'border-red-100 bg-red-50 text-red-700';
  if (severity === 'warning') return 'border-amber-100 bg-amber-50 text-amber-700';
  if (severity === 'success') return 'border-emerald-100 bg-emerald-50 text-emerald-700';
  return 'border-slate-200 bg-white/80 text-slate-700';
}

export default function DashboardPage() {
  const { user } = useAuthContext();
  const { activeMission, missions, loadMissions } = useMissionContext();
  const [dashboardData, setDashboardData] = useState<MissionDashboardData[]>([]);
  const [loadingDashboard, setLoadingDashboard] = useState(false);
  const [dashboardError, setDashboardError] = useState<string | null>(null);

  const loadDashboardData = async () => {
    setLoadingDashboard(true);
    setDashboardError(null);

    try {
      if (!missions.length) {
        await loadMissions();
        return;
      }

      const data = await Promise.all(
        missions.map(async (mission) => {
          const [observationsResult, feedbacksResult, qualityGateResult] = await Promise.allSettled([
            getMissionObservations(mission.mission_id),
            getMissionFeedbacks(mission.mission_id),
            hasReportGenerated(mission) ? getMissionQualityGate(mission.mission_id) : Promise.resolve(null)
          ]);

          return {
            mission,
            observations:
              observationsResult.status === 'fulfilled' ? observationsResult.value.observations : [],
            feedbacks: feedbacksResult.status === 'fulfilled' ? feedbacksResult.value : [],
            qualityGate: qualityGateResult.status === 'fulfilled' ? qualityGateResult.value : null
          };
        })
      );

      setDashboardData(data);
    } catch (error) {
      console.error('Failed to load dashboard data:', error);
      setDashboardError(error instanceof Error ? error.message : 'Failed to load dashboard data.');
      setDashboardData([]);
    } finally {
      setLoadingDashboard(false);
    }
  };

  useEffect(() => {
    void loadDashboardData();
  }, [missions]);

  const allObservations = useMemo(
    () => dashboardData.flatMap((entry) => entry.observations),
    [dashboardData]
  );

  const allFeedbacks = useMemo(
    () => dashboardData.flatMap((entry) => entry.feedbacks),
    [dashboardData]
  );

  const activeMissions = useMemo(
    () => dashboardData.filter((entry) => entry.mission.status !== 'Finalized').length,
    [dashboardData]
  );

  const finalizedMissions = useMemo(
    () => dashboardData.filter((entry) => entry.mission.status === 'Finalized').length,
    [dashboardData]
  );

  const criticalHighCount = useMemo(
    () => allObservations.filter((observation) => observation.priority === 'Critical' || observation.priority === 'High').length,
    [allObservations]
  );

  const validatedCount = useMemo(
    () => allObservations.filter(isObservationValidated).length,
    [allObservations]
  );

  const qualityScores = useMemo(
    () =>
      dashboardData
        .map((entry) => entry.qualityGate?.readiness_score)
        .filter((value): value is number => typeof value === 'number'),
    [dashboardData]
  );

  const reportsBlocked = useMemo(
    () => dashboardData.filter((entry) => entry.qualityGate && !entry.qualityGate.export_allowed).length,
    [dashboardData]
  );

  const workflowSteps: WorkflowStep[] = useMemo(() => {
    const total = dashboardData.length;
    const allValidated = (entry: MissionDashboardData) =>
      entry.observations.length > 0 && entry.observations.every(isObservationValidated);

    return [
      {
        key: 'created',
        label: 'Mission created',
        count: total,
        total,
        icon: CheckCircle2
      },
      {
        key: 'excel',
        label: 'Excel uploaded',
        count: dashboardData.filter((entry) => hasExcelUploaded(entry.mission)).length,
        total,
        icon: FileSpreadsheet
      },
      {
        key: 'parsed',
        label: 'Observations parsed',
        count: dashboardData.filter((entry) => hasObservationsParsed(entry.mission, entry.observations)).length,
        total,
        icon: ListChecks
      },
      {
        key: 'validated',
        label: 'Observations validated',
        count: dashboardData.filter(allValidated).length,
        total,
        icon: FileCheck2
      },
      {
        key: 'generated',
        label: 'Report generated',
        count: dashboardData.filter((entry) => hasReportGenerated(entry.mission)).length,
        total,
        icon: Target
      },
      {
        key: 'quality',
        label: 'Quality gate passed',
        count: dashboardData.filter((entry) => entry.qualityGate?.export_allowed).length,
        total,
        icon: ShieldAlert
      },
      {
        key: 'exported',
        label: 'Report exported',
        count: dashboardData.filter((entry) => hasReportExported(entry.mission)).length,
        total,
        icon: Flag
      }
    ];
  }, [dashboardData]);

  const priorityData = useMemo(() => {
    const totals: Record<PriorityLevel, number> = {
      Critical: 0,
      High: 0,
      Medium: 0,
      Low: 0
    };

    allObservations.forEach((observation) => {
      const priority = observation.priority || 'Low';
      totals[priority] += 1;
    });

    return Object.entries(totals).map(([name, value]) => ({
      name,
      value
    }));
  }, [allObservations]);

  const priorityInsightSummary = useMemo(() => {
    const total = allObservations.length;
    const highRiskObservations = allObservations.filter(
      (observation) => observation.priority === 'Critical' || observation.priority === 'High'
    );
    const highRiskCount = highRiskObservations.length;
    const highRiskRate = percent(highRiskCount, total);
    const concentrationCandidates = mostCommon([
      ...highRiskObservations.map((observation) => observation.domaine_controle || observation.domain || ''),
      ...highRiskObservations.map((observation) => observation.categorie_controle || observation.category || '')
    ]);
    const concentrationText = concentrationCandidates.length
      ? `Most risks are concentrated in ${joinReadable(concentrationCandidates)}.`
      : 'Risk concentration will appear once control domains or categories are available.';

    if (total === 0) {
      return [
        'No observations have been parsed yet.',
        'Priority insights will appear after importing an audit workbook.',
        'Risk concentration will be calculated from the observation domains and categories.'
      ];
    }

    return [
      `${formatNumber(highRiskCount)} high-risk observation${highRiskCount === 1 ? '' : 's'} detected.`,
      `Critical and High represent ${highRiskRate}% of all findings.`,
      concentrationText
    ];
  }, [allObservations]);

  const feedbackCategoryData = useMemo(() => {
    const totals = new Map<string, number>();

    allFeedbacks.forEach((feedback) => {
      feedback.categories.forEach((category) => {
        totals.set(category, (totals.get(category) || 0) + 1);
      });
    });

    return Array.from(totals.entries())
      .map(([category, count]) => ({
        category: feedbackCategoryLabels[category] || category,
        count
      }))
      .sort((left, right) => right.count - left.count);
  }, [allFeedbacks]);

  const latestFeedbacks = useMemo(
    () =>
      [...allFeedbacks]
        .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())
        .slice(0, 4),
    [allFeedbacks]
  );

  const averageRating = useMemo(
    () => {
      const ratings = allFeedbacks
        .map((feedback) => feedback.rating)
        .filter((rating): rating is 1 | 2 | 3 | 4 | 5 => typeof rating === 'number');
      if (!ratings.length) return 'N/A';
      return (ratings.reduce((sum, rating) => sum + rating, 0) / ratings.length).toFixed(1);
    },
    [allFeedbacks]
  );

  const pendingFeedbackCount = allFeedbacks.filter((feedback) => feedback.status === 'pending').length;
  const actionFeedbackCount = allFeedbacks.filter((feedback) => feedback.requires_action).length;
  const roleLabel = user?.role === 'manager' ? 'Manager portfolio' : 'Auditor workspace';
  const visibleMissionCount = dashboardData.length;
  const actionCenterItems = useMemo<ActionCenterItem[]>(() => {
    const invalidObservations = allObservations.length - validatedCount;
    const reportsNotExported = dashboardData.filter((entry) => hasReportGenerated(entry.mission) && !hasReportExported(entry.mission)).length;
    const missionsWithoutGeneratedReport = dashboardData.filter(
      (entry) => hasObservationsParsed(entry.mission, entry.observations) && !hasReportGenerated(entry.mission)
    ).length;

    const items: ActionCenterItem[] = [];

    if (reportsBlocked > 0) {
      items.push({
        key: 'blocked-reports',
        title: `Resolve ${reportsBlocked} blocked report${reportsBlocked === 1 ? '' : 's'}`,
        detail: 'Review Quality Gate issues before export approval.',
        severity: 'critical'
      });
    }

    if (invalidObservations > 0) {
      items.push({
        key: 'validation-gap',
        title: `Validate ${formatNumber(invalidObservations)} remaining observation${invalidObservations === 1 ? '' : 's'}`,
        detail: `${percent(validatedCount, allObservations.length)}% validation progress across visible missions.`,
        severity: 'warning'
      });
    }

    if (actionFeedbackCount > 0) {
      items.push({
        key: 'feedback-actions',
        title: `Review ${actionFeedbackCount} feedback item${actionFeedbackCount === 1 ? '' : 's'} requiring action`,
        detail: 'Use reviewer comments to improve report quality and AI outputs.',
        severity: 'warning'
      });
    }

    if (reportsNotExported > 0) {
      items.push({
        key: 'export-gap',
        title: `Export ${reportsNotExported} generated report${reportsNotExported === 1 ? '' : 's'}`,
        detail: 'Generated reports are waiting for final delivery.',
        severity: 'info'
      });
    }

    if (missionsWithoutGeneratedReport > 0) {
      items.push({
        key: 'report-generation-gap',
        title: `Generate ${missionsWithoutGeneratedReport} pending report draft${missionsWithoutGeneratedReport === 1 ? '' : 's'}`,
        detail: 'Parsed missions can move forward to report review.',
        severity: 'info'
      });
    }

    if (items.length === 0) {
      items.push({
        key: 'all-clear',
        title: 'No urgent portfolio actions',
        detail: 'Visible missions have no blocked reports, validation gaps, or pending action feedback.',
        severity: 'success'
      });
    }

    return items.slice(0, 5);
  }, [actionFeedbackCount, allObservations.length, dashboardData, reportsBlocked, validatedCount]);

  return (
    <div className="dashboard-studio space-y-6">
      <section className="dashboard-studio-hero">
        <div className="dashboard-studio-brand">
          <span>{roleLabel}</span>
          <strong>{activeMission?.client || activeMission?.name || 'Portfolio'} / {visibleMissionCount} mission{visibleMissionCount === 1 ? '' : 's'}</strong>
        </div>

        <div className="dashboard-studio-command">
          <div>
            <h1>Audit Performance Dashboard</h1>
            <p>
              Dynamic overview of visible missions, quality gates, validation progress, report blockers, and reviewer feedback.
            </p>
          </div>

        </div>

        <div className="dashboard-studio-hero-footer">
          <span>Active mission: {activeMission?.name || 'none selected'}</span>
          <button
            type="button"
            onClick={() => void loadDashboardData()}
            disabled={loadingDashboard}
          >
            {loadingDashboard ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
            Refresh
          </button>
        </div>
      </section>

      {dashboardError && (
        <div className="rounded-3xl border border-red-100 bg-red-50 p-4 text-sm text-red-700">
          {dashboardError}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Total missions"
          value={formatNumber(visibleMissionCount)}
          helper="Missions accessible to the current user role."
          icon={Target}
        />
        <KpiCard
          label="Active missions"
          value={formatNumber(activeMissions)}
          helper={`${formatNumber(finalizedMissions)} finalized mission${finalizedMissions === 1 ? '' : 's'}.`}
          icon={TrendingUp}
          tone="success"
        />
        <KpiCard
          label="Total observations"
          value={formatNumber(allObservations.length)}
          helper={`${validatedCount}/${allObservations.length || 0} validated observations.`}
          icon={ListChecks}
        />
        <KpiCard
          label="Critical / High"
          value={formatNumber(criticalHighCount)}
          helper="Highest-risk observations detected across visible missions."
          icon={AlertTriangle}
          tone={criticalHighCount > 0 ? 'danger' : 'success'}
        />
        <KpiCard
          label="Validation progress"
          value={`${percent(validatedCount, allObservations.length)}%`}
          helper={`${formatNumber(validatedCount)} validated out of ${formatNumber(allObservations.length)} observations.`}
          icon={CheckCircle2}
          tone="success"
        />
        <KpiCard
          label="Average quality score"
          value={qualityScores.length ? `${average(qualityScores)}%` : 'N/A'}
          helper={`${qualityScores.length} mission${qualityScores.length === 1 ? '' : 's'} with available Quality Gate data.`}
          icon={ShieldAlert}
          tone={average(qualityScores) >= 80 ? 'success' : 'warning'}
        />
        <KpiCard
          label="Reports blocked"
          value={formatNumber(reportsBlocked)}
          helper="Reports currently blocked by Quality Gate checks."
          icon={Flag}
          tone={reportsBlocked > 0 ? 'danger' : 'success'}
        />
        <KpiCard
          label="Feedback requiring action"
          value={formatNumber(actionFeedbackCount)}
          helper={`${formatNumber(pendingFeedbackCount)} pending feedback item${pendingFeedbackCount === 1 ? '' : 's'}.`}
          icon={MessageSquareText}
          tone={actionFeedbackCount > 0 ? 'warning' : 'success'}
        />
      </div>

      <div className="dashboard-studio-panel">
        <div className="mb-6 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm text-slate-500">Mission workflow progress</p>
            <h2 className="mt-2 text-lg font-semibold text-slate-900">Where visible missions are in the audit lifecycle</h2>
          </div>
          <p className="text-sm text-slate-500">{formatNumber(visibleMissionCount)} mission{visibleMissionCount === 1 ? '' : 's'} in scope</p>
        </div>

        {visibleMissionCount === 0 ? (
          <EmptyPanel title="No missions yet" message="Create or assign missions to start building dashboard statistics." />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-7">
            {workflowSteps.map((step) => {
              const Icon = step.icon;
              const completion = percent(step.count, step.total);

              return (
                <div key={step.key} className="dashboard-studio-workflow">
                  <div className="flex items-center justify-between gap-3">
                    <span className="inline-flex h-10 w-10 items-center justify-center rounded-2xl bg-[#fff3eb] text-[#ef5b0c]">
                      <Icon className="h-5 w-5" />
                    </span>
                    <span className="text-sm font-semibold text-slate-900">{completion}%</span>
                  </div>
                  <p className="mt-4 min-h-[40px] text-sm font-semibold leading-5 text-slate-800">{step.label}</p>
                  <p className="mt-2 text-xs text-slate-500">{step.count}/{step.total} missions</p>
                  <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-[#ef5b0c]" style={{ width: `${completion}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_0.7fr]">
        <div className="dashboard-studio-panel">
          <div className="mb-6">
            <p className="text-sm text-slate-500">Priority distribution</p>
            <h2 className="mt-2 text-lg font-semibold text-slate-900">Critical, High, Medium, and Low observations</h2>
          </div>

          {allObservations.length === 0 ? (
            <EmptyPanel title="No observations parsed" message="Upload and parse an audit workbook to populate the priority distribution." />
          ) : (
            <div className="grid gap-6 md:grid-cols-[1fr_0.85fr]">
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={priorityData} dataKey="value" innerRadius={72} outerRadius={112} paddingAngle={4}>
                      {priorityData.map((entry) => (
                        <Cell key={entry.name} fill={priorityColors[entry.name as PriorityLevel]} />
                      ))}
                    </Pie>
                    <Tooltip />
                    <Legend />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="grid content-center gap-3">
                {priorityData.map((entry) => (
                  <div key={entry.name} className="dashboard-studio-list-row">
                    <span className="flex items-center gap-3 text-sm font-medium text-slate-700">
                      <span
                        className="h-3 w-3 rounded-full"
                        style={{ backgroundColor: priorityColors[entry.name as PriorityLevel] }}
                      />
                      {entry.name}
                    </span>
                    <span className="text-sm font-semibold text-slate-950">{entry.value}</span>
                  </div>
                ))}
              </div>
              <div className="dashboard-studio-insight md:col-span-2">
                <p className="text-sm font-semibold text-slate-900">Priority insight summary</p>
                <div className="mt-4 grid gap-3 md:grid-cols-3">
                  {priorityInsightSummary.map((insight) => (
                    <div key={insight} className="rounded-2xl bg-white/80 px-4 py-3 text-sm leading-6 text-slate-600 ring-1 ring-orange-100">
                      {insight}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="dashboard-studio-panel">
          <div className="mb-6">
            <p className="text-sm text-slate-500">Feedback summary</p>
            <h2 className="mt-2 text-lg font-semibold text-slate-900">User validation and improvement signals</h2>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="dashboard-studio-mini-stat">
              <Star className="h-5 w-5 text-[#ffb600]" />
              <p className="mt-3 text-sm text-slate-500">Average rating</p>
              <p className="mt-2 text-2xl font-semibold text-slate-950">{averageRating}</p>
            </div>
            <div className="dashboard-studio-mini-stat">
              <MessageSquareText className="h-5 w-5 text-[#ef5b0c]" />
              <p className="mt-3 text-sm text-slate-500">Pending</p>
              <p className="mt-2 text-2xl font-semibold text-slate-950">{pendingFeedbackCount}</p>
            </div>
            <div className="dashboard-studio-mini-stat">
              <AlertTriangle className="h-5 w-5 text-red-600" />
              <p className="mt-3 text-sm text-slate-500">Requires action</p>
              <p className="mt-2 text-2xl font-semibold text-slate-950">{actionFeedbackCount}</p>
            </div>
          </div>

          <div className="mt-6">
            <p className="text-sm font-semibold text-slate-900">Feedback by category</p>
            {feedbackCategoryData.length === 0 ? (
              <div className="mt-4 rounded-3xl border border-dashed border-slate-200 bg-white/50 p-6 text-sm text-slate-500">
                No categorized feedback yet.
              </div>
            ) : (
              <div className="mt-4 h-52">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={feedbackCategoryData} margin={{ left: -18, right: 8, bottom: 28 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="category" angle={-20} textAnchor="end" height={64} tick={{ fontSize: 11 }} />
                    <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#ef5b0c" radius={[10, 10, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          <div className="mt-6">
            <p className="text-sm font-semibold text-slate-900">Latest feedback comments</p>
            {latestFeedbacks.length === 0 ? (
              <div className="mt-4 rounded-3xl border border-dashed border-slate-200 bg-white/50 p-6 text-sm text-slate-500">
                No feedback comments have been submitted yet.
              </div>
            ) : (
              <div className="mt-4 space-y-3">
                {latestFeedbacks.map((feedback) => (
                  <div key={feedback.feedback_id} className="dashboard-studio-feedback-item">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{feedback.author || 'Auditor feedback'}</p>
                        <p className="mt-1 text-xs text-slate-500">{feedback.scope || 'report'} feedback</p>
                      </div>
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
                        {feedback.status}
                      </span>
                    </div>
                    <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-600">
                      {feedback.comment || 'No written comment provided.'}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="dashboard-studio-panel">
        <div className="mb-6 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm text-slate-500">Action center</p>
            <h2 className="mt-2 text-lg font-semibold text-slate-900">What needs attention now</h2>
          </div>
          <p className="text-sm text-slate-500">{actionCenterItems.length} prioritized action{actionCenterItems.length === 1 ? '' : 's'}</p>
        </div>

        <div className="grid gap-4 lg:grid-cols-5">
          {actionCenterItems.map((item) => (
            <div key={item.key} className={`rounded-3xl border p-4 ${actionSeverityClass(item.severity)}`}>
              <div className="flex items-start justify-between gap-3">
                <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-white/75">
                  {item.severity === 'critical' ? (
                    <AlertTriangle className="h-4 w-4" />
                  ) : item.severity === 'success' ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <ArrowRight className="h-4 w-4" />
                  )}
                </span>
              </div>
              <p className="mt-4 min-h-[48px] text-sm font-semibold leading-6">{item.title}</p>
              <p className="mt-2 text-xs leading-5 opacity-80">{item.detail}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
