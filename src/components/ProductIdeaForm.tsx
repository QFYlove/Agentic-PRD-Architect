import { ArrowRight, Sparkles } from "lucide-react";
import { useState } from "react";
import type { FormEvent } from "react";

import type { CreateRunRequest } from "../lib/types";

interface ProductIdeaFormProps {
  isSubmitting: boolean;
  onSubmit(request: CreateRunRequest): Promise<void>;
}

interface FormErrors {
  idea?: string;
  audience?: string;
  constraints?: string;
}

export function ProductIdeaForm({
  isSubmitting,
  onSubmit,
}: ProductIdeaFormProps) {
  const [idea, setIdea] = useState("");
  const [audience, setAudience] = useState("");
  const [constraints, setConstraints] = useState("");
  const [qualityThreshold, setQualityThreshold] = useState(85);
  const [maxIterations, setMaxIterations] = useState(3);
  const [errors, setErrors] = useState<FormErrors>({});
  const [submittingLocally, setSubmittingLocally] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting || submittingLocally) {
      return;
    }
    const normalizedIdea = idea.trim();
    const nextErrors: FormErrors = {};
    if (normalizedIdea.length < 10) {
      nextErrors.idea = "请至少用 10 个字符描述产品想法。";
    } else if (idea.length > 5000) {
      nextErrors.idea = "产品想法不能超过 5,000 个字符。";
    }
    if (audience.length > 1000) {
      nextErrors.audience = "目标用户不能超过 1,000 个字符。";
    }
    if (constraints.length > 2000) {
      nextErrors.constraints = "约束条件不能超过 2,000 个字符。";
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      return;
    }

    setSubmittingLocally(true);
    try {
      await onSubmit({
        user_idea: normalizedIdea,
        target_audience: audience.trim() || null,
        user_constraints: constraints.trim() || null,
        quality_threshold: qualityThreshold,
        max_iterations: maxIterations,
      });
    } finally {
      setSubmittingLocally(false);
    }
  }

  const busy = isSubmitting || submittingLocally;

  return (
    <form
      className="rounded-[2rem] border border-white/10 bg-slate-950/75 p-6 shadow-2xl shadow-cyan-950/20 backdrop-blur-xl sm:p-8"
      onSubmit={handleSubmit}
      noValidate
    >
      <div className="flex items-start gap-3">
        <span className="rounded-2xl bg-cyan-400/10 p-2.5 text-cyan-300">
          <Sparkles aria-hidden="true" size={20} />
        </span>
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.24em] text-cyan-300">
            新建架构任务
          </p>
          <h2 className="mt-1 text-2xl font-semibold text-white">
            把想法变成经过评审的 PRD
          </h2>
        </div>
      </div>

      <label className="mt-7 block text-sm font-medium text-slate-200">
        产品想法
        <textarea
          className="field mt-2 min-h-36 resize-y"
          value={idea}
          onChange={(event) => setIdea(event.target.value)}
          maxLength={5001}
          aria-describedby="idea-help idea-count"
          aria-invalid={Boolean(errors.idea)}
          placeholder="例如：面向播客听众的移动端单集订阅产品，让用户可以直接支持喜欢的节目……"
          autoFocus
        />
      </label>
      <div className="mt-2 flex justify-between gap-4 text-xs">
        <span
          id="idea-help"
          className={errors.idea ? "text-rose-300" : "text-slate-500"}
        >
          {errors.idea ?? "请尽量说明用户问题、使用场景和期望结果。"}
        </span>
        <span id="idea-count" className="shrink-0 text-slate-500">
          {idea.length}/5000
        </span>
      </div>

      <div className="mt-5 grid gap-5 md:grid-cols-2">
        <label className="block text-sm font-medium text-slate-200">
          目标用户
          <input
            className="field mt-2"
            value={audience}
            onChange={(event) => setAudience(event.target.value)}
            maxLength={1001}
            aria-invalid={Boolean(errors.audience)}
            placeholder="例如：播客听众和独立创作者"
          />
          <span className="mt-2 block text-xs text-slate-500">
            {errors.audience ?? `${audience.length}/1000 · 选填`}
          </span>
        </label>
        <label className="block text-sm font-medium text-slate-200">
          约束条件
          <input
            className="field mt-2"
            value={constraints}
            onChange={(event) => setConstraints(event.target.value)}
            maxLength={2001}
            aria-invalid={Boolean(errors.constraints)}
            placeholder="例如：移动端优先、隐私要求、预算限制……"
          />
          <span className="mt-2 block text-xs text-slate-500">
            {errors.constraints ?? `${constraints.length}/2000 · 选填`}
          </span>
        </label>
      </div>

      <details className="mt-6 rounded-2xl border border-white/8 bg-white/[0.025] p-4">
        <summary className="cursor-pointer text-sm font-medium text-slate-300">
          质量设置
        </summary>
        <div className="mt-4 grid gap-5 sm:grid-cols-2">
          <label className="text-sm text-slate-300">
            质量门槛：{qualityThreshold}
            <input
              className="mt-3 w-full accent-cyan-400"
              type="range"
              min="50"
              max="100"
              value={qualityThreshold}
              onChange={(event) =>
                setQualityThreshold(Number(event.target.value))
              }
            />
          </label>
          <label className="text-sm text-slate-300">
            最大迭代次数
            <select
              className="field mt-2"
              value={maxIterations}
              onChange={(event) => setMaxIterations(Number(event.target.value))}
            >
              {[1, 2, 3, 4, 5].map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>
      </details>

      <button
        className="button-primary mt-6 w-full sm:w-auto"
        type="submit"
        disabled={busy}
      >
        {busy ? "正在创建任务…" : "开始生成 PRD"}
        {!busy && <ArrowRight aria-hidden="true" size={18} />}
      </button>
    </form>
  );
}
