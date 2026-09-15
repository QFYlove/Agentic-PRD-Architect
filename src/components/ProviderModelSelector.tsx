import type { Provider } from "../lib/types";
export function ProviderModelSelector({ providers, providerId, modelId, onProviderChange, onModelChange, disabled=false }: { providers: Provider[]; providerId: string; modelId: string; onProviderChange: (id:string)=>void; onModelChange:(id:string)=>void; disabled?: boolean }) {
  const provider = providers.find((item) => item.provider_id === providerId);
  return <div className="mt-5 grid gap-5 md:grid-cols-2">
    <label className="block text-sm font-medium text-ink">Provider<select className="field mt-2" value={providerId} onChange={(e)=>onProviderChange(e.target.value)} disabled={disabled}><option value="">请选择 Provider</option>{providers.map((item)=><option key={item.provider_id} value={item.provider_id}>{item.provider_display_name}</option>)}</select></label>
    <label className="block text-sm font-medium text-ink">Model<select className="field mt-2" value={modelId} onChange={(e)=>onModelChange(e.target.value)} disabled={disabled || !provider}><option value="">请选择 Model</option>{provider?.models.map((item)=><option key={item.model_id} value={item.model_id}>{item.model_display_name}</option>)}</select></label>
  </div>;
}
