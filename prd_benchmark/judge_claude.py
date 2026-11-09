"""Claude Code CLI as an isolated, budget-guarded Judge runner.

Each evaluation spawns one fresh ``claude -p`` process (no shell) in an empty
temporary directory with an empty ``HOME``, so no project file, CLAUDE.md,
memory, plugin, MCP config, or prior session is in reach. Flags used were
checked against the installed CLI's ``--help`` (see ``KNOWN_FLAGS``); the
adapter refuses to build a command for a CLI version it has not been told
about.

What this module cannot guarantee, and therefore reports instead of claims:

- that one CLI run makes exactly one API request (reservations multiply by
  ``max_api_requests_per_call`` and a reported cost above the reservation
  stops the batch);
- that ``--max-budget-usd`` is a hard cap (the CLI documents that spend can
  pass it; it is passed only as a secondary, soft limit);
- the billed amount (``total_cost_usd`` is the CLI's own client-side
  estimate; the guard prices reported tokens with a dated snapshot);
- the exact served model snapshot (only the identifiers the CLI reports).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from prd_benchmark.guard import CallGuard, StopBatchError
from prd_benchmark.judge import (
    JudgeOutput,
    JudgeParseError,
    JudgeRequest,
    parse_judge_response,
)
from prd_benchmark.judge_prompt import PROMPT_VERSION, build_prompt, output_schema
from prd_benchmark.pricing import UsageBreakdown

SCHEMA_VERSION = "judge-output-v0.4"
FIRST_PARTY_HOSTS = frozenset({"api.anthropic.com"})
#: Flags this adapter relies on, verified in ``claude --help`` of the CLI
#: version(s) listed in ``VERIFIED_CLI_VERSIONS``. ``--max-turns`` is in the
#: public docs but absent from the installed 2.1.258.6 help, so it is not used.
KNOWN_FLAGS = (
    "-p",
    "--bare",
    "--restricted",
    "--tools",
    "--strict-mcp-config",
    "--disallowedTools",
    "--disable-slash-commands",
    "--no-session-persistence",
    "--system-prompt",
    "--output-format",
    "--json-schema",
    "--model",
    "--max-budget-usd",
    "--effort",
)
VERIFIED_CLI_VERSIONS = frozenset({"2.1.258.6"})
_SECRET_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(authorization|x-api-key)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{8,}"),
)

AuthMode = Literal[
    "anthropic_api_key",
    "anthropic_api_key_via_gateway",
    "gateway_without_api_key",
    "bedrock",
    "vertex",
    "foundry",
    "none_for_bare_mode",
]


class ClaudeCodeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cli_path: str = "claude"
    #: The exact ``claude --version`` the run is approved for.
    cli_version: str | None = None
    model_id: str = Field(min_length=1)
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    #: Sent as CLAUDE_CODE_MAX_OUTPUT_TOKENS; caps "most requests" per docs.
    max_output_tokens: int = Field(default=32_000, ge=1_000, le=128_000)
    #: Reservation multiplier: worst-case API requests in one CLI run.
    max_api_requests_per_call: int = Field(default=3, ge=1, le=20)
    timeout_seconds: float = Field(default=600, gt=0, le=3600)
    #: Passed as --max-budget-usd. Soft: the CLI documents it can be passed.
    per_call_soft_budget_usd: float | None = Field(default=None, gt=0)


@dataclass(frozen=True)
class AuthInfo:
    mode: AuthMode
    base_url_kind: Literal["default", "first_party", "custom_gateway"]
    api_key_present: bool
    billing_attribution: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_auth(env: Mapping[str, str]) -> AuthInfo:
    """Classify credentials by *presence* only; no value is read or kept.

    ``--bare`` never reads OAuth or the keychain, so a subscription login
    cannot back a bare run at all.
    """
    key = bool(env.get("ANTHROPIC_API_KEY"))
    base = env.get("ANTHROPIC_BASE_URL") or ""
    if not base:
        kind: Literal["default", "first_party", "custom_gateway"] = "default"
    elif (urlparse(base).hostname or "") in FIRST_PARTY_HOSTS:
        kind = "first_party"
    else:
        kind = "custom_gateway"
    if env.get("CLAUDE_CODE_USE_BEDROCK"):
        return AuthInfo("bedrock", kind, key, "aws_bedrock_partner_pricing")
    if env.get("CLAUDE_CODE_USE_VERTEX"):
        return AuthInfo("vertex", kind, key, "gcp_vertex_partner_pricing")
    if env.get("CLAUDE_CODE_USE_FOUNDRY"):
        return AuthInfo("foundry", kind, key, "azure_foundry_api_rates")
    if kind == "custom_gateway":
        mode: AuthMode = (
            "anthropic_api_key_via_gateway" if key else "gateway_without_api_key"
        )
        return AuthInfo(mode, kind, key, "unknown_gateway_billing")
    if key:
        return AuthInfo("anthropic_api_key", kind, key, "anthropic_api_per_token")
    return AuthInfo("none_for_bare_mode", kind, key, "none")


def judge_auth_blockers(
    auth: AuthInfo,
    *,
    allow_gateway: bool = False,
    gateway_billing_declared: bool = False,
) -> list[str]:
    """Why the automatic CLI judge cannot run under this authentication.

    ``--bare`` authenticates only with an explicit ``ANTHROPIC_API_KEY``; it
    never reads OAuth, the keychain, or the IDE's settings, and this harness
    does not read or forward them either. A gateway is acceptable only with an
    explicitly provided key, an explicit opt-in, and a verified price snapshot
    whose billing is declared as the gateway's (``gateway_per_token``).
    Otherwise use the manual IDE judge workflow (``judge_manual.py``).
    """
    if auth.mode == "anthropic_api_key":
        return []
    if auth.mode == "anthropic_api_key_via_gateway":
        problems = []
        if not allow_gateway:
            problems.append("judge.claude_code.allow_gateway is false")
        if not gateway_billing_declared:
            problems.append(
                "no verified judge price snapshot with billing gateway_per_token"
            )
        return [f"judge auth is a gateway with an API key: {p}" for p in problems]
    if auth.mode == "gateway_without_api_key":
        return [
            "judge auth is a gateway without ANTHROPIC_API_KEY; --bare cannot "
            "authenticate, and the IDE's gateway credentials are not read or "
            "reused. Use the manual IDE judge workflow instead"
        ]
    return [
        f"judge auth is {auth.mode} ({auth.billing_attribution}); this harness "
        "has no applicable prices. Use the manual IDE judge workflow instead"
    ]


def redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, "[REDACTED]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def build_command(config: ClaudeCodeConfig, system: str, schema: str) -> list[str]:
    """argv for one isolated judge run. The user prompt goes on stdin."""
    argv = [
        config.cli_path,
        "-p",
        "--bare",
        "--restricted",
        "--tools",
        "",
        "--strict-mcp-config",
        "--disallowedTools",
        "mcp__*",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--system-prompt",
        system,
        "--output-format",
        "json",
        "--json-schema",
        schema,
        "--model",
        config.model_id,
    ]
    if config.effort is not None:
        argv += ["--effort", config.effort]
    if config.per_call_soft_budget_usd is not None:
        argv += ["--max-budget-usd", f"{config.per_call_soft_budget_usd:.4f}"]
    return argv


_ENV_PASSTHROUGH = ("PATH", "LANG", "LC_ALL", "TMPDIR")


def build_env(
    base: Mapping[str, str], config: ClaudeCodeConfig, home: str
) -> dict[str, str]:
    """A minimal environment: no inherited model, settings, or feature vars."""
    env = {k: base[k] for k in _ENV_PASSTHROUGH if base.get(k)}
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"):
        if base.get(name):
            env[name] = base[name]
    env.update(
        {
            "HOME": home,
            "CLAUDE_CODE_SIMPLE": "1",
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(config.max_output_tokens),
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
            "DISABLE_TELEMETRY": "1",
            "CLAUDE_CODE_MAX_RETRIES": "0",
        }
    )
    return env


@dataclass
class ProcessResult:
    exit_code: int | None
    stdout: str
    stderr: str
    seconds: float
    timed_out: bool = False
    interrupted: bool = False


Runner = Callable[
    [list[str], str, dict[str, str], str, float], Awaitable[ProcessResult]
]


async def run_subprocess(
    argv: list[str], stdin: str, env: dict[str, str], cwd: str, limit_s: float
) -> ProcessResult:
    """Run without a shell; kill on timeout. Never used by the tests."""
    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        *argv,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=cwd,
    )
    try:
        out, err = await asyncio.wait_for(
            process.communicate(stdin.encode("utf-8")), limit_s
        )
    except TimeoutError:
        process.kill()
        await process.wait()
        return ProcessResult(None, "", "", time.monotonic() - started, timed_out=True)
    except asyncio.CancelledError:
        process.kill()
        await process.wait()
        raise
    code = process.returncode
    return ProcessResult(
        code,
        out.decode("utf-8", "replace"),
        err.decode("utf-8", "replace"),
        time.monotonic() - started,
        interrupted=code is not None and (code < 0 or code == 143),
    )


@dataclass
class CliEnvelope:
    """Fields of ``--output-format json``; any missing field stays ``None``."""

    parsed: bool
    is_error: bool | None = None
    subtype: str | None = None
    session_id: str | None = None
    result_text: str | None = None
    structured_output: Any = None
    total_cost_usd: float | None = None
    num_turns: int | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    model_usage: dict[str, Any] = field(default_factory=dict)

    @property
    def models(self) -> list[str]:
        return sorted(self.model_usage)

    def usage_breakdown(self) -> UsageBreakdown:
        def num(name: str) -> int | None:
            value = self.usage.get(name)
            return int(value) if isinstance(value, int | float) else None

        return UsageBreakdown(
            input_cache_miss=num("input_tokens"),
            input_cache_hit=num("cache_read_input_tokens"),
            cache_write=num("cache_creation_input_tokens"),
            output=num("output_tokens"),
        )


def parse_envelope(stdout: str) -> CliEnvelope:
    try:
        data = json.loads(stdout.strip())
    except json.JSONDecodeError:
        return CliEnvelope(parsed=False)
    if not isinstance(data, dict):
        return CliEnvelope(parsed=False)

    def opt(name: str, kind: type | tuple[type, ...]) -> Any:
        value = data.get(name)
        return value if isinstance(value, kind) else None

    cost = data.get("total_cost_usd")
    return CliEnvelope(
        parsed=True,
        is_error=opt("is_error", bool),
        subtype=opt("subtype", str),
        session_id=opt("session_id", str),
        result_text=opt("result", str),
        structured_output=data.get("structured_output"),
        total_cost_usd=float(cost) if isinstance(cost, int | float) else None,
        num_turns=opt("num_turns", int),
        usage=opt("usage", dict) or {},
        model_usage=opt("modelUsage", dict) or {},
    )


@dataclass
class JudgeAttempt:
    """One judge call: the parsed output (or None) plus the raw record."""

    output: JudgeOutput | None
    error: str | None
    raw: dict[str, Any]
    stop_reason: str | None = None


class ClaudeCodeJudge:
    """Runs one isolated ``claude -p`` per document and judge pass."""

    def __init__(
        self,
        config: ClaudeCodeConfig,
        guard: CallGuard,
        *,
        runner: Runner = run_subprocess,
        environ: Mapping[str, str] | None = None,
        observed_cli_version: str | None = None,
    ) -> None:
        self.config = config
        self.guard = guard
        self.runner = runner
        self.environ = dict(os.environ if environ is None else environ)
        self.observed_cli_version = observed_cli_version
        self.judge_id = f"claude-code:{config.model_id}"
        self.auth = detect_auth(self.environ)

    def _secrets(self) -> list[str]:
        return [v for k, v in self.environ.items() if "KEY" in k or "TOKEN" in k]

    async def attempt(self, request: JudgeRequest) -> JudgeAttempt:
        prompt = build_prompt(request)
        schema = json.dumps(output_schema(), ensure_ascii=False, separators=(",", ":"))
        argv = build_command(self.config, prompt.system, schema)
        started_at = datetime.now(UTC)
        raw: dict[str, Any] = {
            "doc_id": request.doc_id,
            "judge_pass": request.judge_pass,
            "runner": "claude-code-cli",
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": prompt.sha256,
            "schema_version": SCHEMA_VERSION,
            "requested_model": self.config.model_id,
            "cli_version": self.observed_cli_version,
            "auth": self.auth.to_dict(),
            "started_at": started_at.isoformat(),
            # argv without the long prompt and schema (stored by hash above).
            "argv_flags": [a for a in argv[1:] if a.startswith("-")],
        }
        try:
            reservation = self.guard.before_call(
                "judge",
                f"{request.doc_id}/pass{request.judge_pass}",
                prompt.system + schema + prompt.user,
                self.config.max_output_tokens,
                requests=self.config.max_api_requests_per_call,
            )
        except StopBatchError as refusal:
            raw["refused_before_call"] = refusal.reason
            return JudgeAttempt(None, str(refusal), raw, refusal.reason)
        raw["reservation"] = {
            "tokens": reservation.reserved_tokens,
            "usd_estimate": reservation.reserved_usd,
        }
        with tempfile.TemporaryDirectory(prefix="pqb-judge-") as workdir:
            home = os.path.join(workdir, "home")
            os.mkdir(home)
            env = build_env(self.environ, self.config, home)
            result = await self.runner(
                argv, prompt.user, env, workdir, self.config.timeout_seconds
            )
        secrets = self._secrets()
        envelope = parse_envelope(result.stdout)
        raw.update(
            {
                "ended_at": datetime.now(UTC).isoformat(),
                "wall_seconds": round(result.seconds, 3),
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "interrupted": result.interrupted,
                "raw_stdout": redact(result.stdout, secrets),
                "raw_stderr": redact(result.stderr, secrets)[:20_000],
                "session_id": envelope.session_id,
                "returned_models": envelope.models or None,
                "num_turns": envelope.num_turns,
                "usage": envelope.usage or None,
                "cli_cost_estimate_usd": envelope.total_cost_usd,
                "cost_basis": "cli_client_side_estimate",
            }
        )
        output, parse_error = self._parse(result, envelope)
        usage = envelope.usage_breakdown() if envelope.parsed else None
        stop: str | None = None
        try:
            self.guard.after_call(
                reservation,
                usage=usage if usage is not None and usage.complete else None,
                at=started_at,
                timed_out=result.timed_out,
                models=envelope.models if envelope.parsed else None,
                note="ok" if output is not None else parse_error,
            )
        except StopBatchError as stop_error:
            stop = stop_error.reason
        if (
            envelope.total_cost_usd is not None
            and envelope.total_cost_usd > reservation.reserved_usd
        ):
            # The run cost more than its reservation: the bound was wrong.
            self.guard.monitor.latch(
                StopBatchError(
                    "budget_accounting",
                    f"cli estimate {envelope.total_cost_usd} > reserved "
                    f"{reservation.reserved_usd}",
                )
            )
            stop = stop or "budget_accounting"
        try:
            self.guard.monitor.observe_judge_validity(output is not None)
        except StopBatchError as stop_error:
            stop = stop or stop_error.reason
        raw["guard_after_call"] = {
            "settled_status": reservation.status,
            "charged_usd_estimate": reservation.charged_usd,
            "stop_reason": self.guard.monitor.stop_reason,
        }
        raw["parse_error"] = parse_error
        return JudgeAttempt(output, parse_error, raw, stop)

    @staticmethod
    def _parse(
        result: ProcessResult, envelope: CliEnvelope
    ) -> tuple[JudgeOutput | None, str | None]:
        if result.timed_out:
            return None, "timeout"
        if result.interrupted:
            return None, "interrupted"
        if result.exit_code != 0:
            return None, f"exit_code_{result.exit_code}"
        if not envelope.parsed:
            return None, "cli_output_not_json"
        if envelope.is_error:
            return None, f"cli_error:{envelope.subtype}"
        body: str | None
        if isinstance(envelope.structured_output, dict):
            body = json.dumps(envelope.structured_output, ensure_ascii=False)
        else:
            body = envelope.result_text
        if not body:
            return None, "no_structured_output"
        try:
            return parse_judge_response(body), None
        except JudgeParseError as error:
            return None, f"judge_parse_error: {error}"[:500]

    async def evaluate(self, request: JudgeRequest) -> JudgeOutput:
        attempt = await self.attempt(request)
        if attempt.output is None:
            raise JudgeParseError(attempt.error or "judge failed")
        return attempt.output
