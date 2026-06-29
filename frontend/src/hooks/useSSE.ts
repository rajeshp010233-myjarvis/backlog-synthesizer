import { useEffect, useRef, useState } from "react";
import type { SSEMessage, ProgressEvent } from "../types";
import { api } from "../services/api";

// runKey: pass a positive integer to connect, -1 to stay disconnected.
// Incrementing runKey while connected closes the old stream and opens a new one.
export function useSSE(sessionId: string | null, runKey: number) {
  const [progress, setProgress] = useState<ProgressEvent[]>([]);
  const [status, setStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!sessionId || runKey < 0) return;

    setStatus("running");
    const es = new EventSource(api.streamUrl(sessionId));
    esRef.current = es;

    es.onmessage = (e) => {
      const msg: SSEMessage = JSON.parse(e.data);
      if (msg.type === "progress") {
        setProgress((prev) => [...prev, msg.payload]);
      } else if (msg.type === "done") {
        setStatus("done");
        es.close();
      } else if (msg.type === "error") {
        setError(msg.message);
        setStatus("error");
        es.close();
      }
    };

    es.onerror = () => {
      setError("Connection lost");
      setStatus("error");
      es.close();
    };

    return () => {
      es.close();
    };
  }, [sessionId, runKey]);

  const reset = () => {
    setProgress([]);
    setStatus("idle");
    setError(null);
  };

  return { progress, status, error, reset };
}
