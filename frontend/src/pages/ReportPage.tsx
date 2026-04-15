import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Download,
  FileText,
  MessageCircleMore,
  ShieldCheck,
  Star,
  X,
  LayoutPanelLeft,
  BookOpenText,
  ShieldAlert,
  CheckCircle2
} from 'lucide-react';
import { useMissionContext } from '../context/MissionContext';
import type { CreateFeedbackPayload, FeedbackCategory, FeedbackSentiment, ReportStructuredOutput, ReportFinding } from '../types';

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
  requires_action: true,
  author: 'Camille Dupont'
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
  const { activeMission, reportPreview, exportReportPptx, activeMissionFeedback, submitFeedback } = useMissionContext();
  const [activeSection, setActiveSection] = useState<SectionId>('cover');
  const [draft, setDraft] = useState<ReportStructuredOutput | null>(null);
  const [expandedFindingId, setExpandedFindingId] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [showFeedbackModal, setShowFeedbackModal] = useState(false);
  const [quickFeedback, setQuickFeedback] = useState<CreateFeedbackPayload>(emptyQuickFeedback);
  const [submittingQuickFeedback, setSubmittingQuickFeedback] = useState(false);

  useEffect(() => {
    setDraft(reportPreview?.structured_output ?? null);
  }, [reportPreview]);

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

  const handleExport = async () => {
    setDownloading(true);
    try {
      const blob = await exportReportPptx();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `${activeMission.name}-Audit-Report.pptx`;
      link.click();
      setShowFeedbackModal(true);
    } catch (error) {
      console.error('Export failed:', error);
    } finally {
      setDownloading(false);
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
            <div className="rounded-[2rem] border border-slate-200 bg-gradient-to-br from-white via-slate-50 to-slate-100 p-8">
              <p className="text-xs uppercase tracking-[0.22em] text-slate-400">{draft.confidentiality_notice || 'Confidential'}</p>
              <h2 className="mt-6 text-4xl font-semibold leading-tight text-slate-900">{draft.cover_title || 'Untitled report'}</h2>
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
                      <TextBlock label="Recommendation" value={finding.recommendation} onChange={(value) => updateFinding(finding.observation_id, (current) => ({ ...current, recommendation: value }))} rows={4} />
                      <TextBlock label="Management summary" value={finding.management_summary} onChange={(value) => updateFinding(finding.observation_id, (current) => ({ ...current, management_summary: value }))} rows={4} />
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
            <div className="rounded-[2rem] border border-slate-200 bg-gradient-to-br from-slate-50 to-white p-8">
              <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Cover preview</p>
              <h2 className="mt-5 text-4xl font-semibold leading-tight text-slate-900">{draft.cover_title || 'Untitled report'}</h2>
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
                <button type="button" onClick={() => void handleExport()} disabled={downloading} className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-red-600 px-5 py-3 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50">
                  <Download className="h-4 w-4" /> {downloading ? 'Exporting...' : 'Export as PPTX'}
                </button>
                <button type="button" disabled className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-slate-100 px-5 py-3 text-sm font-semibold text-slate-500">
                  <ShieldCheck className="h-4 w-4" /> Export as PDF
                </button>
              </div>
            </div>
          </aside>
        </div>
      </div>

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
