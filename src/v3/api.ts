import { resolvePublicApiBaseUrl } from "../lib/config";
import type {
  Brief,
  Conversation,
  DiffSection,
  Finding,
  FindingEvent,
  FindingStatus,
  GroupKey,
  Impact,
  Item,
  ItemStatus,
  Job,
  Meta,
  ProjectSummary,
  Proposal,
  Quality,
  ReviewResult,
  Revision,
  Section,
  SectionList,
  Sources,
  VersionDetail,
  VersionSummary,
} from "./types";

export class V3Error extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
    public readonly current: unknown = null,
  ) {
    super(message);
    this.name = "V3Error";
  }
}

/** User-facing Chinese text for the backend's error codes. */
const MESSAGES: Record<string, string> = {
  JOB_IN_PROGRESS: "这个项目正在执行一个 AI 任务，请等它完成。",
  SECTION_CHANGED: "这一节刚刚被修改过。已载入最新内容，请在此基础上再改。",
  BRIEF_CONFIRMED: "已确认的 Brief 不能修改，可以重新整理一个新版本。",
  BRIEF_NOT_CONFIRMED: "请先确认 Product Brief。",
  OUTLINE_NOT_CONFIRMED: "请先确认大纲。",
  NOTHING_ACCEPTED: "先采纳至少一条审查意见，再生成修改提案。",
  NOTHING_TO_GENERATE: "所有章节都已经有内容。",
  HUMAN_SECTION: "你写过的章节不会被重新生成，请直接编辑。",
  BASELINE_EMPTY: "需求基线还是空的，先回答几个问题。",
  DOCUMENT_EMPTY: "还没有 PRD 正文。",
  DOCUMENT_INCOMPLETE: "还有章节没有完成，全部完成后才能审查全文。",
  NOTE_REQUIRED: "请写下你希望怎么改。",
  PROPOSAL_CLOSED: "这个提案已经处理过了。",
  EMPTY_TURN: "回答、跳过或补充一点内容后再发送。",
  PROJECT_NOT_FOUND: "项目不存在或已删除。",
  REQUEST_VALIDATION_FAILED: "提交的内容格式不正确。",
};

export function errorText(error: unknown): string {
  if (error instanceof V3Error) {
    return MESSAGES[error.code] ?? error.message;
  }
  if (error instanceof TypeError) {
    return "无法连接到服务，请确认后端已经启动。";
  }
  return "操作没有完成，请重试。";
}

type Body = Record<string, unknown> | undefined;

export class V3Api {
  readonly base: string;

  constructor(base: string = resolvePublicApiBaseUrl()) {
    this.base = base.replace(/\/$/, "");
  }

  async call<T>(path: string, method = "GET", body?: Body): Promise<T> {
    const init: RequestInit = {
      method,
      headers: { Accept: "application/json" },
    };
    if (body !== undefined) {
      init.body = JSON.stringify(body);
      init.headers = { ...init.headers, "Content-Type": "application/json" };
    }
    const response = await fetch(`${this.base}/api/v3${path}`, init);
    if (response.status === 204) {
      return undefined as T;
    }
    const text = await response.text();
    const data: unknown = text ? JSON.parse(text) : null;
    if (!response.ok) {
      const detail =
        data && typeof data === "object" && "error" in data
          ? (data as { error: { code: string; message: string } }).error
          : { code: "HTTP_ERROR", message: `HTTP ${response.status}` };
      throw new V3Error(detail.message, detail.code, response.status);
    }
    return data as T;
  }

  async text(path: string): Promise<string> {
    const response = await fetch(`${this.base}/api/v3${path}`);
    if (!response.ok) {
      throw new V3Error(
        `HTTP ${response.status}`,
        "HTTP_ERROR",
        response.status,
      );
    }
    return response.text();
  }

  eventsUrl(jobId: string, after: number): string {
    return `${this.base}/api/v3/jobs/${jobId}/events?after_sequence=${after}`;
  }

  meta = () => this.call<Meta>("/meta");
  projects = () => this.call<{ items: ProjectSummary[] }>("/projects");
  project = (id: string) => this.call<ProjectSummary>(`/projects/${id}`);
  createProject = (body: { text: string; entry_mode: string; depth: string }) =>
    this.call<{ project: ProjectSummary; job: Job | null }>(
      "/projects",
      "POST",
      body,
    );
  rename = (id: string, name: string) =>
    this.call<ProjectSummary>(`/projects/${id}`, "PATCH", { name });
  remove = (id: string) => this.call<void>(`/projects/${id}`, "DELETE");
  jobs = (id: string) => this.call<{ items: Job[] }>(`/projects/${id}/jobs`);
  job = (id: string) => this.call<Job>(`/jobs/${id}`);

  conversation = (id: string) =>
    this.call<Conversation>(`/projects/${id}/conversation`);
  submitTurn = (
    id: string,
    body: {
      answers: { question: string; kind: string; text: string }[];
      supplement: string;
      depth?: string;
    },
  ) => this.call<Job>(`/projects/${id}/turns`, "POST", body);
  items = (id: string) =>
    this.call<{ items: Item[]; core_ready: boolean }>(`/projects/${id}/items`);
  addItem = (id: string, group: GroupKey, content: string) =>
    this.call<Item>(`/projects/${id}/items`, "POST", { group, content });
  patchItem = (
    itemId: string,
    body: { content?: string; status?: ItemStatus; reason?: string },
  ) => this.call<Item>(`/items/${itemId}`, "PATCH", body);
  revisions = (itemId: string) =>
    this.call<{ items: Revision[] }>(`/items/${itemId}/revisions`);
  analyze = (id: string, briefId?: string) =>
    this.call<Job>(
      `/projects/${id}/analyze`,
      "POST",
      briefId ? { brief_id: briefId } : undefined,
    );

  briefs = (id: string) =>
    this.call<{ items: Brief[] }>(`/projects/${id}/briefs`);
  draftBrief = (id: string) =>
    this.call<Brief>(`/projects/${id}/briefs`, "POST");
  editBrief = (briefId: string, key: string, text: string) =>
    this.call<Brief>(`/briefs/${briefId}`, "PATCH", { key, text });
  confirmBrief = (briefId: string) =>
    this.call<Brief>(`/briefs/${briefId}/confirm`, "POST");
  outline = (id: string) => this.call<Job>(`/projects/${id}/outline`, "POST");
  confirmOutline = (id: string) =>
    this.call<ProjectSummary>(`/projects/${id}/outline/confirm`, "POST");

  sections = (id: string) => this.call<SectionList>(`/projects/${id}/sections`);
  addSection = (
    id: string,
    title: string,
    after: string | null,
    level: number,
  ) =>
    this.call<Section>(`/projects/${id}/sections`, "POST", {
      title,
      after,
      level,
    });
  reorder = (id: string, order: { code: string; level: number }[]) =>
    this.call<{ items: Section[] }>(`/projects/${id}/sections/order`, "PUT", {
      order,
    });
  saveSection = (
    sectionId: string,
    body: { row_version: number; body?: string; title?: string },
  ) =>
    this.call<{ section: Section; impact: Impact }>(
      `/sections/${sectionId}`,
      "PATCH",
      body,
    );
  deleteSection = (sectionId: string, rowVersion: number) =>
    this.call<void>(
      `/sections/${sectionId}?row_version=${rowVersion}`,
      "DELETE",
    );
  sources = (sectionId: string) =>
    this.call<Sources>(`/sections/${sectionId}/sources`);
  generate = (id: string, sections?: string[]) =>
    this.call<Job>(
      `/projects/${id}/generate`,
      "POST",
      sections ? { sections } : {},
    );

  review = (id: string, sections?: string[]) =>
    this.call<Job>(
      `/projects/${id}/reviews`,
      "POST",
      sections ? { sections } : {},
    );
  reviews = (id: string) =>
    this.call<{ items: ReviewResult[] }>(`/projects/${id}/reviews`);
  findings = (id: string, scope: "baseline" | "prd") =>
    this.call<{ items: Finding[] }>(`/projects/${id}/findings?scope=${scope}`);
  decide = (findingId: string, status: FindingStatus, note?: string) =>
    this.call<Finding>(
      `/findings/${findingId}`,
      "PATCH",
      note ? { status, note } : { status },
    );
  findingHistory = (findingId: string) =>
    this.call<{ items: FindingEvent[] }>(`/findings/${findingId}/history`);

  optimize = (id: string) => this.call<Job>(`/projects/${id}/optimize`, "POST");
  proposals = (id: string) =>
    this.call<{ items: Proposal[] }>(`/projects/${id}/proposals`);
  apply = (proposalId: string, changes: string[]) =>
    this.call<{
      applied: string[];
      conflicts: string[];
      findings: string[];
      impact: Impact;
      version: number | null;
    }>(`/proposals/${proposalId}/apply`, "POST", { changes });
  discard = (proposalId: string) =>
    this.call<Proposal>(`/proposals/${proposalId}/discard`, "POST");

  versions = (id: string) =>
    this.call<{ items: VersionSummary[] }>(`/projects/${id}/versions`);
  version = (id: string, n: number) =>
    this.call<VersionDetail>(`/projects/${id}/versions/${n}`);
  saveVersion = (id: string, note: string) =>
    this.call<VersionSummary>(`/projects/${id}/versions`, "POST", { note });
  diff = (id: string, a: number, b: number) =>
    this.call<{ sections: DiffSection[] }>(
      `/projects/${id}/versions/${a}/diff/${b}`,
    );
  quality = (id: string) => this.call<Quality>(`/projects/${id}/quality`);
  exportMarkdown = (id: string, version?: number) =>
    this.text(
      `/projects/${id}/export.md${version ? `?version=${version}` : ""}`,
    );
}

export const api = new V3Api();
