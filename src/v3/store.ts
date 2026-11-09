import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, errorText } from "./api";
import type {
  Brief,
  Conversation,
  Finding,
  Item,
  Job,
  JobEvent,
  Meta,
  ProjectSummary,
  Proposal,
  ReviewResult,
  SectionList,
  VersionSummary,
} from "./types";
import { isTerminal, watchJob } from "./useJob";
import { useToast } from "./ui";

export interface ProjectData {
  summary: ProjectSummary | null;
  conversation: Conversation | null;
  items: Item[];
  baseline: Finding[];
  findings: Finding[];
  sections: SectionList | null;
  reviews: ReviewResult[];
  proposals: Proposal[];
  versions: VersionSummary[];
  briefs: Brief[];
}

const EMPTY: ProjectData = {
  summary: null,
  conversation: null,
  items: [],
  baseline: [],
  findings: [],
  sections: null,
  reviews: [],
  proposals: [],
  versions: [],
  briefs: [],
};

/** Live text of sections being generated, keyed by section code. */
export type Streams = Record<string, string>;

export interface ProjectStore {
  data: ProjectData;
  meta: Meta | null;
  loaded: boolean;
  missing: boolean;
  job: Job | null;
  streams: Streams;
  reload: () => Promise<void>;
  /** Run a mutation; reload afterwards; report errors as a toast. */
  act: <T>(run: () => Promise<T>, done?: string) => Promise<T | undefined>;
  /** Start an AI task returned by ``run`` and follow it to the end. */
  startJob: (run: () => Promise<Job>, label: string) => Promise<void>;
}

const JOB_DONE: Record<string, string> = {
  explore: "已整理这一轮的回答。",
  analyze: "产品分析完成。",
  outline: "大纲已生成，请检查后确认。",
  generate: "章节生成完成。",
  review: "审查完成。",
  optimize: "修改提案已生成，请逐条确认。",
};

export function useProjectStore(
  projectId: string,
  meta: Meta | null,
): ProjectStore {
  const toast = useToast();
  const [data, setData] = useState<ProjectData>(EMPTY);
  const [loaded, setLoaded] = useState(false);
  const [missing, setMissing] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [streams, setStreams] = useState<Streams>({});
  const current = useRef(projectId);
  current.current = projectId;

  const reload = useCallback(async () => {
    const id = projectId;
    try {
      const [
        summary,
        conversation,
        items,
        baseline,
        findings,
        sections,
        reviews,
        proposals,
        versions,
        briefs,
      ] = await Promise.all([
        api.project(id),
        api.conversation(id),
        api.items(id),
        api.findings(id, "baseline"),
        api.findings(id, "prd"),
        api.sections(id),
        api.reviews(id),
        api.proposals(id),
        api.versions(id),
        api.briefs(id),
      ]);
      if (current.current !== id) return;
      setData({
        summary,
        conversation,
        items: items.items,
        baseline: baseline.items,
        findings: findings.items,
        sections,
        reviews: reviews.items,
        proposals: proposals.items,
        versions: versions.items,
        briefs: briefs.items,
      });
      setLoaded(true);
      setJob((existing) => existing ?? summary.active_job);
    } catch (error) {
      if (error instanceof Error && "status" in error && error.status === 404) {
        setMissing(true);
        return;
      }
      toast({ text: errorText(error), error: true });
    }
  }, [projectId, toast]);

  useEffect(() => {
    setData(EMPTY);
    setLoaded(false);
    setMissing(false);
    setJob(null);
    void reload();
  }, [reload]);

  // Follow a running job; reload project data when it ends.
  useEffect(() => {
    if (!job || isTerminal(job)) return;
    const onEvent = (event: JobEvent) => {
      const code = String(event.payload.code ?? "");
      if (
        event.event === "section_started" ||
        event.event === "section_reset"
      ) {
        setStreams((prev) => ({ ...prev, [code]: "" }));
      } else if (event.event === "section_delta") {
        const delta = String(event.payload.delta ?? "");
        setStreams((prev) => ({ ...prev, [code]: (prev[code] ?? "") + delta }));
      } else if (
        event.event === "section_done" ||
        event.event === "section_failed"
      ) {
        setStreams((prev) => {
          const next = { ...prev };
          delete next[code];
          return next;
        });
        void reload();
      }
    };
    const watch = watchJob(job, onEvent, (finished) => {
      setJob(finished);
      setStreams({});
      void reload();
      if (finished.status === "succeeded") {
        const failed = (finished.result.failed as string[] | undefined) ?? [];
        const reviewers =
          (finished.result.failed_reviewers as string[] | undefined) ?? [];
        if (failed.length) {
          toast({
            text: `${failed.length} 个章节生成失败，其他章节已保存。可以单独重试。`,
            error: true,
          });
        } else if (reviewers.length) {
          toast({
            text: `有 ${reviewers.length} 个审查角色没有完成，其余结果已保存。`,
            error: true,
          });
        } else {
          toast({ text: JOB_DONE[finished.kind] ?? "完成。" });
        }
      } else if (finished.status === "failed") {
        toast({
          text: `${finished.error?.message ?? "AI 任务失败"}（${finished.error?.code ?? "ERROR"}）`,
          error: true,
        });
      }
    });
    return () => watch.stop();
    // Only a new job id needs a new subscription.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id]);

  const act = useCallback(
    async <T>(run: () => Promise<T>, done?: string): Promise<T | undefined> => {
      try {
        const result = await run();
        await reload();
        if (done) toast({ text: done });
        return result;
      } catch (error) {
        toast({ text: errorText(error), error: true });
        await reload();
        return undefined;
      }
    },
    [reload, toast],
  );

  const startJob = useCallback(
    async (run: () => Promise<Job>, label: string) => {
      try {
        const started = await run();
        setJob(started);
        await reload();
      } catch (error) {
        toast({ text: `${label}：${errorText(error)}`, error: true });
        await reload();
      }
    },
    [reload, toast],
  );

  return useMemo(
    () => ({
      data,
      meta,
      loaded,
      missing,
      job,
      streams,
      reload,
      act,
      startJob,
    }),
    [data, meta, loaded, missing, job, streams, reload, act, startJob],
  );
}

export function running(store: ProjectStore, kind?: string): boolean {
  const { job } = store;
  return !!job && !isTerminal(job) && (!kind || job.kind === kind);
}
