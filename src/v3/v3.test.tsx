import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { nextStep } from "./Home";
import type { ProjectSummary } from "./types";
import { Markdown, quoteOf, StatusMark } from "./ui";

function summary(overrides: Partial<ProjectSummary> = {}): ProjectSummary {
  return {
    id: "p",
    code: "P-0001",
    name: "云盘",
    entry_mode: "idea",
    depth: "detailed",
    round: 2,
    doc_title: "",
    outline_confirmed_at: null,
    updated_at: new Date().toISOString(),
    created_at: new Date().toISOString(),
    stage: "explore",
    counts: {
      questions: 0,
      decide: 0,
      items: 3,
      sections: 0,
      written: 0,
      open_findings: 0,
      blocking: 0,
    },
    brief_version: null,
    active_job: null,
    ...overrides,
  };
}

describe("next step on the home page", () => {
  it("names what waits for the user first", () => {
    const p = summary({
      counts: { ...summary().counts, questions: 3, decide: 8 },
    });
    expect(nextStep(p)).toBe("3 个问题等你回答，8 项内容等你决定");
  });

  it("follows the stage when nothing is pending", () => {
    expect(nextStep(summary({ stage: "brief" }))).toBe("生成 PRD 大纲");
    expect(
      nextStep(
        summary({
          stage: "review",
          counts: { ...summary().counts, open_findings: 2 },
        }),
      ),
    ).toBe("2 条审查意见待处理");
  });
});

describe("status marks", () => {
  it("leaves confirmed items unmarked", () => {
    const { container } = render(<StatusMark status="confirmed" />);
    expect(container.firstChild).toBeNull();
  });

  it("labels undecided items", () => {
    render(<StatusMark status="inferred" />);
    expect(screen.getByRole("img", { name: "AI 推断" })).toBeTruthy();
  });
});

describe("document rendering", () => {
  it("turns a finding's quoted evidence into a clickable mark", () => {
    render(
      <Markdown
        body="- 任务长时间没有响应：标记为失败 [待确认]"
        marks={[
          { quote: "长时间没有响应", code: "FD-01", severity: "must_fix" },
        ]}
      />,
    );
    const mark = screen.getByRole("button", { name: "长时间没有响应" });
    expect(mark.getAttribute("data-finding")).toBe("FD-01");
    expect(mark.getAttribute("data-sev")).toBe("high");
    expect(screen.getByText("待确认").className).toContain("fact--open");
  });

  it("extracts the quoted span from evidence", () => {
    expect(quoteOf("4.1 写道「下载完成后发送通知」")).toBe(
      "下载完成后发送通知",
    );
    expect(quoteOf("没有引用")).toBe("");
  });
});
