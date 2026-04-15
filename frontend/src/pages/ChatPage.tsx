import { useMemo, useRef, useState } from 'react';
import { Send, MessageSquare } from 'lucide-react';
import { useMissionContext } from '../context/MissionContext';
import type { AssistantMessagePayload } from '../types';

const actions = [
  'Why is this observation Critical?',
  'Top risks',
  'Suggest a recommendation',
  'Summarize the mission'
];

export default function ChatPage() {
  const { activeMission, observations, chatHistory, loadingChat, sendAssistantMessage } = useMissionContext();
  const inputRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const summary = useMemo(
    () => ({
      observations: observations.length,
      topPriority: observations.reduce((prev, obs) => (prev === 'Critical' ? 'Critical' : obs.priority === 'Critical' ? 'Critical' : prev), 'High' as string)
    }),
    [observations]
  );

  if (!activeMission) {
    return (
      <div className="flex items-center justify-center min-h-[50vh]">
        <p className="text-slate-500">Please select a mission from the workspace first.</p>
      </div>
    );
  }

  const handleAction = (text: string) => {
    setMessage(text);
    inputRef.current?.focus();
  };

  const handleSend = async () => {
    if (!message.trim() || !activeMission) return;
    const payload: AssistantMessagePayload = {
      message: message.trim(),
      history: chatHistory
    };
    setErrorMessage(null);
    try {
      await sendAssistantMessage(payload);
      setMessage('');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to get an answer from the assistant.');
    }
  };

  return (
    <div className="grid gap-6 xl:grid-cols-[0.38fr_0.62fr]">
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-card">
        <div className="mb-6">
          <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Mission context</p>
          <h1 className="mt-3 text-2xl font-semibold text-slate-900">{activeMission?.name}</h1>
          <p className="mt-2 text-sm text-slate-600">Status: {activeMission?.status}</p>
        </div>
        <div className="rounded-3xl bg-slate-50 p-5">
          <p className="text-sm text-slate-500">Summary</p>
          <div className="mt-4 space-y-2 text-sm text-slate-700">
            <p>{summary.observations} observations loaded</p>
            <p>Top priority: {summary.topPriority}</p>
          </div>
        </div>
        <div className="mt-6 space-y-3">
          {actions.map((action) => (
            <button
              key={action}
              type="button"
              className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 hover:bg-slate-50"
              onClick={() => handleAction(action)}
            >
              {action}
            </button>
          ))}
        </div>
      </div>

      <div className="flex min-h-[70vh] flex-col rounded-3xl border border-slate-200 bg-white shadow-card">
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {chatHistory.length === 0 ? (
            <div className="max-w-3xl rounded-3xl border border-slate-200 bg-slate-50 p-6 text-left">
              <div className="flex items-start gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-slate-200 text-slate-700">
                  <MessageSquare className="h-5 w-5" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-slate-900">Hello, I am your assistant for mission {activeMission?.name}.</p>
                  <p className="mt-3 text-sm leading-6 text-slate-700">
                    I loaded {summary.observations} observations. I can help you understand priorities, explain a finding, or suggest recommendations. How can I help?
                  </p>
                </div>
              </div>
            </div>
          ) : (
            chatHistory.map((messageItem) => (
              <div
                key={messageItem.id}
                className={`rounded-3xl p-5 ${messageItem.role === 'assistant' ? 'bg-slate-50 text-slate-900' : 'bg-red-50 text-slate-900 self-end'}`}
              >
                <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{messageItem.role}</p>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-700">{messageItem.content}</p>
                {messageItem.role === 'assistant' && messageItem.sources && messageItem.sources.length > 0 && (
                  <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
                    <p className="text-xs uppercase tracking-[0.18em] text-slate-400">Sources</p>
                    <div className="mt-3 space-y-3">
                      {messageItem.sources.map((source) => (
                        <div key={`${messageItem.id}-${source.source_id}`} className="rounded-2xl bg-slate-50 p-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-semibold text-slate-900">{source.source_id} - {source.document_name}</p>
                            {source.score !== null && (
                              <span className="text-xs text-slate-500">Score: {source.score.toFixed(3)}</span>
                            )}
                          </div>
                          <p className="mt-2 text-xs text-slate-500">Chunk: {source.chunk_id ?? 'n/a'}</p>
                          {source.excerpt && (
                            <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-600">{source.excerpt}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))
          )}
          {loadingChat && (
            <div className="flex items-center gap-3 text-sm text-slate-500">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-slate-500" /> Assistant is thinking...
            </div>
          )}
          {errorMessage && (
            <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
              {errorMessage}
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 p-6">
          <p className="mb-3 text-xs uppercase tracking-[0.2em] text-slate-500">
            Assistant is aware of mission {activeMission?.name} - {summary.observations} observations loaded
          </p>
          <div className="flex gap-3">
            <input
              ref={inputRef}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              className="flex-1 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 focus:border-slate-400 focus:outline-none"
              placeholder="Ask the assistant a question"
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault();
                  void handleSend();
                }
              }}
            />
            <button
              type="button"
              onClick={() => void handleSend()}
              disabled={loadingChat}
              className="inline-flex items-center gap-2 rounded-2xl bg-red-600 px-5 py-3 text-sm font-semibold text-white hover:bg-red-700 disabled:opacity-50"
            >
              <Send className="h-4 w-4" /> Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

