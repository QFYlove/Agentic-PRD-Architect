import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const PODCAST_IDEA =
  "打造一个移动端优先的播客单集订阅产品，让听众可以直接支持喜欢的节目。";
export const E2E_API_BASE_URL = "http://127.0.0.1:8011";

export function apiUrl(path: string): string {
  return `${E2E_API_BASE_URL}${path}`;
}

export interface RunSnapshot {
  run_id: string;
  status: string;
  latest_event_sequence: number;
  current_prd: string;
  current_prd_attempt: number;
  versions: Array<{
    version: number;
    content: string;
    evaluation: {
      overall_score: number;
      tech: { score: number };
      ux: { score: number };
      biz: { score: number };
    } | null;
    revision_plan: {
      user_override: string | null;
      items: unknown[];
    } | null;
  }>;
  node_statuses: Record<string, string>;
  error: { code: string; message: string } | null;
}

export interface RunEvent {
  sequence: number;
  event: string;
  payload: Record<string, unknown>;
}

export async function setScenario(
  request: APIRequestContext,
  scenario: string,
): Promise<void> {
  const response = await request.put(apiUrl("/api/test/scenario"), {
    data: { scenario },
  });
  expect(response.ok()).toBeTruthy();
  expect((await response.json()).scenario).toBe(scenario);
}

export async function startRun(
  page: Page,
  options: {
    idea?: string;
    threshold?: number;
    maxIterations?: number;
  } = {},
): Promise<string> {
  await page.goto("/");
  await page.getByLabel("产品想法").fill(options.idea ?? PODCAST_IDEA);
  await page.getByLabel("目标用户").fill("播客听众和独立内容创作者");
  await page.getByLabel("约束条件").fill("移动端优先、无障碍并保护隐私的 MVP");
  if (options.threshold !== undefined || options.maxIterations !== undefined) {
    await page.getByText("质量设置").click();
  }
  if (options.threshold !== undefined) {
    await page.getByLabel(/质量门槛/).fill(String(options.threshold));
  }
  if (options.maxIterations !== undefined) {
    await page
      .getByLabel("最大迭代次数")
      .selectOption(String(options.maxIterations));
  }
  await page.getByRole("button", { name: "开始生成 PRD" }).click();
  await expect
    .poll(() => new URL(page.url()).searchParams.get("run_id"))
    .not.toBeNull();
  return new URL(page.url()).searchParams.get("run_id")!;
}

export async function waitForStatus(page: Page, label: string): Promise<void> {
  await expect(page.getByTestId("run-status")).toHaveText(label);
}

export async function getSnapshot(
  request: APIRequestContext,
  runId: string,
): Promise<RunSnapshot> {
  const response = await request.get(apiUrl(`/api/runs/${runId}`));
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as RunSnapshot;
}

export async function waitForTerminalSnapshot(
  request: APIRequestContext,
  runId: string,
): Promise<RunSnapshot> {
  let snapshot = await getSnapshot(request, runId);
  await expect
    .poll(
      async () => {
        snapshot = await getSnapshot(request, runId);
        return snapshot.status;
      },
      { timeout: 15_000 },
    )
    .toMatch(/^(COMPLETED|MAX_ITERATIONS_REACHED|CANCELLED|FAILED)$/);
  return snapshot;
}

export async function getEvents(
  request: APIRequestContext,
  runId: string,
): Promise<RunEvent[]> {
  const response = await request.get(
    apiUrl(`/api/runs/${runId}/events?after_sequence=0`),
  );
  expect(response.ok()).toBeTruthy();
  const body = await response.text();
  return body
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data: "))
    .map((line) => JSON.parse(line.slice(6)) as RunEvent);
}
