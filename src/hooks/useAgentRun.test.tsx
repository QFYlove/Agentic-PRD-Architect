import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentApi, HealthResponse } from "../lib/api";
import type {
  ControlResponse,
  CreateRunRequest,
  CreateRunResponse,
  ResumeRunRequest,
  RunSnapshot,
  RunListResponse,
} from "../lib/types";
import { makeEvent, makeSnapshot, RUN_ID } from "../test/fixtures";
import {
  SOURCE_CLOSED,
  SOURCE_CONNECTING,
  SOURCE_OPEN,
  useAgentRun,
  type EventSourceLike,
} from "./useAgentRun";

class MockEventSource implements EventSourceLike {
  readonly listeners = new Map<
    string,
    Array<(event: MessageEvent<string>) => void>
  >();
  onopen: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  closed = false;
  readyState = SOURCE_CONNECTING;

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
    this.readyState = SOURCE_OPEN;
    this.onopen?.(new Event("open"));
  }

  /** A recoverable error: the browser keeps retrying on its own. */
  error(): void {
    this.readyState = SOURCE_CONNECTING;
    this.onerror?.(new Event("error"));
  }

  /** A fatal close: EventSource will never reconnect by itself. */
  fatalError(): void {
    this.readyState = SOURCE_CLOSED;
    this.onerror?.(new Event("error"));
  }

  close(): void {
    this.closed = true;
    this.readyState = SOURCE_CLOSED;
  }
}

class FakeApi implements AgentApi {
  listRuns = vi.fn<() => Promise<RunListResponse>>();
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
  api.listRuns.mockResolvedValue({ items: [], total: 0 });
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

  it("loads conversations and switches the selected run", async () => {
    const alternateRunId = "6f0de4df-13f5-4126-ac32-3a1795b99270";
    const { api, sources, factory } = setup();
    api.listRuns.mockResolvedValue({
      items: [
        {
          run_id: alternateRunId,
          user_idea: "A persisted conversation for another product.",
          status: "COMPLETED",
          current_iteration: 2,
          max_iterations: 3,
          latest_score: 88,
          created_at: "2026-07-26T09:00:00Z",
          updated_at: "2026-07-26T09:05:00Z",
        },
      ],
      total: 1,
    });
    api.getRun.mockImplementation(async (runId) =>
      makeSnapshot({
        run_id: runId,
        status: runId === alternateRunId ? "COMPLETED" : "GENERATING",
      }),
    );
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );

    await waitFor(() => expect(result.current.conversations).toHaveLength(1));
    await act(async () => {
      await result.current.selectRun(alternateRunId);
    });

    expect(result.current.state.runId).toBe(alternateRunId);
    expect(new URL(window.location.href).searchParams.get("run_id")).toBe(
      alternateRunId,
    );
    expect(sources).toHaveLength(0);
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

  it("recovers immediately on a single fatal CLOSED error", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );
    await waitFor(() => expect(sources).toHaveLength(1));
    act(() => sources[0]?.fatalError());
    await waitFor(() => expect(sources).toHaveLength(2));
    expect(api.getRun).toHaveBeenCalledTimes(2);
    expect(sources[0]?.closed).toBe(true);
    expect(result.current.state.runId).toBe(RUN_ID);
  });

  it("keeps a single CONNECTING error on native retry without rebuilding", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );
    await waitFor(() => expect(sources).toHaveLength(1));
    act(() => sources[0]?.open());
    act(() => sources[0]?.error());
    expect(api.getRun).toHaveBeenCalledTimes(1);
    expect(sources).toHaveLength(1);
    expect(sources[0]?.closed).toBe(false);
    expect(result.current.state.connection).toBe("connecting");
  });

  it("ignores late events from the superseded source after recovery", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );
    await waitFor(() => expect(sources).toHaveLength(1));
    act(() => sources[0]?.fatalError());
    await waitFor(() => expect(sources).toHaveLength(2));

    const ghost = makeEvent(8, "prd_delta", {
      version: 1,
      attempt: 1,
      delta: "ghost",
    });
    act(() => sources[0]?.emit("prd_delta", ghost));
    expect(result.current.state.drafts[1]).toBeUndefined();

    act(() =>
      sources[1]?.emit(
        "prd_delta",
        makeEvent(8, "prd_delta", {
          version: 1,
          attempt: 1,
          delta: "real",
        }),
      ),
    );
    expect(result.current.state.drafts[1]?.content).toBe("real");
  });

  it("stops reconnecting once the run is terminal", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );
    await waitFor(() => expect(sources).toHaveLength(1));
    act(() => sources[0]?.emit("run_completed", makeEvent(8, "run_completed")));
    expect(sources[0]?.closed).toBe(true);
    act(() => sources[0]?.fatalError());
    expect(sources).toHaveLength(1);
    expect(api.getRun).toHaveBeenCalledTimes(1);
    expect(result.current.state.connection).toBe("closed");
  });

  it("recovers a terminal run found by the recovery snapshot without resubscribing", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    api.getRun
      .mockResolvedValueOnce(makeSnapshot({ latest_event_sequence: 7 }))
      .mockResolvedValueOnce(
        makeSnapshot({ status: "COMPLETED", latest_event_sequence: 12 }),
      );
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );
    await waitFor(() => expect(sources).toHaveLength(1));
    act(() => sources[0]?.fatalError());
    await waitFor(() => expect(result.current.state.status).toBe("COMPLETED"));
    expect(sources).toHaveLength(1);
    expect(result.current.state.connection).toBe("closed");
  });

  it("manual retry recalibrates the existing run instead of creating one", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );
    await waitFor(() => expect(sources).toHaveLength(1));
    act(() =>
      sources[0]?.emit(
        "status_changed",
        makeEvent(8, "status_changed", { current: "REVIEWING" }),
      ),
    );
    expect(result.current.state.events).toHaveLength(1);

    await act(async () => {
      await result.current.retryConnection();
    });

    expect(api.createRun).not.toHaveBeenCalled();
    expect(api.getRun).toHaveBeenCalledTimes(2);
    expect(result.current.state.runId).toBe(RUN_ID);
    expect(result.current.state.events).toHaveLength(1);
    expect(sources).toHaveLength(2);
    expect(sources[0]?.closed).toBe(true);
    expect(new URL(window.location.href).searchParams.get("run_id")).toBe(
      RUN_ID,
    );
  });

  it("manual retry during automatic recovery leaves one live source", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const { api, sources, factory } = setup();
    let releaseRecovery: (() => void) | null = null;
    api.getRun
      .mockResolvedValueOnce(makeSnapshot({ latest_event_sequence: 7 }))
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            releaseRecovery = () =>
              resolve(makeSnapshot({ latest_event_sequence: 7 }));
          }),
      )
      .mockResolvedValue(makeSnapshot({ latest_event_sequence: 9 }));
    const { result } = renderHook(() =>
      useAgentRun({ api, eventSourceFactory: factory }),
    );
    await waitFor(() => expect(sources).toHaveLength(1));
    act(() => sources[0]?.fatalError());
    await waitFor(() => expect(releaseRecovery).not.toBeNull());

    await act(async () => {
      await result.current.retryConnection();
    });
    act(() => releaseRecovery?.());
    await waitFor(() => expect(sources).toHaveLength(2));

    expect(sources).toHaveLength(2);
    expect(sources[1]?.closed).toBe(false);
    expect(sources[1]?.url).toContain("after_sequence=9");
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
