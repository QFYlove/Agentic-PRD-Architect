import { describe, expect, it } from "vitest";

import { outcomeSummary, summarizeOutcome } from "./outcomeSummary";
import { EMPTY_SEVERITY_COUNTS, type RunOutcome } from "./runReducer";

function outcome(overrides: Partial<RunOutcome> = {}): RunOutcome {
  return {
    thresholdMet: false,
    qualityGatePassed: false,
    qualityThreshold: 85,
    completedIterations: 3,
    maxIterations: 3,
    bestVersion: 2,
    bestScore: 81.7,
    severity: EMPTY_SEVERITY_COUNTS,
    ...overrides,
  };
}

function factValue(result: RunOutcome, label: string): string | undefined {
  return summarizeOutcome(result).facts.find((fact) => fact.label === label)
    ?.value;
}

describe("summarizeOutcome", () => {
  it("reports a run that never reached the target as unmet", () => {
    const summary = summarizeOutcome(outcome());
    expect(summary.tone).toBe("unmet");
    expect(summary.headline).toBe("未达到目标评分");
    expect(summary.note).toBe("迭代预算已用尽");
  });

  /**
   * The case that motivated the gate: the score cleared the target, so the old
   * summary said "已达到目标质量" while three reviewers still listed blocking
   * work. Presenting that as done is the specific dishonesty under test.
   */
  it("separates a met score from a held gate and names the blockers", () => {
    const summary = summarizeOutcome(
      outcome({
        thresholdMet: true,
        qualityGatePassed: false,
        bestVersion: 3,
        bestScore: 91,
        severity: { mustFix: 1, shouldFix: 3, optional: 8 },
      }),
    );
    expect(summary.tone).toBe("blocked");
    expect(summary.headline).toBe("已达到评分目标，但质量门禁未通过");
    expect(summary.note).toBe("剩余 1 项必须修复问题 · 已达到最大迭代次数");
    expect(summary.headline).not.toContain("已达到目标质量");
  });

  it("reports a passed gate as done and marks leftover items as advice", () => {
    const summary = summarizeOutcome(
      outcome({
        thresholdMet: true,
        qualityGatePassed: true,
        completedIterations: 2,
        bestVersion: 2,
        bestScore: 90.7,
        severity: { mustFix: 0, shouldFix: 3, optional: 8 },
      }),
    );
    expect(summary.tone).toBe("passed");
    expect(summary.headline).toBe("已达到目标质量");
    expect(summary.note).toBe("剩余条目为改进建议，不阻塞交付");
  });

  it("adds no note when a passed run has nothing left at all", () => {
    expect(
      summarizeOutcome(outcome({ thresholdMet: true, qualityGatePassed: true }))
        .note,
    ).toBeNull();
  });

  it("reports the three severity tiers as separate facts", () => {
    const result = outcome({
      severity: { mustFix: 1, shouldFix: 3, optional: 8 },
    });
    expect(factValue(result, "必须修复")).toBe("1");
    expect(factValue(result, "重要改进")).toBe("3");
    expect(factValue(result, "可选优化")).toBe("8");
  });

  it("reports the best version rather than the last one", () => {
    expect(
      factValue(outcome({ bestVersion: 2, bestScore: 88 }), "最佳版本"),
    ).toBe("v2 · 88.0");
  });

  it("omits the best version when the run has no scored version", () => {
    const summary = summarizeOutcome(
      outcome({ bestVersion: null, bestScore: null }),
    );
    expect(summary.facts.some((fact) => fact.label === "最佳版本")).toBe(false);
  });

  it("keeps a fractional threshold and drops a whole one's decimal", () => {
    expect(factValue(outcome({ qualityThreshold: 71.5 }), "目标评分")).toBe(
      "71.5",
    );
    expect(factValue(outcome({ qualityThreshold: 85 }), "目标评分")).toBe("85");
  });

  it("reports iterations as spent over budget", () => {
    expect(
      factValue(
        outcome({ completedIterations: 2, maxIterations: 4 }),
        "已完成迭代",
      ),
    ).toBe("2/4 轮");
  });
});

describe("outcomeSummary", () => {
  it("joins the headline and every fact into one line for the live region", () => {
    expect(
      outcomeSummary(
        outcome({
          thresholdMet: true,
          qualityGatePassed: true,
          completedIterations: 2,
          bestVersion: 2,
          bestScore: 90.7,
          severity: { mustFix: 0, shouldFix: 3, optional: 8 },
        }),
      ),
    ).toBe(
      "已达到目标质量 · 目标评分 85 · 最佳版本 v2 · 90.7 · 已完成迭代 2/3 轮 · 必须修复 0 · 重要改进 3 · 可选优化 8",
    );
  });

  it("never claims a finished document while a blocker is open", () => {
    const line = outcomeSummary(
      outcome({
        thresholdMet: true,
        severity: { mustFix: 1, shouldFix: 0, optional: 0 },
      }),
    );
    expect(line).toContain("质量门禁未通过");
    expect(line).toContain("必须修复 1");
  });
});
