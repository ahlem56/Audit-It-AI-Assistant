import { useState } from 'react';
import { sendMissionAssistantMessage } from '../services/api';
import type { ChatMessage } from '../types';

export function useChat(mission_id: string) {
  const [history, setHistory] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(false);

  const sendMessage = async (message: string) => {
    const nextHistory = [
      ...history,
      { id: `user-${Date.now()}`, role: 'user', content: message }
    ];
    setHistory(nextHistory);
    setLoading(true);

    try {
      const response = await sendMissionAssistantMessage(mission_id, {
        message,
        history: nextHistory
      });
      setHistory((current) => [...current, response.message]);
    } finally {
      setLoading(false);
    }
  };

  return { history, setHistory, loading, sendMessage };
}
