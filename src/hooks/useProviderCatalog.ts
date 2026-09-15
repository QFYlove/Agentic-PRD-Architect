import { useCallback, useEffect, useState } from "react";
import { HttpAgentApi, type AgentApi } from "../lib/api";
import type { Provider } from "../lib/types";

export type ProviderCatalogState = "loading" | "loaded" | "empty" | "error";
const defaultApi: AgentApi = new HttpAgentApi();
export function useProviderCatalog(api: Pick<AgentApi, "getProviders"> = defaultApi) {
  const [state, setState] = useState<ProviderCatalogState>("loading");
  const [providers, setProviders] = useState<Provider[]>([]);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setState("loading"); setError(null);
    try { const result = await api.getProviders(); setProviders(result.providers); setState(result.providers.length ? "loaded" : "empty"); }
    catch { setProviders([]); setState("error"); setError("无法加载可用的 Provider 和 Model。"); }
  }, [api]);
  useEffect(() => { void load(); }, [load]);
  return { state, providers, error, retry: load };
}
