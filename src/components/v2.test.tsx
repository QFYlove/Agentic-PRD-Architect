import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { buildRunTimeline } from "../lib/runTimeline";
import { digestRequest, locateSection, parseOutline } from "../lib/prdOutline";
import {
  initialRunViewState,
  isUsableDraft,
  runReducer,
  type RunViewState,
} from "../lib/runReducer";
import type { RunSnapshot } from "../lib/types";
import {
  makeEvaluation,
  makeEvent,
  makeRevisionPlan,
  makeSnapshot,
  makeVersion,
  RUN_ID,
} from "../test/fixtures";
import { PRDViewer } from "./PRDViewer";
import { RevisionPlanPanel } from "./RevisionPlanPanel";
import { RunRequest } from "./RunRequest";
import { RunTimeline } from "./RunTimeline";

function loaded(
  snapshot: RunSnapshot,
  ...events: ReturnType<typeof makeEvent>[]
): RunViewState {
  return events.reduce(
    (state, event) => runReducer(state, { type: "EVENT_RECEIVED", event }),
    runReducer(
      runReducer(initialRunViewState, { type: "RUN_SELECTED", runId: RUN_ID }),
      { type: "SNAPSHOT_LOADED", snapshot },
    ),
  );
}

/** Run 9fa59292's shape: v1 finished and reviewed, v2 cut off mid-sentence. */
function failedV2(): RunSnapshot {
  return makeSnapshot({
    status: "FAILED",
    current_iteration: 2,
    best_version: 1,
    best_score: 76,
    current_prd: "# v2\n\n## 12.3 开发优先级\n第三方解析",
    current_prd_attempt: 1,
    versions: [makeVersion(1, { evaluation: makeEvaluation(78, 76, 74) })],
    pending_revision_plan: makeRevisionPlan(1),
    incomplete_draft: {
      version: 2,
      attempt: 1,
      characters: 30,
      error_code: "PROVIDER_OUTPUT_TRUNCATED",
    },
    error: {
      code: "PROVIDER_OUTPUT_TRUNCATED",
      message: "x",
      retryable: false,
      stage: "generation",
      node: "generator",
      version: 2,
      attempt: 1,
      recovery_action: "continue_from_best",
      category: "output_limit",
    },
    node_timings: [
      {
        node: "generator",
        version: 1,
        attempt: 1,
        seconds: 75.4,
        succeeded: true,
        input_tokens: 1,
        output_tokens: 2,
      },
      {
        node: "generator",
        version: 2,
        attempt: 1,
        seconds: 76.3,
        succeeded: false,
        input_tokens: 1,
        output_tokens: 2,
      },
    ],
  });
}

describe("version lifecycle", () => {
  it("opens a failed run on its best finished version, not the interrupted draft", () => {
    const state = loaded(failedV2());

    expect(state.drafts[2]?.interrupted).toBe(true);
    expect(isUsableDraft(state.drafts[2])).toBe(false);
    expect(isUsableDraft(state.drafts[1])).toBe(true);
    expect(state.selectedVersion).toBe(1);
    expect(state.runError?.node).toBe("generator");
  });

  it("marks a live draft interrupted when the run fails and moves off it", () => {
    const state = loaded(
      makeSnapshot({
        status: "GENERATING",
        current_iteration: 2,
        best_version: 1,
        best_score: 76,
        versions: [makeVersion(1, { evaluation: makeEvaluation(78, 76, 74) })],
      }),
      makeEvent(1, "prd_delta", { version: 2, delta: "# half" }, 2),
      makeEvent(
        2,
        "run_failed",
        {
          error_code: "PROVIDER_OUTPUT_TRUNCATED",
          node_statuses: { generator: "FAILED" },
        },
        2,
      ),
    );

    expect(state.drafts[2]).toMatchObject({
      complete: false,
      interrupted: true,
    });
    expect(state.selectedVersion).toBe(1);
    expect(state.snapshot?.node_statuses.generator).toBe("FAILED");
    expect(state.snapshot?.active_node).toBeNull();
  });

  it("merges durable history once and keeps events ordered and unique", () => {
    const base = loaded(
      makeSnapshot({ status: "COMPLETED", latest_event_sequence: 4 }),
    );
    const history = [
      makeEvent(1, "run_started"),
      makeEvent(3, "prd_generated", { version: 1, content: "# v1" }),
      makeEvent(4, "run_completed"),
    ];
    const once = runReducer(base, {
      type: "HISTORY_LOADED",
      runId: RUN_ID,
      events: history,
    });
    const twice = runReducer(once, {
      type: "HISTORY_LOADED",
      runId: RUN_ID,
      events: history,
    });

    expect(twice.events.map((event) => event.sequence)).toEqual([1, 3, 4]);
    expect(twice.historyLoaded).toBe(true);
    // A live event already delivered by history is not listed twice.
    const live = runReducer(
      { ...twice, status: "GENERATING", latestSequence: 0 },
      {
        type: "EVENT_RECEIVED",
        event: makeEvent(3, "prd_generated", { version: 1, content: "# v1" }),
      },
    );
    expect(live.events.map((event) => event.sequence)).toEqual([1, 3, 4]);
    // History from another run is ignored.
    expect(
      runReducer(base, {
        type: "HISTORY_LOADED",
        runId: "other",
        events: history,
      }).events,
    ).toEqual([]);
  });
});

describe("PRDViewer", () => {
  it("labels an interrupted draft as unfinished and refuses to download it", () => {
    render(
      <PRDViewer
        runId={RUN_ID}
        draft={{
          version: 2,
          attempt: 1,
          content: "# Half",
          complete: false,
          interrupted: true,
        }}
        score={undefined}
      />,
    );

    expect(screen.getByTestId("prd-incomplete-label").textContent).toContain(
      "未完成",
    );
    expect(screen.getByTestId("prd-incomplete-notice")).toBeTruthy();
    expect(screen.queryByText("正在生成")).toBeNull();
    expect(
      (screen.getByTestId("download-markdown") as HTMLButtonElement).disabled,
    ).toBe(true);
  });

  it("builds a table of contents with anchors that match the headings", () => {
    const content =
      "# T\n\n## 1. 概述\n- a\n\n## 2. 用户\n- b\n\n### 2.1 画像\n- c\n";
    const { container } = render(
      <PRDViewer
        runId={RUN_ID}
        draft={{ version: 1, attempt: 1, content, complete: true }}
        score={undefined}
      />,
    );

    const links = within(screen.getByTestId("prd-outline")).getAllByRole(
      "link",
    );
    expect(links.map((link) => link.textContent)).toEqual([
      "1. 概述",
      "2. 用户",
      "2.1 画像",
    ]);
    for (const link of links) {
      const id = link.getAttribute("href")!.slice(1);
      expect(container.querySelector(`#${id}`)).not.toBeNull();
    }
  });

  it("surfaces the structure check without blocking the document", () => {
    render(
      <PRDViewer
        runId={RUN_ID}
        draft={{ version: 1, attempt: 1, content: "# T", complete: true }}
        score={undefined}
        quality={{
          characters: 3,
          sections: 1,
          tables: 0,
          list_items: 0,
          paragraphs: 0,
          long_paragraphs: 2,
          longest_paragraph: 400,
          unlabeled_figures: 3,
          structure_complete: false,
          missing_sections: ["假设与待确认 / Assumptions & open questions"],
          issues: [
            {
              code: "missing_section",
              severity: "error",
              message: "缺少必需章节",
            },
          ],
        }}
      />,
    );

    const note = screen.getByTestId("prd-quality").textContent ?? "";
    expect(note).toContain("缺少章节");
    expect(note).toContain("2 个超长段落");
    expect(note).toContain("3 处数值未标注");
    expect(screen.getByTestId("prd-content")).toBeTruthy();
  });
});

describe("request digest and section lookup", () => {
  it("skips a role-play preamble and finds the product sentence", () => {
    const digest = digestRequest(
      "# 一、你的角色\n\n你是一名资深产品经理。\n\n# 二、项目背景\n\n我们计划开发一款面向中国及海外市场的云端下载与个人云盘一体化产品。目标是闭环。\n\n# 三、功能\n- 下载\n",
    );

    expect(digest.title).toContain("云端下载与个人云盘");
    expect(digest.title).not.toContain("你是");
    expect(digest.topics).toEqual(["你的角色", "项目背景", "功能"]);
  });

  it("locates a reviewer's section by number first, then by wording", () => {
    const outline = parseOutline(
      "# T\n## 5. 需求\n### 5.5 配额与限制\n### 5.6 回收站\n```\n## 9 in code\n```\n",
    );

    expect(locateSection(outline, "5.5 配额")?.text).toBe("5.5 配额与限制");
    expect(locateSection(outline, "§5.6")?.text).toBe("5.6 回收站");
    expect(locateSection(outline, "回收站规则")?.text).toBe("5.6 回收站");
    expect(locateSection(outline, "退款流程")).toBeNull();
    expect(locateSection(outline, "9 in code")).toBeNull();
  });
});

describe("RunRequest", () => {
  it("shows a title and keeps the full Markdown request one click away", async () => {
    const idea = "# 背景\n\n打造一个播客单集付费产品。\n\n- 第一条\n- 第二条";
    render(
      <RunRequest
        snapshot={makeSnapshot({
          user_idea: idea,
          target_audience: "播客听众",
          user_constraints: "移动端优先",
        })}
      />,
    );

    expect(screen.getByTestId("run-title").textContent).toBe(
      "打造一个播客单集付费产品",
    );
    const raw = screen.getByTestId("raw-request") as HTMLDetailsElement;
    expect(raw.open).toBe(false);
    await userEvent.click(screen.getByText("查看原始需求"));
    const content = screen.getByTestId("raw-request-content");
    // Rendered as Markdown: real list items, no literal "#" or "-".
    expect(within(content).getAllByRole("listitem")).toHaveLength(2);
    expect(within(content).getByRole("heading", { name: "背景" })).toBeTruthy();
    expect(content.textContent).not.toContain("- 第一条");
    expect(raw.textContent).toContain("移动端优先");
  });
});

describe("RunTimeline", () => {
  it("reconstructs a failed run from the snapshot alone, with no events", () => {
    const state = loaded(failedV2());
    const model = buildRunTimeline(state)!;

    expect(state.events).toEqual([]);
    expect(model.usableVersions).toEqual([1]);
    const v1 = model.versions.find((item) => item.version === 1)!;
    expect(v1.stages.map((stage) => stage.state)).toEqual([
      "done",
      "done",
      "done",
      "done",
    ]);
    const v2 = model.versions.find((item) => item.version === 2)!;
    expect(v2.stages[0]).toMatchObject({ key: "generation", state: "failed" });
    expect(v2.stages[0]!.result).toContain("未成为正式版本");
    expect(v2.stages.slice(1).every((stage) => stage.state === "skipped")).toBe(
      true,
    );
    expect(model.finalState).toBe("failed");
  });

  it("keeps developer detail folded and the failure reason in the user view", () => {
    render(<RunTimeline state={loaded(failedV2())} />);

    expect(screen.getByTestId("timeline-usable").textContent).toBe("v1");
    expect(screen.getByTestId("timeline-failure").textContent).toContain(
      "输出上限",
    );
    const debug = screen.getByTestId("run-debug") as HTMLDetailsElement;
    expect(debug.open).toBe(false);
    expect(within(debug).getByTestId("debug-error").textContent).toContain(
      "PROVIDER_OUTPUT_TRUNCATED @ generator",
    );
  });
});

describe("RevisionPlanPanel V2 fields", () => {
  it("shows change type, affected sections, declined findings and outcome", () => {
    render(
      <RevisionPlanPanel
        entry={{
          sourceVersion: 1,
          targetVersion: 2,
          plan: makeRevisionPlan(1, {
            items: [
              {
                source_role: "tech",
                source_roles: ["tech", "biz"],
                issue: "第三方分享 MVP 口径不一致",
                required_change: "统一为不纳入 MVP",
                target_section: "5.5 第三方分享",
                target_sections: ["5.5 第三方分享"],
                affected_sections: ["12.1 MVP 范围", "功能架构"],
                priority: "medium",
                change_type: "CONSOLIDATE",
                source_finding_ids: ["v1-tech-3"],
                reason: "三处说法不同",
                must_preserve: ["P1 优先级"],
              },
            ],
            declined_findings: [
              { finding_id: "v1-biz-1", reason: "用户未提供成本数据" },
            ],
          }),
        }}
        resolutions={[
          { finding_id: "v1-tech-3", status: "partially_resolved" },
        ]}
      />,
    );

    const item = screen.getByTestId("revision-item");
    expect(item.dataset.changeType).toBe("CONSOLIDATE");
    expect(within(item).getByTestId("revision-item-change").textContent).toBe(
      "合并",
    );
    expect(
      within(item).getByTestId("revision-item-affected").textContent,
    ).toContain("12.1 MVP 范围");
    expect(within(item).getByTestId("revision-item-status").textContent).toBe(
      "部分解决",
    );
    expect(item.textContent).toContain("必须保留：P1 优先级");
    expect(screen.getByTestId("revision-plan-declined").textContent).toContain(
      "用户未提供成本数据",
    );
  });
});

describe("recovery", () => {
  it("starts a new run from the failure panel and opens it", async () => {
    const { AgentDashboard } = await import("./AgentDashboard");
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const recovered = makeSnapshot({
      run_id: "11111111-2222-3333-4444-555555555555",
      status: "GENERATING",
    });
    const api = {
      getProviders: vi.fn().mockResolvedValue({ providers: [] }),
      createRun: vi.fn(),
      listRuns: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      getRun: vi
        .fn()
        .mockImplementation((id: string) =>
          Promise.resolve(id === RUN_ID ? failedV2() : recovered),
        ),
      getRunHistory: vi.fn().mockResolvedValue({ items: [] }),
      recoverRun: vi.fn().mockResolvedValue({
        run_id: recovered.run_id,
        status: "QUEUED",
        events_url: "/x",
        created_at: "2026-11-08T00:00:00Z",
      }),
      pauseRun: vi.fn(),
      resumeRun: vi.fn(),
      cancelRun: vi.fn(),
      health: vi.fn(),
      eventsUrl: vi.fn().mockReturnValue("http://x/events"),
    };
    const source = {
      addEventListener: vi.fn(),
      close: vi.fn(),
      readyState: 1,
      onopen: null,
      onerror: null,
    };
    render(<AgentDashboard api={api} eventSourceFactory={() => source} />);

    await userEvent.click(
      await screen.findByTestId("recover-continue_from_best"),
    );

    expect(api.recoverRun).toHaveBeenCalledWith(RUN_ID, "continue_from_best");
    await waitFor(() =>
      expect(new URL(window.location.href).searchParams.get("run_id")).toBe(
        recovered.run_id,
      ),
    );
    expect(api.getRunHistory).toHaveBeenCalledWith(RUN_ID);
  });
});
