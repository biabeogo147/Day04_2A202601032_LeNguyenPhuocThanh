import type { ConversationContext, Run, Session, TraceEvent } from "./types";

const jsonHeaders = { "Content-Type": "application/json" };

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const message = await response.text();
    throw new Error(message || `HTTP ${response.status}`);
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export const api = {
  createSession: (context: ConversationContext = {}) =>
    request<Session>("/api/v1/sessions", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        context,
        version_id: "version_1",
        provider: "openai",
      }),
    }),
  getSession: (sessionId: string) =>
    request<Session>(`/api/v1/sessions/${sessionId}`),
  createRun: (sessionId: string, message: string) =>
    request<Run>(`/api/v1/sessions/${sessionId}/runs`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ message }),
    }),
  getRun: (runId: string) => request<Run>(`/api/v1/runs/${runId}`),
  resumeRun: (
    runId: string,
    contextPatch: ConversationContext,
    response: Record<string, unknown>,
  ) =>
    request<Run>(`/api/v1/runs/${runId}/resume`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ context_patch: contextPatch, response }),
    }),
};

export function subscribeToRun(
  runId: string,
  onEvent: (event: TraceEvent) => void,
  onTerminal: () => void,
  onError: (error: Event) => void,
  lastEventId = 0,
): () => void {
  const cursor = lastEventId > 0 ? `?last_event_id=${lastEventId}` : "";
  const source = new EventSource(`/api/v1/runs/${runId}/events${cursor}`);
  const eventTypes = [
    "run.started",
    "run.resumed",
    "node.completed",
    "public.decision",
    "profile.required",
    "tool.requested",
    "tool.completed",
    "retrieval.index.ready",
    "retrieval.candidates",
    "ranking.completed",
    "safety.completed",
    "answer.completed",
    "run.failed",
  ];
  eventTypes.forEach((type) => {
    source.addEventListener(type, (raw) => {
      const event = raw as MessageEvent<string>;
      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse(event.data);
      } catch {
        payload = { summary: event.data };
      }
      onEvent({
        id: Number(event.lastEventId),
        type,
        payload,
        receivedAt: Date.now(),
      });
      if (
        type === "answer.completed" ||
        type === "run.failed" ||
        type === "profile.required"
      ) {
        source.close();
        onTerminal();
      }
    });
  });
  source.onerror = onError;
  return () => source.close();
}
