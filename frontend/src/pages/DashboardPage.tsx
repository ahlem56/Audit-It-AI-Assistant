import { useEffect, useMemo, useRef, useState } from 'react';
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
import logo from '../assets/pwc-logo.png';

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

type ReadinessItem = {
  label: string;
  detail: string;
  complete: boolean;
};

type RiskHeatmapRow = {
  area: string;
  Critical: number;
  High: number;
  Medium: number;
  Low: number;
  total: number;
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

const ALL_MISSIONS = 'all';

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

function missionLabel(mission: Mission) {
  const parts = [mission.name, mission.client, mission.fiscal_year].filter(Boolean);
  return parts.length ? parts.join(' - ') : mission.mission_id;
}

function compactMissionLabel(mission: Mission) {
  const primary = mission.client || mission.name || mission.mission_id;
  return mission.fiscal_year ? `${primary} - ${mission.fiscal_year}` : primary;
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

function healthTone(score: number) {
  if (score >= 85) return 'text-emerald-700 bg-emerald-50 ring-emerald-100';
  if (score >= 65) return 'text-amber-700 bg-amber-50 ring-amber-100';
  return 'text-red-700 bg-red-50 ring-red-100';
}

function heatmapCellClass(value: number, maxValue: number, priority: PriorityLevel) {
  if (value === 0) return 'bg-slate-50 text-slate-300';
  const intensity = maxValue > 0 ? value / maxValue : 0;
  const opacity = intensity > 0.66 ? 'text-white' : 'text-slate-900';
  const color =
    priority === 'Critical'
      ? 'bg-red-600'
      : priority === 'High'
      ? 'bg-orange-500'
      : priority === 'Medium'
      ? 'bg-amber-300'
      : 'bg-stone-200';
  return `${color} ${opacity}`;
}

export default function DashboardPage() {
  const { user } = useAuthContext();
  const { activeMission, missions, loadMissions } = useMissionContext();
  const [dashboardData, setDashboardData] = useState<MissionDashboardData[]>([]);
  const [selectedMissionId, setSelectedMissionId] = useState(ALL_MISSIONS);
  const [filterTransitionKey, setFilterTransitionKey] = useState(0);
  const [filterTransitionActive, setFilterTransitionActive] = useState(false);
  const [loadingDashboard, setLoadingDashboard] = useState(false);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const filterFrameRef = useRef<number | null>(null);
  const filterTimerRef = useRef<number | null>(null);

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

  useEffect(() => {
    return () => {
      if (filterFrameRef.current) window.cancelAnimationFrame(filterFrameRef.current);
      if (filterTimerRef.current) window.clearTimeout(filterTimerRef.current);
    };
  }, []);

  const triggerFilterTransition = () => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    if (filterFrameRef.current) window.cancelAnimationFrame(filterFrameRef.current);
    if (filterTimerRef.current) window.clearTimeout(filterTimerRef.current);

    setFilterTransitionKey((current) => current + 1);
    setFilterTransitionActive(false);
    filterFrameRef.current = window.requestAnimationFrame(() => setFilterTransitionActive(true));
    filterTimerRef.current = window.setTimeout(() => setFilterTransitionActive(false), 820);
  };

  const handleMissionFilterChange = (missionId: string) => {
    if (missionId === selectedMissionId) return;
    triggerFilterTransition();
    setSelectedMissionId(missionId);
  };

  useEffect(() => {
    if (
      selectedMissionId !== ALL_MISSIONS &&
      dashboardData.length > 0 &&
      !dashboardData.some((entry) => entry.mission.mission_id === selectedMissionId)
    ) {
      setSelectedMissionId(ALL_MISSIONS);
    }
  }, [dashboardData, selectedMissionId]);

  const filteredDashboardData = useMemo(
    () =>
      selectedMissionId === ALL_MISSIONS
        ? dashboardData
        : dashboardData.filter((entry) => entry.mission.mission_id === selectedMissionId),
    [dashboardData, selectedMissionId]
  );

  const selectedMission = useMemo(
    () => dashboardData.find((entry) => entry.mission.mission_id === selectedMissionId)?.mission ?? null,
    [dashboardData, selectedMissionId]
  );

  const dashboardScopeLabel = selectedMission ? missionLabel(selectedMission) : 'All missions';
  const dashboardScopeText = selectedMission
    ? 'Dashboard scoped to the selected mission.'
    : 'Dashboard scoped to every visible mission.';

  const allObservations = useMemo(
    () => filteredDashboardData.flatMap((entry) => entry.observations),
    [filteredDashboardData]
  );

  const allFeedbacks = useMemo(
    () => filteredDashboardData.flatMap((entry) => entry.feedbacks),
    [filteredDashboardData]
  );

  const activeMissions = useMemo(
    () => filteredDashboardData.filter((entry) => entry.mission.status !== 'Finalized').length,
    [filteredDashboardData]
  );

  const finalizedMissions = useMemo(
    () => filteredDashboardData.filter((entry) => entry.mission.status === 'Finalized').length,
    [filteredDashboardData]
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
      filteredDashboardData
        .map((entry) => entry.qualityGate?.readiness_score)
        .filter((value): value is number => typeof value === 'number'),
    [filteredDashboardData]
  );

  const reportsBlocked = useMemo(
    () => filteredDashboardData.filter((entry) => entry.qualityGate && !entry.qualityGate.export_allowed).length,
    [filteredDashboardData]
  );

  const workflowSteps: WorkflowStep[] = useMemo(() => {
    const total = filteredDashboardData.length;
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
        count: filteredDashboardData.filter((entry) => hasExcelUploaded(entry.mission)).length,
        total,
        icon: FileSpreadsheet
      },
      {
        key: 'parsed',
        label: 'Observations parsed',
        count: filteredDashboardData.filter((entry) => hasObservationsParsed(entry.mission, entry.observations)).length,
        total,
        icon: ListChecks
      },
      {
        key: 'validated',
        label: 'Observations validated',
        count: filteredDashboardData.filter(allValidated).length,
        total,
        icon: FileCheck2
      },
      {
        key: 'generated',
        label: 'Report generated',
        count: filteredDashboardData.filter((entry) => hasReportGenerated(entry.mission)).length,
        total,
        icon: Target
      },
      {
        key: 'quality',
        label: 'Quality gate passed',
        count: filteredDashboardData.filter((entry) => entry.qualityGate?.export_allowed).length,
        total,
        icon: ShieldAlert
      },
      {
        key: 'exported',
        label: 'Report exported',
        count: filteredDashboardData.filter((entry) => hasReportExported(entry.mission)).length,
        total,
        icon: Flag
      }
    ];
  }, [filteredDashboardData]);

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
  const generatedReports = filteredDashboardData.filter((entry) => hasReportGenerated(entry.mission)).length;
  const exportedReports = filteredDashboardData.filter((entry) => hasReportExported(entry.mission)).length;
  const qualityGatePassed = filteredDashboardData.filter((entry) => entry.qualityGate?.export_allowed).length;
  const parsedMissions = filteredDashboardData.filter((entry) => hasObservationsParsed(entry.mission, entry.observations)).length;
  const roleLabel = user?.role === 'manager' ? 'Manager portfolio' : 'Auditor workspace';
  const visibleMissionCount = filteredDashboardData.length;

  const validationRate = percent(validatedCount, allObservations.length);
  const averageQualityScore = average(qualityScores);
  const reportGenerationRate = percent(generatedReports, visibleMissionCount);
  const exportRate = percent(exportedReports, visibleMissionCount);
  const feedbackClosureRate = allFeedbacks.length
    ? percent(allFeedbacks.filter((feedback) => feedback.status !== 'pending' && !feedback.requires_action).length, allFeedbacks.length)
    : 100;
  const riskControlScore = allObservations.length
    ? Math.max(0, 100 - percent(criticalHighCount, allObservations.length))
    : 0;
  const missionHealthScore = Math.round(
    validationRate * 0.3 +
      averageQualityScore * 0.25 +
      reportGenerationRate * 0.15 +
      exportRate * 0.1 +
      feedbackClosureRate * 0.1 +
      riskControlScore * 0.1
  );

  const readinessItems: ReadinessItem[] = [
    {
      label: 'Workbook parsed',
      detail: `${parsedMissions}/${visibleMissionCount || 0} mission${visibleMissionCount === 1 ? '' : 's'}`,
      complete: visibleMissionCount > 0 && parsedMissions === visibleMissionCount
    },
    {
      label: 'Observations validated',
      detail: `${validatedCount}/${allObservations.length || 0} observations`,
      complete: allObservations.length > 0 && validatedCount === allObservations.length
    },
    {
      label: 'Report generated',
      detail: `${generatedReports}/${visibleMissionCount || 0} mission${visibleMissionCount === 1 ? '' : 's'}`,
      complete: visibleMissionCount > 0 && generatedReports === visibleMissionCount
    },
    {
      label: 'Quality Gate passed',
      detail: `${qualityGatePassed}/${visibleMissionCount || 0} mission${visibleMissionCount === 1 ? '' : 's'}`,
      complete: visibleMissionCount > 0 && qualityGatePassed === visibleMissionCount
    },
    {
      label: 'Report exported',
      detail: `${exportedReports}/${visibleMissionCount || 0} mission${visibleMissionCount === 1 ? '' : 's'}`,
      complete: visibleMissionCount > 0 && exportedReports === visibleMissionCount
    }
  ];

  const riskHeatmapRows = useMemo<RiskHeatmapRow[]>(() => {
    const rows = new Map<string, RiskHeatmapRow>();

    allObservations.forEach((observation) => {
      const area =
        observation.domaine_controle ||
        observation.domain ||
        observation.categorie_controle ||
        observation.category ||
        'Unclassified';
      const priority = observation.priority || 'Low';
      const row = rows.get(area) || { area, Critical: 0, High: 0, Medium: 0, Low: 0, total: 0 };

      row[priority] += 1;
      row.total += 1;
      rows.set(area, row);
    });

    return Array.from(rows.values())
      .sort((left, right) => right.Critical - left.Critical || right.High - left.High || right.total - left.total)
      .slice(0, 5);
  }, [allObservations]);

  const maxHeatmapValue = Math.max(
    1,
    ...riskHeatmapRows.flatMap((row) => [row.Critical, row.High, row.Medium, row.Low])
  );

  const topRiskArea = riskHeatmapRows[0]?.area || 'No risk area yet';
  const qualityIssueSummary = useMemo(() => {
    const counts = new Map<string, { title: string; count: number; severity: 'blocking' | 'warning' }>();

    filteredDashboardData.forEach((entry) => {
      entry.qualityGate?.issues?.forEach((issue) => {
        const key = issue.rule_id || issue.title;
        const current = counts.get(key) || { title: issue.title, count: 0, severity: issue.severity };
        current.count += 1;
        current.severity = current.severity === 'blocking' || issue.severity === 'blocking' ? 'blocking' : 'warning';
        counts.set(key, current);
      });
    });

    return Array.from(counts.values())
      .sort((left, right) => {
        if (left.severity !== right.severity) return left.severity === 'blocking' ? -1 : 1;
        return right.count - left.count;
      })
      .slice(0, 4);
  }, [filteredDashboardData]);

  const actionCenterItems = useMemo<ActionCenterItem[]>(() => {
    const invalidObservations = allObservations.length - validatedCount;
    const reportsNotExported = filteredDashboardData.filter((entry) => hasReportGenerated(entry.mission) && !hasReportExported(entry.mission)).length;
    const missionsWithoutGeneratedReport = filteredDashboardData.filter(
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
  }, [actionFeedbackCount, allObservations.length, filteredDashboardData, reportsBlocked, validatedCount]);

  const executiveSnapshot = [
    {
      label: 'Health',
      value: `${missionHealthScore}%`,
      detail: missionHealthScore >= 85 ? 'Ready for leadership review.' : missionHealthScore >= 65 ? 'Needs targeted follow-up.' : 'Requires immediate attention.'
    },
    {
      label: 'Top risk area',
      value: topRiskArea,
      detail: criticalHighCount > 0 ? `${criticalHighCount} Critical / High observation${criticalHighCount === 1 ? '' : 's'}` : 'No Critical / High observations.'
    },
    {
      label: 'Quality Gate',
      value: reportsBlocked > 0 ? `${reportsBlocked} blocked` : 'Clear',
      detail: qualityScores.length ? `${averageQualityScore}% average readiness score.` : 'No Quality Gate data yet.'
    },
    {
      label: 'Next action',
      value: actionCenterItems[0]?.title || 'No action',
      detail: actionCenterItems[0]?.detail || 'Scope is currently clean.'
    }
  ];

  return (
    <>
    <div className={`dashboard-studio space-y-6 ${filterTransitionActive ? 'pwc-mission-page-enter' : ''}`}>
      <section className="dashboard-studio-hero">
        <div className="dashboard-studio-brand">
          <span>{roleLabel}</span>
          <strong>{dashboardScopeLabel} / {visibleMissionCount} mission{visibleMissionCount === 1 ? '' : 's'}</strong>
        </div>

        <div className="dashboard-studio-command">
          <div>
            <h1>Audit Performance Dashboard</h1>
            <p>
              Dynamic overview of quality gates, validation progress, report blockers, and reviewer feedback.
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

      <div className="dashboard-studio-panel">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-900">Filtre par mission</p>
            <p className="mt-1 text-sm text-slate-500">{dashboardScopeText}</p>
          </div>
          <label className="w-full lg:max-w-xs">
            <span className="sr-only">Mission</span>
            <select
              value={selectedMissionId}
              onChange={(event) => handleMissionFilterChange(event.target.value)}
              className="h-11 w-full truncate rounded-xl border border-slate-200 bg-white px-3 text-sm font-medium text-slate-700 shadow-sm outline-none transition focus:border-[#ef5b0c] focus:ring-4 focus:ring-orange-100"
              disabled={loadingDashboard || dashboardData.length === 0}
            >
              <option value={ALL_MISSIONS}>Toutes les missions</option>
              {dashboardData.map((entry) => (
                <option key={entry.mission.mission_id} value={entry.mission.mission_id}>
                  {compactMissionLabel(entry.mission)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Total missions"
          value={formatNumber(visibleMissionCount)}
          helper={selectedMission ? 'Selected mission in scope.' : 'Missions accessible to the current user role.'}
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

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <div className="dashboard-studio-panel">
          <div className="mb-6 flex items-start justify-between gap-4">
            <div>
              <p className="text-sm text-slate-500">Command center</p>
              <h2 className="mt-2 text-lg font-semibold text-slate-900">Mission health and executive snapshot</h2>
            </div>
            <span className={`inline-flex shrink-0 rounded-2xl px-4 py-2 text-sm font-semibold ring-1 ${healthTone(missionHealthScore)}`}>
              {missionHealthScore}%
            </span>
          </div>

          <div className="grid gap-3 sm:grid-cols-2">
            {executiveSnapshot.map((item) => (
              <div key={item.label} className="rounded-2xl border border-slate-100 bg-white/75 p-4">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">{item.label}</p>
                <p className="mt-2 line-clamp-2 text-base font-semibold text-slate-950">{item.value}</p>
                <p className="mt-2 text-xs leading-5 text-slate-500">{item.detail}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="dashboard-studio-panel">
          <div className="mb-6">
            <p className="text-sm text-slate-500">Report readiness</p>
            <h2 className="mt-2 text-lg font-semibold text-slate-900">Delivery checklist</h2>
          </div>

          <div className="grid gap-3 md:grid-cols-5">
            {readinessItems.map((item) => (
              <div key={item.label} className="rounded-2xl border border-slate-100 bg-white/75 p-4">
                <span className={`inline-flex h-9 w-9 items-center justify-center rounded-xl ${item.complete ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                  {item.complete ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
                </span>
                <p className="mt-3 min-h-[40px] text-sm font-semibold leading-5 text-slate-900">{item.label}</p>
                <p className="mt-2 text-xs text-slate-500">{item.detail}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_0.75fr]">
        <div className="dashboard-studio-panel">
          <div className="mb-6 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-sm text-slate-500">Risk heatmap</p>
              <h2 className="mt-2 text-lg font-semibold text-slate-900">Risk concentration by control area</h2>
            </div>
            <p className="text-sm text-slate-500">Top {riskHeatmapRows.length} area{riskHeatmapRows.length === 1 ? '' : 's'}</p>
          </div>

          {riskHeatmapRows.length === 0 ? (
            <EmptyPanel title="No risk concentration yet" message="Parsed observations will populate the control-area heatmap." />
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-[640px] text-left text-sm">
                <thead className="text-xs uppercase tracking-[0.14em] text-slate-400">
                  <tr>
                    <th className="pb-3 font-semibold">Area</th>
                    {(['Critical', 'High', 'Medium', 'Low'] as PriorityLevel[]).map((priority) => (
                      <th key={priority} className="pb-3 text-center font-semibold">{priority}</th>
                    ))}
                    <th className="pb-3 text-right font-semibold">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {riskHeatmapRows.map((row) => (
                    <tr key={row.area}>
                      <td className="max-w-[240px] py-3 pr-4 font-medium text-slate-800">
                        <span className="line-clamp-2">{row.area}</span>
                      </td>
                      {(['Critical', 'High', 'Medium', 'Low'] as PriorityLevel[]).map((priority) => (
                        <td key={priority} className="py-3 text-center">
                          <span className={`inline-flex h-9 min-w-9 items-center justify-center rounded-xl px-3 text-sm font-semibold ${heatmapCellClass(row[priority], maxHeatmapValue, priority)}`}>
                            {row[priority]}
                          </span>
                        </td>
                      ))}
                      <td className="py-3 text-right font-semibold text-slate-900">{row.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="dashboard-studio-panel">
          <div className="mb-6">
            <p className="text-sm text-slate-500">Quality Gate breakdown</p>
            <h2 className="mt-2 text-lg font-semibold text-slate-900">Main blockers and warnings</h2>
          </div>

          {qualityIssueSummary.length === 0 ? (
            <EmptyPanel title="No Quality Gate issues" message="Generated reports with Quality Gate checks will show blockers here." />
          ) : (
            <div className="space-y-3">
              {qualityIssueSummary.map((issue) => (
                <div
                  key={`${issue.severity}-${issue.title}`}
                  className={`rounded-2xl border p-4 ${issue.severity === 'blocking' ? 'border-red-100 bg-red-50 text-red-700' : 'border-amber-100 bg-amber-50 text-amber-700'}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-semibold leading-5">{issue.title}</p>
                    <span className="shrink-0 rounded-full bg-white/70 px-2.5 py-1 text-xs font-semibold">
                      {issue.count}
                    </span>
                  </div>
                  <p className="mt-2 text-xs uppercase tracking-[0.14em] opacity-75">{issue.severity}</p>
                </div>
              ))}
            </div>
          )}
        </div>
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
    {filterTransitionKey > 0 && (
      <div key={filterTransitionKey} className="pwc-mission-transition" aria-hidden="true">
        <div className="pwc-mission-transition-surface">
          <span className="pwc-mission-transition-line pwc-mission-transition-yellow" />
          <span className="pwc-mission-transition-line pwc-mission-transition-red" />
          <span className="pwc-mission-transition-line pwc-mission-transition-orange" />
          <div className="pwc-mission-transition-label">
            <img src={logo} alt="" />
            <div>
              <span>Dashboard scope</span>
              <strong>Refreshing mission view</strong>
            </div>
          </div>
        </div>
      </div>
    )}
    </>
  );
}
