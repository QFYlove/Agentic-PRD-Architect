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
});
