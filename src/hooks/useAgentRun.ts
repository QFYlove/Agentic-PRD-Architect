import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";

import { ApiClientError, HttpAgentApi, type AgentApi } from "../lib/api";
import { parseRunEvent } from "../lib/contracts";
import {
  initialRunViewState,
  runReducer,
  type RunViewState,
} from "../lib/runReducer";
import { localizedErrorMessage } from "../lib/errorMessages";
import type {
  CreateRunRequest,
  ResumeRunRequest,
  RunEventType,
  RunSummary,
} from "../lib/types";
import { isTerminalRunStatus } from "../lib/types";

const EVENT_TYPES: RunEventType[] = [
  "run_started",
  "status_changed",
  "node_started",
  "prd_delta",
  "prd_stream_reset",
  "prd_generated",
  "review_completed",
  "scores_updated",
  "revision_planned",
  "pause_requested",
  "run_paused",
  "run_resumed",
  "telemetry_updated",
  "run_completed",
  "max_iterations_reached",
  "run_cancelled",
  "run_failed",
];

/** `EventSource.readyState` values, per the WHATWG spec. */
export const SOURCE_CONNECTING = 0;
export const SOURCE_OPEN = 1;
export const SOURCE_CLOSED = 2;

/** Consecutive CONNECTING-state errors tolerated before forcing recovery. */
const MAX_NATIVE_RETRIES = 3;

export interface EventSourceLike {
  addEventListener(
    type: string,
    listener: (event: MessageEvent<string>) => void,
  ): void;
  close(): void;
  readonly readyState: number;
  onopen: ((event: Event) => void) | null;
  onerror: ((event: Event) => void) | null;
}

export type EventSourceFactory = (url: string) => EventSourceLike;

export interface UseAgentRunOptions {
  api?: AgentApi;
  eventSourceFactory?: EventSourceFactory;
}

export interface AgentRunController {
  state: RunViewState;
  conversations: RunSummary[];
  isLoadingConversations: boolean;
  createRun(request: CreateRunRequest): Promise<void>;
  selectRun(runId: string): Promise<void>;
  refreshConversations(): Promise<void>;
  pause(): Promise<void>;
  resume(userOverride?: string): Promise<void>;
  cancel(): Promise<void>;
  retryConnection(): Promise<void>;
  newRun(): void;
  selectVersion(version: number): void;
  clearError(): void;
}

function defaultEventSourceFactory(url: string): EventSourceLike {
  return new EventSource(url) as unknown as EventSourceLike;
}

function messageFromError(error: unknown): string {
  if (error instanceof ApiClientError) {
    return localizedErrorMessage(error.code);
  }
  return "客户端发生了意外错误，请重试。";
}

function readRunIdFromUrl(): string | null {
  const value = new URL(window.location.href).searchParams.get("run_id");
  return value?.trim() || null;
}

function writeRunIdToUrl(runId: string | null): void {
  const url = new URL(window.location.href);
  if (runId) {
    url.searchParams.set("run_id", runId);
  } else {
    url.searchParams.delete("run_id");
  }
  window.history.replaceState({}, "", url);
}

export function useAgentRun(
  options: UseAgentRunOptions = {},
): AgentRunController {
  const api = useMemo(() => options.api ?? new HttpAgentApi(), [options.api]);
  const eventSourceFactory =
    options.eventSourceFactory ?? defaultEventSourceFactory;
  const [state, dispatch] = useReducer(runReducer, initialRunViewState);
  const [conversations, setConversations] = useState<RunSummary[]>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(true);
  const sourceRef = useRef<EventSourceLike | null>(null);
  const sessionRef = useRef(0);
  const mountedRef = useRef(false);

  const closeSource = useCallback(() => {
    sourceRef.current?.close();
    sourceRef.current = null;
  }, []);

  const refreshConversations = useCallback(async (): Promise<void> => {
    setIsLoadingConversations(true);
    try {
      const response = await api.listRuns();
      if (mountedRef.current) {
        setConversations(response.items);
      }
    } catch {
      if (mountedRef.current) {
        setConversations([]);
      }
    } finally {
      if (mountedRef.current) {
        setIsLoadingConversations(false);
      }
    }
  }, [api]);

  const connect = useCallback(
    (runId: string, afterSequence: number, session: number): void => {
      if (!mountedRef.current || session !== sessionRef.current) {
        return;
      }
      closeSource();
      dispatch({ type: "CONNECTION_CHANGED", connection: "connecting" });
      const source = eventSourceFactory(api.eventsUrl(runId, afterSequence));
      sourceRef.current = source;
      let consecutiveErrors = 0;
      let recovering = false;

      source.onopen = () => {
        if (session !== sessionRef.current) {
          source.close();
          return;
        }
        consecutiveErrors = 0;
        dispatch({ type: "CONNECTION_CHANGED", connection: "open" });
      };

      for (const eventType of EVENT_TYPES) {
        source.addEventListener(eventType, (message) => {
          // A superseded source can still deliver buffered events after
          // recovery swapped in its replacement; those would double-apply
          // deltas the new source is about to replay.
          if (session !== sessionRef.current || sourceRef.current !== source) {
            return;
          }
          try {
            const event = parseRunEvent(JSON.parse(message.data));
            dispatch({ type: "EVENT_RECEIVED", event });
            if (
              event.event === "run_completed" ||
              event.event === "max_iterations_reached" ||
              event.event === "run_cancelled" ||
              event.event === "run_failed"
            ) {
              source.close();
              if (sourceRef.current === source) {
                sourceRef.current = null;
              }
              dispatch({
                type: "CONNECTION_CHANGED",
                connection: "closed",
              });
              void refreshConversations();
            }
          } catch {
            dispatch({
              type: "ERROR",
              message: "收到的实时事件格式无效，已停止处理该事件。",
            });
          }
        });
      }

      source.onerror = () => {
        if (
          session !== sessionRef.current ||
          recovering ||
          sourceRef.current !== source
        ) {
          return;
        }
        consecutiveErrors += 1;
        // CONNECTING means the browser is already retrying on its own, so let
        // it. CLOSED is fatal -- EventSource will never reconnect, and waiting
        // for a third error that can never arrive is what used to strand the UI
        // in "connecting" forever.
        if (
          source.readyState !== SOURCE_CLOSED &&
          consecutiveErrors < MAX_NATIVE_RETRIES
        ) {
          dispatch({ type: "CONNECTION_CHANGED", connection: "connecting" });
          return;
        }
        recovering = true;
        source.close();
        sourceRef.current = null;
        dispatch({ type: "CONNECTION_CHANGED", connection: "recovering" });
        void api
          .getRun(runId)
          .then((snapshot) => {
            if (!mountedRef.current || session !== sessionRef.current) {
              return;
            }
            dispatch({ type: "SNAPSHOT_LOADED", snapshot });
            if (isTerminalRunStatus(snapshot.status)) {
              dispatch({
                type: "CONNECTION_CHANGED",
                connection: "closed",
              });
              return;
            }
            connect(runId, snapshot.latest_event_sequence, session);
          })
          .catch((error: unknown) => {
            if (mountedRef.current && session === sessionRef.current) {
              dispatch({ type: "ERROR", message: messageFromError(error) });
              dispatch({
                type: "CONNECTION_CHANGED",
                connection: "closed",
              });
            }
          });
      };
    },
    [api, closeSource, eventSourceFactory, refreshConversations],
  );

  const hydrate = useCallback(
    async (runId: string, session: number): Promise<void> => {
      try {
        const snapshot = await api.getRun(runId);
        if (!mountedRef.current || session !== sessionRef.current) {
          return;
        }
        dispatch({ type: "SNAPSHOT_LOADED", snapshot });
        void refreshConversations();
        if (isTerminalRunStatus(snapshot.status)) {
          dispatch({ type: "CONNECTION_CHANGED", connection: "closed" });
          return;
        }
        connect(runId, snapshot.latest_event_sequence, session);
      } catch (error) {
        if (!mountedRef.current || session !== sessionRef.current) {
          return;
        }
        closeSource();
        writeRunIdToUrl(null);
        dispatch({ type: "RESET" });
        dispatch({
          type: "ERROR",
          message: `无法恢复该任务。${messageFromError(error)}`,
        });
      }
    },
    [api, closeSource, connect, refreshConversations],
  );

  useEffect(() => {
    mountedRef.current = true;
    void refreshConversations();
    const runId = readRunIdFromUrl();
    if (runId) {
      const session = ++sessionRef.current;
      dispatch({ type: "RUN_SELECTED", runId });
      void hydrate(runId, session);
    }
    return () => {
      mountedRef.current = false;
      sessionRef.current += 1;
      closeSource();
    };
  }, [closeSource, hydrate, refreshConversations]);

  const createRun = useCallback(
    async (request: CreateRunRequest): Promise<void> => {
      const session = ++sessionRef.current;
      closeSource();
      dispatch({ type: "CREATE_STARTED" });
      try {
        const created = await api.createRun(request);
        if (!mountedRef.current || session !== sessionRef.current) {
          return;
        }
        writeRunIdToUrl(created.run_id);
        dispatch({ type: "RUN_SELECTED", runId: created.run_id });
        void refreshConversations();
        await hydrate(created.run_id, session);
      } catch (error) {
        if (mountedRef.current && session === sessionRef.current) {
          writeRunIdToUrl(null);
          dispatch({ type: "ERROR", message: messageFromError(error) });
        }
      }
    },
    [api, closeSource, hydrate, refreshConversations],
  );

  const selectRun = useCallback(
    async (runId: string): Promise<void> => {
      if (!runId || runId === state.runId) {
        return;
      }
      const session = ++sessionRef.current;
      closeSource();
      writeRunIdToUrl(runId);
      dispatch({ type: "RUN_SELECTED", runId });
      await hydrate(runId, session);
    },
    [closeSource, hydrate, state.runId],
  );

  const runControl = useCallback(
    async (
      control: "pause" | "resume" | "cancel",
      request?: ResumeRunRequest,
    ): Promise<void> => {
      if (!state.runId || state.pendingControl) {
        return;
      }
      dispatch({ type: "CONTROL_STARTED", control });
      try {
        const response =
          control === "pause"
            ? await api.pauseRun(state.runId)
            : control === "cancel"
              ? await api.cancelRun(state.runId)
              : await api.resumeRun(state.runId, request ?? {});
        dispatch({ type: "STATUS_UPDATED", status: response.status });
      } catch (error) {
        dispatch({ type: "ERROR", message: messageFromError(error) });
      } finally {
        dispatch({ type: "CONTROL_FINISHED" });
      }
    },
    [api, state.pendingControl, state.runId],
  );

  const retryConnection = useCallback(async (): Promise<void> => {
    if (!state.runId) {
      return;
    }
    // Bumping the session first invalidates any in-flight automatic recovery,
    // so a manual retry never races it into two live EventSources.
    const session = ++sessionRef.current;
    closeSource();
    dispatch({ type: "CLEAR_ERROR" });
    dispatch({ type: "CONNECTION_CHANGED", connection: "recovering" });
    // Deliberately not RUN_SELECTED: this recalibrates the existing run from
    // its latest snapshot rather than discarding the trace and starting over.
    await hydrate(state.runId, session);
  }, [closeSource, hydrate, state.runId]);

  const newRun = useCallback(() => {
    sessionRef.current += 1;
    closeSource();
    writeRunIdToUrl(null);
    dispatch({ type: "RESET" });
  }, [closeSource]);

  return {
    state,
    conversations,
    isLoadingConversations,
    createRun,
    selectRun,
    refreshConversations,
    pause: () => runControl("pause"),
    resume: (userOverride?: string) =>
      runControl("resume", {
        user_override: userOverride?.trim() || null,
      }),
    cancel: () => runControl("cancel"),
    retryConnection,
    newRun,
    selectVersion: (version: number) =>
      dispatch({ type: "VERSION_SELECTED", version }),
    clearError: () => dispatch({ type: "CLEAR_ERROR" }),
  };
}
