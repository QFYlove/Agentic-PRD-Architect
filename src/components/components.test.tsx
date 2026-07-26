import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { makeSnapshot, RUN_ID } from "../test/fixtures";
import { PRDViewer } from "./PRDViewer";
import { ProductIdeaForm } from "./ProductIdeaForm";
import { RadarScoreChart } from "./RadarScoreChart";
import { RunControls } from "./RunControls";
import { TelemetryPanel } from "./TelemetryPanel";
import { WorkflowDiagram } from "./WorkflowDiagram";

function expectBasicAccessibility(container: HTMLElement) {
  for (const button of container.querySelectorAll("button")) {
    expect(
      button.textContent?.trim() || button.getAttribute("aria-label"),
    ).toBeTruthy();
  }
  for (const field of container.querySelectorAll("input, textarea, select")) {
    expect(
      field.closest("label") ?? field.getAttribute("aria-label"),
    ).toBeTruthy();
  }
  expect(container.querySelectorAll("img:not([alt])")).toHaveLength(0);
}

describe("ProductIdeaForm", () => {
  it("blocks invalid input and shows the boundary message", async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    const { container } = render(
      <ProductIdeaForm isSubmitting={false} onSubmit={submit} />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /开始生成 PRD/i }),
    );
    expect(submit).not.toHaveBeenCalled();
    expect(screen.getByText(/至少用 10 个字符/)).toBeTruthy();
    expectBasicAccessibility(container);
  });

  it("normalizes optional fields and prevents duplicate submission", async () => {
    let release: (() => void) | undefined;
    const submit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          release = resolve;
        }),
    );
    render(<ProductIdeaForm isSubmitting={false} onSubmit={submit} />);
    await userEvent.type(
      screen.getByLabelText(/产品想法/),
      "A detailed podcast subscription experience",
    );
    await userEvent.type(screen.getByLabelText(/目标用户/), "  Fans  ");
    const button = screen.getByRole("button", { name: /开始生成 PRD/i });
    await userEvent.click(button);
    await userEvent.click(button);
    expect(submit).toHaveBeenCalledOnce();
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        target_audience: "Fans",
        user_constraints: null,
      }),
    );
    release?.();
  });
});

describe("RunControls", () => {
  const handlers = {
    onPause: vi.fn().mockResolvedValue(undefined),
    onResume: vi.fn().mockResolvedValue(undefined),
    onCancel: vi.fn().mockResolvedValue(undefined),
    onNewRun: vi.fn(),
  };

  it("shows only legal running controls and explains safe pausing", () => {
    const { rerender } = render(
      <RunControls status="GENERATING" pendingControl={null} {...handlers} />,
    );
    expect(screen.getByRole("button", { name: "暂停" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /继续运行/ })).toBeNull();

    rerender(
      <RunControls
        status="PAUSE_REQUESTED"
        pendingControl={null}
        {...handlers}
      />,
    );
    expect(screen.getByRole("status").textContent).toMatch(/安全步骤/);
    expect(screen.queryByRole("button", { name: "暂停" })).toBeNull();
  });

  it("sends an optional paused override and enforces its limit", async () => {
    render(<RunControls status="PAUSED" pendingControl={null} {...handlers} />);
    const field = screen.getByLabelText(/补充优化要求/);
    await userEvent.type(field, "Include refund handling");
    await userEvent.click(screen.getByRole("button", { name: /继续运行/ }));
    expect(handlers.onResume).toHaveBeenCalledWith("Include refund handling");
  });
});

describe("PRDViewer", () => {
  it("renders GFM, skips raw HTML, and exposes version tabs", () => {
    const { container } = render(
      <PRDViewer
        runId={RUN_ID}
        drafts={{
          1: {
            version: 1,
            attempt: 1,
            content:
              "# Title\n\n| A | B |\n| - | - |\n| 1 | 2 |\n\n<script>alert(1)</script>",
            complete: true,
          },
          2: {
            version: 2,
            attempt: 1,
            content: "# Streaming",
            complete: false,
          },
        }}
        scores={{
          1: { version: 1, tech: 80, ux: 81, biz: 82, overall: 81 },
        }}
        selectedVersion={1}
        onSelectVersion={vi.fn()}
      />,
    );
    expect(screen.getByRole("heading", { name: "Title" })).toBeTruthy();
    expect(container.querySelector("table")).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getAllByRole("tab")).toHaveLength(2);
  });
});

describe("visualization and telemetry fallbacks", () => {
  it("exposes every workflow node and its current status", () => {
    render(
      <WorkflowDiagram
        statuses={{ generator: "RUNNING", tech_reviewer: "FAILED" }}
        runStatus="REVIEWING"
      />,
    );
    expect(screen.getByRole("list", { name: /智能体工作流步骤/ })).toBeTruthy();
    expect(screen.getByLabelText("生成器：运行中")).toBeTruthy();
    expect(screen.getByLabelText("技术：失败")).toBeTruthy();
    expect(screen.getByLabelText("体验：等待中")).toBeTruthy();
  });

  it("updates node and completion states without an asynchronous renderer", () => {
    const { rerender } = render(
      <WorkflowDiagram
        statuses={{ generator: "PENDING" }}
        runStatus="QUEUED"
      />,
    );
    expect(screen.getByLabelText("生成器：等待中")).toBeTruthy();
    expect(screen.getByLabelText("完成：等待中")).toBeTruthy();

    rerender(
      <WorkflowDiagram
        statuses={{ generator: "SUCCEEDED" }}
        runStatus="COMPLETED"
      />,
    );
    expect(screen.getByLabelText("生成器：已完成")).toBeTruthy();
    expect(screen.getByLabelText("完成：已完成")).toBeTruthy();
  });

  it("always exposes textual scores including zero and full values", () => {
    render(
      <RadarScoreChart
        scores={{
          1: { version: 1, tech: 0, ux: 50, biz: 100, overall: 50 },
        }}
      />,
    );
    const table = screen.getByRole("table", {
      name: /PRD 质量评分的文本表格/i,
    });
    expect(within(table).getByText("0")).toBeTruthy();
    expect(within(table).getByText("100")).toBeTruthy();
  });

  it("shows only backend telemetry and mock cost formatting", () => {
    render(
      <TelemetryPanel
        snapshot={makeSnapshot({
          current_iteration: 2,
          total_tokens: {
            input_tokens: 1200,
            output_tokens: 968,
            total_tokens: 2168,
          },
          estimated_cost_usd: 0,
          elapsed_seconds: 65,
        })}
      />,
    );
    expect(screen.getByText("2/3")).toBeTruthy();
    expect(screen.getByText("1分 5秒")).toBeTruthy();
    expect(screen.getByText("2,168")).toBeTruthy();
    expect(screen.getByText("$0.0000")).toBeTruthy();
    expect(screen.getByText("模拟")).toBeTruthy();
  });
});
