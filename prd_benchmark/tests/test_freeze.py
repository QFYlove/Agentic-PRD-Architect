from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from prd_benchmark._yaml import load_yaml
from prd_benchmark.cases import DEFAULT_CASES_DIR, PACKAGE_DIR, freeze_problems
from prd_benchmark.config import PilotConfig
from prd_benchmark.freeze import (
    GATED_FILES,
    case_freeze_problems,
    computed_hashes,
    manifest_path,
    pre_freeze_problems,
    scoring_rule_problems,
)

P07 = "PQB-P07"


def test_scoring_rules_in_the_rubric_match_the_code(config: PilotConfig) -> None:
    assert scoring_rule_problems(config) == []


def test_pre_freeze_checks_pass_for_p07(
    cases: dict[str, object], config: PilotConfig
) -> None:
    assert pre_freeze_problems(cases[P07], config) == []  # type: ignore[arg-type]


def test_p07_freeze_manifest_records_scope_versions_and_hashes(
    cases: dict[str, object], config: PilotConfig
) -> None:
    data = load_yaml(manifest_path(DEFAULT_CASES_DIR, P07))
    assert data["case_id"] == P07 and data["pre_freeze_checks"] == "passed"
    scope = data["scope"]
    assert scope["hard_constraints"] == [f"H{n}" for n in range(1, 9)]
    assert len(scope["required_items"]) == 13 and len(scope["clarifications"]) == 11
    assert scope["rule_relations"]["design_choice"]
    versions = data["versions"]
    assert versions["rubric"] == "rubric-v0.4"
    assert versions["judge_prompt"] and versions["judge_schema"]
    assert "stream_prd(iteration=1" in data["parity_rule"]
    gated = data["gated_sha256"]
    assert set(GATED_FILES) <= set(gated)
    assert "cases/PQB-P07-recruiting-candidate-data.yaml" in gated
    assert data["computed_sha256"] == computed_hashes(cases[P07], config)  # type: ignore[arg-type]
    # Technical freeze only: a person must still sign it.
    assert data["confirmed_by"] is None
    assert case_freeze_problems(DEFAULT_CASES_DIR, P07, config) == [
        f"{P07} freeze is not confirmed by a person (confirmed_by)"
    ]


def _copy(tmp_path: Path) -> tuple[Path, Path]:
    """A copy of the package so edits never touch the real files."""
    package = tmp_path / "pkg"
    shutil.copytree(PACKAGE_DIR, package, ignore=shutil.ignore_patterns("__pycache__"))
    return package, package / "cases"


def _confirm(cases_dir: Path) -> None:
    path = manifest_path(cases_dir, P07)
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("confirmed_by: null", "confirmed_by: reviewer-tbd"))


def test_p07_alone_is_allowed_once_confirmed_and_any_change_voids_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, config: PilotConfig
) -> None:
    package, cases_dir = _copy(tmp_path)
    monkeypatch.setattr("prd_benchmark.freeze.PACKAGE_DIR", package)
    _confirm(cases_dir)
    assert freeze_problems(cases_dir, [P07], config) == []
    # The rest of the set is still draft, so a full-set run stays blocked.
    assert freeze_problems(cases_dir)
    (package / "rubric.md").write_text(
        (package / "rubric.md").read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    assert any("rubric.md changed" in p for p in freeze_problems(cases_dir, [P07]))


def test_editing_the_frozen_case_voids_the_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package, cases_dir = _copy(tmp_path)
    monkeypatch.setattr("prd_benchmark.freeze.PACKAGE_DIR", package)
    _confirm(cases_dir)
    case_file = cases_dir / "PQB-P07-recruiting-candidate-data.yaml"
    case_file.write_text(
        case_file.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8"
    )
    problems = freeze_problems(cases_dir, [P07])
    assert any("sha256 does not match" in p for p in problems)
    assert any("changed after the freeze" in p for p in problems)


def test_config_change_that_affects_generation_voids_the_freeze(
    config: PilotConfig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package, cases_dir = _copy(tmp_path)
    monkeypatch.setattr("prd_benchmark.freeze.PACKAGE_DIR", package)
    _confirm(cases_dir)
    changed = config.model_copy(
        update={"model": config.model.model_copy(update={"max_output_tokens": 8000})}
    )
    assert freeze_problems(cases_dir, [P07], changed) == [
        f"{P07}: config_sections changed after the freeze"
    ]
    # Approval and budget fields are not part of the freeze.
    approvals = config.approvals.model_copy(update={"token_budget_limit": 300000})
    assert (
        freeze_problems(
            cases_dir, [P07], config.model_copy(update={"approvals": approvals})
        )
        == []
    )
