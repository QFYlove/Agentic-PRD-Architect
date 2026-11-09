"""Freezing a single case for a real batch.

A freeze manifest (``cases/freeze/<case_id>.yaml``) records what a frozen case
is graded against: the case file, the rubric, the judge prompt and schema, the
scoring and A/B generation code, and the scoring-relevant config sections, each
by SHA-256. A real batch over that case is allowed only while every gated hash
still matches and a person has signed the freeze (``confirmed_by``). Any change
after the freeze needs a new version and a new freeze manifest.

Checks run before freezing (``pre_freeze_problems``) are mechanical. They
catch structural slips; they do not replace the human review of the case.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from prd_benchmark._yaml import dump_yaml, load_yaml
from prd_benchmark.artifacts import write_text_once
from prd_benchmark.cases import (
    PACKAGE_DIR,
    Case,
    file_sha256,
    load_case,
    load_manifest,
    normalize_whitespace,
)
from prd_benchmark.config import PilotConfig

FREEZE_MANIFEST_VERSION = 1
#: A change to any of these after a freeze invalidates it.
GATED_FILES = (
    "rubric.md",
    "prompts/system-prompt.md",
    "scoring.py",
    "judge.py",
    "judge_prompt.py",
    "evidence.py",
    "run_single.py",
    "run_workflow.py",
)
#: Config sections that change what is generated or how it is scored. The
#: approval, pricing, and execution sections are filled in at approval time
#: and are deliberately not part of the freeze.
#: ``config_version`` is recorded under ``versions`` but not hashed, so bumping
#: it when the config is frozen for approval does not void the case freeze.
FROZEN_CONFIG_KEYS = ("model", "conditions", "output_language")
FROZEN_JUDGE_KEYS = ("passes_per_document", "shuffle_items_on_second_pass")
PARITY_RULE = (
    "Condition A is the same generator call as condition B's v1: "
    "stream_prd(iteration=1, revision_plan=None, baseline_prd=None), built from "
    "the same CreateRunRequest, so both see byte-identical first requests "
    "(tests/test_streaming_and_parity.py)."
)
_RUBRIC_DIMENSION = re.compile(r"^### 4\.(\d) .+?（(\d+) 分）", re.MULTILINE)
_RUBRIC_ORDER = (
    "coverage",
    "correctness",
    "flow",
    "exceptions",
    "acceptance",
    "consistency",
)
_RUBRIC_VERDICT = re.compile(
    r"^\| `(covered|partial|missing|contradicted)` \|.*\| ([0-9.]+)", re.MULTILINE
)


def manifest_path(cases_dir: Path, case_id: str) -> Path:
    return cases_dir / "freeze" / f"{case_id}.yaml"


def _relative(path: Path) -> str:
    return str(path.resolve().relative_to(PACKAGE_DIR.resolve()))


def _json_sha(value: Any) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def config_sections(config: PilotConfig) -> dict[str, Any]:
    data = config.model_dump(mode="json")
    sections = {key: data[key] for key in FROZEN_CONFIG_KEYS}
    sections["scoring"] = data["scoring"]
    sections["judge"] = {key: data["judge"][key] for key in FROZEN_JUDGE_KEYS}
    return sections


def computed_hashes(case: Case, config: PilotConfig) -> dict[str, str]:
    """Hashes of what the judge actually receives, built from the code.

    The gold standard is hashed in the case's declared item order (pass 1);
    later passes only reorder it.
    """
    from prd_benchmark.judge_prompt import gold_standard, output_schema, system_prompt

    order = tuple(
        [r.id for r in case.required_items] + [c.id for c in case.clarifications]
    )
    return {
        "judge_system_prompt": hashlib.sha256(
            system_prompt().encode("utf-8")
        ).hexdigest(),
        "judge_output_schema": _json_sha(output_schema()),
        "judge_gold_standard": _json_sha(gold_standard(case, order)),
        "config_sections": _json_sha(config_sections(config)),
    }


def scoring_rule_problems(config: PilotConfig) -> list[str]:
    """The rubric's points and verdict scores must equal the scoring code."""
    from prd_benchmark.scoring import COVERAGE_WEIGHT, DIMENSION_WEIGHTS, VERDICT_SCORE

    rubric = (PACKAGE_DIR / "rubric.md").read_text(encoding="utf-8")
    problems: list[str] = []
    if f"`{config.scoring.rubric_version}`" not in rubric.split("\n", 3)[2]:
        problems.append(
            f"rubric.md header does not name {config.scoring.rubric_version}"
        )
    code = {"coverage": COVERAGE_WEIGHT, **DIMENSION_WEIGHTS}
    found = {
        _RUBRIC_ORDER[int(n) - 1]: int(points)
        for n, points in _RUBRIC_DIMENSION.findall(rubric)
        if 1 <= int(n) <= len(_RUBRIC_ORDER)
    }
    if found != code:
        problems.append(f"rubric dimension points {found} differ from code {code}")
    verdicts = dict(_RUBRIC_VERDICT.findall(rubric))
    for verdict, score in VERDICT_SCORE.items():
        if verdict not in verdicts or float(verdicts[verdict]) != score:
            problems.append(f"rubric score for {verdict} differs from code ({score})")
    if sum(code.values()) != 100:
        problems.append("dimension points do not add up to 100")
    return problems


def pre_freeze_problems(case: Case, config: PilotConfig) -> list[str]:
    problems: list[str] = []
    source = case.frozen_input.normalized_text()
    for h in case.hard_constraints:
        if not h.quote.strip() or normalize_whitespace(h.quote) not in source:
            problems.append(f"{h.id}: quote missing or not in the frozen input")
    h_texts = {normalize_whitespace(h.text) for h in case.hard_constraints}
    h_quotes = {normalize_whitespace(h.quote) for h in case.hard_constraints}
    for relation in case.rule_relations:
        if relation.kind == "explicit":
            continue
        if relation.constraints:
            problems.append(f"{relation.id}: {relation.kind} relation cites H ids")
        if normalize_whitespace(relation.text) in h_texts:
            problems.append(f"{relation.id}: {relation.kind} relation restated as an H")
    # A clarification may ask how to read an H entry; it must not *be* one.
    for clarification in case.clarifications:
        question = normalize_whitespace(clarification.question)
        if question in h_texts | h_quotes:
            problems.append(f"{clarification.id}: clarification restated as an H")
    if not case.clarifications:
        problems.append("case has no clarifications")
    problems.extend(scoring_rule_problems(config))
    return problems


def build_manifest(
    case: Case,
    case_file: Path,
    config: PilotConfig,
    *,
    frozen_at: str,
    git_commit: str | None,
) -> dict[str, Any]:
    from prd_benchmark.judge_claude import SCHEMA_VERSION
    from prd_benchmark.judge_prompt import PROMPT_VERSION

    case_set = load_manifest(case_file.parent)
    relations: dict[str, list[str]] = {
        "explicit": [],
        "derived": [],
        "design_choice": [],
    }
    for relation in case.rule_relations:
        relations[relation.kind].append(relation.id)
    code = sorted(
        p for p in PACKAGE_DIR.glob("*.py") if _relative(p) not in GATED_FILES
    )
    return {
        "freeze_manifest_version": FREEZE_MANIFEST_VERSION,
        "case_id": case.id,
        "case_version": case.case_version,
        "case_set_version": case_set.case_set_version,
        "frozen_at": frozen_at,
        "confirmed_by": None,
        "note": (
            "Technical freeze. Real batches stay blocked until a person who "
            "reviewed the case sets confirmed_by. Any change to a gated file "
            "needs a new version and a new freeze manifest."
        ),
        "scope": {
            "frozen_input_fields": [
                name
                for name, value in case.frozen_input.model_dump().items()
                if value is not None
            ],
            "hard_constraints": [h.id for h in case.hard_constraints],
            "required_items": [r.id for r in case.required_items],
            "core_required_items": [r.id for r in case.required_items if r.core],
            "clarifications": [c.id for c in case.clarifications],
            "core_clarifications": [c.id for c in case.clarifications if c.core],
            "critical_defects": [x.id for x in case.critical_defects],
            "rule_relations": relations,
            "conflicts": [k.id for k in case.conflicts],
        },
        "versions": {
            "rubric": config.scoring.rubric_version,
            "judge_prompt": PROMPT_VERSION,
            "judge_schema": SCHEMA_VERSION,
            "config": config.config_version,
            "config_status_at_freeze": config.status,
        },
        "parity_rule": PARITY_RULE,
        "git": {
            "commit": git_commit,
            "note": (
                "prd_benchmark/ was not committed at this commit; the code is "
                "identified by the hashes below."
            ),
        },
        "pre_freeze_checks": "passed",
        "gated_sha256": {
            _relative(case_file): file_sha256(case_file),
            **{name: file_sha256(PACKAGE_DIR / name) for name in GATED_FILES},
        },
        "computed_sha256": computed_hashes(case, config),
        "recorded_sha256": {_relative(p): file_sha256(p) for p in code},
    }


def freeze_case(
    cases_dir: Path,
    case_id: str,
    config: PilotConfig,
    *,
    frozen_at: str,
    git_commit: str | None,
) -> Path:
    """Write the freeze manifest once. The case must already say ``frozen``."""
    entry = next((e for e in load_manifest(cases_dir).cases if e.id == case_id), None)
    if entry is None:
        raise ValueError(f"{case_id} is not in the manifest")
    case_file = cases_dir / entry.file
    case = load_case(case_file)
    if case.status != "frozen" or entry.status != "frozen":
        raise ValueError(f"{case_id}: set status frozen in the case and manifest first")
    problems = pre_freeze_problems(case, config)
    if problems:
        raise ValueError("pre-freeze checks failed: " + "; ".join(problems))
    target = manifest_path(cases_dir, case_id)
    data = build_manifest(
        case, case_file, config, frozen_at=frozen_at, git_commit=git_commit
    )
    write_text_once(target, dump_yaml(data))
    return target


def case_freeze_problems(
    cases_dir: Path, case_id: str, config: PilotConfig | None = None
) -> list[str]:
    """Why a frozen case's freeze no longer holds (empty when it does)."""
    path = manifest_path(cases_dir, case_id)
    if not path.exists():
        return [f"{case_id} has no freeze manifest"]
    data = load_yaml(path)
    problems: list[str] = []
    if not data.get("confirmed_by"):
        problems.append(f"{case_id} freeze is not confirmed by a person (confirmed_by)")
    for relative, expected in data.get("gated_sha256", {}).items():
        current = PACKAGE_DIR / relative
        if not current.exists() or file_sha256(current) != expected:
            problems.append(
                f"{case_id}: {relative} changed after the freeze; bump the version "
                "and freeze again"
            )
    if config is not None:
        entry = next(e for e in load_manifest(cases_dir).cases if e.id == case_id)
        case = load_case(cases_dir / entry.file)
        current_hashes = computed_hashes(case, config)
        for name, expected in data.get("computed_sha256", {}).items():
            if current_hashes.get(name) != expected:
                problems.append(f"{case_id}: {name} changed after the freeze")
    return problems
