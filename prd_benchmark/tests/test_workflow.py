from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from prd_benchmark.config import PilotConfig
from prd_benchmark.fake_openai import FakeBehavior
from prd_benchmark.run_workflow import make_settings, run_condition_b
from prd_benchmark.tests.helpers import recorded_provider, status_error


async def test_full_workflow_records_every_call(
    config: PilotConfig, cases: dict[str, Any]
) -> None:
    recorder, provider = recorded_provider(config, condition="B")
    result = await run_condition_b(
        cases["PQB-P01"].frozen_input.to_request(),
        provider,
        model=config.model,
        condition=config.conditions.B,
    )
    # v1 scores 80 with must_fix items, v2 scores 90 with none: completes at v2.
    assert result.status == "COMPLETED"
    assert result.snapshot.model_id == "deepseek-flash"
    assert result.snapshot.quality_threshold == 85
    assert result.snapshot.max_iterations == 3
    documents = result.documents()
    assert set(documents) == {"B.best", "B.last", "B.v1"}
    assert documents["B.best"] == documents["B.last"] != documents["B.v1"]
    nodes = [c.node for c in recorder.records]
    assert nodes.count("generator") == 2
    assert nodes.count("optimizer") == 1
    assert sorted(n for n in nodes if n.endswith("_reviewer")) == sorted(
        ["tech_reviewer", "ux_reviewer", "biz_reviewer"] * 2
    )
    assert all(c.response_model == "deepseek-flash" for c in recorder.records)
    assert {c.version for c in recorder.records if c.node == "generator"} == {1, 2}
    meta = result.meta()
    assert meta["best_version"] == 2 and meta["quality_gate_passed"]
    # The snapshot meters only successful calls; the recorder sees all of them.
    recorded = sum(c.total_tokens or 0 for c in recorder.records)
    assert recorded == result.snapshot.total_tokens.total_tokens


async def test_reviewer_repair_is_recorded_separately(
    config: PilotConfig, cases: dict[str, Any]
) -> None:
    recorder, provider = recorded_provider(
        config, FakeBehavior(invalid_review_calls={1}), condition="B"
    )
    result = await run_condition_b(
        cases["PQB-P01"].frozen_input.to_request(),
        provider,
        model=config.model,
        condition=config.conditions.B,
    )
    assert result.status == "COMPLETED"
    repairs = [c for c in recorder.records if c.node == "repair"]
    assert len(repairs) == 1
    assert repairs[0].version == 1


async def test_best_and_last_differ_when_a_later_version_regresses(
    config: PilotConfig, cases: dict[str, Any]
) -> None:
    behavior = FakeBehavior(
        review_scores={1: 82, 2: 70, 3: 75}, must_fix_iterations={1, 2, 3}
    )
    _, provider = recorded_provider(config, behavior, condition="B")
    result = await run_condition_b(
        cases["PQB-P03"].frozen_input.to_request(),
        provider,
        model=config.model,
        condition=config.conditions.B,
    )
    assert result.status == "MAX_ITERATIONS_REACHED"
    assert result.snapshot.best_version == 1
    documents = result.documents()
    assert documents["B.best"] == documents["B.v1"]
    assert documents["B.last"] != documents["B.best"]
    assert result.meta()["last_version"] == 3


async def test_invalid_model_fails_the_run_without_retry(
    config: PilotConfig, cases: dict[str, Any]
) -> None:
    recorder, provider = recorded_provider(
        config, FakeBehavior(raise_on_call={1: status_error(404)}), condition="B"
    )
    result = await run_condition_b(
        cases["PQB-P01"].frozen_input.to_request(),
        provider,
        model=config.model,
        condition=config.conditions.B,
    )
    assert result.status == "FAILED"
    assert result.error_code == "PROVIDER_MODEL_INVALID"
    assert result.documents() == {}
    assert len(recorder.records) == 1


def test_settings_ignore_env_file_and_process_environment(
    config: PilotConfig,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("RUN_TIMEOUT_SECONDS=11\n", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-must-not-leak")
    monkeypatch.setenv("REVIEWER_TIMEOUT_SECONDS", "3")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "leak.sqlite3"))
    settings = make_settings(config.conditions.B)
    assert settings.run_timeout_seconds == 600
    assert settings.reviewer_timeout_seconds == 45
    assert settings.generator_timeout_seconds == 240
    assert settings.optimizer_timeout_seconds == 60
    assert settings.database_path == ":memory:"
    assert settings.deepseek_api_key is None
    assert "sk-test" not in repr(settings)


async def test_workflow_does_not_touch_the_product_database(
    config: PilotConfig, cases: dict[str, Any]
) -> None:
    # Only stat()-ed, never opened: the product database is not ours to read.
    data_dir = Path(__file__).resolve().parents[2] / "data"

    def fingerprint() -> dict[str, tuple[int, int]]:
        if not data_dir.exists():
            return {}
        return {
            p.name: (p.stat().st_size, p.stat().st_mtime_ns)
            for p in data_dir.iterdir()
            if p.is_file()
        }

    before = fingerprint()
    _, provider = recorded_provider(config, condition="B")
    await run_condition_b(
        cases["PQB-P02"].frozen_input.to_request(),
        provider,
        model=config.model,
        condition=config.conditions.B,
    )
    assert fingerprint() == before
