import { useEffect, useRef, useCallback } from "react";
import { getAuthToken } from "../api/client";
import type { SSEEvent } from "../types";

type EventHandler = (event: SSEEvent) => void;

export function useSSE(onEvent: EventHandler) {
  const sourceRef = useRef<EventSource | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const connect = useCallback(() => {
    const token = getAuthToken();
    if (!token) return;

    // Pass JWT as query param for SSE (EventSource doesn't support custom headers)
    const url = `/api/events?authorization=Bearer%20${encodeURIComponent(token)}`;
    const es = new EventSource(url);

    es.addEventListener("message", (e) => {
      try {
        const payload = JSON.parse(e.data) as SSEEvent;
        onEventRef.current(payload);
      } catch {
        // ignore parse errors
      }
    });

    es.addEventListener("connected", (e) => {
      try {
        const data = JSON.parse(e.data);
        console.log("SSE connected:", data);
      } catch {
        // ignore
      }
    });

    es.addEventListener("ping", () => {
      // heartbeat — connection is alive
    });

    es.onerror = () => {
      es.close();
      sourceRef.current = null;
      // Reconnect after 3 seconds
      setTimeout(connect, 3000);
    };

    sourceRef.current = es;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (sourceRef.current) {
        sourceRef.current.close();
        sourceRef.current = null;
      }
    };
  }, [connect]);

  return sourceRef.current !== null;
}
