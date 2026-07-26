import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentApi } from "../lib/api";
import type { RunStatus } from "../lib/types";
import { makeSnapshot, RUN_ID } from "../test/fixtures";
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
});
