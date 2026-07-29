import { beforeEach, describe, expect, it, vi } from "vitest";
import { subscribeToRun } from "./api";

class FakeEventSource {
  static instance: FakeEventSource;
  listeners = new Map<string, (event: MessageEvent<string>) => void>();
  onerror: ((event: Event) => void) | null = null;
  closed = false;
  url: string;

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instance = this;
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    this.listeners.set(type, listener as (event: MessageEvent<string>) => void);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, data: object, id: string) {
    this.listeners.get(type)?.({
      data: JSON.stringify(data),
      lastEventId: id,
    } as MessageEvent<string>);
  }
}

describe("SSE run subscription", () => {
  beforeEach(() => {
    vi.stubGlobal("EventSource", FakeEventSource);
  });

  it("parses typed events and closes after a terminal event", () => {
    const received: string[] = [];
    const terminal = vi.fn();
    const stop = subscribeToRun(
      "run-1",
      (event) => received.push(`${event.id}:${event.type}`),
      terminal,
      vi.fn(),
    );

    expect(FakeEventSource.instance.url).toBe("/api/v1/runs/run-1/events");
    FakeEventSource.instance.emit("tool.completed", { tool: "search" }, "4");
    FakeEventSource.instance.emit("answer.completed", { status: "answered" }, "5");

    expect(received).toEqual(["4:tool.completed", "5:answer.completed"]);
    expect(terminal).toHaveBeenCalledOnce();
    expect(FakeEventSource.instance.closed).toBe(true);
    stop();
  });

  it("closes the stream at profile interrupt so resume can open a new stream", () => {
    const terminal = vi.fn();
    subscribeToRun("run-2", vi.fn(), terminal, vi.fn());

    FakeEventSource.instance.emit(
      "profile.required",
      { fields: ["goals"], question: "Mục tiêu?" },
      "3",
    );

    expect(FakeEventSource.instance.closed).toBe(true);
    expect(terminal).toHaveBeenCalledOnce();
  });
});
