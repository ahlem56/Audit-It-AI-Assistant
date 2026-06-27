import { useMemo, useState, type CSSProperties } from 'react';
import {
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  Filter,
  MessageSquareQuote,
  Search,
  Star,
  Target,
  TrendingUp
} from 'lucide-react';
import { useAuthContext } from '../context/AuthContext';
import { useMissionContext } from '../context/MissionContext';
import type { AuditorFeedback, CreateFeedbackPayload, FeedbackCategory, FeedbackSentiment, FeedbackStatus } from '../types';

const categoryOptions: Array<{ value: FeedbackCategory; label: string; short: string }> = [
  { value: 'report_quality', label: 'Report quality', short: 'Quality' },
  { value: 'priority_logic', label: 'Priority logic', short: 'Priority' },
  { value: 'recommendations', label: 'Recommendations', short: 'Actions' },
  { value: 'ppt_design', label: 'PPT design', short: 'Deck' },
  { value: 'data_accuracy', label: 'Data accuracy', short: 'Data' },
  { value: 'missing_content', label: 'Missing content', short: 'Gaps' },
  { value: 'usability', label: 'Usability', short: 'Flow' }
];

const sentimentOptions: Array<{ value: FeedbackSentiment; label: string }> = [
  { value: 'positive', label: 'Positive' },
  { value: 'neutral', label: 'Neutral' },
  { value: 'negative', label: 'Negative' }
];

const statusFilters: Array<{ value: FeedbackStatus | 'all'; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'pending', label: 'Pending' },
  { value: 'reviewed', label: 'Reviewed' },
  { value: 'resolved', label: 'Resolved' }
];

const emptyForm: CreateFeedbackPayload = {
  scope: 'report',
  rating: 4,
  sentiment: 'neutral',
  categories: ['report_quality'],
  comment: '',
  requires_action: true
};

const statusTone: Record<FeedbackStatus, string> = {
  pending: 'feedback-studio-status-pending',
  reviewed: 'feedback-studio-status-reviewed',
  resolved: 'feedback-studio-status-resolved'
};

const sentimentDot: Record<FeedbackSentiment, string> = {
  positive: 'bg-emerald-500',
  neutral: 'bg-[#ffb600]',
  negative: 'bg-[#c74634]'
};

const formatDate = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('fr-TN', {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(date);
};

const categoryLabel = (value: FeedbackCategory) => categoryOptions.find((option) => option.value === value)?.label ?? value;

const getInitials = (value?: string) => {
  const fallback = 'AU';
  const parts = String(value ?? '')
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (parts.length === 0) return fallback;
  return parts
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase();
};

function qualityLabel(score: number) {
  if (score >= 88) return 'Board-ready';
  if (score >= 72) return 'Controlled';
  if (score >= 55) return 'Focused review';
  return 'Needs attention';
}

function recentFeedbackCount(feedback: AuditorFeedback[]) {
  const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
  return feedback.filter((entry) => {
    const created = new Date(entry.created_at).getTime();
    return !Number.isNaN(created) && created >= sevenDaysAgo;
  }).length;
}

function FeedbackAvatar({ name, imageUrl, compact = false }: { name?: string; imageUrl?: string | null; compact?: boolean }) {
  return (
    <div className={compact ? 'feedback-studio-avatar feedback-studio-avatar-compact' : 'feedback-studio-avatar'}>
      {imageUrl ? <img src={imageUrl} alt={name || 'Auditor'} /> : <span>{getInitials(name)}</span>}
    </div>
  );
}

export default function FeedbackPage() {
  const { user } = useAuthContext();
  const { activeMission, activeMissionFeedback, submitFeedback, updateFeedbackStatus, loadingFeedback } = useMissionContext();
  const [form, setForm] = useState<CreateFeedbackPayload>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [statusUpdateId, setStatusUpdateId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<FeedbackStatus | 'all'>('all');
  const [query, setQuery] = useState('');
  const fallbackAuthor = user?.display_name || user?.email || 'Authenticated user';
  const fallbackAvatar = user?.profile_image_url;

  const analytics = useMemo(() => {
    const total = activeMissionFeedback.length;
    const ratedFeedback = activeMissionFeedback.filter((item): item is AuditorFeedback & { rating: 1 | 2 | 3 | 4 | 5 } => typeof item.rating === 'number');
    const averageRating = ratedFeedback.length ? ratedFeedback.reduce((sum, item) => sum + item.rating, 0) / ratedFeedback.length : 0;
    const resolved = activeMissionFeedback.filter((entry) => entry.status === 'resolved').length;
    const openActions = activeMissionFeedback.filter((entry) => entry.requires_action && entry.status !== 'resolved').length;
    const negative = activeMissionFeedback.filter((entry) => entry.sentiment === 'negative').length;
    const positive = activeMissionFeedback.filter((entry) => entry.sentiment === 'positive').length;
    const closure = total ? Math.round((resolved / total) * 100) : 0;
    const qualityScore = Math.max(
      0,
      Math.min(100, Math.round((averageRating / 5) * 58 + closure * 0.28 + (total ? (positive / total) * 14 : 7) - negative * 5))
    );

    return {
      total,
      averageRating,
      resolved,
      openActions,
      closure,
      qualityScore,
      recent: recentFeedbackCount(activeMissionFeedback)
    };
  }, [activeMissionFeedback]);

  const filteredFeedback = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return activeMissionFeedback.filter((entry) => {
      const matchesStatus = statusFilter === 'all' || entry.status === statusFilter;
      if (!matchesStatus) return false;
      if (!normalizedQuery) return true;
      return [entry.comment, entry.author, entry.sentiment, entry.status, entry.scope, ...entry.categories.map(categoryLabel)]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery));
    });
  }, [activeMissionFeedback, query, statusFilter]);

  if (!activeMission) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <p className="text-slate-500">Please select a mission from the workspace first.</p>
      </div>
    );
  }

  const handleCategoryToggle = (category: FeedbackCategory) => {
    setForm((current) => ({
      ...current,
      categories: current.categories.includes(category)
        ? current.categories.filter((item) => item !== category)
        : [...current.categories, category]
    }));
  };

  const handleSubmit = async () => {
    if (!form.comment?.trim()) return;
    setSubmitting(true);
    try {
      await submitFeedback({
        ...form,
        categories: form.categories.length > 0 ? form.categories : ['report_quality']
      });
      setForm(emptyForm);
    } catch (error) {
      console.error('Failed to submit feedback:', error);
    } finally {
      setSubmitting(false);
    }
  };

  const handleStatusUpdate = async (feedbackId: string, status: FeedbackStatus) => {
    setStatusUpdateId(feedbackId);
    try {
      await updateFeedbackStatus(feedbackId, status);
    } catch (error) {
      console.error('Failed to update feedback status:', error);
    } finally {
      setStatusUpdateId(null);
    }
  };

  return (
    <div className="feedback-studio space-y-5">
      <section className="feedback-studio-hero">
        <div className="feedback-studio-brand">
          <span>Feedback</span>
          <strong>{activeMission.client || 'Client'} / {activeMission.fiscal_year || 'FY'}</strong>
        </div>

        <div className="feedback-studio-command">
          <div>
            <h1>Feedback and review controls.</h1>
            <p>Capture reviewer input, assign follow-up actions, and maintain a clear resolution trail.</p>
          </div>
        </div>

        <div className="feedback-studio-hero-footer">
          <span>Quality index <strong>{analytics.qualityScore}</strong> · {qualityLabel(analytics.qualityScore)}</span>
          <span>{analytics.recent} new feedback item{analytics.recent === 1 ? '' : 's'} in the last 7 days</span>
        </div>
      </section>

      <section className="feedback-studio-metrics">
        {[
          { label: 'Feedback', value: analytics.total, icon: MessageSquareQuote },
          { label: 'Avg rating', value: analytics.averageRating ? analytics.averageRating.toFixed(1) : '--', icon: Star },
          { label: 'Open actions', value: analytics.openActions, icon: Target },
          { label: 'Closure', value: `${analytics.closure}%`, icon: TrendingUp }
        ].map((metric) => (
          <div key={metric.label} className="feedback-studio-metric">
            <div>
              <span>{metric.label}</span>
              <strong>{metric.value}</strong>
            </div>
            <span className="feedback-studio-metric-icon"><metric.icon className="h-5 w-5" /></span>
          </div>
        ))}
      </section>

      <section className="grid gap-6 xl:grid-cols-[25rem_minmax(0,1fr)]">
        <div className="space-y-6">
          <section className="feedback-studio-card feedback-studio-compose">
            <div className="feedback-studio-card-header">
              <div className="feedback-studio-card-icon">
                <MessageSquareQuote className="h-4 w-4" />
              </div>
              <div>
                <p className="feedback-studio-kicker">Reviewer input</p>
                <h2>Submit feedback</h2>
                <p>Record a clear, actionable review note.</p>
              </div>
            </div>

            <div className="mt-5 space-y-5">
              <div>
                <div className="mb-2 flex items-center justify-between text-sm">
                  <span className="font-semibold text-slate-700">Rating</span>
                  <span className="font-semibold text-slate-500">{form.rating}/5</span>
                </div>
                <div className="grid grid-cols-5 gap-2">
                  {[1, 2, 3, 4, 5].map((rating) => (
                    <button
                      key={rating}
                      type="button"
                      onClick={() => setForm((current) => ({ ...current, rating: rating as 1 | 2 | 3 | 4 | 5 }))}
                      className={`feedback-studio-star ${form.rating === rating ? 'feedback-studio-star-active' : ''}`}
                    >
                      <Star className={`h-4 w-4 ${form.rating === rating ? 'fill-white' : ''}`} />
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <span className="text-sm font-semibold text-slate-700">Sentiment</span>
                <div className="mt-2 grid grid-cols-3 gap-2">
                  {sentimentOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setForm((current) => ({ ...current, sentiment: option.value }))}
                      className={`feedback-studio-segment ${form.sentiment === option.value ? 'feedback-studio-segment-active' : ''}`}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <span className="text-sm font-semibold text-slate-700">Theme</span>
                <div className="mt-2 flex flex-wrap gap-2">
                  {categoryOptions.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => handleCategoryToggle(option.value)}
                      className={`feedback-studio-chip ${form.categories.includes(option.value) ? 'feedback-studio-chip-active' : ''}`}
                    >
                      {option.short}
                    </button>
                  ))}
                </div>
              </div>

              <textarea
                rows={5}
                value={form.comment}
                onChange={(event) => setForm((current) => ({ ...current, comment: event.target.value }))}
                placeholder="Describe the issue, its impact, and the expected follow-up..."
                className="feedback-studio-textarea"
              />

              <div className="flex items-center justify-between gap-3">
                <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
                  <input
                    type="checkbox"
                    checked={form.requires_action}
                    onChange={(event) => setForm((current) => ({ ...current, requires_action: event.target.checked }))}
                    className="h-4 w-4 rounded border-slate-300 text-[#ef5b0c] focus:ring-orange-500"
                  />
                  Action required
                </label>
                <button
                  type="button"
                  onClick={() => void handleSubmit()}
                  disabled={submitting || !form.comment?.trim()}
                  className="feedback-studio-submit"
                >
                  {submitting ? 'Submitting' : 'Submit feedback'}
                  <ArrowUpRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </section>
        </div>

        <section className="feedback-studio-card feedback-studio-ledger">
          <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
            <div>
              <p className="feedback-studio-kicker">Review register</p>
              <h2>Engagement feedback</h2>
              <p className="feedback-studio-section-copy">A controlled record of reviewer observations and resolution status.</p>
            </div>
            <div className="feedback-studio-next">
              <span>Open actions</span>
              <strong>{analytics.openActions}</strong>
            </div>
          </div>

          <div className="mt-5 grid gap-3 xl:grid-cols-[1fr_auto]">
            <label className="feedback-studio-search">
              <Search className="h-4 w-4 text-slate-400" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search feedback by note, author, status, or theme"
              />
            </label>
            <div className="feedback-studio-filters">
              <Filter className="h-4 w-4 text-slate-400" />
              {statusFilters.map((filter) => (
                <button
                  key={filter.value}
                  type="button"
                  onClick={() => setStatusFilter(filter.value)}
                  className={statusFilter === filter.value ? 'feedback-studio-filter-active' : ''}
                >
                  {filter.label}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-5 space-y-3">
            {loadingFeedback ? (
              <div className="space-y-3">
                {[1, 2, 3].map((item) => (
                  <div key={item} className="h-28 animate-pulse rounded-2xl bg-slate-100" />
                ))}
              </div>
            ) : filteredFeedback.length > 0 ? (
              filteredFeedback.map((entry, index) => (
                <article
                  key={entry.feedback_id}
                  className="feedback-studio-entry"
                  style={{ '--entry-delay': `${Math.min(index, 8) * 55}ms` } as CSSProperties}
                >
                  <div className="feedback-studio-entry-index">{String(index + 1).padStart(2, '0')}</div>
                  <FeedbackAvatar name={entry.author || fallbackAuthor} imageUrl={entry.author ? null : fallbackAvatar} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`feedback-studio-status ${statusTone[entry.status]}`}>{entry.status}</span>
                      {entry.sentiment && <span className={`h-2.5 w-2.5 rounded-full ${sentimentDot[entry.sentiment]}`} />}
                      {entry.requires_action && <span className="feedback-studio-action-tag">Action</span>}
                    </div>
                    <p className="mt-3 text-sm leading-6 text-slate-800">{entry.comment || 'No comment provided.'}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {entry.categories.map((category) => (
                        <span key={category} className="feedback-studio-mini-chip">{categoryLabel(category)}</span>
                      ))}
                    </div>
                  </div>

                  <div className="feedback-studio-entry-side">
                    <div className="feedback-studio-rating">
                      <strong>{entry.rating ?? '--'}</strong>
                      <span>rating</span>
                    </div>
                    <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
                      <Clock3 className="h-3.5 w-3.5" />
                      {formatDate(entry.created_at)}
                    </span>
                    <span className="text-xs text-slate-500">{entry.author || fallbackAuthor}</span>
                    <div className="flex flex-wrap justify-end gap-2">
                      {entry.status === 'pending' && (
                        <button
                          type="button"
                          onClick={() => void handleStatusUpdate(entry.feedback_id, 'reviewed')}
                          disabled={statusUpdateId === entry.feedback_id}
                          className="feedback-studio-secondary"
                        >
                          Review
                        </button>
                      )}
                      {entry.status !== 'resolved' && (
                        <button
                          type="button"
                          onClick={() => void handleStatusUpdate(entry.feedback_id, 'resolved')}
                          disabled={statusUpdateId === entry.feedback_id}
                          className="feedback-studio-resolve"
                        >
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          Resolve
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center text-sm text-slate-500">
                No feedback matches this view.
              </div>
            )}
          </div>
        </section>
      </section>
    </div>
  );
}
