"use client";
import { useEffect, useRef, useState } from "react";
import { tokenStore } from "@/lib/api";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_URL = API_URL.replace(/^http/, "ws");

export type ReviewEvent = {
  type: "pr_status" | "review_completed" | "review_failed";
  payload: Record<string, any>;
  receivedAt: number;
};

const MAX_EVENTS = 25;
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 15000;

/**
 * Subscribes to the backend's /ws/reviews channel and keeps a rolling log of
 * review pipeline events (queued/reviewing/completed/failed) so the
 * dashboard can render them live instead of polling.
 */
export function useReviewEvents(enabled: boolean) {
  const [events, setEvents] = useState<ReviewEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef<WebSocket | null>(null);
  const attemptRef = useRef(0);
  const closedByClientRef = useRef(false);

  useEffect(() => {
    if (!enabled) return;

    closedByClientRef.current = false;

    function connect() {
      tokenStore.load();
      const token = tokenStore.access;
      if (!token) return;

      const ws = new WebSocket(`${WS_URL}/api/v1/ws/reviews?token=${encodeURIComponent(token)}`);
      socketRef.current = ws;

      ws.onopen = () => {
        attemptRef.current = 0;
        setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setEvents((prev) => [
            { type: data.type, payload: data.payload, receivedAt: Date.now() },
            ...prev,
          ].slice(0, MAX_EVENTS));
        } catch {
          // ignore malformed frames
        }
      };

      ws.onclose = () => {
        setConnected(false);
        socketRef.current = null;
        if (closedByClientRef.current) return;
        const delay = Math.min(RECONNECT_BASE_MS * 2 ** attemptRef.current, RECONNECT_MAX_MS);
        attemptRef.current += 1;
        setTimeout(connect, delay);
      };

      ws.onerror = () => {
        ws.close();
      };
    }

    connect();

    return () => {
      closedByClientRef.current = true;
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, [enabled]);

  return { events, connected };
}
