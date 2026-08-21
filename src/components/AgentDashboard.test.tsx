import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentApi } from "../lib/api";
import type { RunStatus } from "../lib/types";
import {
  makeEvaluation,
  makeRevisionPlan,
  makeSnapshot,
  makeVersion,
  RUN_ID,
} from "../test/fixtures";
import { AgentDashboard } from "./AgentDashboard";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi
      .fn()
      .mockResolvedValue({ svg: "<svg><title>Workflow</title></svg>" }),
  },
}));

function apiFor(status: RunStatus): AgentApi {
  return {
    createRun: vi.fn(),
    listRuns: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    getRun: vi.fn().mockResolvedValue(
      makeSnapshot({
        status,
        error:
          status === "FAILED"
            ? {
                code: "WORKFLOW_FAILED",
                message: "The workflow could not complete.",
                retryable: false,
              }
            : null,
      }),
    ),
    pauseRun: vi.fn(),
    resumeRun: vi.fn(),
    cancelRun: vi.fn(),
    health: vi.fn(),
    eventsUrl: (runId, afterSequence) =>
      `http://api.test/${runId}?after_sequence=${afterSequence}`,
  };
}

function eventSourceFactory() {
  return {
    addEventListener: vi.fn(),
    close: vi.fn(),
    readyState: 0,
    onopen: null,
    onerror: null,
  };
}

describe("AgentDashboard state framework", () => {
  afterEach(() => {
    window.history.replaceState({}, "", "/");
  });

  it("shows the empty creation state without a run URL", () => {
    render(
      <AgentDashboard
        api={apiFor("QUEUED")}
        eventSourceFactory={eventSourceFactory}
      />,
    );
    expect(screen.getByRole("heading", { name: /让每一份需求/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /开始生成 PRD/i })).toBeTruthy();
  });

  it("shows an explicit creating state while POST /api/runs is pending", async () => {
    const api = apiFor("QUEUED");
    api.createRun = vi.fn(() => new Promise<never>(() => undefined));
    render(
      <AgentDashboard api={api} eventSourceFactory={eventSourceFactory} />,
    );
    await userEvent.type(
      screen.getByLabelText(/产品想法/),
      "A detailed product workflow for independent creators",
    );
    await userEvent.click(
      screen.getByRole("button", { name: /开始生成 PRD/i }),
    );
    expect(
      (
        screen.getByRole("button", {
          name: /正在创建任务/i,
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  it.each([
    ["GENERATING", "生成中"],
    ["PAUSE_REQUESTED", "安全暂停中"],
    ["PAUSED", "已暂停"],
    ["COMPLETED", "已完成"],
    ["FAILED", "运行失败"],
  ] as const)("renders the %s dashboard state", async (status, label) => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    render(
      <AgentDashboard
        api={apiFor(status)}
        eventSourceFactory={eventSourceFactory}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("run-status").textContent).toBe(label),
    );
    expect(screen.getByRole("heading", { name: /运行控制/i })).toBeTruthy();
    if (status === "PAUSED") {
      expect(screen.getByLabelText(/补充优化要求/)).toBeTruthy();
    }
    if (status === "FAILED") {
      expect(screen.getByRole("alert")).toBeTruthy();
    }
  });

  it("offers manual recalibration while a live run is not connected", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const api = apiFor("GENERATING");
    render(
      <AgentDashboard api={api} eventSourceFactory={eventSourceFactory} />,
    );
    const reconnect = await screen.findByTestId("reconnect");
    await userEvent.click(reconnect);
    await waitFor(() => expect(api.getRun).toHaveBeenCalledTimes(2));
    expect(api.createRun).not.toHaveBeenCalled();
    expect(screen.getByTestId("run-status").textContent).toBe("生成中");
  });

  it("hides manual recalibration once the run is terminal", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    render(
      <AgentDashboard
        api={apiFor("COMPLETED")}
        eventSourceFactory={eventSourceFactory}
      />,
    );
    await waitFor(() =>
      expect(screen.getByTestId("run-status").textContent).toBe("已完成"),
    );
    expect(screen.queryByTestId("reconnect")).toBeNull();
  });

  it("follows the selected version through reviewer detail and its revision plan", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const api = apiFor("COMPLETED");
    api.getRun = vi.fn().mockResolvedValue(
      makeSnapshot({
        status: "COMPLETED",
        current_iteration: 2,
        current_prd: "# Version 2",
        versions: [
          makeVersion(1, { evaluation: makeEvaluation(65, 70, 78) }),
          makeVersion(2, {
            evaluation: makeEvaluation(88, 89, 87),
            revision_plan: makeRevisionPlan(1, { objective: "Fix v1." }),
          }),
        ],
      }),
    );
    render(
      <AgentDashboard api={api} eventSourceFactory={eventSourceFactory} />,
    );

    // v2 is selected on load: it has reviews, but no plan came from it.
    await userEvent.click(await screen.findByTestId("workspace-tab-review"));
    const panel = await screen.findByTestId("review-panel");
    expect(panel.dataset.version).toBe("2");
    expect(screen.getByTestId("reviewer-score-tech").textContent).toContain(
      "88",
    );
    expect(
      (screen.getByTestId("workspace-tab-plan") as HTMLButtonElement).disabled,
    ).toBe(true);

    await userEvent.click(await screen.findByTestId("version-tab-v1"));
    await waitFor(() =>
      expect(screen.getByTestId("review-panel").dataset.version).toBe("1"),
    );
    expect(screen.getByTestId("reviewer-score-tech").textContent).toContain(
      "65",
    );

    await userEvent.click(screen.getByTestId("workspace-tab-plan"));
    const plan = screen.getByTestId("revision-plan-panel");
    expect(plan.dataset.sourceVersion).toBe("1");
    expect(plan.dataset.targetVersion).toBe("2");
    expect(screen.getByTestId("revision-plan-objective").textContent).toContain(
      "Fix v1.",
    );
  });

  it("opens on the document and keeps run observability behind its own tab", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const api = apiFor("COMPLETED");
    api.getRun = vi.fn().mockResolvedValue(
      makeSnapshot({
        status: "COMPLETED",
        current_iteration: 2,
        current_prd: "# Version 2",
        versions: [
          makeVersion(1, { evaluation: makeEvaluation(65, 70, 78) }),
          makeVersion(2, { evaluation: makeEvaluation(88, 89, 87) }),
        ],
      }),
    );
    render(
      <AgentDashboard api={api} eventSourceFactory={eventSourceFactory} />,
    );

    // The PRD is the default panel, and the trace panels are not on screen.
    expect(await screen.findByTestId("workspace-panel-prd")).toBeTruthy();
    expect(
      screen.getByTestId("workspace-tab-prd").getAttribute("aria-selected"),
    ).toBe("true");
    expect(screen.queryByTestId("trace-heading")).toBeNull();
    expect(screen.queryByRole("heading", { name: "运行指标" })).toBeNull();

    await userEvent.click(screen.getByTestId("workspace-tab-trace"));
    expect(screen.getByTestId("workspace-panel-trace")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "运行指标" })).toBeTruthy();
    expect(screen.queryByTestId("prd-content")).toBeNull();
  });

  it("compares the selected version against the one before it", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const api = apiFor("COMPLETED");
    api.getRun = vi.fn().mockResolvedValue(
      makeSnapshot({
        status: "COMPLETED",
        current_iteration: 2,
        current_prd: "# v2\n\n- Refunds within 14 days.\n",
        versions: [
          makeVersion(1, {
            content: "# v1\n\n- Buy an episode.\n",
            evaluation: makeEvaluation(65, 70, 78),
          }),
          makeVersion(2, {
            content: "# v2\n\n- Refunds within 14 days.\n",
            evaluation: makeEvaluation(88, 89, 87),
          }),
        ],
      }),
    );
    render(
      <AgentDashboard api={api} eventSourceFactory={eventSourceFactory} />,
    );

    await userEvent.click(await screen.findByTestId("workspace-tab-diff"));
    const diff = await screen.findByTestId("version-diff");
    expect(diff.dataset.sourceVersion).toBe("1");
    expect(diff.dataset.targetVersion).toBe("2");
    expect(diff.dataset.mode).toBe("reading");

    // v1 has nothing before it, so the tab has nothing to show.
    await userEvent.click(screen.getByTestId("version-tab-v1"));
    await waitFor(() =>
      expect(
        (screen.getByTestId("workspace-tab-diff") as HTMLButtonElement)
          .disabled,
      ).toBe(true),
    );
    expect(screen.getByTestId("workspace-panel-prd")).toBeTruthy();
  });

  it("says plainly that a capped run never reached its target", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const api = apiFor("MAX_ITERATIONS_REACHED");
    api.getRun = vi.fn().mockResolvedValue(
      makeSnapshot({
        status: "MAX_ITERATIONS_REACHED",
        current_iteration: 3,
        max_iterations: 3,
        quality_threshold: 85,
        best_version: 2,
        best_score: 81.7,
        versions: [
          makeVersion(1, { evaluation: makeEvaluation(65, 66, 69) }),
          makeVersion(2, { evaluation: makeEvaluation(80, 82, 83) }),
          makeVersion(3, { evaluation: makeEvaluation(77, 78, 80) }),
        ],
      }),
    );
    render(
      <AgentDashboard api={api} eventSourceFactory={eventSourceFactory} />,
    );

    const outcome = await screen.findByTestId("run-outcome");
    expect(outcome.dataset.tone).toBe("unmet");
    expect(outcome.textContent).toContain("未达到目标评分");
    expect(screen.getByTestId("outcome-fact-目标评分").textContent).toBe("85");
    expect(screen.getByTestId("outcome-fact-最佳版本").textContent).toBe(
      "v2 · 81.7",
    );
    expect(screen.getByTestId("outcome-fact-已完成迭代").textContent).toBe(
      "3/3 轮",
    );
    expect(screen.getByTestId("run-outcome-note").textContent).toBe(
      "迭代预算已用尽",
    );
  });

  it("reports a passed gate when the score cleared the target with no blockers", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const api = apiFor("COMPLETED");
    api.getRun = vi.fn().mockResolvedValue(
      makeSnapshot({
        status: "COMPLETED",
        current_iteration: 2,
        max_iterations: 3,
        quality_threshold: 85,
        best_version: 2,
        best_score: 88,
        versions: [
          makeVersion(1, { evaluation: makeEvaluation(65, 66, 69) }),
          makeVersion(2, { evaluation: makeEvaluation(88, 88, 88) }),
        ],
      }),
    );
    render(
      <AgentDashboard api={api} eventSourceFactory={eventSourceFactory} />,
    );

    const outcome = await screen.findByTestId("run-outcome");
    expect(outcome.dataset.tone).toBe("passed");
    expect(outcome.textContent).toContain("已达到目标质量");
    // The advice-only fixture leaves no blocker, so nothing may read as one.
    expect(screen.getByTestId("outcome-fact-必须修复").textContent).toBe("0");
    expect(outcome.textContent).not.toContain("需要修改");
    expect(screen.getByTestId("run-outcome-note").textContent).toBe(
      "剩余条目为改进建议，不阻塞交付",
    );
  });

  it("does not present a blocked gate as a finished document", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const api = apiFor("MAX_ITERATIONS_REACHED");
    api.getRun = vi.fn().mockResolvedValue(
      makeSnapshot({
        status: "MAX_ITERATIONS_REACHED",
        current_iteration: 3,
        max_iterations: 3,
        quality_threshold: 85,
        best_version: 3,
        best_score: 91,
        versions: [
          makeVersion(3, {
            evaluation: makeEvaluation(91, 91, 91, {
              blockers: 1,
            }),
          }),
        ],
      }),
    );
    render(
      <AgentDashboard api={api} eventSourceFactory={eventSourceFactory} />,
    );

    const outcome = await screen.findByTestId("run-outcome");
    expect(outcome.dataset.tone).toBe("blocked");
    expect(outcome.textContent).toContain("已达到评分目标，但质量门禁未通过");
    expect(screen.getByTestId("outcome-fact-必须修复").textContent).toBe("1");
    expect(screen.getByTestId("run-outcome-note").textContent).toBe(
      "剩余 1 项必须修复问题 · 已达到最大迭代次数",
    );
  });

  it("shows no outcome line for a cancelled run", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    render(
      <AgentDashboard
        api={apiFor("CANCELLED")}
        eventSourceFactory={eventSourceFactory}
      />,
    );

    await waitFor(() =>
      expect(screen.getByTestId("run-status").textContent).toBe("已取消"),
    );
    expect(screen.queryByTestId("run-outcome")).toBeNull();
  });

  /**
   * The real failure this covers: v1 and v2 generated and were reviewed, the
   * optimizer planned v3, and v3 was cut off. The page reported 「首版 PRD 生成失
   * 败」 with two finished documents on screen.
   */
  it("names the version that failed and keeps every earlier version reachable", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const api = apiFor("FAILED");
    api.getRun = vi.fn().mockResolvedValue(
      makeSnapshot({
        status: "FAILED",
        current_iteration: 3,
        best_version: 2,
        best_score: 80.7,
        versions: [
          makeVersion(1, { evaluation: makeEvaluation(60, 64, 68) }),
          makeVersion(2, {
            evaluation: makeEvaluation(78, 82, 82),
            revision_plan: makeRevisionPlan(1),
          }),
        ],
        pending_revision_plan: makeRevisionPlan(2),
        error: {
          code: "PROVIDER_OUTPUT_TRUNCATED",
          message: "Truncated output.",
          retryable: true,
        },
      }),
    );
    render(
      <AgentDashboard api={api} eventSourceFactory={eventSourceFactory} />,
    );

    const notice = await screen.findByTestId("failure-notice");
    expect(notice.textContent).toContain("v3 生成失败");
    expect(notice.textContent).not.toContain("首版 PRD 生成失败");
    // Both survivors and which one is worth reading.
    expect(screen.getByTestId("failure-notice-detail").textContent).toBe(
      "v1、v2 及已有评审和修订计划已保留。最佳可用版本：v2 · 80.7",
    );
    // The distinct cause reaches the reader instead of the generic fallback.
    expect(screen.getByRole("alert").textContent).toContain("长度限制");
    expect(screen.getByRole("alert").textContent).not.toContain(
      "操作失败，请稍后重试",
    );
    // Nothing from the provider or the process leaks into the page.
    expect(document.body.textContent).not.toContain("Truncated output.");
    // v1 and v2 are still selectable, and review and plan tabs are still open.
    expect(screen.getByTestId("version-tab-v1")).toBeTruthy();
    expect(screen.getByTestId("version-tab-v2")).toBeTruthy();
    expect(
      (screen.getByTestId("workspace-tab-review") as HTMLButtonElement)
        .disabled,
    ).toBe(false);
    await userEvent.click(screen.getByTestId("version-tab-v1"));
    expect(
      (screen.getByTestId("workspace-tab-plan") as HTMLButtonElement).disabled,
    ).toBe(false);
  });

  /** The only state 「首版」 describes: nothing was ever committed. */
  it("says the first version failed only when no version landed", async () => {
    window.history.replaceState({}, "", `/?run_id=${RUN_ID}`);
    const api = apiFor("FAILED");
    api.getRun = vi.fn().mockResolvedValue(
      makeSnapshot({
        status: "FAILED",
        current_iteration: 1,
        versions: [],
        error: {
          code: "RUN_TIMEOUT",
          message: "Deadline exceeded after 900s.",
          retryable: true,
        },
      }),
    );
    render(
      <AgentDashboard api={api} eventSourceFactory={eventSourceFactory} />,
    );

    const notice = await screen.findByTestId("failure-notice");
    expect(notice.textContent).toContain("首版 PRD 生成失败");
    expect(screen.queryByTestId("failure-notice-detail")).toBeNull();
    // A known code, so the banner says what actually happened.
    expect(screen.getByRole("alert").textContent).toContain("任务运行超时");
    expect(document.body.textContent).not.toContain("Deadline exceeded");
  });
});
