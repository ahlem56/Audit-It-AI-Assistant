import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  Download,
  FileText,
  MessageCircleMore,
  Mail,
  ShieldCheck,
  ShieldX,
  Star,
  X,
  LayoutPanelLeft,
  BookOpenText,
  ShieldAlert,
  CheckCircle2,
  Sparkles
} from 'lucide-react';
import { useMissionContext } from '../context/MissionContext';
import type {
  CreateFeedbackPayload,
  FeedbackCategory,
  FeedbackSentiment,
  ReportStructuredOutput,
  ReportFinding,
  ReportEmailDefaults,
  MissionQualityGateResult
} from '../types';

const quickFeedbackPresets = [
  { label: 'Very good', rating: 5 as const, sentiment: 'positive' as FeedbackSentiment, categories: ['report_quality'] as FeedbackCategory[] },
  { label: 'Good but needs tuning', rating: 3 as const, sentiment: 'neutral' as FeedbackSentiment, categories: ['report_quality', 'recommendations'] as FeedbackCategory[] },
  { label: 'Not usable', rating: 1 as const, sentiment: 'negative' as FeedbackSentiment, categories: ['missing_content', 'data_accuracy'] as FeedbackCategory[] }
];

const emptyQuickFeedback: CreateFeedbackPayload = {
  scope: 'report',
  rating: 4,
  sentiment: 'neutral',
  categories: ['report_quality'],
  comment: '',
  requires_action: true
};

const sections = [
  { id: 'cover', label: 'Cover', icon: LayoutPanelLeft },
  { id: 'context', label: 'Context', icon: BookOpenText },
  { id: 'controls', label: 'Controls', icon: ShieldAlert },
  { id: 'synthesis', label: 'Synthesis', icon: FileText },
  { id: 'findings', label: 'Findings', icon: ShieldAlert },
  { id: 'export', label: 'Final review', icon: CheckCircle2 }
] as const;

type SectionId = (typeof sections)[number]['id'];

function TextBlock({ label, value, onChange, rows = 5 }: { label: string; value: string; onChange: (value: string) => void; rows?: number }) {
  return (
    <label className="block space-y-2">
      <span className="text-sm font-semibold text-slate-900">{label}</span>
      <textarea
        rows={rows}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-3xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm leading-6 text-slate-900"
      />
    </label>
  );
}

function reportPreviewSurface() {
  return 'pwc-report-cover';
}

function ListBlock({ label, items, onChange }: { label: string; items: string[]; onChange: (items: string[]) => void }) {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-slate-900">{label}</p>
        <button type="button" onClick={() => onChange([...items, ''])} className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50">
          Add item
        </button>
      </div>
      {items.length > 0 ? (
        items.map((item, index) => (
          <div key={`${label}-${index}`} className="flex gap-3">
            <textarea
              rows={2}
              value={item}
              onChange={(event) => {
                const next = [...items];
                next[index] = event.target.value;
                onChange(next);
              }}
              className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900"
            />
            <button type="button" onClick={() => onChange(items.filter((_, itemIndex) => itemIndex !== index))} className="rounded-2xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-100">
              Remove
            </button>
          </div>
        ))
      ) : (
        <p className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-4 py-4 text-sm text-slate-500">No items yet.</p>
      )}
    </div>
  );
}

function priorityPill(priority: string) {
  const normalized = priority.trim().toLowerCase();
  if (normalized === 'critical') return 'bg-red-100 text-red-700';
  if (normalized === 'high') return 'bg-orange-100 text-orange-700';
  if (normalized === 'medium') return 'bg-amber-100 text-amber-700';
  return 'bg-emerald-100 text-emerald-700';
}

export default function ReportPage() {
  const navigate = useNavigate();
  const { activeMission, reportPreview, qualityGate, loadingQualityGate, exportReportPptx, exportReportPdf, exportReportDocx, getReportEmailDefaults, sendReportEmail, activeMissionFeedback, submitFeedback } = useMissionContext();
  const [activeSection, setActiveSection] = useState<SectionId>('cover');
  const [draft, setDraft] = useState<ReportStructuredOutput | null>(null);
  const [expandedFindingId, setExpandedFindingId] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [downloadingDocx, setDownloadingDocx] = useState(false);
  const [showExportModal, setShowExportModal] = useState(false);
  const [loadingEmailDefaults, setLoadingEmailDefaults] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportWarning, setExportWarning] = useState<string | null>(null);
  const [sendByEmail, setSendByEmail] = useState(false);
  const [emailDefaultsLoaded, setEmailDefaultsLoaded] = useState(false);
  const [emailForm, setEmailForm] = useState<ReportEmailDefaults>({
    to_email: 'ahlem.bouchahoua@esprit.tn',
    subject: '',
    body: ''
  });
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);
  const [quickFeedback, setQuickFeedback] = useState<CreateFeedbackPayload>(emptyQuickFeedback);
  const [submittingQuickFeedback, setSubmittingQuickFeedback] = useState(false);

  useEffect(() => {
    setDraft(reportPreview?.structured_output ?? null);
  }, [reportPreview]);

  const effectiveQualityGate = useMemo<MissionQualityGateResult | null>(() => {
    if (qualityGate) return qualityGate;
    if (!draft) return null;
    return {
      mission_id: activeMission?.mission_id || '',
      ...draft.quality_gate
    };
  }, [activeMission?.mission_id, draft, qualityGate]);

  const readinessChecks = useMemo(() => {
    if (!draft) return [];
    return [
      { label: 'Cover title is defined', value: draft.cover_title.trim().length > 0 },
      { label: 'Executive summary is filled', value: draft.executive_summary.trim().length > 40 },
      { label: 'Conclusion is filled', value: draft.conclusion.trim().length > 20 },
      { label: 'All findings have recommendations', value: draft.detailed_findings.every((finding) => finding.recommendation.trim().length > 0) }
    ];
  }, [draft]);

  if (!activeMission) {
    return <div className="flex min-h-[50vh] items-center justify-center"><p className="text-slate-500">Please select a mission from the workspace first.</p></div>;
  }

  if (!draft) {
    return (
      <div className="space-y-6">
        <div>
          <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Report builder</p>
          <h1 className="text-3xl font-semibold text-slate-900">Report review studio</h1>
        </div>
        <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-card">
          <p className="text-sm text-slate-500">The report preview is still loading or no structured report draft is available for this mission yet.</p>
        </div>
      </div>
    );
  }

  const updateField = <K extends keyof ReportStructuredOutput>(field: K, value: ReportStructuredOutput[K]) => {
    setDraft((current) => (current ? { ...current, [field]: value } : current));
  };

  const updateFinding = (observationId: string, updater: (finding: ReportFinding) => ReportFinding) => {
    setDraft((current) =>
      current
        ? { ...current, detailed_findings: current.detailed_findings.map((finding) => (finding.observation_id === observationId ? updater(finding) : finding)) }
        : current
    );
  };

  const handleOpenExportModal = async () => {
    setShowExportModal(true);
    setExportError(null);
    setExportWarning(null);
    if (emailDefaultsLoaded) return;

    setLoadingEmailDefaults(true);
    try {
      const defaults = await getReportEmailDefaults();
      setEmailForm(defaults);
      setEmailDefaultsLoaded(true);
    } catch (error) {
      console.error('Failed to load report email defaults:', error);
      setExportError(error instanceof Error ? error.message : 'Failed to load email defaults.');
    } finally {
      setLoadingEmailDefaults(false);
    }
  };

  const handleExport = async () => {
    setDownloading(true);
    setExportError(null);
    setExportWarning(null);
    try {
      if (sendByEmail) {
        setSendingEmail(true);
        try {
          await sendReportEmail(emailForm);
        } catch (emailError) {
          console.error('Report email failed, continuing with PPTX export:', emailError);
          setExportWarning(
            emailError instanceof Error
              ? `Email was not sent: ${emailError.message}. The PPTX download will continue.`
              : 'Email was not sent. The PPTX download will continue.'
          );
        } finally {
          setSendingEmail(false);
        }
      }

      const blob = await exportReportPptx();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${activeMission.name}-Audit-Report.pptx`;
      link.click();
      URL.revokeObjectURL(link.href);
      setShowExportModal(false);
      setShowFeedbackModal(true);
    } catch (error) {
      console.error('Export failed:', error);
      setExportError(error instanceof Error ? error.message : 'Export failed.');
    } finally {
      setSendingEmail(false);
      setDownloading(false);
    }
  };

  const handleExportPdf = async () => {
    setDownloadingPdf(true);
    setExportError(null);
    try {
      const blob = await exportReportPdf();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${activeMission.name}-Audit-Report.pdf`;
      link.click();
      URL.revokeObjectURL(link.href);
      setShowFeedbackModal(true);
    } catch (error) {
      console.error('PDF export failed:', error);
      setExportError(error instanceof Error ? error.message : 'PDF export failed.');
    } finally {
      setDownloadingPdf(false);
    }
  };

  const handleExportDocx = async () => {
    setDownloadingDocx(true);
    setExportError(null);
    try {
      const blob = await exportReportDocx();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${activeMission.name}-Audit-Report.docx`;
      link.click();
      URL.revokeObjectURL(link.href);
      setShowFeedbackModal(true);
    } catch (error) {
      console.error('Word export failed:', error);
      setExportError(error instanceof Error ? error.message : 'Word export failed.');
    } finally {
      setDownloadingDocx(false);
    }
  };

  const handleQuickFeedbackPreset = (preset: (typeof quickFeedbackPresets)[number]) => {
    setQuickFeedback((current) => ({ ...current, rating: preset.rating, sentiment: preset.sentiment, categories: preset.categories }));
  };

  const handleQuickFeedbackSubmit = async () => {
    setSubmittingQuickFeedback(true);
    try {
      await submitFeedback(quickFeedback);
      setQuickFeedback(emptyQuickFeedback);
      setShowFeedbackModal(false);
    } catch (error) {
      console.error('Failed to submit quick feedback:', error);
    } finally {
      setSubmittingQuickFeedback(false);
    }
  };

  const renderSection = () => {
    switch (activeSection) {
      case 'cover':
        return (
          <section className="space-y-6">
            <div className={reportPreviewSurface()}>
              <p className="text-xs uppercase tracking-[0.22em] text-slate-400">{draft.confidentiality_notice || 'Confidential'}</p>
              <h2 className="pwc-report-cover-title mt-6 text-4xl font-semibold leading-tight text-slate-900">{draft.cover_title || 'Untitled report'}</h2>
              <p className="mt-3 max-w-2xl text-lg text-slate-600">{draft.cover_subtitle || 'Version projet'}</p>
            </div>
            <div className="grid gap-5 lg:grid-cols-2">
              <label className="space-y-2"><span className="text-sm font-semibold text-slate-900">Cover title</span><input value={draft.cover_title} onChange={(event) => updateField('cover_title', event.target.value)} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900" /></label>
              <label className="space-y-2"><span className="text-sm font-semibold text-slate-900">Cover subtitle</span><input value={draft.cover_subtitle} onChange={(event) => updateField('cover_subtitle', event.target.value)} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900" /></label>
              <label className="space-y-2"><span className="text-sm font-semibold text-slate-900">Client name</span><input value={draft.client_name} onChange={(event) => updateField('client_name', event.target.value)} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900" /></label>
              <label className="space-y-2"><span className="text-sm font-semibold text-slate-900">Report period</span><input value={draft.report_period} onChange={(event) => updateField('report_period', event.target.value)} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900" /></label>
            </div>
            <ListBlock label="Table of contents" items={draft.table_of_contents} onChange={(items) => updateField('table_of_contents', items)} />
          </section>
        );
      case 'context':
        return (
          <section className="space-y-6">
            <TextBlock label="Préambule" value={draft.preamble} onChange={(value) => updateField('preamble', value)} rows={7} />
            <ListBlock label="Objectives" items={draft.objectives} onChange={(items) => updateField('objectives', items)} />
            <ListBlock label="Stakeholders" items={draft.stakeholders} onChange={(items) => updateField('stakeholders', items)} />
            <TextBlock label="Scope summary" value={draft.scope_summary} onChange={(value) => updateField('scope_summary', value)} rows={6} />
            <ListBlock label="Applications in scope" items={draft.applications} onChange={(items) => updateField('applications', items)} />
          </section>
        );
      case 'controls':
        return (
          <section className="space-y-8">
            <ListBlock label="Audit approach" items={draft.audit_approach} onChange={(items) => updateField('audit_approach', items)} />
            <div className="rounded-3xl border border-slate-200 bg-white">
              <div className="border-b border-slate-200 px-6 py-4"><p className="text-sm font-semibold text-slate-900">Covered controls</p></div>
              <div className="overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="bg-slate-50 text-slate-500"><tr><th className="px-6 py-3 font-medium">Ref</th><th className="px-6 py-3 font-medium">Process</th><th className="px-6 py-3 font-medium">Control</th></tr></thead>
                  <tbody>{draft.covered_controls.map((control, index) => <tr key={`${control.reference}-${index}`} className="border-t border-slate-200"><td className="px-6 py-4 font-semibold text-slate-900">{control.reference || 'n/a'}</td><td className="px-6 py-4 text-slate-700">{control.process || 'n/a'}</td><td className="px-6 py-4 text-slate-700">{control.description || 'n/a'}</td></tr>)}</tbody>
                </table>
              </div>
            </div>
          </section>
        );
      case 'synthesis':
        return (
          <section className="space-y-6">
            <TextBlock label="Executive summary" value={draft.executive_summary} onChange={(value) => updateField('executive_summary', value)} rows={8} />
            <TextBlock label="General synthesis" value={draft.general_synthesis} onChange={(value) => updateField('general_synthesis', value)} rows={7} />
            <TextBlock label="Conclusion" value={draft.conclusion} onChange={(value) => updateField('conclusion', value)} rows={5} />
            <TextBlock label="Maturity assessment" value={draft.maturity_assessment} onChange={(value) => updateField('maturity_assessment', value)} rows={5} />
            <TextBlock label="Priority insight" value={draft.priority_insight} onChange={(value) => updateField('priority_insight', value)} rows={4} />
            <ListBlock label="Executive highlights" items={draft.executive_highlights} onChange={(items) => updateField('executive_highlights', items)} />
            <ListBlock label="Strategic priorities" items={draft.strategic_priorities} onChange={(items) => updateField('strategic_priorities', items)} />
          </section>
        );
      case 'findings':
        return (
          <section className="space-y-4">
            {draft.detailed_findings.map((finding, index) => {
              const expanded = expandedFindingId === finding.observation_id;
              return (
                <article key={`${finding.observation_id}-${index}`} className="rounded-3xl border border-slate-200 bg-white p-6">
                  <button type="button" onClick={() => setExpandedFindingId(expanded ? null : finding.observation_id)} className="w-full text-left">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">{finding.observation_id || `Finding ${index + 1}`}</span>
                          <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-700 ring-1 ring-slate-200">{finding.reference || 'No ref'}</span>
                        </div>
                        <h3 className="mt-3 text-lg font-semibold text-slate-900">{finding.title || 'Untitled finding'}</h3>
                        <p className="mt-2 text-sm text-slate-500">{finding.application || 'No application'} - {finding.layer || 'No layer'}</p>
                      </div>
                      <span className={`rounded-full px-3 py-1 text-xs font-semibold ${priorityPill(finding.priority || 'low')}`}>{finding.priority || 'No priority'}</span>
                    </div>
                  </button>
                  {expanded && (
                    <div className="mt-6 space-y-5">
                      <label className="space-y-2"><span className="text-sm font-semibold text-slate-900">Title</span><input value={finding.title} onChange={(event) => updateFinding(finding.observation_id, (current) => ({ ...current, title: event.target.value }))} className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900" /></label>
                      <TextBlock label="Finding" value={finding.finding} onChange={(value) => updateFinding(finding.observation_id, (current) => ({ ...current, finding: value }))} rows={5} />
                      <TextBlock label="Risk impact" value={finding.risk_impact} onChange={(value) => updateFinding(finding.observation_id, (current) => ({ ...current, risk_impact: value }))} rows={4} />
                      <TextBlock label="Risk scenario" value={finding.risk_scenario} onChange={(value) => updateFinding(finding.observation_id, (current) => ({ ...current, risk_scenario: value }))} rows={3} />
                      <TextBlock label="Business impact" value={finding.business_impact} onChange={(value) => updateFinding(finding.observation_id, (current) => ({ ...current, business_impact: value }))} rows={3} />
                      <TextBlock label="Internal control impact" value={finding.control_impact} onChange={(value) => updateFinding(finding.observation_id, (current) => ({ ...current, control_impact: value }))} rows={3} />
                      <ListBlock label="Aggravating factors" items={finding.aggravating_factors} onChange={(items) => updateFinding(finding.observation_id, (current) => ({ ...current, aggravating_factors: items }))} />
                      <TextBlock label="Recommendation" value={finding.recommendation} onChange={(value) => updateFinding(finding.observation_id, (current) => ({ ...current, recommendation: value }))} rows={4} />
                      <TextBlock label="Evidence expected" value={finding.evidence_expected} onChange={(value) => updateFinding(finding.observation_id, (current) => ({ ...current, evidence_expected: value }))} rows={2} />
                      <TextBlock label="Follow-up mechanism" value={finding.follow_up_mechanism} onChange={(value) => updateFinding(finding.observation_id, (current) => ({ ...current, follow_up_mechanism: value }))} rows={2} />
                      <TextBlock label="Management summary" value={finding.management_summary} onChange={(value) => updateFinding(finding.observation_id, (current) => ({ ...current, management_summary: value }))} rows={4} />

                      <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                        <div className="flex items-center gap-2">
                          <Sparkles className="h-4 w-4 text-slate-500" />
                          <p className="text-sm font-semibold text-slate-900">Traceability</p>
                        </div>
                        <div className="mt-4 grid gap-3 sm:grid-cols-2">
                          <div className="rounded-2xl bg-white px-4 py-3">
                            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Observation source</p>
                            <p className="mt-2 text-sm text-slate-800">{finding.traceability.observation_source_id || finding.observation_id || 'n/a'}</p>
                          </div>
                          <div className="rounded-2xl bg-white px-4 py-3">
                            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Confidence score</p>
                            <p className="mt-2 text-sm text-slate-800">{Math.round((finding.traceability.confidence_score || 0) * 100)}%</p>
                          </div>
                          <div className="rounded-2xl bg-white px-4 py-3">
                            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Agent</p>
                            <p className="mt-2 text-sm text-slate-800">{finding.traceability.agent || 'report_agent'}</p>
                          </div>
                          <div className="rounded-2xl bg-white px-4 py-3">
                            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Report version</p>
                            <p className="mt-2 break-all text-sm text-slate-800">{finding.traceability.report_version || 'n/a'}</p>
                          </div>
                        </div>

                        <div className="mt-4 rounded-2xl bg-white px-4 py-4">
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Why this priority?</p>
                          <p className="mt-2 text-sm leading-6 text-slate-700">
                            {finding.traceability.priority_justification || finding.priority_justification || 'No priority justification available.'}
                          </p>
                        </div>

                        <div className="mt-4 grid gap-4 sm:grid-cols-2">
                          <div className="rounded-2xl bg-white px-4 py-4">
                            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Fields used</p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {finding.traceability.fields_used.map((field) => (
                                <span key={field} className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">{field}</span>
                              ))}
                            </div>
                          </div>
                          <div className="rounded-2xl bg-white px-4 py-4">
                            <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Triggered rules</p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {finding.traceability.heuristic_rules_triggered.map((rule) => (
                                <span key={rule} className="rounded-full bg-[#fff3eb] px-3 py-1 text-xs text-[#c75612]">{rule}</span>
                              ))}
                            </div>
                          </div>
                        </div>

                        <div className="mt-4 rounded-2xl bg-white px-4 py-4">
                          <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Sources consulted</p>
                          <div className="mt-3 space-y-3">
                            {finding.traceability.source_documents.length > 0 ? finding.traceability.source_documents.map((source) => (
                              <div key={`${finding.observation_id}-${source.source_id}`} className="rounded-2xl bg-slate-50 px-4 py-3">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <p className="text-sm font-semibold text-slate-900">{source.document_name || source.source_id}</p>
                                  <span className="text-xs text-slate-500">{source.source_type || 'source'}</span>
                                </div>
                                <p className="mt-2 text-sm leading-6 text-slate-600">{source.excerpt || 'No excerpt available.'}</p>
                              </div>
                            )) : (
                              <p className="text-sm text-slate-500">No source documents were attached to this finding.</p>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </article>
              );
            })}
          </section>
        );
      case 'export':
        return (
          <section className="space-y-6">
            <div className={reportPreviewSurface()}>
              <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Cover preview</p>
              <h2 className="pwc-report-cover-title mt-5 text-4xl font-semibold leading-tight text-slate-900">{draft.cover_title || 'Untitled report'}</h2>
              <p className="mt-3 text-lg text-slate-600">{draft.cover_subtitle || 'Version projet'}</p>
            </div>
            {reportPreview.answer && <div className="rounded-3xl border border-slate-200 bg-white p-6"><p className="text-xs uppercase tracking-[0.18em] text-slate-400">AI summary</p><p className="mt-4 whitespace-pre-wrap text-sm leading-7 text-slate-700">{reportPreview.answer}</p></div>}
            <TextBlock label="Conclusion" value={draft.conclusion} onChange={(value) => updateField('conclusion', value)} rows={5} />
          </section>
        );
    }
  };

  return (
    <>
      <div className="space-y-8">
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Report builder</p>
            <h1 className="text-3xl font-semibold text-slate-900">Report review studio</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-500">Review the backend-generated report in PPT order, polish the narrative, and check export readiness.</p>
          </div>
          <button type="button" onClick={() => navigate('/feedback')} className="inline-flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50">
            <MessageCircleMore className="h-4 w-4" /> Open feedback hub
          </button>
        </div>

        {activeMissionFeedback.length > 0 && <div className="rounded-3xl border border-slate-200 bg-white p-5 shadow-card"><p className="text-sm text-slate-500">Feedback pulse</p><p className="mt-2 text-sm text-slate-700">{activeMissionFeedback.length} feedback item(s) already captured for this mission. Latest status: <span className="font-semibold text-slate-900">{activeMissionFeedback[0].status}</span></p></div>}

        <div className="grid gap-6 xl:grid-cols-[220px_minmax(0,1fr)_320px]">
          <aside className="rounded-[2rem] border border-slate-200 bg-white p-5 shadow-card">
            <p className="text-xs uppercase tracking-[0.2em] text-slate-400">PPT order</p>
            <div className="mt-4 space-y-2">
              {sections.map((section, index) => {
                const Icon = section.icon;
                return (
                  <button key={section.id} type="button" onClick={() => setActiveSection(section.id)} className={`flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-sm font-medium transition ${activeSection === section.id ? 'bg-slate-900 text-white' : 'bg-slate-50 text-slate-700 hover:bg-slate-100'}`}>
                    <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-white/10 text-xs font-semibold">{index + 1}</span>
                    <Icon className="h-4 w-4" />
                    {section.label}
                  </button>
                );
              })}
            </div>
          </aside>

          <main className="rounded-[2rem] border border-slate-200 bg-white p-8 shadow-card">{renderSection()}</main>

          <aside className="space-y-5">
            <div className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-card">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Quality Gate</p>
                  <p className="mt-2 text-3xl font-semibold text-slate-900">
                    {loadingQualityGate && !effectiveQualityGate ? '--' : `${effectiveQualityGate?.readiness_score ?? 100}/100`}
                  </p>
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {effectiveQualityGate?.summary || 'No quality-gate result available yet.'}
                  </p>
                </div>
                <span className={`inline-flex h-11 w-11 items-center justify-center rounded-2xl ${effectiveQualityGate?.export_allowed !== false ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-700'}`}>
                  {effectiveQualityGate?.export_allowed !== false ? <ShieldCheck className="h-5 w-5" /> : <ShieldX className="h-5 w-5" />}
                </span>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-2xl bg-red-50 px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.16em] text-red-500">Blocking</p>
                  <p className="mt-2 text-lg font-semibold text-red-700">{effectiveQualityGate?.blocking_issues_count ?? 0}</p>
                </div>
                <div className="rounded-2xl bg-amber-50 px-4 py-3">
                  <p className="text-xs uppercase tracking-[0.16em] text-amber-600">Warnings</p>
                  <p className="mt-2 text-lg font-semibold text-amber-700">{effectiveQualityGate?.warning_issues_count ?? 0}</p>
                </div>
              </div>

              <div className="mt-4 space-y-3">
                {effectiveQualityGate?.issues.length ? effectiveQualityGate.issues.map((issue) => (
                  <div key={`${issue.rule_id}-${issue.title}`} className={`rounded-2xl px-4 py-4 ${issue.severity === 'blocking' ? 'bg-red-50' : 'bg-amber-50'}`}>
                    <div className="flex items-start gap-3">
                      <span className={`mt-0.5 inline-flex h-8 w-8 items-center justify-center rounded-full ${issue.severity === 'blocking' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>
                        <AlertTriangle className="h-4 w-4" />
                      </span>
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{issue.title}</p>
                        <p className="mt-1 text-sm leading-6 text-slate-700">{issue.message}</p>
                        <p className="mt-2 text-sm leading-6 text-slate-600">{issue.recommendation}</p>
                        {issue.affected_observation_ids.length > 0 && (
                          <p className="mt-2 text-xs text-slate-500">Observations: {issue.affected_observation_ids.join(', ')}</p>
                        )}
                        {issue.affected_applications.length > 0 && (
                          <p className="mt-1 text-xs text-slate-500">Applications: {issue.affected_applications.join(', ')}</p>
                        )}
                      </div>
                    </div>
                  </div>
                )) : (
                  <div className="rounded-2xl bg-emerald-50 px-4 py-4 text-sm text-emerald-700">
                    No blocking issue detected. The report is ready for executive review.
                  </div>
                )}
              </div>
            </div>

            <div className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-card">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Readiness</p>
              <div className="mt-4 space-y-3">
                {readinessChecks.map((item) => (
                  <div key={item.label} className="flex items-center gap-3 rounded-2xl bg-slate-50 px-4 py-3">
                    <span className={`inline-flex h-8 w-8 items-center justify-center rounded-full ${item.value ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-200 text-slate-500'}`}>{item.value ? '✓' : '!'}</span>
                    <p className="text-sm text-slate-700">{item.label}</p>
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-card">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Review notes</p>
              <p className="mt-4 text-sm leading-6 text-slate-600">Preview edits are session-local for now. They help the auditor review the narrative, but PPT export still uses the latest backend-generated preview payload until save-sync is added.</p>
            </div>
            <div className="rounded-[2rem] border border-slate-200 bg-white p-6 shadow-card">
              <div className="space-y-3">
                <button type="button" onClick={() => void handleOpenExportModal()} disabled={downloading} className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-red-600 px-5 py-3 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50">
                  <Download className="h-4 w-4" /> {downloading ? 'Exporting...' : 'Export as PPTX'}
                </button>
                <button type="button" onClick={() => void handleExportPdf()} disabled={downloadingPdf || downloading} className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500">
                  <ShieldCheck className="h-4 w-4" /> {downloadingPdf ? 'Exporting PDF...' : 'Export as PDF'}
                </button>
                <button type="button" onClick={() => void handleExportDocx()} disabled={downloadingDocx || downloading} className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500">
                  <FileText className="h-4 w-4" /> {downloadingDocx ? 'Exporting Word...' : 'Export as Word'}
                </button>
              </div>
              {effectiveQualityGate?.export_allowed === false && (
                <p className="mt-3 rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-700">
                  Quality Gate has blocking issues, but export is allowed.
                </p>
              )}
              {exportError && <p className="mt-3 rounded-2xl bg-red-50 px-4 py-3 text-sm text-red-700">{exportError}</p>}
            </div>
          </aside>
        </div>
      </div>

      {showExportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-6">
          <div className="flex max-h-[88vh] w-full max-w-2xl flex-col overflow-hidden rounded-[2rem] bg-white shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-6 py-5 sm:px-8">
              <div>
                <p className="text-sm uppercase tracking-[0.2em] text-slate-400">Export report</p>
                <h2 className="mt-2 text-xl font-semibold text-slate-900 sm:text-2xl">Export the PPTX and optionally send it by email</h2>
                <p className="mt-2 text-sm text-slate-500">
                  The PowerPoint export will start after confirmation. You can also send the same report by email before the download begins.
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (downloading || sendingEmail) return;
                  setShowExportModal(false);
                  setExportError(null);
                  setExportWarning(null);
                }}
                className="rounded-2xl bg-slate-100 p-3 text-slate-500 hover:bg-slate-200"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-5 sm:px-8">
              <div className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                <label className="flex items-start gap-4">
                  <input
                    type="checkbox"
                    checked={sendByEmail}
                    onChange={(event) => setSendByEmail(event.target.checked)}
                    className="mt-1 h-4 w-4 rounded border-slate-300 text-red-600 focus:ring-red-500"
                  />
                  <div>
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                      <Mail className="h-4 w-4 text-slate-500" />
                      Send this report by email
                    </div>
                    <p className="mt-1 text-sm text-slate-500">
                      For now the report can be sent from your configured personal mailbox to a default recipient. In production, this can be redirected to the mission intervenants automatically.
                    </p>
                  </div>
                </label>
              </div>

              {sendByEmail && (
                <div className="mt-6 space-y-4">
                  <label className="space-y-2">
                    <span className="text-sm font-semibold text-slate-900">Recipient</span>
                    <input
                      value={emailForm.to_email}
                      onChange={(event) => setEmailForm((current) => ({ ...current, to_email: event.target.value }))}
                      placeholder="ahlem.bouchahoua@esprit.tn"
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900"
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-sm font-semibold text-slate-900">Subject</span>
                    <input
                      value={emailForm.subject}
                      onChange={(event) => setEmailForm((current) => ({ ...current, subject: event.target.value }))}
                      placeholder="Transmission du rapport d'audit ITGC"
                      className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900"
                    />
                  </label>
                  <label className="space-y-2">
                    <span className="text-sm font-semibold text-slate-900">Email body</span>
                    <textarea
                      rows={9}
                      value={emailForm.body}
                      onChange={(event) => setEmailForm((current) => ({ ...current, body: event.target.value }))}
                      className="min-h-[240px] w-full rounded-3xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm leading-6 text-slate-900"
                    />
                  </label>
                </div>
              )}

              {(loadingEmailDefaults || exportError || exportWarning) && (
                <div className={`mt-6 rounded-2xl px-4 py-3 text-sm ${exportError ? 'bg-red-50 text-red-700' : exportWarning ? 'bg-amber-50 text-amber-800' : 'bg-slate-100 text-slate-600'}`}>
                  {exportError || exportWarning || 'Loading email defaults...'}
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center justify-end gap-3 border-t border-slate-200 px-6 py-5 sm:px-8">
              <button
                type="button"
                onClick={() => {
                  if (downloading || sendingEmail) return;
                  setShowExportModal(false);
                  setExportError(null);
                  setExportWarning(null);
                }}
                className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleExport()}
                disabled={downloading || sendingEmail || loadingEmailDefaults || (sendByEmail && (!emailForm.to_email.trim() || !emailForm.subject.trim() || !emailForm.body.trim()))}
                className="rounded-2xl bg-red-600 px-4 py-3 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
              >
                {sendingEmail ? 'Sending email...' : downloading ? 'Exporting...' : sendByEmail ? 'Send email and export' : 'Export now'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showFeedbackModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/35 p-6">
          <div className="w-full max-w-2xl rounded-[2rem] bg-white p-8 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm uppercase tracking-[0.2em] text-slate-400">Post-export feedback</p>
                <h2 className="mt-2 text-2xl font-semibold text-slate-900">How good was this export?</h2>
                <p className="mt-2 text-sm text-slate-500">Capture a quick review now, then continue deeper in the Feedback hub if needed.</p>
              </div>
              <button type="button" onClick={() => setShowFeedbackModal(false)} className="rounded-2xl bg-slate-100 p-3 text-slate-500 hover:bg-slate-200"><X className="h-4 w-4" /></button>
            </div>
            <div className="mt-6 flex flex-wrap gap-3">
              {quickFeedbackPresets.map((preset) => (
                <button key={preset.label} type="button" onClick={() => handleQuickFeedbackPreset(preset)} className={`rounded-2xl px-4 py-3 text-sm font-semibold ${quickFeedback.rating === preset.rating && quickFeedback.sentiment === preset.sentiment ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-700'}`}>{preset.label}</button>
              ))}
            </div>
            <div className="mt-6">
              <p className="text-sm font-semibold text-slate-700">Rating</p>
              <div className="mt-3 flex gap-2">
                {[1, 2, 3, 4, 5].map((rating) => (
                  <button key={rating} type="button" onClick={() => setQuickFeedback((current) => ({ ...current, rating: rating as 1 | 2 | 3 | 4 | 5 }))} className={`flex h-11 w-11 items-center justify-center rounded-2xl border ${quickFeedback.rating === rating ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-500'}`}>
                    <Star className="h-4 w-4" />
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-6">
              <textarea rows={5} value={quickFeedback.comment} onChange={(event) => setQuickFeedback((current) => ({ ...current, comment: event.target.value }))} placeholder="What should be improved in the report, wording, or PPT design?" className="w-full rounded-3xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-900" />
            </div>
            <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
              <button type="button" onClick={() => navigate('/feedback')} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700">Open full feedback page</button>
              <div className="flex gap-3">
                <button type="button" onClick={() => setShowFeedbackModal(false)} className="rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700">Later</button>
                <button type="button" onClick={() => void handleQuickFeedbackSubmit()} disabled={submittingQuickFeedback} className="rounded-2xl bg-red-600 px-4 py-3 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50">
                  {submittingQuickFeedback ? 'Sending...' : 'Send feedback'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
