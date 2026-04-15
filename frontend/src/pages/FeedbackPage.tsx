import { useMemo, useState } from 'react';
import { CheckCircle2, ClipboardList, MessageSquareQuote, Sparkles, Star } from 'lucide-react';
import { useMissionContext } from '../context/MissionContext';
import type { CreateFeedbackPayload, FeedbackCategory, FeedbackSentiment } from '../types';

const categoryOptions: Array<{ value: FeedbackCategory; label: string }> = [
  { value: 'report_quality', label: 'Report quality' },
  { value: 'priority_logic', label: 'Priority logic' },
  { value: 'recommendations', label: 'Recommendations' },
  { value: 'ppt_design', label: 'PPT design' },
  { value: 'data_accuracy', label: 'Data accuracy' },
  { value: 'missing_content', label: 'Missing content' },
  { value: 'usability', label: 'Usability' }
];

const sentimentOptions: Array<{ value: FeedbackSentiment; label: string }> = [
  { value: 'positive', label: 'Positive' },
  { value: 'neutral', label: 'Neutral' },
  { value: 'negative', label: 'Negative' }
];

const emptyForm: CreateFeedbackPayload = {
  scope: 'mission',
  rating: 4,
  sentiment: 'neutral',
  categories: ['report_quality'],
  comment: '',
  requires_action: true,
  author: 'Camille Dupont'
};

const formatDate = (value: string) => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('fr-TN', {
    dateStyle: 'short',
    timeStyle: 'short'
  }).format(date);
};

export default function FeedbackPage() {
  const { activeMission, activeMissionFeedback, submitFeedback, updateFeedbackStatus, loadingFeedback } = useMissionContext();
  const [form, setForm] = useState<CreateFeedbackPayload>(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [statusUpdateId, setStatusUpdateId] = useState<string | null>(null);

  const averageRating = useMemo(() => {
    if (activeMissionFeedback.length === 0) return null;
    const ratedFeedback = activeMissionFeedback.filter((item): item is typeof item & { rating: number } => typeof item.rating === 'number');
    if (ratedFeedback.length === 0) return null;
    const total = ratedFeedback.reduce((sum, item) => sum + item.rating, 0);
    return (total / ratedFeedback.length).toFixed(1);
  }, [activeMissionFeedback]);

  const categorizedSummary = useMemo(() => {
    const counts = new Map<FeedbackCategory, number>();
    activeMissionFeedback.forEach((entry) => {
      entry.categories.forEach((category) => {
        counts.set(category, (counts.get(category) ?? 0) + 1);
      });
    });
    return categoryOptions
      .map((option) => ({ ...option, count: counts.get(option.value) ?? 0 }))
      .filter((option) => option.count > 0)
      .sort((left, right) => right.count - left.count)
      .slice(0, 4);
  }, [activeMissionFeedback]);

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
    if (!form.comment.trim()) return;
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

  const handleStatusUpdate = async (feedbackId: string, status: 'reviewed' | 'resolved') => {
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
    <div className="space-y-8">
      <div>
        <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Quality loop</p>
        <h1 className="text-3xl font-semibold text-slate-900">Auditor feedback</h1>
        <p className="mt-2 text-sm text-slate-500">
          Capture what works, what needs review, and the concrete improvement requests for the active mission.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
          <p className="text-sm text-slate-500">Mission feedbacks</p>
          <p className="mt-3 text-3xl font-semibold text-slate-900">{activeMissionFeedback.length}</p>
        </div>
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
          <p className="text-sm text-slate-500">Average rating</p>
          <p className="mt-3 text-3xl font-semibold text-slate-900">{averageRating ?? '--'}</p>
        </div>
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
          <p className="text-sm text-slate-500">Needs action</p>
          <p className="mt-3 text-3xl font-semibold text-slate-900">
            {activeMissionFeedback.filter((entry) => entry.requires_action && entry.status !== 'resolved').length}
          </p>
        </div>
        <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
          <p className="text-sm text-slate-500">Resolved</p>
          <p className="mt-3 text-3xl font-semibold text-slate-900">
            {activeMissionFeedback.filter((entry) => entry.status === 'resolved').length}
          </p>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <section className="rounded-3xl border border-slate-200 bg-white p-8 shadow-card">
          <div className="flex items-center gap-3">
            <MessageSquareQuote className="h-5 w-5 text-slate-500" />
            <div>
              <p className="text-sm uppercase tracking-[0.2em] text-slate-400">New feedback</p>
              <h2 className="mt-1 text-xl font-semibold text-slate-900">Add auditor review</h2>
            </div>
          </div>

          <div className="mt-6 space-y-5">
            <div>
              <p className="text-sm font-semibold text-slate-700">Rating</p>
              <div className="mt-3 flex gap-2">
                {[1, 2, 3, 4, 5].map((rating) => (
                  <button
                    key={rating}
                    type="button"
                    onClick={() => setForm((current) => ({ ...current, rating: rating as 1 | 2 | 3 | 4 | 5 }))}
                    className={`flex h-11 w-11 items-center justify-center rounded-2xl border ${
                      form.rating === rating
                        ? 'border-slate-900 bg-slate-900 text-white'
                        : 'border-slate-200 bg-white text-slate-500'
                    }`}
                  >
                    <Star className="h-4 w-4" />
                  </button>
                ))}
              </div>
            </div>

            <div>
              <p className="text-sm font-semibold text-slate-700">Sentiment</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {sentimentOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => setForm((current) => ({ ...current, sentiment: option.value }))}
                    className={`rounded-full px-4 py-2 text-sm font-medium ${
                      form.sentiment === option.value
                        ? 'bg-slate-900 text-white'
                        : 'bg-slate-100 text-slate-700'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <p className="text-sm font-semibold text-slate-700">Categories</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {categoryOptions.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => handleCategoryToggle(option.value)}
                    className={`rounded-full px-4 py-2 text-sm font-medium ${
                      form.categories.includes(option.value)
                        ? 'bg-red-600 text-white'
                        : 'bg-slate-100 text-slate-700'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="space-y-2">
                <span className="text-sm font-semibold text-slate-700">Feedback scope</span>
                <select
                  value={form.scope}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      scope: event.target.value as CreateFeedbackPayload['scope']
                    }))
                  }
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900"
                >
                  <option value="mission">Mission</option>
                  <option value="report">Report</option>
                  <option value="observation">Observation</option>
                </select>
              </label>
              <label className="space-y-2">
                <span className="text-sm font-semibold text-slate-700">Author</span>
                <input
                  value={form.author ?? ''}
                  onChange={(event) => setForm((current) => ({ ...current, author: event.target.value }))}
                  className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900"
                />
              </label>
            </div>

            <label className="space-y-2">
              <span className="text-sm font-semibold text-slate-700">Comment</span>
              <textarea
                rows={6}
                value={form.comment}
                onChange={(event) => setForm((current) => ({ ...current, comment: event.target.value }))}
                placeholder="What was strong, what felt weak, and what should be improved next?"
                className="w-full rounded-3xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-900"
              />
            </label>

            <label className="flex items-center gap-3 rounded-2xl bg-slate-50 px-4 py-3">
              <input
                type="checkbox"
                checked={form.requires_action}
                onChange={(event) => setForm((current) => ({ ...current, requires_action: event.target.checked }))}
              />
              <span className="text-sm text-slate-700">This feedback requires a follow-up action</span>
            </label>

            <button
              type="button"
              onClick={() => void handleSubmit()}
              disabled={submitting}
              className="rounded-2xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
            >
              {submitting ? 'Saving...' : 'Save feedback'}
            </button>
          </div>
        </section>

        <section className="space-y-6">
          <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-card">
            <div className="flex items-center gap-3">
              <Sparkles className="h-5 w-5 text-slate-500" />
              <div>
                <p className="text-sm uppercase tracking-[0.2em] text-slate-400">Insights</p>
                <h2 className="mt-1 text-xl font-semibold text-slate-900">Themes surfacing from auditors</h2>
              </div>
            </div>

            <div className="mt-6 flex flex-wrap gap-3">
              {categorizedSummary.length > 0 ? (
                categorizedSummary.map((item) => (
                  <div key={item.value} className="rounded-2xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
                    <span className="font-semibold text-slate-900">{item.label}</span> - {item.count}
                  </div>
                ))
              ) : (
                <p className="text-sm text-slate-500">No theme yet. The first feedback will start the quality history.</p>
              )}
            </div>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-card">
            <div className="flex items-center gap-3">
              <ClipboardList className="h-5 w-5 text-slate-500" />
              <div>
                <p className="text-sm uppercase tracking-[0.2em] text-slate-400">Timeline</p>
                <h2 className="mt-1 text-xl font-semibold text-slate-900">Previous feedbacks</h2>
              </div>
            </div>

            <div className="mt-6 space-y-4">
              {loadingFeedback ? (
                <p className="text-sm text-slate-500">Loading feedback...</p>
              ) : activeMissionFeedback.length > 0 ? (
                activeMissionFeedback.map((entry) => (
                  <article key={entry.feedback_id} className="rounded-3xl border border-slate-200 bg-slate-50 p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-700 ring-1 ring-slate-200">
                            {entry.scope || 'mission'}
                          </span>
                          <span className="rounded-full bg-red-50 px-3 py-1 text-xs font-semibold text-red-700">
                            {entry.status}
                          </span>
                        </div>
                        <p className="mt-3 text-sm text-slate-900">{entry.comment || 'No comment provided.'}</p>
                        <p className="mt-2 text-xs text-slate-500">
                          {formatDate(entry.created_at)} - {entry.author || 'Unknown author'}
                        </p>
                      </div>

                      <div className="flex flex-col items-end gap-2">
                        <span className="text-sm font-semibold text-slate-900">{entry.rating ? `${entry.rating}/5` : '--'}</span>
                        <span className="text-xs text-slate-500">{entry.sentiment || 'No sentiment'}</span>
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                      {entry.categories.map((category) => (
                        <span key={category} className="rounded-full bg-white px-3 py-1 text-xs text-slate-600 ring-1 ring-slate-200">
                          {category}
                        </span>
                      ))}
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                      {entry.status !== 'reviewed' && (
                        <button
                          type="button"
                          onClick={() => void handleStatusUpdate(entry.feedback_id, 'reviewed')}
                          disabled={statusUpdateId === entry.feedback_id}
                          className="rounded-2xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-50"
                        >
                          Mark as reviewed
                        </button>
                      )}
                      {entry.status !== 'resolved' && (
                        <button
                          type="button"
                          onClick={() => void handleStatusUpdate(entry.feedback_id, 'resolved')}
                          disabled={statusUpdateId === entry.feedback_id}
                          className="rounded-2xl bg-emerald-600 px-3 py-2 text-xs font-semibold text-white disabled:opacity-50"
                        >
                          <span className="inline-flex items-center gap-1">
                            <CheckCircle2 className="h-3.5 w-3.5" /> Resolve
                          </span>
                        </button>
                      )}
                    </div>
                  </article>
                ))
              ) : (
                <p className="text-sm text-slate-500">No feedback has been captured for this mission yet.</p>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

