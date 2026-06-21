import { useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUpRight, Send } from 'lucide-react';
import logo from '../assets/pwc-logo.png';
import { useMissionContext } from '../context/MissionContext';
import type { AssistantMessagePayload } from '../types';

const suggestions = [
  { title: 'Review critical findings', prompt: 'Explain the critical observations and why they require immediate attention.' },
  { title: 'Summarize key risks', prompt: 'Summarize the top risks identified in this mission.' },
  { title: 'Draft a recommendation', prompt: 'Suggest a practical recommendation for the highest-priority finding.' },
  { title: 'Prepare an executive brief', prompt: 'Summarize this mission for an executive audience.' }
];

const missionStopWords = new Set([
  'audit', 'itgc', 'revue', 'controles', 'controle', 'generaux', 'informatique', 'informatiques',
  'direction', 'generale', 'systemes', 'systeme', 'information', 'fy2026', 'mission'
]);

const missionTokens = (value: string) =>
  value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .match(/[a-z0-9]+/g)
    ?.filter((token) => token.length >= 4 && !missionStopWords.has(token)) ?? [];

export default function ChatPage() {
  const { activeMission, missions, observations, chatHistory, loadingChat, sendAssistantMessage } = useMissionContext();
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [message, setMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [missionMismatch, setMissionMismatch] = useState(false);

  const observationCount = useMemo(() => observations.length, [observations]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [chatHistory.length, loadingChat]);

  if (!activeMission) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <p className="text-slate-500">Please select a mission from the workspace first.</p>
      </div>
    );
  }

  const useSuggestion = (prompt: string) => {
    setMessage(prompt);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  const handleSend = async () => {
    const content = message.trim();
    if (!content || loadingChat) return;

    const promptTokens = new Set(missionTokens(content));
    const activeTokens = new Set(missionTokens(`${activeMission.name} ${activeMission.client}`));
    const referencesAccessibleMission = missions.some((mission) => {
      if (mission.mission_id === activeMission.mission_id) return false;
      const distinctiveTokens = missionTokens(`${mission.name} ${mission.client}`).filter((token) => !activeTokens.has(token));
      return distinctiveTokens.some((token) => promptTokens.has(token));
    });
    const normalizedContent = content.normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const explicitReference = normalizedContent.match(/\baudit\s+itgc\s*[-–—:]\s*([^"”'\n]+)/i);
    const referencesDifferentNamedMission = Boolean(
      explicitReference && missionTokens(explicitReference[1]).some((token) => !activeTokens.has(token))
    );

    if (referencesAccessibleMission || referencesDifferentNamedMission) {
      setMissionMismatch(true);
      setErrorMessage(null);
      return;
    }

    const payload: AssistantMessagePayload = { message: content, history: chatHistory };
    setMissionMismatch(false);
    setErrorMessage(null);
    try {
      await sendAssistantMessage(payload);
      setMessage('');
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Failed to get an answer from the assistant.');
    }
  };

  return (
    <section className="pwc-chat-shell">
      <header className="pwc-chat-header">
        <div className="pwc-chat-identity">
          <img src={logo} alt="PwC" />
          <div>
            <h1>Audit IT Assistant</h1>
            <p><span /> Mission workspace</p>
          </div>
        </div>
        <p className="pwc-chat-mission" title={activeMission.name}>{activeMission.name}</p>
      </header>

      <div className="pwc-chat-scroll">
        <div className="pwc-chat-content">
          {chatHistory.length === 0 ? (
            <div className="pwc-chat-welcome">
              <img src={logo} alt="" aria-hidden="true" />
              <p className="pwc-chat-eyebrow">Mission-ready assistant</p>
              <h2>How can I help with this audit?</h2>
              <p className="pwc-chat-intro">
                Ask about findings, priorities, risks, or recommendations. The assistant is working with {observationCount} observations from the active mission.
              </p>
              <div className="pwc-chat-suggestions">
                {suggestions.map((suggestion) => (
                  <button key={suggestion.title} type="button" onClick={() => useSuggestion(suggestion.prompt)}>
                    <span>
                      <strong>{suggestion.title}</strong>
                      <small>{suggestion.prompt}</small>
                    </span>
                    <ArrowUpRight className="h-4 w-4" />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="pwc-chat-thread">
              {chatHistory.map((messageItem) => {
                const isAssistant = messageItem.role === 'assistant';
                return (
                  <article key={messageItem.id} className={`pwc-chat-message ${isAssistant ? 'is-assistant' : 'is-user'}`}>
                    {isAssistant && <img src={logo} alt="PwC assistant" />}
                    <div className="pwc-chat-message-body">
                      <p className="pwc-chat-message-author">{isAssistant ? 'Audit IT Assistant' : 'You'}</p>
                      <div className="pwc-chat-message-copy">{messageItem.content}</div>

                      {isAssistant && messageItem.sources && messageItem.sources.length > 0 && (
                        <details className="pwc-chat-sources">
                          <summary>Sources <span>{messageItem.sources.length}</span></summary>
                          <div>
                            {messageItem.sources.map((source) => (
                              <section key={`${messageItem.id}-${source.source_id}`}>
                                <header>
                                  <strong>{source.document_name || source.source_id}</strong>
                                  {source.score !== null && <span>{Math.round(source.score * 100)}% match</span>}
                                </header>
                                <small>{source.source_id} / chunk {source.chunk_id ?? 'n/a'}</small>
                                {source.excerpt && <p>{source.excerpt}</p>}
                              </section>
                            ))}
                          </div>
                        </details>
                      )}
                    </div>
                  </article>
                );
              })}

              {loadingChat && (
                <div className="pwc-chat-thinking">
                  <img src={logo} alt="" aria-hidden="true" />
                  <span><i /><i /><i /></span>
                </div>
              )}
              {errorMessage && <div className="pwc-chat-error">{errorMessage}</div>}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      <footer className="pwc-chat-footer">
        {missionMismatch && (
          <div className="pwc-chat-context-warning">
            <div>
              <strong>Different mission reference detected</strong>
              <span>This assistant can only use the mission currently selected in your workspace. Select the intended mission yourself if it is available to you.</span>
            </div>
          </div>
        )}
        <div className="pwc-chat-composer">
          <textarea
            ref={inputRef}
            rows={1}
            value={message}
            onChange={(event) => {
              setMessage(event.target.value);
              setMissionMismatch(false);
            }}
            placeholder="Message Audit IT Assistant"
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                void handleSend();
              }
            }}
          />
          <button
            type="button"
            onClick={() => void handleSend()}
            disabled={loadingChat || !message.trim()}
            aria-label="Send message"
            title="Send message"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
        <p>Responses may require professional judgment. Verify conclusions against the cited evidence.</p>
      </footer>
    </section>
  );
}
