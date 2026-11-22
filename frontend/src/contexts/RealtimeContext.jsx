import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useAuth } from './AuthContext';

const RealtimeContext = createContext(null);
const realtimeEnabled = import.meta.env.VITE_REALTIME_ENABLED !== 'false';

const socketUrl = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/api/v1/realtime/ws`;
};

export const RealtimeProvider = ({ children }) => {
  const { isAuthenticated, user } = useAuth();
  const listenersRef = useRef(new Set());
  const socketRef = useRef(null);
  const reconnectRef = useRef(null);
  const heartbeatRef = useRef(null);
  const attemptRef = useRef(0);
  const [status, setStatus] = useState('disconnected');

  const subscribe = useCallback((listener) => {
    listenersRef.current.add(listener);
    return () => listenersRef.current.delete(listener);
  }, []);

  useEffect(() => {
    if (!realtimeEnabled || !isAuthenticated || !user?.id) {
      setStatus('disconnected');
      return undefined;
    }

    let disposed = false;
    const clearTimers = () => {
      window.clearTimeout(reconnectRef.current);
      window.clearInterval(heartbeatRef.current);
    };
    const connect = () => {
      if (disposed) return;
      clearTimers();
      setStatus('connecting');
      const socket = new WebSocket(socketUrl());
      socketRef.current = socket;

      socket.addEventListener('open', () => {
        if (disposed) return;
        attemptRef.current = 0;
        setStatus('connected');
        heartbeatRef.current = window.setInterval(() => {
          if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'ping' }));
          }
        }, 25_000);
      });
      socket.addEventListener('message', (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.type === 'pong' || payload.type === 'realtime.ready') return;
          listenersRef.current.forEach((listener) => listener(payload));
        } catch {
          // REST remains authoritative if a supplementary event is malformed.
        }
      });
      socket.addEventListener('close', (event) => {
        clearTimers();
        if (disposed) return;
        setStatus('disconnected');
        if (event.code === 4401 || event.code === 4403) return;
        const delay = Math.min(1_000 * (2 ** attemptRef.current), 20_000);
        attemptRef.current += 1;
        reconnectRef.current = window.setTimeout(connect, delay);
      });
      socket.addEventListener('error', () => {
        if (socket.readyState !== WebSocket.CLOSED) socket.close();
      });
    };

    connect();
    return () => {
      disposed = true;
      clearTimers();
      socketRef.current?.close(1000, 'Session changed');
      socketRef.current = null;
    };
  }, [isAuthenticated, user?.id]);

  const value = useMemo(() => ({ status, subscribe }), [status, subscribe]);
  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
};

export const useRealtime = () => {
  const context = useContext(RealtimeContext);
  if (!context) throw new Error('useRealtime must be used inside RealtimeProvider');
  return context;
};

export const useRealtimeEvent = (handler) => {
  const { subscribe } = useRealtime();
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);
  useEffect(() => subscribe((payload) => handlerRef.current(payload)), [subscribe]);
};
