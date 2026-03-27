import { useCallback, useEffect, useRef, useState } from 'react';
import type { WSAction, WSMessage } from '../types';

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws';

export type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error';

interface UseWebSocketReturn {
  connectionState: ConnectionState;
  lastMessage: WSMessage | null;
  send: (action: WSAction) => void;
  reconnect: () => void;
}

const INITIAL_RETRY_DELAY_MS = 1000;
const MAX_RETRY_DELAY_MS = 16000;
const MAX_RETRIES = 10;

export function useWebSocket(
  onMessage?: (msg: WSMessage) => void,
): UseWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const retryCountRef = useRef(0);
  const retryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isMountedRef = useRef(true);
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);

  const clearRetryTimer = () => {
    if (retryTimerRef.current) {
      clearTimeout(retryTimerRef.current);
      retryTimerRef.current = null;
    }
  };

  const connect = useCallback(() => {
    if (!isMountedRef.current) return;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) return;

    setConnectionState('connecting');

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!isMountedRef.current) return;
      setConnectionState('connected');
      retryCountRef.current = 0;
    };

    ws.onmessage = (event: MessageEvent) => {
      if (!isMountedRef.current) return;
      try {
        const msg: WSMessage = JSON.parse(event.data as string);
        setLastMessage(msg);
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
  }, []);

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    isMountedRef.current = true;
    connect();
    return () => {
      isMountedRef.current = false;
      clearRetryTimer();
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent retry on intentional close
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect]);

  const send = useCallback((action: WSAction) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(action));
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

  return { connectionState, lastMessage, send, reconnect };
}
