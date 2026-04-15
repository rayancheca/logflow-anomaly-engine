import { useEffect, useRef, useState } from "react";
import type { StreamMessage } from "../types";

export function useLiveStream(url: string): { data: StreamMessage | null; connected: boolean } {
  const [data, setData] = useState<StreamMessage | null>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;

    function connect() {
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const full = url.startsWith("ws") ? url : `${proto}//${window.location.host}${url}`;
      const ws = new WebSocket(full);
      wsRef.current = ws;
      ws.onopen = () => {
        if (!cancelled) setConnected(true);
      };
      ws.onclose = () => {
        if (cancelled) return;
        setConnected(false);
        retryTimer = setTimeout(connect, 800);
      };
      ws.onerror = () => {
        try { ws.close(); } catch { /* noop */ }
      };
      ws.onmessage = (ev) => {
        try {
          const parsed = JSON.parse(ev.data) as StreamMessage;
          if (!cancelled) setData(parsed);
        } catch {
          /* noop */
        }
      };
    }

    connect();
    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      if (wsRef.current) try { wsRef.current.close(); } catch { /* noop */ }
    };
  }, [url]);

  return { data, connected };
}
