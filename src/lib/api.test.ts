import { describe, expect, it, vi } from "vitest";

import { HttpAgentApi } from "./api";
import { DEFAULT_PUBLIC_API_BASE_URL, resolvePublicApiBaseUrl } from "./config";
import { makeSnapshot, RUN_ID } from "../test/fixtures";

function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("public API configuration", () => {
  it("uses the local API when the public value is missing", () => {
    expect(resolvePublicApiBaseUrl(undefined)).toBe(
      DEFAULT_PUBLIC_API_BASE_URL,
    );
  });

  it("normalizes a custom public address", () => {
    expect(resolvePublicApiBaseUrl("https://api.example.com/")).toBe(
      "https://api.example.com",
    );
  });

  it("rejects non-HTTP and malformed addresses", () => {
    expect(() => resolvePublicApiBaseUrl("file:///secret")).toThrow(/HTTP/);
    expect(() => resolvePublicApiBaseUrl("not a url")).toThrow(/absolute/);
  });
});

describe("HttpAgentApi", () => {
  it("parses successful requests and centralizes URL construction", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse({
        run_id: RUN_ID,
        status: "QUEUED",
        events_url: `/api/runs/${RUN_ID}/events`,
        created_at: "2026-07-26T10:00:00Z",
      }),
    );
    const api = new HttpAgentApi("http://api.test", fetcher);
    const created = await api.createRun({
      user_idea: "A sufficiently detailed product idea.",
      quality_threshold: 85,
      max_iterations: 3,
    });

    expect(created.run_id).toBe(RUN_ID);
    expect(fetcher).toHaveBeenCalledWith(
      "http://api.test/api/runs",
      expect.objectContaining({ method: "POST" }),
    );
    expect(api.eventsUrl(RUN_ID, 42)).toBe(
      `http://api.test/api/runs/${RUN_ID}/events?after_sequence=42`,
    );
  });

  it.each([
    [422, "VALIDATION_ERROR"],
    [409, "RUN_NOT_PAUSED"],
  ])("returns structured errors for HTTP %i", async (status, code) => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      jsonResponse(
        {
          error: {
            code,
            message: "Action rejected.",
            request_id: "request-1",
          },
        },
        status,
      ),
    );
    const api = new HttpAgentApi("http://api.test", fetcher);

    await expect(api.getRun(RUN_ID)).rejects.toMatchObject({
      name: "ApiClientError",
      code,
      status,
      requestId: "request-1",
    });
  });

  it("maps network failures to a stable client error", async () => {
    const api = new HttpAgentApi(
      "http://api.test",
      vi.fn<typeof fetch>().mockRejectedValue(new Error("socket details")),
    );
    await expect(api.health()).rejects.toEqual(
      expect.objectContaining({
        code: "NETWORK_ERROR",
        status: null,
      }),
    );
  });

  it("rejects invalid JSON and invalid contracts", async () => {
    const invalidJson = new HttpAgentApi(
      "http://api.test",
      vi
        .fn<typeof fetch>()
        .mockResolvedValue(new Response("{", { status: 200 })),
    );
    await expect(invalidJson.health()).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });

    const invalidContract = new HttpAgentApi(
      "http://api.test",
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({ status: "ok" })),
    );
    await expect(invalidContract.health()).rejects.toMatchObject({
      code: "INVALID_RESPONSE",
    });
  });

  it("parses snapshots", async () => {
    const api = new HttpAgentApi(
      "http://api.test",
      vi.fn<typeof fetch>().mockResolvedValue(jsonResponse(makeSnapshot())),
    );
    await expect(api.getRun(RUN_ID)).resolves.toMatchObject({ run_id: RUN_ID });
  });

  it("constructs all control and health endpoints", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        jsonResponse({
          run_id: RUN_ID,
          status: "PAUSE_REQUESTED",
          message: "Pause requested.",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          run_id: RUN_ID,
          status: "OPTIMIZING",
          message: "Resumed.",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          run_id: RUN_ID,
          status: "CANCEL_REQUESTED",
          message: "Cancel requested.",
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({ status: "ok", mock_mode: true, provider: "mock" }),
      );
    const api = new HttpAgentApi("http://api.test", fetcher);

    await api.pauseRun(RUN_ID);
    await api.resumeRun(RUN_ID, { user_override: "Add refunds." });
    await api.cancelRun(RUN_ID);
    await expect(api.health()).resolves.toEqual({
      status: "ok",
      mock_mode: true,
      provider: "mock",
    });

    expect(fetcher.mock.calls.map(([url]) => url)).toEqual([
      `http://api.test/api/runs/${RUN_ID}/pause`,
      `http://api.test/api/runs/${RUN_ID}/resume`,
      `http://api.test/api/runs/${RUN_ID}/cancel`,
      "http://api.test/api/health",
    ]);
  });
});
