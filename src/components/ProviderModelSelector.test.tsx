import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ProviderModelSelector } from "./ProviderModelSelector";

const providers=[{provider_id:"p1",provider_display_name:"Alpha",models:[{model_id:"a",model_display_name:"Alpha Model"}]},{provider_id:"p2",provider_display_name:"Beta",models:[{model_id:"b",model_display_name:"Beta Model"}]}];
describe("ProviderModelSelector",()=>{
 it("uses display names, does not default, filters models, and clears incompatible model",async()=>{const onP=vi.fn(),onM=vi.fn(); const {rerender}=render(<ProviderModelSelector providers={providers} providerId="" modelId="" onProviderChange={onP} onModelChange={onM}/>); const provider=screen.getByLabelText("Provider") as HTMLSelectElement; const model=screen.getByLabelText("Model") as HTMLSelectElement; expect(provider.value).toBe(""); expect(model.disabled).toBe(true); expect(screen.getByText("Alpha")).toBeTruthy(); await userEvent.selectOptions(provider,"p1"); expect(onP).toHaveBeenCalledWith("p1"); rerender(<ProviderModelSelector providers={providers} providerId="p1" modelId="a" onProviderChange={onP} onModelChange={onM}/>); expect(model.querySelectorAll("option")).toHaveLength(2); expect(model.value).toBe("a"); rerender(<ProviderModelSelector providers={providers} providerId="p2" modelId="" onProviderChange={onP} onModelChange={onM}/>); expect((screen.getByLabelText("Model") as HTMLSelectElement).value).toBe("");});
});
