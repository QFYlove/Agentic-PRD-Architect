"""Review from every entry point, and internal codes kept out of documents."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from backend.tests.test_v3_workflow import (
    IDEA,
    confirm_all,
    gateway,
    items,
    review,
    sections,
    wait_job,
)
from backend.v3.rules import strip_internal_refs

CODE = re.compile(r"\b(?:POS|GOAL|USR|PRB|SCN|ALT|SOL|FR|CON|ASM|DEC|OPEN)-\d+\b")


async def start(app: Any, client: AsyncClient, mode: str, text: str = IDEA) -> str:
    response = await client.post(
        "/api/v3/projects", json={"text": text, "entry_mode": mode}
    )
    assert response.status_code == 201, response.text
    body = response.json()
    if body["job"]:
        await wait_job(app, body["job"])
    return str(body["project"]["id"])


async def explore_round(app: Any, client: AsyncClient, project_id: str) -> None:
    conversation = (
        await client.get(f"/api/v3/projects/{project_id}/conversation")
    ).json()
    pending = [q for q in conversation["questions"] if q["state"] == "pending"]
    answers = [{"question": pending[0]["code"], "kind": "answer", "text": "上班族"}]
    job = (
        await client.post(
            f"/api/v3/projects/{project_id}/turns", json={"answers": answers}
        )
    ).json()
    await wait_job(app, job)


async def brief_of(client: AsyncClient, project_id: str) -> dict[str, Any]:
    return dict((await client.post(f"/api/v3/projects/{project_id}/briefs")).json())


async def write_prd(app: Any, client: AsyncClient, project_id: str) -> None:
    await confirm_all(client, project_id)
    brief = await brief_of(client, project_id)
    await client.post(f"/api/v3/briefs/{brief['id']}/confirm")
    await wait_job(
        app, (await client.post(f"/api/v3/projects/{project_id}/outline")).json()
    )
    await client.post(f"/api/v3/projects/{project_id}/outline/confirm")
    job = (await client.post(f"/api/v3/projects/{project_id}/generate", json={})).json()
    assert (await wait_job(app, job))["status"] == "succeeded"


# --- problem 1: review from every entry ---------------------------------------


@pytest.mark.parametrize("mode", ["idea", "requirement"])
async def test_brief_check_then_four_reviewers(
    app: Any, client: AsyncClient, mode: str
) -> None:
    project_id = await start(app, client, mode)
    await explore_round(app, client, project_id)
    brief = await brief_of(client, project_id)

    # Brief stage: the PRD review is refused, the Brief check runs.
    early = await client.post(f"/api/v3/projects/{project_id}/reviews", json={})
    assert early.json()["error"]["code"] == "DOCUMENT_EMPTY"
    job = (
        await client.post(
            f"/api/v3/projects/{project_id}/analyze", json={"brief_id": brief["id"]}
        )
    ).json()
    assert (await wait_job(app, job))["status"] == "succeeded"
    found = (
        await client.get(
            f"/api/v3/projects/{project_id}/findings", params={"scope": "baseline"}
        )
    ).json()["items"]
    assert found and all(f["brief_version"] == brief["version"] for f in found)
    assert all(f["related_items"] for f in found)
    assert not any(c.startswith("review:") for c in gateway(app).calls)

    # PRD stage: four reviewers, results tied to the version they read.
    await write_prd(app, client, project_id)
    result = await review(app, client, project_id)
    assert result["status"] == "succeeded"
    assert sorted(result["result"]["reviewers"]) == ["biz", "product", "tech", "ux"]
    results = (await client.get(f"/api/v3/projects/{project_id}/reviews")).json()
    versions = (await client.get(f"/api/v3/projects/{project_id}/versions")).json()
    assert {r["version_number"] for r in results["items"]} == {
        versions["items"][0]["number"]
    }

    # Drafting a new Brief keeps both the Brief findings and the PRD reviews.
    await brief_of(client, project_id)
    after = (
        await client.get(
            f"/api/v3/projects/{project_id}/findings", params={"scope": "baseline"}
        )
    ).json()["items"]
    assert {f["code"] for f in found} <= {f["code"] for f in after}
    again = (await client.get(f"/api/v3/projects/{project_id}/reviews")).json()
    assert len(again["items"]) == 4


async def test_review_entry_still_works(app: Any, client: AsyncClient) -> None:
    project_id = await start(
        app, client, "review", "# 打卡\n\n## 1. 概述\n帮助用户养成习惯。"
    )
    result = await review(app, client, project_id)
    assert result["status"] == "succeeded"


async def test_unfinished_document_cannot_be_fully_reviewed(
    app: Any, client: AsyncClient
) -> None:
    project_id = await start(app, client, "idea")
    await confirm_all(client, project_id)
    brief = await brief_of(client, project_id)
    await client.post(f"/api/v3/briefs/{brief['id']}/confirm")
    await wait_job(
        app, (await client.post(f"/api/v3/projects/{project_id}/outline")).json()
    )
    await client.post(f"/api/v3/projects/{project_id}/outline/confirm")
    gateway(app).fail_sections = {"异常处理"}
    await wait_job(
        app,
        (await client.post(f"/api/v3/projects/{project_id}/generate", json={})).json(),
    )
    full = await client.post(f"/api/v3/projects/{project_id}/reviews", json={})
    assert full.json()["error"]["code"] == "DOCUMENT_INCOMPLETE"
    done = next(s for s in await sections(client, project_id) if s["status"] == "done")
    scoped = await client.post(
        f"/api/v3/projects/{project_id}/reviews", json={"sections": [done["code"]]}
    )
    assert scoped.status_code == 202


async def test_edited_document_is_saved_before_review(
    app: Any, client: AsyncClient
) -> None:
    project_id = await start(app, client, "idea")
    await write_prd(app, client, project_id)
    target = (await sections(client, project_id))[0]
    await client.patch(
        f"/api/v3/sections/{target['id']}",
        json={"row_version": target["row_version"], "body": "改过的概述。"},
    )
    await review(app, client, project_id)
    versions = (await client.get(f"/api/v3/projects/{project_id}/versions")).json()
    latest = versions["items"][0]
    assert latest["number"] == 2 and latest["source"] == "review"
    results = (await client.get(f"/api/v3/projects/{project_id}/reviews")).json()
    assert {r["version_number"] for r in results["items"]} == {2}


# --- problem 2: internal codes ---------------------------------------------------


async def test_codes_are_data_not_document_text(app: Any, client: AsyncClient) -> None:
    project_id = await start(app, client, "idea")
    job = (await client.post(f"/api/v3/projects/{project_id}/analyze")).json()
    await wait_job(app, job)
    brief = await brief_of(client, project_id)
    for section in brief["sections"]:
        assert not CODE.search(section["text"]), section
        assert not re.search(r"\bF-\d+\b", section["text"])
    position = next(s for s in brief["sections"] if s["key"] == "position")
    assert position["item_codes"] == ["POS-01"]
    risks = next(s for s in brief["sections"] if s["key"] == "risks")
    assert risks["finding_codes"]

    await write_prd(app, client, project_id)
    for section in await sections(client, project_id):
        assert not CODE.search(section["title"] + section["body"]), section
    linked = [s for s in await sections(client, project_id) if s["item_codes"]]
    assert linked  # the structure still links sections to items
    sources = (await client.get(f"/api/v3/sections/{linked[0]['id']}/sources")).json()
    assert sources["items"] and sources["items"][0]["code"] in linked[0]["item_codes"]
    text = (await client.get(f"/api/v3/projects/{project_id}/export.md")).text
    assert not CODE.search(text)

    stored = {i["code"] for i in await items(client, project_id)}
    assert {"POS-01", "USR-01", "PRB-01"} <= stored
    baseline = (
        await client.get(
            f"/api/v3/projects/{project_id}/findings", params={"scope": "baseline"}
        )
    ).json()["items"]
    assert all(set(f["related_items"]) <= stored for f in baseline)


async def test_model_written_codes_are_removed_from_sections(
    app: Any, client: AsyncClient
) -> None:
    project_id = await start(app, client, "idea")
    original = gateway(app)._section_body

    def leaky(payload: dict[str, Any]) -> str:
        return original(payload).replace("\n\n<!--", "（POS-01、USR-01）\n\n<!--", 1)

    gateway(app)._section_body = leaky  # type: ignore[method-assign]
    await write_prd(app, client, project_id)
    for section in await sections(client, project_id):
        assert "POS-01" not in section["body"]


async def test_user_typed_codes_are_kept(app: Any, client: AsyncClient) -> None:
    text = "我想做一个工单系统，支持 SKU-100 商品同步。参考旧系统编号（FR-01）。"
    project_id = await start(app, client, "idea", text)
    await write_prd(app, client, project_id)
    exported = (await client.get(f"/api/v3/projects/{project_id}/export.md")).text
    # FR-01 is also an internal code here, but the user wrote it, so it stays.
    body = "\n".join(s["body"] for s in await sections(client, project_id))
    assert "SKU-100" in body + exported
    assert "（FR-01）" in body and "（FR-01）" in exported


def test_strip_only_removes_known_codes() -> None:
    codes = {"POS-01", "USR-02"}
    assert strip_internal_refs("定位（POS-01、USR-02）。", codes) == "定位。"
    assert strip_internal_refs("型号（X-200）", codes) == "型号（X-200）"
    assert (
        strip_internal_refs("混合（POS-01、X-200）", codes) == "混合（POS-01、X-200）"
    )
    assert strip_internal_refs("见 [USR-02] 说明", codes) == "见 说明"


async def test_briefs_saved_with_codes_read_clean(
    app: Any, client: AsyncClient, tmp_path: Path
) -> None:
    project_id = await start(app, client, "idea")
    brief = await brief_of(client, project_id)
    # Simulate a Brief stored by the earlier build, with codes in its text.
    store = app.state.project_store
    row = store.rows("SELECT sections FROM v3_briefs WHERE id = ?", (brief["id"],))
    legacy = row[0][0].replace('大学生"', '大学生（USR-01）"')
    store._connection.execute(
        "UPDATE v3_briefs SET sections = ? WHERE id = ?", (legacy, brief["id"])
    )
    store._connection.commit()
    listed = (await client.get(f"/api/v3/projects/{project_id}/briefs")).json()
    texts = "".join(s["text"] for s in listed["items"][0]["sections"])
    assert "USR-01" not in texts and "大学生" in texts
    # The stored snapshot itself is left unchanged.
    raw = store.rows("SELECT sections FROM v3_briefs WHERE id = ?", (brief["id"],))
    assert "USR-01" in raw[0][0]


async def test_brief_check_after_baseline_check_reuses_findings(
    app: Any, client: AsyncClient
) -> None:
    """Checking the Brief after checking the baseline must still show results
    for the Brief, without duplicating the findings already raised."""
    project_id = await start(app, client, "idea")
    await wait_job(
        app, (await client.post(f"/api/v3/projects/{project_id}/analyze")).json()
    )
    first = (
        await client.get(
            f"/api/v3/projects/{project_id}/findings", params={"scope": "baseline"}
        )
    ).json()["items"]
    brief = await brief_of(client, project_id)
    job = (
        await client.post(
            f"/api/v3/projects/{project_id}/analyze", json={"brief_id": brief["id"]}
        )
    ).json()
    result = await wait_job(app, job)
    assert result["result"]["repeated"] == len(first)
    after = (
        await client.get(
            f"/api/v3/projects/{project_id}/findings", params={"scope": "baseline"}
        )
    ).json()["items"]
    assert [f["code"] for f in after] == [f["code"] for f in first]
    assert all(f["brief_version"] == brief["version"] for f in after)
