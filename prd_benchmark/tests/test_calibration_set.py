from __future__ import annotations

from prd_benchmark.cases import PACKAGE_DIR, freeze_problems, load_cases
from prd_benchmark.evidence import EvidenceIndex

ROOT = PACKAGE_DIR / "calibration_set"


def test_calibration_cases_load_and_are_separate_from_the_pilot() -> None:
    cal = {c.id: c for c in load_cases(ROOT / "cases")}
    pilot = {c.id for c in load_cases()}
    assert set(cal) == {"PQB-P91", "PQB-P92"}
    assert not set(cal) & pilot
    assert freeze_problems(ROOT / "cases")  # draft until humans score them
    assert cal["PQB-P92"].conflicts[0].id == "K1"


def test_calibration_documents_are_complete_and_quote_their_traps() -> None:
    doc1 = (ROOT / "documents" / "PQB-P91-doc-1.md").read_text(encoding="utf-8")
    doc2 = (ROOT / "documents" / "PQB-P92-doc-1.md").read_text(encoding="utf-8")
    index1, index2 = EvidenceIndex(doc1), EvidenceIndex(doc2)
    # Hard-constraint violation and its internal counterpart.
    assert index1.check("员工最多可提前 30 天预订").valid
    assert index1.check("预订最多可提前 14 天").valid
    # Clarification stated as settled fact.
    assert index2.check("经确认，到账目标为提交后 3 个工作日").valid
    for doc in (doc1, doc2):
        assert "## " in doc and "验收标准" in doc and len(doc) > 400
