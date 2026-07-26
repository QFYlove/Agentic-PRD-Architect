import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentApi, HealthResponse } from "../lib/api";
import type {
  ControlResponse,
  CreateRunRequest,
  CreateRunResponse,
  ResumeRunRequest,
  RunSnapshot,
} from "../lib/types";
import { makeEvent, makeSnapshot, RUN_ID } from "../test/fixtures";
import { useAgentRun, type EventSourceLike } from "./useAgentRun";

class MockEventSource implements EventSourceLike {
  readonly listeners = new Map<
    string,
    Array<(event: MessageEvent<string>) => void>
  >();
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closed = false;

  constructor(public readonly url: string) {}

  addEventListener(
    type: string,
    listener: (event: MessageEvent<string>) => void,
  ): void {
    const existing = this.listeners.get(type) ?? [];
    existing.push(listener);
    this.listeners.set(type, existing);
  }

  emit(type: string, value: unknown): void {
    const event = new MessageEvent<string>(type, {
      data: JSON.stringify(value),
    });
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }

  open(): void {
    this.onopen?.(new Event("open"));
  }

  error(): void {
    this.onerror?.(new Event("error"));
  }

  close(): void {
    this.closed = true;
  }
}

class FakeApi implements AgentApi {
  getRun = vi.fn<(runId: string) => Promise<RunSnapshot>>();
  createRun =
    vi.fn<(request: CreateRunRequest) => Promise<CreateRunResponse>>();
  pauseRun = vi.fn<(runId: string) => Promise<ControlResponse>>();
  resumeRun =
    vi.fn<
      (runId: string, request: ResumeRunRequest) => Promise<ControlResponse>
    >();
  cancelRun = vi.fn<(runId: string) => Promise<ControlResponse>>();
  health = vi.fn<() => Promise<HealthResponse>>();

  eventsUrl(runId: string, afterSequence: number): string {
    return `http://api.test/api/runs/${runId}/events?after_sequence=${afterSequence}`;
  }
}

function setup(snapshot = makeSnapshot({ latest_event_sequence: 7 })) {
  const api = new FakeApi();
  api.getRun.mockResolvedValue(snapshot);
  api.createRun.mockResolvedValue({
    run_id: RUN_ID,
    status: "QUEUED",
    events_url: `/api/runs/${RUN_ID}/events`,
    created_at: "2026-07-26T10:00:00Z",
  });
  api.pauseRun.mockResolvedValue({
    run_id: RUN_ID,
    status: "PAUSE_REQUESTED",
    message: "Pause requested.",
  });
  api.resumeRun.mockResolvedValue({
    run_id: RUN_ID,
    status: "OPTIMIZING",
    message: "Resumed.",
  });
  api.cancelRun.mockResolvedValue({
    run_id: RUN_ID,
    status: "CANCEL_REQUESTED",
    message: "Cancel requested.",
  });
  const sources: MockEventSource[] = [];
  const factory = (url: string) => {
    const source = new MockEventSource(url);
    sources.push(source);
    return source;
  };
  return { api, sources, factory };
}

describe("useAgentRun restoration and EventSource lifecycle", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/");
  });

  it("restores solely from URL, snapshots first, then subscribes after sequence", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );

    await waitFor(() => expect(sources).toHaveLength(1));
    expect(api.getRun).toHaveBeenCalledWith(RUN_ID);
    expect(sources[0]?.url).toContain("after_sequence=7");
    expect(result.current.state.runId).toBe(RUN_ID);
  });

  it("creates one run, updates URL, and ignores duplicate submit while hydrating", async () => {
    const { api, sources, factory } = setup();
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );
    const request: CreateRunRequest = {
      user_idea: "A sufficiently detailed podcast idea.",
      quality_threshold: 85,
      max_iterations: 3,
    };
    await act(async () => {
      await result.current.createRun(request);
    });
    expect(new URL(window.location.href).searchParams.get("run_id")).toBe(
      RUN_ID,
    );
    expect(api.createRun).toHaveBeenCalledOnce();
    expect(sources).toHaveLength(1);
  });

  it("keeps native reconnect for two errors and snapshot-recovers exactly once on three", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    renderHook(() => useAgentRun({ api, eventSourceFactory: factory }));
    await waitFor(() => expect(sources).toHaveLength(1));
    act(() => {
      sources[0]?.error();
      sources[0]?.error();
    });
    expect(api.getRun).toHaveBeenCalledTimes(1);
    act(() => sources[0]?.error());
    await waitFor(() => expect(sources).toHaveLength(2));
    expect(api.getRun).toHaveBeenCalledTimes(2);
    expect(sources[0]?.closed).toBe(true);
  });

  it("resets the error streak after a successful open", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    renderHook(() => useAgentRun({ api, eventSourceFactory: factory }));
    await waitFor(() => expect(sources).toHaveLength(1));
    act(() => {
      sources[0]?.error();
      sources[0]?.error();
      sources[0]?.open();
      sources[0]?.error();
    });
    expect(api.getRun).toHaveBeenCalledTimes(1);
  });

  it("closes at terminal and stops accepting later events", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );
    await waitFor(() => expect(sources).toHaveLength(1));
    act(() => sources[0]?.emit("run_completed", makeEvent(8, "run_completed")));
    expect(result.current.state.status).toBe("COMPLETED");
    expect(sources[0]?.closed).toBe(true);
    act(() =>
      sources[0]?.emit(
        "prd_delta",
        makeEvent(9, "prd_delta", {
          version: 1,
          attempt: 1,
          delta: "late",
        }),
      ),
    );
    expect(result.current.state.drafts[1]).toBeUndefined();
  });

  it("New Run closes and invalidates the old source and removes URL identity", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );
    await waitFor(() => expect(sources).toHaveLength(1));
    act(() => result.current.newRun());
    expect(sources[0]?.closed).toBe(true);
    expect(new URL(window.location.href).searchParams.has("run_id")).toBe(
      false,
    );
    act(() =>
      sources[0]?.emit(
        "prd_delta",
        makeEvent(8, "prd_delta", {
          version: 1,
          attempt: 1,
          delta: "late",
        }),
      ),
    );
    expect(result.current.state).toMatchObject({
      runId: null,
      selectedVersion: null,
      drafts: {},
    });
  });

  it("cleans an unknown run from the URL and closes on unmount", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const unknown = setup();
    unknown.api.getRun.mockRejectedValue(new Error("not found"));
    const first = renderHook(() =>
      useAgentRun({
        api: unknown.api,
        eventSourceFactory: unknown.factory,
      }),
    );
    await waitFor(() =>
      expect(first.result.current.state.error).toMatch(/无法恢复该任务/),
    );
    expect(new URL(window.location.href).searchParams.has("run_id")).toBe(
      false,
    );
    first.unmount();

    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const active = setup();
    const second = renderHook(() =>
      useAgentRun({ api: active.api, eventSourceFactory: active.factory }),
    );
    await waitFor(() => expect(active.sources).toHaveLength(1));
    second.unmount();
    expect(active.sources[0]?.closed).toBe(true);
  });

  it("reports recovery snapshot failures without creating another source", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    api.getRun
      .mockResolvedValueOnce(makeSnapshot({ latest_event_sequence: 7 }))
      .mockRejectedValueOnce(new Error("snapshot unavailable"));
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );
    await waitFor(() => expect(sources).toHaveLength(1));
    act(() => {
      sources[0]?.error();
      sources[0]?.error();
      sources[0]?.error();
    });
    await waitFor(() =>
      expect(result.current.state.error).toMatch(/客户端发生了意外错误/),
    );
    expect(sources).toHaveLength(1);
    expect(result.current.state.connection).toBe("closed");
  });
});
