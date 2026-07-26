const ERROR_MESSAGES: Record<string, string> = {
  NETWORK_ERROR: "无法连接后端服务，请检查服务是否已启动。",
  INVALID_RESPONSE: "服务返回了无法识别的数据，请稍后重试。",
  HTTP_ERROR: "请求失败，请稍后重试。",
  REQUEST_VALIDATION_FAILED: "提交的数据不符合要求，请检查后重试。",
  RUN_NOT_FOUND: "找不到该任务，它可能已经过期或被清理。",
  RUN_CAPACITY_REACHED: "当前运行中的任务已达上限，请稍后再试。",
  STORE_CAPACITY_REACHED: "任务存储空间已满，请稍后再试。",
  EVENTS_EXPIRED: "部分历史事件已经过期，请重新打开任务。",
  PROVIDER_TEMPORARY_ERROR: "模型服务暂时不可用，请稍后重试。",
  PROVIDER_AUTHENTICATION_FAILED: "模型服务认证失败，请检查 API Key。",
  PROVIDER_MODEL_INVALID: "当前模型名称无效，请检查 Provider 配置。",
  PROVIDER_UNAVAILABLE: "模型服务不可用，请检查 Provider 配置。",
  RUN_TIMEOUT: "任务运行超时，请缩小需求范围后重试。",
  STRUCTURED_OUTPUT_INVALID: "模型返回的数据格式无效，请重新运行。",
  WORKFLOW_FAILED: "工作流未能完成，请重新运行。",
  APP_SHUTTING_DOWN: "服务正在关闭，请稍后重试。",
  RUN_TERMINAL: "该任务已经结束，无法继续执行此操作。",
  RUN_NOT_PAUSABLE: "当前阶段暂时无法暂停。",
  RUN_NOT_PAUSED: "该任务当前并未处于暂停状态。",
  INTERNAL_ERROR: "服务发生内部错误，请稍后重试。",
};

export function localizedErrorMessage(
  code: unknown,
  fallback = "操作失败，请稍后重试。",
): string {
  return typeof code === "string"
    ? (ERROR_MESSAGES[code] ?? fallback)
    : fallback;
}
