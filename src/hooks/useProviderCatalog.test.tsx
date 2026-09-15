import { renderHook, waitFor, act } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useProviderCatalog } from "./useProviderCatalog";
import { HttpAgentApi } from "../lib/api";

const catalog = { providers: [{ provider_id: "p1", provider_display_name: "Provider One", models: [{ model_id: "m1", model_display_name: "Model One" }] }] };
describe("useProviderCatalog", () => {
  it("keeps the default client identity stable across rerenders", async () => {
    const getProviders = vi.spyOn(HttpAgentApi.prototype, "getProviders").mockResolvedValue(catalog);
    const { result, rerender } = renderHook(() => useProviderCatalog());
    await waitFor(() => expect(result.current.state).toBe("loaded"));
    rerender(); rerender();
    expect(getProviders).toHaveBeenCalledTimes(1);
    getProviders.mockRestore();
  });
  it("exposes loading and loaded states", async () => { let resolve!: (v: typeof catalog) => void; const api={getProviders:vi.fn(()=>new Promise<typeof catalog>(r=>{resolve=r}))}; const {result}=renderHook(()=>useProviderCatalog(api)); expect(result.current.state).toBe("loading"); act(()=>resolve(catalog)); await waitFor(()=>expect(result.current.state).toBe("loaded")); });
  it("exposes empty and error states and retries", async () => { const api={getProviders:vi.fn().mockRejectedValueOnce(new Error()).mockResolvedValueOnce({providers:[]}).mockResolvedValueOnce(catalog)}; const {result}=renderHook(()=>useProviderCatalog(api)); await waitFor(()=>expect(result.current.state).toBe("error")); act(()=>void result.current.retry()); await waitFor(()=>expect(result.current.state).toBe("empty")); act(()=>void result.current.retry()); await waitFor(()=>expect(result.current.state).toBe("loaded")); expect(api.getProviders).toHaveBeenCalledTimes(3); });
});
