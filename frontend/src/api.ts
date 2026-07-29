import type { Profile, ProfileDraft, Run, Session, TraceEvent } from "./types";

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
  profiles: () => request<Profile[]>("/api/v1/profiles"),
  createProfile: (payload: ProfileDraft) =>
    request<Profile>("/api/v1/profiles", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),
  updateProfile: (id: string, payload: Partial<ProfileDraft>) =>
    request<Profile>(`/api/v1/profiles/${id}`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify(payload),
    }),
  createSession: (profileId: string) =>
    request<Session>("/api/v1/sessions", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        profile_id: profileId,
        version_id: "version_1",
        provider: "openai",
      }),
    }),
  createRun: (sessionId: string, message: string) =>
    request<Run>(`/api/v1/sessions/${sessionId}/runs`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ message }),
    }),
  getRun: (runId: string) => request<Run>(`/api/v1/runs/${runId}`),
  resumeRun: (
    runId: string,
    profilePatch: Partial<ProfileDraft>,
    response: Record<string, unknown>,
  ) =>
    request<Run>(`/api/v1/runs/${runId}/resume`, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ profile_patch: profilePatch, response }),
    }),
};

export function subscribeToRun(
  runId: string,
  onEvent: (event: TraceEvent) => void,
  onTerminal: () => void,
  onError: (error: Event) => void,
): () => void {
  const source = new EventSource(`/api/v1/runs/${runId}/events`);
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
