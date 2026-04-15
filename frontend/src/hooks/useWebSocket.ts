import { useCallback, useEffect, useRef, useState } from 'react';
import type { WSAgentMessage } from '../types';

const WS_BASE = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws';

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error';

interface UseWebSocketReturn {
  connectionState: ConnectionState;
  isThinking: boolean;
  send: (text: string) => void;
  reconnect: () => void;
}

const INITIAL_RETRY_DELAY_MS = 1000;
const MAX_RETRY_DELAY_MS = 16000;
const MAX_RETRIES = 10;

export function useWebSocket(
  sessionId: string | null,
  onMessage?: (msg: WSAgentMessage) => void,
): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMountedRef = useRef(true);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [isThinking, setIsThinking] = useState(false);

  const clearRetryTimer = () => {
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  };

  const connect = useCallback(() => {
    if (!isMountedRef.current || !sessionId) return;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    setConnectionState('connecting');

    const ws = new WebSocket(`${WS_BASE}/${sessionId}`);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!isMountedRef.current) return;
      setConnectionState('connected');
      retryCountRef.current = 0;
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!isMountedRef.current) return;
      try {
        const msg: WSAgentMessage = JSON.parse(event.data as string);

        if (msg.type === 'thinking') {
          setIsThinking(true);
        } else if (msg.type === 'response' || msg.type === 'error') {
          setIsThinking(false);
        }

        onMessageRef.current?.(msg);
      } catch {
        // Ignore malformed messages
      }
    };

    ws.onerror = () => {
      if (!isMountedRef.current) return;
      setConnectionState('error');
    };

    ws.onclose = () => {
      if (!isMountedRef.current) return;
      setConnectionState('disconnected');
      setIsThinking(false);
      wsRef.current = null;

      if (retryCountRef.current < MAX_RETRIES) {
        const delay = Math.min(
          INITIAL_RETRY_DELAY_MS * 2 ** retryCountRef.current,
          MAX_RETRY_DELAY_MS,
        );
        retryCountRef.current += 1;
        retryTimerRef.current = setTimeout(() => {
          if (isMountedRef.current) connect();
        }, delay);
      }
    };
  }, [sessionId]);

  useEffect(() => {
    isMountedRef.current = true;

    if (sessionId) {
      connect();
    }

    return () => {
      isMountedRef.current = false;
      clearRetryTimer();
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect, sessionId]);

  const send = useCallback((text: string) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ text }));
    }
  }, []);

  const reconnect = useCallback(() => {
    clearRetryTimer();
    retryCountRef.current = 0;
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    connect();
  }, [connect]);

  return { connectionState, isThinking, send, reconnect };
}
