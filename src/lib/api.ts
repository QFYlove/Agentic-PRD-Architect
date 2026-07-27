import {
  isRunStatus,
  parseErrorResponse,
  parseRunListResponse,
  parseRunSnapshot,
} from "./contracts";
import { resolvePublicApiBaseUrl } from "./config";
import type {
  ControlResponse,
  CreateRunRequest,
  CreateRunResponse,
  ResumeRunRequest,
  RunListResponse,
  RunSnapshot,
  RunStatus,
} from "./types";

export interface HealthResponse {
  status: string;
  mock_mode: boolean;
  provider: string;
}

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number | null,
    public readonly requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export interface AgentApi {
  createRun(request: CreateRunRequest): Promise<CreateRunResponse>;
  listRuns(limit?: number): Promise<RunListResponse>;
  getRun(runId: string): Promise<RunSnapshot>;
  pauseRun(runId: string): Promise<ControlResponse>;
  resumeRun(runId: string, request: ResumeRunRequest): Promise<ControlResponse>;
  cancelRun(runId: string): Promise<ControlResponse>;
  health(): Promise<HealthResponse>;
  eventsUrl(runId: string, afterSequence: number): string;
}

type FetchLike = typeof fetch;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseCreateRunResponse(value: unknown): CreateRunResponse {
  if (
    !isRecord(value) ||
    typeof value.run_id !== "string" ||
    typeof value.status !== "string" ||
    !isRunStatus(value.status) ||
    typeof value.events_url !== "string" ||
    typeof value.created_at !== "string"
  ) {
    throw new TypeError("Invalid create run response");
  }
  return value as unknown as CreateRunResponse;
}

function parseControlResponse(value: unknown): ControlResponse {
  if (
    !isRecord(value) ||
    typeof value.run_id !== "string" ||
    typeof value.status !== "string" ||
    !isRunStatus(value.status) ||
    typeof value.message !== "string"
  ) {
    throw new TypeError("Invalid control response");
  }
  return value as unknown as ControlResponse;
}

function parseHealthResponse(value: unknown): HealthResponse {
  if (
    !isRecord(value) ||
    typeof value.status !== "string" ||
    typeof value.mock_mode !== "boolean" ||
    typeof value.provider !== "string"
  ) {
    throw new TypeError("Invalid health response");
  }
  return value as unknown as HealthResponse;
}

export class HttpAgentApi implements AgentApi {
  readonly baseUrl: string;

  constructor(
    baseUrl: string = resolvePublicApiBaseUrl(),
    private readonly fetcher: FetchLike = fetch,
  ) {
    this.baseUrl = resolvePublicApiBaseUrl(baseUrl);
  }

  createRun(request: CreateRunRequest): Promise<CreateRunResponse> {
    return this.request(
      "/api/runs",
      {
        method: "POST",
        body: JSON.stringify(request),
      },
      parseCreateRunResponse,
    );
  }

  listRuns(limit = 50): Promise<RunListResponse> {
    return this.request(
      `/api/runs?limit=${encodeURIComponent(String(limit))}`,
      undefined,
      parseRunListResponse,
    );
  }

  getRun(runId: string): Promise<RunSnapshot> {
    return this.request(
      `/api/runs/${encodeURIComponent(runId)}`,
      undefined,
      parseRunSnapshot,
    );
  }

  pauseRun(runId: string): Promise<ControlResponse> {
    return this.request(
      `/api/runs/${encodeURIComponent(runId)}/pause`,
      { method: "POST" },
      parseControlResponse,
    );
  }

  resumeRun(
    runId: string,
    request: ResumeRunRequest,
  ): Promise<ControlResponse> {
    return this.request(
      `/api/runs/${encodeURIComponent(runId)}/resume`,
      { method: "POST", body: JSON.stringify(request) },
      parseControlResponse,
    );
  }

  cancelRun(runId: string): Promise<ControlResponse> {
    return this.request(
      `/api/runs/${encodeURIComponent(runId)}/cancel`,
      { method: "POST" },
      parseControlResponse,
    );
  }

  health(): Promise<HealthResponse> {
    return this.request("/api/health", undefined, parseHealthResponse);
  }

  eventsUrl(runId: string, afterSequence: number): string {
    const url = new URL(
      `/api/runs/${encodeURIComponent(runId)}/events`,
      `${this.baseUrl}/`,
    );
    url.searchParams.set("after_sequence", String(afterSequence));
    return url.toString();
  }

  private async request<T>(
    path: string,
    init: RequestInit | undefined,
    parser: (value: unknown) => T,
  ): Promise<T> {
    let response: Response;
    try {
      response = await this.fetcher.call(globalThis, `${this.baseUrl}${path}`, {
        ...init,
        headers: {
          Accept: "application/json",
          ...(init?.body ? { "Content-Type": "application/json" } : {}),
          ...init?.headers,
        },
      });
    } catch {
      throw new ApiClientError(
        "无法连接 Agentic PRD API，请确认后端服务是否正常运行。",
        "NETWORK_ERROR",
        null,
      );
    }

    let data: unknown;
    try {
      data = await response.json();
    } catch {
      throw new ApiClientError(
        "API 返回了无法读取的响应。",
        "INVALID_RESPONSE",
        response.status,
      );
    }

    if (!response.ok) {
      try {
        const error = parseErrorResponse(data).error;
        throw new ApiClientError(
          error.message,
          error.code,
          response.status,
          error.request_id,
        );
      } catch (error) {
        if (error instanceof ApiClientError) {
          throw error;
        }
        throw new ApiClientError(
          `API 请求失败，状态码：${response.status}。`,
          "HTTP_ERROR",
          response.status,
        );
      }
    }

    try {
      return parser(data);
    } catch {
      throw new ApiClientError(
        "API 响应与预期数据格式不一致。",
        "INVALID_RESPONSE",
        response.status,
      );
    }
  }
}

export function statusFromControl(response: ControlResponse): RunStatus {
  return response.status;
}
