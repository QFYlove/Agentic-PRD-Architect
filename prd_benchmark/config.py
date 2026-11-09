"""Typed view of ``config/pilot.yaml`` and the approval gate for real calls."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from prd_benchmark._yaml import load_yaml
from prd_benchmark.cases import PACKAGE_DIR

DEFAULT_CONFIG_PATH = PACKAGE_DIR / "config" / "pilot.yaml"

Approval = Literal["not_approved", "approved"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Approvals(_Strict):
    real_model_calls: Approval
    judge_calls: Approval
    other_keyed_calls: Approval
    #: Batch-wide caps over generator + judge calls; both must be set before
    #: any real call. The first one reached stops further calls.
    token_budget_limit: int | None = Field(default=None, gt=0)
    usd_budget_limit: float | None = Field(default=None, gt=0)


class ModelConfig(_Strict):
    provider_id: Literal["deepseek"]
    base_url: str
    model_id: str = Field(min_length=1)
    model_id_is_floating_alias: bool
    record_response_model: Literal["required"]
    api_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    max_output_tokens: int = Field(ge=1000, le=200_000)
    request_timeout_seconds: float = Field(gt=0, le=600)
    thinking: Literal["disabled"]
    temperature: None = None
    seed: None = None


class ConditionA(_Strict):
    description: str
    generator_call: str
    max_attempts: int = Field(ge=1, le=5)
    attempt_timeout_seconds: int = Field(ge=1)


class Timeouts(_Strict):
    generator: int = Field(ge=1)
    reviewer: int = Field(ge=1)
    optimizer: int = Field(ge=1)
    run: int = Field(ge=10)


class ConditionB(_Strict):
    description: str
    quality_threshold: float = Field(ge=50, le=100)
    max_iterations: int = Field(ge=1, le=5)
    timeouts_seconds: Timeouts
    wait_for_completion_seconds: int = Field(ge=1)
    primary_result: Literal["best_version"]
    also_report: tuple[Literal["last_version", "v1"], ...]


class Conditions(_Strict):
    A: ConditionA
    B: ConditionB


class Execution(_Strict):
    concurrency: Literal[1]
    case_order: Literal["by_id"]
    condition_order: Literal["randomized_per_case"]
    condition_order_seed: int | None = None
    same_pricing_window_per_case: bool


class Pricing(_Strict):
    """Paths (relative to the package) of dated official price snapshots."""

    generator_snapshot: str | None = None
    judge_snapshot: str | None = None
    #: How input tokens are bounded before a call (see guard.py).
    input_token_estimator: Literal["utf8_bytes", "chars"] = "utf8_bytes"


class ClaudeCodeRunner(_Strict):
    cli_path: str = "claude"
    #: The exact ``claude --version`` approved for the run; null = not chosen.
    cli_version: str | None = None
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    max_output_tokens: int = Field(default=32_000, ge=1_000, le=128_000)
    max_api_requests_per_call: int = Field(default=3, ge=1, le=20)
    timeout_seconds: float = Field(default=600, gt=0, le=3600)
    per_call_soft_budget_usd: float | None = Field(default=None, gt=0)
    #: Allow an ANTHROPIC_BASE_URL gateway (needs an explicit API key and a
    #: verified ``gateway_per_token`` price snapshot).
    allow_gateway: bool = False


class JudgeConfig(_Strict):
    status: Literal["deferred", "approved"]
    #: ``claude_code_cli``: automatic, budget-guarded. ``manual_ide``: a person
    #: runs each judge task in a fresh, isolated Claude Code session and
    #: imports the reply (judge_manual.py). Both need ``judge_calls: approved``.
    runner: Literal["claude_code_cli", "manual_ide"] = "claude_code_cli"
    model_id: str | None = None
    #: Recommendation only; ``model_id`` stays null until a person decides.
    candidate_model_id: str | None = None
    second_model_id: str | None = None
    passes_per_document: int = Field(ge=1, le=5)
    shuffle_items_on_second_pass: bool
    claude_code: ClaudeCodeRunner = ClaudeCodeRunner()
    #: ``smoke``: stop on the first invalid output. ``pilot``: stop once more
    #: than 25% of at least 4 judge calls are invalid.
    stop_mode: Literal["smoke", "pilot"] = "smoke"


class Scoring(_Strict):
    rubric_version: str
    pass_threshold: float = Field(ge=0, le=100)
    tie_band_points: float = Field(ge=0)
    human_sample_fraction: float = Field(gt=0, le=1)


class OpenDecision(_Strict):
    id: str
    question: str


class PilotConfig(_Strict):
    benchmark: Literal["prd-quality"]
    config_version: str
    status: Literal["draft", "frozen"]
    approvals: Approvals
    model: ModelConfig
    conditions: Conditions
    output_language: Literal["zh", "en"]
    execution: Execution
    pricing: Pricing
    judge: JudgeConfig
    scoring: Scoring
    open_decisions: tuple[OpenDecision, ...] = ()


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> PilotConfig:
    return PilotConfig.model_validate(load_yaml(path))


def real_run_blockers(
    config: PilotConfig,
    *,
    confirm_spend: bool,
    case_freeze_problems: list[str],
    provider_changelog_date: str | None,
) -> list[str]:
    """Every reason a real (billed) model run must not start.

    An empty list is the only state in which the harness may construct a real
    client. Each gate is independent: approval in the config, an explicit flag
    on the command line, a hard token cap, frozen cases, and the bookkeeping the
    protocol requires before a batch.
    """
    blockers: list[str] = []
    if config.approvals.real_model_calls != "approved":
        blockers.append("approvals.real_model_calls is not 'approved'")
    if not confirm_spend:
        blockers.append("--confirm-spend was not passed")
    blockers.extend(budget_blockers(config, "generator"))
    if config.execution.condition_order_seed is None:
        blockers.append("execution.condition_order_seed is not set")
    if config.status != "frozen":
        blockers.append(f"config status is {config.status}, not frozen")
    if not provider_changelog_date:
        blockers.append("--provider-changelog-date was not given")
    blockers.extend(case_freeze_problems)
    return blockers


def budget_blockers(config: PilotConfig, channel: str) -> list[str]:
    """Both caps and a *verified* price snapshot are required for real calls."""
    from prd_benchmark.pricing import load_snapshot

    blockers: list[str] = []
    if config.approvals.token_budget_limit is None:
        blockers.append("approvals.token_budget_limit is not set")
    if config.approvals.usd_budget_limit is None:
        blockers.append("approvals.usd_budget_limit is not set")
    relative = (
        config.pricing.generator_snapshot
        if channel == "generator"
        else config.pricing.judge_snapshot
    )
    if relative is None:
        blockers.append(f"pricing.{channel}_snapshot is not set")
        return blockers
    snapshot = load_snapshot(PACKAGE_DIR / relative)
    if snapshot.status != "verified":
        blockers.append(f"price snapshot {snapshot.snapshot_id} is not verified")
    return blockers


def judge_run_blockers(
    config: PilotConfig,
    *,
    confirm_spend: bool,
    auth_blockers: list[str] | None = None,
    observed_cli_version: str | None = None,
) -> list[str]:
    """Every reason a real Claude Code judge call must not start."""
    blockers: list[str] = []
    if config.approvals.judge_calls != "approved":
        blockers.append("approvals.judge_calls is not 'approved'")
    if config.judge.status != "approved" or config.judge.model_id is None:
        blockers.append("judge model is not approved and configured")
    if not confirm_spend:
        blockers.append("--confirm-spend was not passed")
    blockers.extend(budget_blockers(config, "judge"))
    runner = config.judge.claude_code
    if runner.cli_version is None:
        blockers.append("judge.claude_code.cli_version is not set")
    elif observed_cli_version != runner.cli_version:
        blockers.append(
            f"installed claude CLI is {observed_cli_version}, approved "
            f"{runner.cli_version}"
        )
    blockers.extend(auth_blockers or ["judge auth was not checked"])
    return blockers
