import { useState, useEffect, useRef, useCallback } from 'react';
import { api } from './api';
import { IuxisWebSocket, ChatWSMessage } from './websocket';

// --- Chat Hook ---

export interface SaveSignal {
  text: string;
  suggested_category: string;
  source: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  status?: 'sending' | 'thinking' | 'complete' | 'error';
  save_signal?: SaveSignal | null;
}

export function useChat(channelId: number = 1) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<IuxisWebSocket | null>(null);

  useEffect(() => {
    // Load history
    api.getChatHistory(channelId).then(data => {
      setMessages(data.messages.map((m: any) => ({
        id: m.id?.toString() || crypto.randomUUID(),
        role: m.role,
        content: m.content,
        timestamp: new Date(m.created_at),
        status: 'complete',
      })));
    }).catch(console.error);

    // Connect WebSocket
    const ws = new IuxisWebSocket(channelId);
    wsRef.current = ws;

    ws.onMessage((data: ChatWSMessage) => {
      if (data.type === 'thinking') {
        setIsThinking(true);
      } else if (data.type === 'response') {
        setIsThinking(false);
        setMessages(prev => [...prev, {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.content,
          timestamp: new Date(),
          status: 'complete',
          save_signal: data.save_signal || null,
        }]);

        // Auto-reload dashboard if actions were executed
        if (data.content && data.content.includes('Actions executed')) {
          setTimeout(() => {
            window.location.reload();
          }, 1500);
        }
      } else if (data.type === 'error') {
        setIsThinking(false);
        setMessages(prev => [...prev, {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `Error: ${data.content}`,
          timestamp: new Date(),
          status: 'error',
          save_signal: null,
        }]);
      }
    });

    ws.connect();
    setIsConnected(true);

    return () => {
      ws.disconnect();
      setIsConnected(false);
    };
  }, [channelId]);

  const sendMessage = useCallback((content: string) => {
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      timestamp: new Date(),
      status: 'complete',
    };
    setMessages(prev => [...prev, userMsg]);

    // Try WebSocket first, fall back to REST
    if (wsRef.current) {
      wsRef.current.send(content);
    } else {
      setIsThinking(true);
      api.sendMessage(content, channelId).then(data => {
        setIsThinking(false);
        setMessages(prev => [...prev, {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: data.response,
          timestamp: new Date(),
          status: 'complete',
          save_signal: data.save_signal || null,
        }]);

        // Auto-reload dashboard if actions were executed
        if (data.response && data.response.includes('Actions executed')) {
          setTimeout(() => {
            window.location.reload();
          }, 1500);
        }
      }).catch(err => {
        setIsThinking(false);
        setMessages(prev => [...prev, {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `Error: ${err.message}`,
          timestamp: new Date(),
          status: 'error',
          save_signal: null,
        }]);
      });
    }
  }, [channelId]);

  return { messages, sendMessage, isThinking, isConnected };
}

// --- Knowledge Hook ---

export function useKnowledge(params?: { projectId?: number; category?: string; limit?: number }) {
  const [entries, setEntries] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const queryParams: Record<string, string> = {};
    if (params?.projectId) queryParams.project_id = params.projectId.toString();
    if (params?.category) queryParams.category = params.category;
    if (params?.limit) queryParams.limit = params.limit.toString();

    api.getKnowledge(queryParams).then(data => {
      setEntries(data.entries);
      setLoading(false);
    }).catch(err => {
      console.error('Knowledge fetch error:', err);
      setLoading(false);
    });
  }, [params?.projectId, params?.category, params?.limit]);

  return { entries, loading };
}
