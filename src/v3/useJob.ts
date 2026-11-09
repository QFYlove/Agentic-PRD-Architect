import { api } from "./api";
import type { Job, JobEvent } from "./types";

const TERMINAL = new Set(["succeeded", "failed", "cancelled"]);
const TERMINAL_EVENTS = new Set([
  "job_succeeded",
  "job_failed",
  "job_cancelled",
]);

export function isTerminal(job: Job | null | undefined): boolean {
  return !!job && TERMINAL.has(job.status);
}

export interface JobWatch {
  stop(): void;
}

/**
 * Follow one job's SSE stream and survive disconnects.
 *
 * The cursor is the last sequence seen. When the stream errors, the job is
 * re-read: a finished job is reported from its stored state, a running one is
 * re-subscribed after the cursor, so no event is applied twice and none of the
 * durable ones is missed.
 */
export function watchJob(
  job: Job,
  onEvent: (event: JobEvent) => void,
  onDone: (job: Job) => void,
): JobWatch {
  let cursor = 0;
  let source: EventSource | null = null;
  let stopped = false;
  let retry: ReturnType<typeof setTimeout> | null = null;
  let finished = false;

  const finish = async () => {
    if (finished || stopped) return;
    finished = true;
    source?.close();
    try {
      onDone(await api.job(job.id));
    } catch {
      onDone({ ...job, status: "failed" });
    }
  };

  const connect = () => {
    if (stopped) return;
    if (typeof EventSource === "undefined") {
      poll();
      return;
    }
    source = new EventSource(api.eventsUrl(job.id, cursor));
    const handle = (message: MessageEvent<string>) => {
      try {
        const event = JSON.parse(message.data) as JobEvent;
        if (typeof event.sequence !== "number" || event.sequence <= cursor)
          return;
        cursor = event.sequence;
        onEvent(event);
        if (TERMINAL_EVENTS.has(event.event)) void finish();
      } catch {
        // A malformed frame is skipped; the stored job state is authoritative.
      }
    };
    for (const name of [
      "job_started",
      "section_started",
      "section_delta",
      "section_reset",
      "section_done",
      "section_failed",
      "reviewer_done",
      "reviewer_failed",
      "job_succeeded",
      "job_failed",
      "job_cancelled",
    ]) {
      source.addEventListener(name, handle as EventListener);
    }
    source.onerror = () => {
      source?.close();
      source = null;
      void api
        .job(job.id)
        .then((latest) => {
          if (TERMINAL.has(latest.status)) {
            void finish();
          } else {
            retry = setTimeout(connect, 800);
          }
        })
        .catch(() => {
          retry = setTimeout(connect, 1500);
        });
    };
  };

  const poll = () => {
    if (stopped) return;
    void api
      .job(job.id)
      .then((latest) => {
        if (TERMINAL.has(latest.status)) void finish();
        else retry = setTimeout(poll, 600);
      })
      .catch(() => {
        retry = setTimeout(poll, 1500);
      });
  };

  connect();
  return {
    stop() {
      stopped = true;
      source?.close();
      if (retry) clearTimeout(retry);
    },
  };
}
