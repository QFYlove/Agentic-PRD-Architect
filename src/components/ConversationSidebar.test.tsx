import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ConversationSidebar } from "./ConversationSidebar";

describe("ConversationSidebar", () => {
  it("renders persisted conversations and selects one", async () => {
    const onSelect = vi.fn();
    render(
      <ConversationSidebar
        conversations={[
          {
            run_id: "run-1",
            user_idea: "构建一个本地持久化的 PRD 对话工作台",
            status: "COMPLETED",
            current_iteration: 2,
            max_iterations: 3,
            latest_score: 88,
            created_at: "2026-07-26T10:00:00Z",
            updated_at: "2026-07-26T10:05:00Z",
          },
        ]}
        selectedRunId={null}
        isLoading={false}
        onSelect={onSelect}
        onNewConversation={vi.fn()}
      />,
    );

    await userEvent.click(
      screen.getByRole("button", {
        name: /构建一个本地持久化的 PRD 对话工作台/,
      }),
    );

    expect(onSelect).toHaveBeenCalledWith("run-1");
    expect(screen.getByText("88.0")).toBeTruthy();
  });

  it("labels the best version rather than the latest score", async () => {
    render(
      <ConversationSidebar
        conversations={[
          {
            run_id: "run-2",
            user_idea: "第三版评分回退的任务",
            status: "MAX_ITERATIONS_REACHED",
            current_iteration: 3,
            max_iterations: 3,
            latest_score: 78.3,
            best_version: 2,
            best_score: 81.7,
            created_at: "2026-07-26T10:00:00Z",
            updated_at: "2026-07-26T10:05:00Z",
          },
        ]}
        selectedRunId={null}
        isLoading={false}
        onSelect={vi.fn()}
        onNewConversation={vi.fn()}
      />,
    );

    expect(screen.getByText("v2 · 81.7")).toBeTruthy();
    expect(screen.queryByText("78.3")).toBeNull();
  });
});
