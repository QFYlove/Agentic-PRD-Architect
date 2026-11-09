const ERROR_MESSAGES: Record<string, string> = {
  NETWORK_ERROR: "无法连接后端服务，请检查服务是否已启动。",
  INVALID_RESPONSE: "服务返回了无法识别的数据，请稍后重试。",
  HTTP_ERROR: "请求失败，请稍后重试。",
  REQUEST_VALIDATION_FAILED: "提交的数据不符合要求，请检查后重试。",
  INVALID_PROVIDER_SELECTION:
    "所选 Provider 或 Model 已不可用，请重新选择后重试。",
  RUN_NOT_FOUND: "找不到该任务，它可能已经过期或被清理。",
  RUN_CAPACITY_REACHED: "当前运行中的任务已达上限，请稍后再试。",
  STORE_CAPACITY_REACHED: "任务存储空间已满，请稍后再试。",
  EVENTS_EXPIRED: "部分历史事件已经过期，请重新打开任务。",
  PROVIDER_TEMPORARY_ERROR: "模型服务暂时不可用，请稍后重试。",
  PROVIDER_AUTHENTICATION_FAILED: "模型服务认证失败，请检查 API Key。",
  PROVIDER_MODEL_INVALID: "当前模型名称无效，请检查 Provider 配置。",
  PROVIDER_INSUFFICIENT_BALANCE: "模型服务账户余额或配额不足，请充值后重试。",
  PROVIDER_FORBIDDEN: "模型服务拒绝访问当前模型，请检查账号权限。",
  PROVIDER_REQUEST_REJECTED: "模型服务拒绝了本次请求内容，请调整输入后重试。",
  // Three distinct causes, three distinct sentences. They used to share one
  // code, which meant an output-length problem and a mid-stream service failure
  // read identically and neither told the user what to change.
  // Not retried with the same request any more: the identical request needs the
  // identical length. The next step is a compact regeneration, which the
  // failure panel offers as a button.
  PROVIDER_OUTPUT_TRUNCATED:
    "PRD 超出了模型单次输出上限，未能完整生成。系统没有重复发送相同请求，可以使用精简模式重新生成。",
  PROVIDER_OUTPUT_UNFINISHED:
    "模型提前结束了 PRD 输出，系统重试后仍未得到完整文档，请重新运行。",
  PROVIDER_OUTPUT_INTERRUPTED: "模型服务在生成过程中暂时中断，请稍后重新生成。",
  // Kept for runs recorded before the split above.
  PROVIDER_OUTPUT_INCOMPLETE:
    "模型生成的文档不完整（可能被输出长度限制截断），请重新运行。",
  PROVIDER_CONTENT_FILTERED:
    "模型服务的内容安全策略拦截了本次生成，请调整需求描述后重试。",
  PROVIDER_ERROR: "模型服务调用失败，请稍后重试。",
  PROVIDER_UNAVAILABLE: "模型服务不可用，请检查 Provider 配置。",
  RUN_TIMEOUT: "任务用完了总运行时长，已完成的版本均已保留。",
  NODE_TIMEOUT: "模型调用超时，系统已自动重试一次仍未成功，请稍后重试。",
  RUN_INTERRUPTED:
    "后端服务在任务完成前重启，任务被中断，已完成的版本均已保留。",
  PROVIDER_SELECTION_UNAVAILABLE:
    "该任务使用的模型已不可用，无法继续；可以新建任务或选择其他模型。",
  RUN_NOT_TERMINAL: "任务仍在运行，结束后才能基于它重新生成。",
  NO_COMPLETED_VERSION: "该任务没有已完成的版本，无法从最佳版本继续。",
  INVALID_E2E_SCENARIO: "测试场景无效。",
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
