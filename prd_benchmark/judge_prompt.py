"""Assemble the formal judge prompt for one blinded document.

The prompt is pure text built from frozen artifacts: the system instructions
(``prompts/system-prompt.md``), rubric section 4, the case's gold standard, the
document, and the JSON Schema of ``JudgeOutput``. Nothing here calls a model;
a real judge client is a later, separately approved step.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from prd_benchmark.cases import PACKAGE_DIR, Case
from prd_benchmark.judge import JudgeOutput, JudgeRequest

SYSTEM_PROMPT_PATH = PACKAGE_DIR / "prompts" / "system-prompt.md"
RUBRIC_PATH = PACKAGE_DIR / "rubric.md"
PROMPT_VERSION = "judge-prompt-v0.1"


@dataclass(frozen=True)
class JudgePrompt:
    system: str
    user: str
    version: str

    @property
    def sha256(self) -> str:
        material = f"{self.version}\x1f{self.system}\x1f{self.user}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()


def rubric_anchor_section() -> str:
    """Rubric section 4 (dimensions and anchors), verbatim."""
    text = RUBRIC_PATH.read_text(encoding="utf-8")
    start = text.index("## 4. 维度与锚点")
    end = text.index("## 5.", start)
    return text[start:end].strip()


def output_schema() -> dict[str, Any]:
    return JudgeOutput.model_json_schema()


def system_prompt() -> str:
    instructions = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    schema = json.dumps(output_schema(), ensure_ascii=False, indent=1)
    return (
        f"{instructions}\n\n## 附：Rubric 第 4 节\n\n{rubric_anchor_section()}\n\n"
        f"## 附：输出 JSON Schema\n\n```json\n{schema}\n```"
    )


def gold_standard(case: Case, item_order: tuple[str, ...]) -> dict[str, Any]:
    """Everything the judge may know about the case, in the given item order.

    ``rationale`` and ``impact`` of R/C items are evaluator notes about *why*
    an item matters; they are included because they define the item's scope.
    Nothing that would reveal a condition (A/B) exists in a case file.
    """
    r_items = {item.id: item for item in case.required_items}
    c_items = {item.id: item for item in case.clarifications}
    return {
        "case_id": case.id,
        "category": case.category,
        "evaluator_context": case.evaluator_context,
        "hard_constraints": [
            {"id": h.id, "text": h.text, "quote": h.quote, "note": h.note}
            for h in case.hard_constraints
        ],
        "rule_relations": [r.model_dump(mode="json") for r in case.rule_relations],
        "conflicts": [k.model_dump(mode="json") for k in case.conflicts],
        "required_items": [
            r_items[i].model_dump(mode="json") for i in item_order if i in r_items
        ],
        "clarifications": [
            c_items[i].model_dump(mode="json") for i in item_order if i in c_items
        ],
        "acceptable_assumptions": list(case.acceptable_assumptions),
        "critical_defects": [x.model_dump(mode="json") for x in case.critical_defects],
        "generic_critical_rules": ["G1", "G2", "G3", "G4", "G5"],
        "judge_notes": case.judge_notes,
    }


def user_prompt(request: JudgeRequest) -> str:
    case = request.case
    frozen = case.frozen_input.model_dump(mode="json")
    gold = gold_standard(case, request.item_order)
    return "\n\n".join(
        [
            f"评审轮次：{request.judge_pass}。"
            f"条目顺序：{', '.join(request.item_order)}。",
            "<frozen_input>\n"
            + json.dumps(frozen, ensure_ascii=False, indent=1)
            + "\n</frozen_input>",
            "<gold_standard>\n"
            + json.dumps(gold, ensure_ascii=False, indent=1)
            + "\n</gold_standard>",
            "<document>\n" + request.document + "\n</document>",
            "只输出一个符合 Schema 的 JSON 对象。",
        ]
    )


def build_prompt(request: JudgeRequest) -> JudgePrompt:
    return JudgePrompt(
        system=system_prompt(), user=user_prompt(request), version=PROMPT_VERSION
    )
