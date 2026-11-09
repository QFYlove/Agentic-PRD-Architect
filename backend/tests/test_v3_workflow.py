"""V3 end-to-end service and API tests, all on the deterministic mock gateway."""

from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import create_app
from backend.providers.mock import MockLLMProvider
from backend.tests.helpers import make_settings
from backend.v3.mock import MockGateway


def gateway(app: Any) -> MockGateway:
    value = app.state.jobs.gateway
    assert isinstance(value, MockGateway)
    return value


async def wait_job(app: Any, job: dict[str, Any]) -> dict[str, Any]:
    done = await app.state.jobs.wait(job["id"], seconds=10)
    return done.model_dump(mode="json")


IDEA = (
    "我想做一个云盘，支持磁力链接下载、在线播放和资源分享。"
    "目标用户是大学生。团队 3 人，预算有限。"
)


async def create(app: Any, client: AsyncClient, text: str = IDEA) -> str:
    response = await client.post("/api/v3/projects", json={"text": text})
    assert response.status_code == 201, response.text
    body = response.json()
    await wait_job(app, body["job"])
    return str(body["project"]["id"])


async def items(client: AsyncClient, project_id: str) -> list[dict[str, Any]]:
    return list(
        (await client.get(f"/api/v3/projects/{project_id}/items")).json()["items"]
    )


async def confirm_all(client: AsyncClient, project_id: str) -> None:
    for item in await items(client, project_id):
        if item["status"] not in ("confirmed", "rejected"):
            await client.patch(
                f"/api/v3/items/{item['id']}", json={"status": "confirmed"}
            )


async def to_document(app: Any, client: AsyncClient) -> str:
    project_id = await create(app, client)
    await confirm_all(client, project_id)
    brief = (await client.post(f"/api/v3/projects/{project_id}/briefs")).json()
    await client.post(f"/api/v3/briefs/{brief['id']}/confirm")
    job = (await client.post(f"/api/v3/projects/{project_id}/outline")).json()
    assert (await wait_job(app, job))["status"] == "succeeded"
    await client.post(f"/api/v3/projects/{project_id}/outline/confirm")
    job = (await client.post(f"/api/v3/projects/{project_id}/generate", json={})).json()
    assert (await wait_job(app, job))["status"] == "succeeded"
    return project_id


async def sections(client: AsyncClient, project_id: str) -> list[dict[str, Any]]:
    response = await client.get(f"/api/v3/projects/{project_id}/sections")
    return list(response.json()["items"])


async def review(app: Any, client: AsyncClient, project_id: str) -> dict[str, Any]:
    job = (await client.post(f"/api/v3/projects/{project_id}/reviews", json={})).json()
    return await wait_job(app, job)


async def findings(client: AsyncClient, project_id: str, **query: str) -> list[Any]:
    response = await client.get(
        f"/api/v3/projects/{project_id}/findings", params={"scope": "prd", **query}
    )
    return list(response.json()["items"])


# --- 1. projects ------------------------------------------------------------------


async def test_project_create_restore_rename_and_soft_delete(
    tmp_path: Path,
) -> None:
    path = str(tmp_path / "persist.sqlite3")
    first = create_app(
        settings=make_settings(database_path=path),
        provider=MockLLMProvider(delays_enabled=False),
    )
    async with AsyncClient(
        transport=ASGITransport(app=first), base_url="http://test"
    ) as http:
        project_id = await create(first, http)
        renamed = await http.patch(
            f"/api/v3/projects/{project_id}", json={"name": "离线云盘"}
        )
        assert renamed.json()["name"] == "离线云盘"
    first.state.project_store.close()

    second = create_app(
        settings=make_settings(database_path=path),
        provider=MockLLMProvider(delays_enabled=False),
    )
    async with AsyncClient(
        transport=ASGITransport(app=second), base_url="http://test"
    ) as http:
        restored = await http.get(f"/api/v3/projects/{project_id}")
        assert restored.status_code == 200
        assert restored.json()["name"] == "离线云盘"
        assert restored.json()["counts"]["questions"] >= 1
        conversation = await http.get(f"/api/v3/projects/{project_id}/conversation")
        assert len(conversation.json()["messages"]) == 2

        deleted = await http.delete(f"/api/v3/projects/{project_id}")
        assert deleted.status_code == 204
        for url in (
            f"/api/v3/projects/{project_id}",
            f"/api/v3/projects/{project_id}/items",
            f"/api/v3/projects/{project_id}/sections",
            f"/api/v3/projects/{project_id}/export.md",
        ):
            assert (await http.get(url)).status_code == 404
        listed = await http.get("/api/v3/projects")
        assert all(p["id"] != project_id for p in listed.json()["items"])
    second.state.project_store.close()


async def test_migration_is_repeatable_backs_up_and_keeps_v2_tables(
    tmp_path: Path,
) -> None:
    from backend.v3.store import ProjectStore, rollback_v3

    path = tmp_path / "existing.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY)")
    connection.execute("INSERT INTO runs VALUES ('old-run')")
    connection.commit()
    connection.close()

    store = ProjectStore(str(path))
    assert store.open() == [1, 2]
    store.close()
    again = ProjectStore(str(path))
    assert again.open() == []
    again.close()
    backups = list((tmp_path / "backups").glob("existing.pre-v3.*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT run_id FROM runs").fetchall() == [("old-run",)]
        assert not backup.execute(
            "SELECT name FROM sqlite_master WHERE name = 'v3_projects'"
        ).fetchall()

    with sqlite3.connect(path) as live:
        rollback_v3(live)
        assert live.execute("SELECT run_id FROM runs").fetchall() == [("old-run",)]
        assert not live.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'v3_%'"
        ).fetchall()


async def test_v2_runs_still_work_beside_v3(app: Any, client: AsyncClient) -> None:
    from uuid import UUID

    created = await client.post(
        "/api/runs", json={"user_idea": "Build a podcast micro-subscription product."}
    )
    run_id = created.json()["run_id"]
    await app.state.manager.wait_for_completion(UUID(run_id), wait_seconds=10)
    snapshot = await client.get(f"/api/runs/{run_id}")
    assert snapshot.status_code == 200
    assert snapshot.json()["versions"]
    assert (await client.get("/api/runs")).json()["total"] == 1
    project_id = await create(app, client)
    assert (await client.get(f"/api/v3/projects/{project_id}")).status_code == 200


# --- 2-4. exploration and the baseline --------------------------------------------


async def test_ai_items_are_never_confirmed_and_user_quotes_are_checked(
    app: Any, client: AsyncClient
) -> None:
    gateway(app).responses["explore"] = {
        "understanding": "记下了。",
        "items": [
            {
                "group": "position",
                "content": "一个离线下载云盘",
                "status": "confirmed",
                "source_kind": "user",
                "source_quote": "我想做一个云盘",
            },
            {
                "group": "user",
                "content": "目标用户是白领",
                "status": "rejected",
                "source_kind": "user",
                "source_quote": "目标用户是白领",
            },
            {
                "group": "open",
                "content": "是否收费",
                "status": "proposed",
                "source_kind": "ai",
            },
        ],
        "questions": [],
    }
    project_id = await create(app, client)
    stored = {i["content"]: i for i in await items(client, project_id)}

    position = stored["一个离线下载云盘"]
    assert position["status"] == "inferred"
    assert position["source_kind"] == "user"
    assert position["source_quote"] == "我想做一个云盘"
    # The user never wrote this, so it cannot be attributed to them.
    invented = stored["目标用户是白领"]
    assert invented["status"] == "inferred"
    assert invented["source_kind"] == "ai"
    assert invented["source_quote"] is None
    assert stored["是否收费"]["status"] == "open"
    assert all(i["status"] != "confirmed" for i in stored.values())

    confirmed = await client.patch(
        f"/api/v3/items/{position['id']}", json={"status": "confirmed"}
    )
    assert confirmed.json()["status"] == "confirmed"
    history = await client.get(f"/api/v3/items/{position['id']}/revisions")
    actors = [(r["actor"], r["after_status"]) for r in history.json()["items"]]
    assert actors == [("ai", "inferred"), ("user", "confirmed")]


async def test_model_cannot_rewrite_a_confirmed_item(
    app: Any, client: AsyncClient
) -> None:
    project_id = await create(app, client)
    target = (await items(client, project_id))[0]
    await client.patch(f"/api/v3/items/{target['id']}", json={"status": "confirmed"})
    gateway(app).responses["explore"] = {
        "understanding": "更新定位。",
        "items": [
            {
                "code": target["code"],
                "group": target["group"],
                "content": "完全不同的定位",
                "status": "inferred",
                "source_kind": "ai",
                "reason": "推测",
            }
        ],
        "questions": [],
    }
    job = (
        await client.post(
            f"/api/v3/projects/{project_id}/turns", json={"supplement": "补充一点"}
        )
    ).json()
    await wait_job(app, job)
    after = {i["code"]: i for i in await items(client, project_id)}
    assert after[target["code"]]["content"] == target["content"]
    assert after[target["code"]]["status"] == "confirmed"
    suggestion = next(i for i in after.values() if i["content"] == "完全不同的定位")
    assert suggestion["status"] == "inferred"
    assert suggestion["links"] == [target["code"]]


async def test_explorer_does_not_repeat_questions_and_skips_create_open_items(
    app: Any, client: AsyncClient
) -> None:
    project_id = await create(app, client)
    conversation = (
        await client.get(f"/api/v3/projects/{project_id}/conversation")
    ).json()
    first_round = [q for q in conversation["questions"] if q["state"] == "pending"]
    assert 1 <= len(first_round) <= 3
    assert all(q["purpose"] for q in first_round)

    answers = [
        {
            "question": first_round[0]["code"],
            "kind": "answer",
            "text": "大学生和刚工作的年轻人",
        },
        *[
            {"question": q["code"], "kind": "skip" if i % 2 else "unknown"}
            for i, q in enumerate(first_round[1:], start=1)
        ],
    ]
    job = (
        await client.post(
            f"/api/v3/projects/{project_id}/turns", json={"answers": answers}
        )
    ).json()
    assert (await wait_job(app, job))["status"] == "succeeded"

    conversation = (
        await client.get(f"/api/v3/projects/{project_id}/conversation")
    ).json()
    texts = [q["text"] for q in conversation["questions"]]
    assert len(texts) == len(set(texts))
    states = {q["code"]: q["state"] for q in conversation["questions"]}
    assert states[first_round[0]["code"]] == "answered"
    open_items = [i for i in await items(client, project_id) if i["group"] == "open"]
    assert len(open_items) == len(first_round) - 1

    # A confirmed group is not asked about again.
    users = [i for i in await items(client, project_id) if i["group"] == "user"]
    for item in users:
        await client.patch(f"/api/v3/items/{item['id']}", json={"status": "confirmed"})
    job = (
        await client.post(
            f"/api/v3/projects/{project_id}/turns", json={"supplement": "补充"}
        )
    ).json()
    await wait_job(app, job)
    latest = (await client.get(f"/api/v3/projects/{project_id}/conversation")).json()
    newest_round = max(q["round"] for q in latest["questions"])
    assert all(
        q["target_group"] != "user"
        for q in latest["questions"]
        if q["round"] == newest_round
    )


async def test_rejected_item_is_not_re_added(app: Any, client: AsyncClient) -> None:
    project_id = await create(app, client)
    target = next(
        i for i in await items(client, project_id) if i["group"] == "assumption"
    )
    await client.patch(f"/api/v3/items/{target['id']}", json={"status": "rejected"})
    gateway(app).responses["explore"] = {
        "understanding": "再次建议。",
        "items": [
            {
                "group": "assumption",
                "content": target["content"],
                "status": "assumption",
                "source_kind": "ai",
            }
        ],
        "questions": [],
    }
    job = (
        await client.post(
            f"/api/v3/projects/{project_id}/turns", json={"supplement": "继续"}
        )
    ).json()
    result = await wait_job(app, job)
    assert result["result"]["dropped"] == 1
    same = [
        i for i in await items(client, project_id) if i["content"] == target["content"]
    ]
    assert [i["status"] for i in same] == ["rejected"]


# --- 5. analyst and reviewer are separate -----------------------------------------


async def test_analyst_requires_item_evidence_and_is_not_a_reviewer(
    app: Any, client: AsyncClient
) -> None:
    project_id = await create(app, client)
    real_code = (await items(client, project_id))[0]["code"]
    gateway(app).responses["analyze"] = {
        "summary": "检查完毕。",
        "findings": [
            {
                "kind": "gap",
                "title": "没有证据的发现",
                "severity": "must_fix",
                "evidence_items": ["USR-99"],
                "evidence": "无",
                "problem": "编造",
                "recommendation": "无",
            },
            {
                "kind": "opportunity",
                "title": "缺少机会说明",
                "severity": "optional",
                "evidence_items": [real_code],
                "evidence": "有",
                "problem": "机会",
                "recommendation": "增加 AI 功能",
            },
            {
                "kind": "risk",
                "title": "预算风险",
                "severity": "should_fix",
                "evidence_items": [real_code],
                "evidence": "预算有限",
                "problem": "带宽成本",
                "recommendation": "设定流量上限",
            },
        ],
    }
    job = (await client.post(f"/api/v3/projects/{project_id}/analyze")).json()
    result = await wait_job(app, job)
    assert result["result"]["without_evidence"] == 2
    baseline = (
        await client.get(
            f"/api/v3/projects/{project_id}/findings", params={"scope": "baseline"}
        )
    ).json()["items"]
    assert [f["title"] for f in baseline] == ["预算风险"]
    assert baseline[0]["reviewer"] == "analyst"
    assert baseline[0]["related_items"] == [real_code]
    # The analyst ran exactly once and no PRD reviewer was called.
    calls = gateway(app).calls
    assert calls.count("analyze") == 1
    assert not any(c.startswith("review:") for c in calls)

    # Running again does not duplicate it.
    job = (await client.post(f"/api/v3/projects/{project_id}/analyze")).json()
    again = await wait_job(app, job)
    assert again["result"]["repeated"] == 1


async def test_accepted_analyst_finding_becomes_a_question(
    app: Any, client: AsyncClient
) -> None:
    project_id = await create(app, client)
    job = (await client.post(f"/api/v3/projects/{project_id}/analyze")).json()
    await wait_job(app, job)
    finding = (
        await client.get(
            f"/api/v3/projects/{project_id}/findings", params={"scope": "baseline"}
        )
    ).json()["items"][0]
    await client.patch(f"/api/v3/findings/{finding['id']}", json={"status": "accepted"})
    job = (
        await client.post(
            f"/api/v3/projects/{project_id}/turns", json={"supplement": "好"}
        )
    ).json()
    await wait_job(app, job)
    questions = (
        await client.get(f"/api/v3/projects/{project_id}/conversation")
    ).json()["questions"]
    assert any(q["finding_code"] == finding["code"] for q in questions)


# --- brief, outline, generation ---------------------------------------------------


async def test_brief_snapshot_is_frozen_and_prd_reads_only_the_confirmed_one(
    app: Any, client: AsyncClient
) -> None:
    project_id = await create(app, client)
    outline = await client.post(f"/api/v3/projects/{project_id}/outline")
    assert outline.status_code == 422
    brief = (await client.post(f"/api/v3/projects/{project_id}/briefs")).json()
    assert brief["unconfirmed_count"] > 0
    text = next(s["text"] for s in brief["sections"] if s["key"] == "position")
    assert "[AI 推断]" in text
    edited = await client.patch(
        f"/api/v3/briefs/{brief['id']}", json={"key": "position", "text": "我的定位"}
    )
    assert edited.status_code == 200
    await client.post(f"/api/v3/briefs/{brief['id']}/confirm")
    locked = await client.patch(
        f"/api/v3/briefs/{brief['id']}", json={"key": "position", "text": "改不了"}
    )
    assert locked.status_code == 409


async def test_one_failed_section_does_not_affect_others_and_retries_alone(
    app: Any, client: AsyncClient
) -> None:
    project_id = await create(app, client)
    await confirm_all(client, project_id)
    brief = (await client.post(f"/api/v3/projects/{project_id}/briefs")).json()
    await client.post(f"/api/v3/briefs/{brief['id']}/confirm")
    await wait_job(
        app, (await client.post(f"/api/v3/projects/{project_id}/outline")).json()
    )
    await client.post(f"/api/v3/projects/{project_id}/outline/confirm")
    gateway(app).fail_sections = {"异常处理"}
    job = (await client.post(f"/api/v3/projects/{project_id}/generate", json={})).json()
    result = await wait_job(app, job)
    assert result["status"] == "succeeded"
    by_title = {s["title"]: s for s in await sections(client, project_id)}
    failed = by_title["异常处理"]
    assert failed["status"] == "failed"
    assert failed["error"]
    assert all(s["status"] == "done" for t, s in by_title.items() if t != "异常处理")
    assert result["result"]["version"] is None  # incomplete documents get no version
    done_body = by_title["验收标准"]["body"]

    gateway(app).fail_sections = set()
    calls_before = len(gateway(app).calls)
    retry = (
        await client.post(
            f"/api/v3/projects/{project_id}/generate",
            json={"sections": [failed["code"]]},
        )
    ).json()
    retried = await wait_job(app, retry)
    assert retried["result"]["done"] == [failed["code"]]
    assert len(gateway(app).calls) - calls_before == 1
    by_title = {s["title"]: s for s in await sections(client, project_id)}
    assert by_title["异常处理"]["status"] == "done"
    assert by_title["验收标准"]["body"] == done_body
    assert retried["result"]["version"] == 1


async def test_outline_edit_add_delete_reorder(app: Any, client: AsyncClient) -> None:
    project_id = await create(app, client)
    await confirm_all(client, project_id)
    brief = (await client.post(f"/api/v3/projects/{project_id}/briefs")).json()
    await client.post(f"/api/v3/briefs/{brief['id']}/confirm")
    await wait_job(
        app, (await client.post(f"/api/v3/projects/{project_id}/outline")).json()
    )
    current = await sections(client, project_id)
    added = (
        await client.post(
            f"/api/v3/projects/{project_id}/sections",
            json={"title": "数据埋点", "after": current[0]["code"], "level": 1},
        )
    ).json()
    current = await sections(client, project_id)
    assert current[1]["code"] == added["code"] and current[1]["num"] == "2"
    renamed = await client.patch(
        f"/api/v3/sections/{added['id']}",
        json={"row_version": added["row_version"], "title": "埋点与指标"},
    )
    assert renamed.json()["section"]["title"] == "埋点与指标"
    order = [{"code": s["code"], "level": s["level"]} for s in current]
    order.append(order.pop(1))
    reordered = (
        await client.put(
            f"/api/v3/projects/{project_id}/sections/order", json={"order": order}
        )
    ).json()["items"]
    assert reordered[-1]["code"] == added["code"]
    victim = reordered[-1]
    removed = await client.delete(
        f"/api/v3/sections/{victim['id']}",
        params={"row_version": victim["row_version"]},
    )
    assert removed.status_code == 204
    assert all(s["code"] != added["code"] for s in await sections(client, project_id))


# --- 6-10. reviewers and the aggregator -------------------------------------------


async def test_four_reviewers_run_independently_and_aggregate(
    app: Any, client: AsyncClient
) -> None:
    project_id = await to_document(app, client)
    result = await review(app, client, project_id)
    assert result["status"] == "succeeded"
    calls = [c for c in gateway(app).calls if c.startswith("review:")]
    assert sorted(calls) == ["review:biz", "review:product", "review:tech", "review:ux"]

    results = (await client.get(f"/api/v3/projects/{project_id}/reviews")).json()[
        "items"
    ]
    assert [r["reviewer"] for r in results] == ["product", "ux", "tech", "biz"]
    for item in results:
        assert item["score"] is not None  # computed by code from dimensions
        assert item["rubric_version"]
    biz = next(r for r in results if r["reviewer"] == "biz")
    assert biz["finding_codes"] == []  # zero findings is allowed

    stored = await findings(client, project_id)
    titles = sorted(f["title"] for f in stored)
    # Tech and UX raised the same timeout problem: merged into one finding.
    timeout = [f for f in stored if "超时" in f["title"]]
    assert len(timeout) == 1
    assert sorted(timeout[0]["reviewers"]) == ["tech", "ux"]
    # Tech's out-of-domain business finding was dropped.
    assert "收费模式不清楚" not in titles
    for finding in stored:
        assert finding["evidence"]
        assert finding["evidence_verified"] is True
        assert finding["related_sections"]
    tech = next(r for r in results if r["reviewer"] == "tech")
    assert tech["filtered_findings"] == 1

    only_ux = await findings(client, project_id, reviewer="ux")
    assert [f["code"] for f in only_ux] == [timeout[0]["code"]]
    blockers = await findings(client, project_id, severity="must_fix")
    assert [f["title"] for f in blockers] == ["验收标准无法测试"]


async def test_finding_without_real_evidence_is_rejected_or_marked(
    app: Any, client: AsyncClient
) -> None:
    project_id = await to_document(app, client)
    target = (await sections(client, project_id))[0]
    gateway(app).responses["review:product"] = {
        "reviewer": "product",
        "summary": "检查完毕。",
        "dimension_scores": [
            {"dimension": d, "score": 4, "rationale": "ok"}
            for d in (
                "problem_fit",
                "solution_soundness",
                "completeness_consistency",
                "scope_priority",
            )
        ],
        "findings": [
            {
                "title": "无证据",
                "severity": "must_fix",
                "category": "requirement_gap",
                "section": target["num"],
                "evidence": "",
                "problem": "空",
                "recommendation": "无",
            },
            {
                "title": "引用不存在",
                "severity": "must_fix",
                "category": "requirement_gap",
                "section": target["num"],
                "evidence": "「文档里根本没有这句话」",
                "problem": "编造的引用",
                "recommendation": "无",
            },
        ],
    }
    await review(app, client, project_id)
    stored = {
        f["title"]: f for f in await findings(client, project_id, reviewer="product")
    }
    assert "无证据" not in stored
    fake = stored["引用不存在"]
    assert fake["evidence_verified"] is False
    assert fake["severity"] == "should_fix"  # unverifiable evidence may not block


async def test_rejected_finding_is_not_raised_again_and_ids_are_stable(
    app: Any, client: AsyncClient
) -> None:
    project_id = await to_document(app, client)
    await review(app, client, project_id)
    first = {f["title"]: f for f in await findings(client, project_id)}
    blocker = first["验收标准无法测试"]
    response = await client.patch(
        f"/api/v3/findings/{blocker['id']}",
        json={"status": "rejected", "note": "不认同"},
    )
    assert response.json()["status"] == "rejected"

    await review(app, client, project_id)
    second = await findings(client, project_id)
    assert len(second) == len(first)
    by_code = {f["code"]: f for f in second}
    assert by_code[blocker["code"]]["status"] == "rejected"
    for title, finding in first.items():
        assert by_code[finding["code"]]["title"] == title
    product = next(
        r
        for r in (await client.get(f"/api/v3/projects/{project_id}/reviews")).json()[
            "items"
        ]
        if r["reviewer"] == "product"
    )
    assert blocker["code"] not in product["finding_codes"]
    history = (await client.get(f"/api/v3/findings/{blocker['id']}/history")).json()
    assert [e["to_status"] for e in history["items"]] == ["open", "rejected"]


async def test_user_cannot_set_system_statuses(app: Any, client: AsyncClient) -> None:
    project_id = await to_document(app, client)
    await review(app, client, project_id)
    finding = (await findings(client, project_id))[0]
    for status in ("resolved", "stale"):
        response = await client.patch(
            f"/api/v3/findings/{finding['id']}", json={"status": status}
        )
        assert response.status_code == 422
    missing_note = await client.patch(
        f"/api/v3/findings/{finding['id']}", json={"status": "modified"}
    )
    assert missing_note.status_code == 422


async def test_one_reviewer_failing_keeps_the_others(
    app: Any, client: AsyncClient
) -> None:
    project_id = await to_document(app, client)
    gateway(app).fail_tasks = {"review:biz"}
    result = await review(app, client, project_id)
    assert result["status"] == "succeeded"
    assert result["result"]["failed_reviewers"] == ["biz"]
    reviewers = [
        r["reviewer"]
        for r in (await client.get(f"/api/v3/projects/{project_id}/reviews")).json()[
            "items"
        ]
    ]
    assert reviewers == ["product", "ux", "tech"]


# --- 11-16. optimisation, edits, impact, versions ---------------------------------


async def accept(
    client: AsyncClient, finding: dict[str, Any], note: str | None = None
) -> None:
    body: dict[str, Any] = {"status": "modified" if note else "accepted"}
    if note:
        body["note"] = note
    response = await client.patch(f"/api/v3/findings/{finding['id']}", json=body)
    assert response.status_code == 200


async def optimize(app: Any, client: AsyncClient, project_id: str) -> dict[str, Any]:
    response = await client.post(f"/api/v3/projects/{project_id}/optimize")
    assert response.status_code == 202, response.text
    await wait_job(app, response.json())
    proposals = (await client.get(f"/api/v3/projects/{project_id}/proposals")).json()
    return dict(proposals["items"][0])


async def test_only_accepted_findings_reach_the_optimizer(
    app: Any, client: AsyncClient
) -> None:
    project_id = await to_document(app, client)
    await review(app, client, project_id)
    nothing = await client.post(f"/api/v3/projects/{project_id}/optimize")
    assert nothing.status_code == 422
    stored = {f["title"]: f for f in await findings(client, project_id)}
    chosen = stored["验收标准无法测试"]
    await accept(client, chosen, note="每条写出输入和结果")
    seen: list[list[str]] = []
    original = gateway(app)._optimize

    def spy(payload: dict[str, Any]) -> dict[str, Any]:
        seen.append([f["finding_code"] for f in payload["findings"]])
        assert payload["findings"][0]["user_note"] == "每条写出输入和结果"
        return original(payload)

    gateway(app).responses["optimize"] = spy
    proposal = await optimize(app, client, project_id)
    assert seen == [[chosen["code"]]]
    assert proposal["status"] == "pending"
    assert all(c["finding_codes"] == [chosen["code"]] for c in proposal["changes"])
    # A proposal changes nothing until the user applies it.
    body = next(
        s for s in await sections(client, project_id) if s["title"] == "验收标准"
    )
    assert "核心流程可以完成" in body["body"]


async def test_apply_proposal_versions_and_rechecks(
    app: Any, client: AsyncClient
) -> None:
    project_id = await to_document(app, client)
    await review(app, client, project_id)
    chosen = next(
        f
        for f in await findings(client, project_id)
        if f["title"] == "验收标准无法测试"
    )
    await accept(client, chosen)
    proposal = await optimize(app, client, project_id)
    change = proposal["changes"][0]
    assert change["before"] and change["after"] and change["reason"]
    applied = (
        await client.post(f"/api/v3/proposals/{proposal['id']}/apply", json={})
    ).json()
    assert applied["conflicts"] == []
    assert applied["findings"] == [chosen["code"]]
    assert applied["version"] == 2
    target = next(
        s for s in await sections(client, project_id) if s["title"] == "验收标准"
    )
    assert "核心流程可以完成" not in target["body"]
    assert target["origin"] == "optimized"
    assert target["needs_recheck"] is True
    finding = next(
        f for f in await findings(client, project_id) if f["id"] == chosen["id"]
    )
    assert finding["status"] == "resolved"

    # The scoped recheck verifies the fix without reopening it.
    job = (
        await client.post(
            f"/api/v3/projects/{project_id}/reviews",
            json={"sections": [target["code"]]},
        )
    ).json()
    await wait_job(app, job)
    finding = next(
        f for f in await findings(client, project_id) if f["id"] == chosen["id"]
    )
    assert finding["status"] == "resolved"
    assert finding["verification"] == "resolved"
    target = next(
        s for s in await sections(client, project_id) if s["title"] == "验收标准"
    )
    assert target["needs_recheck"] is False
    versions = (await client.get(f"/api/v3/projects/{project_id}/versions")).json()[
        "items"
    ]
    assert [v["number"] for v in versions] == [2, 1]
    assert versions[0]["finding_codes"] == [chosen["code"]]


async def test_optimizer_never_overwrites_human_sections(
    app: Any, client: AsyncClient
) -> None:
    project_id = await to_document(app, client)
    await review(app, client, project_id)
    chosen = next(
        f
        for f in await findings(client, project_id)
        if f["title"] == "验收标准无法测试"
    )
    await accept(client, chosen)
    proposal = await optimize(app, client, project_id)
    target = next(
        s for s in await sections(client, project_id) if s["title"] == "验收标准"
    )
    # The user edits the section after the proposal was made.
    saved = await client.patch(
        f"/api/v3/sections/{target['id']}",
        json={
            "row_version": target["row_version"],
            "body": target["body"] + "\n4. 我自己加的验收标准。",
        },
    )
    assert saved.json()["section"]["origin"] == "human"
    applied = (
        await client.post(f"/api/v3/proposals/{proposal['id']}/apply", json={})
    ).json()
    assert applied["applied"] == []
    assert applied["conflicts"] == [proposal["changes"][0]["id"]]
    after = next(
        s for s in await sections(client, project_id) if s["id"] == target["id"]
    )
    assert "我自己加的验收标准" in after["body"]

    # The edit made the finding stale; the user accepts it again, and the new
    # proposal is marked as touching a human section.
    stale = next(
        f for f in await findings(client, project_id) if f["id"] == chosen["id"]
    )
    assert stale["status"] == "stale"
    await accept(client, stale)
    again = await optimize(app, client, project_id)
    assert again["changes"][0]["human_section"] is True
    await client.post(f"/api/v3/proposals/{again['id']}/apply", json={})
    after = next(
        s for s in await sections(client, project_id) if s["id"] == target["id"]
    )
    assert after["origin"] == "human"


async def test_optimistic_lock_returns_409(app: Any, client: AsyncClient) -> None:
    project_id = await to_document(app, client)
    target = (await sections(client, project_id))[0]
    url = f"/api/v3/sections/{target['id']}"
    first = await client.patch(
        url, json={"row_version": target["row_version"], "body": "A 版本"}
    )
    assert first.status_code == 200
    second = await client.patch(
        url, json={"row_version": target["row_version"], "body": "B 版本"}
    )
    assert second.status_code == 409
    current = next(
        s for s in await sections(client, project_id) if s["id"] == target["id"]
    )
    assert current["body"] == "A 版本"


async def test_edit_marks_findings_stale_but_formatting_does_not(
    app: Any, client: AsyncClient
) -> None:
    project_id = await to_document(app, client)
    await review(app, client, project_id)
    timeout = next(
        f for f in await findings(client, project_id) if "超时" in f["title"]
    )
    target = next(
        s
        for s in await sections(client, project_id)
        if timeout["related_sections"][0] == s["code"]
    )
    calls = len(gateway(app).calls)

    formatted = await client.patch(
        f"/api/v3/sections/{target['id']}",
        json={
            "row_version": target["row_version"],
            "body": target["body"].replace("- ", "* ") + "\n",
        },
    )
    impact = formatted.json()["impact"]
    assert impact == {"change": "format", "sections": [], "stale": []}
    assert formatted.json()["section"]["origin"] == "ai"
    still = next(
        f for f in await findings(client, project_id) if f["id"] == timeout["id"]
    )
    assert still["status"] == "open"

    section = formatted.json()["section"]
    edited = await client.patch(
        f"/api/v3/sections/{section['id']}",
        json={
            "row_version": section["row_version"],
            "body": section["body"].replace("长时间没有响应", "超过 30 分钟没有进度"),
        },
    )
    impact = edited.json()["impact"]
    assert impact["change"] == "rule"
    assert timeout["code"] in impact["stale"]
    assert impact["sections"]  # acceptance criteria depend on exception handling
    acceptance = next(
        s for s in await sections(client, project_id) if s["title"] == "验收标准"
    )
    assert acceptance["needs_recheck"] is True
    stale = next(
        f for f in await findings(client, project_id) if f["id"] == timeout["id"]
    )
    assert stale["status"] == "stale"
    # Saving never calls a model.
    assert len(gateway(app).calls) == calls


async def test_versions_are_append_only(app: Any, client: AsyncClient) -> None:
    project_id = await to_document(app, client)
    v1 = (await client.get(f"/api/v3/projects/{project_id}/versions/1")).json()
    target = (await sections(client, project_id))[0]
    await client.patch(
        f"/api/v3/sections/{target['id']}",
        json={"row_version": target["row_version"], "body": "全新的概述内容。"},
    )
    saved = await client.post(
        f"/api/v3/projects/{project_id}/versions", json={"note": "改了概述"}
    )
    assert saved.json()["number"] == 2
    assert saved.json()["section_codes"] == [target["code"]]
    assert saved.json()["actor"] == "你"
    again = (await client.get(f"/api/v3/projects/{project_id}/versions/1")).json()
    assert again == v1
    diff = (
        await client.get(f"/api/v3/projects/{project_id}/versions/1/diff/2")
    ).json()["sections"]
    assert [d["code"] for d in diff] == [target["code"]]
    assert {"kind": "add", "text": "全新的概述内容。"} in diff[0]["lines"]
    store = app.state.project_store
    with pytest.raises(sqlite3.IntegrityError):
        from backend.v3.models import PRDVersion

        store.insert(PRDVersion.model_validate({**v1, "id": "dup"}))


async def test_export_strips_internal_markers(app: Any, client: AsyncClient) -> None:
    project_id = await to_document(app, client)
    target = (await sections(client, project_id))[0]
    await client.patch(
        f"/api/v3/sections/{target['id']}",
        json={
            "row_version": target["row_version"],
            "body": "[[FD-01|离线下载]]是核心（USR-01、PRB-01）。<!-- PRD_COMPLETE -->",
        },
    )
    text = (await client.get(f"/api/v3/projects/{project_id}/export.md")).text
    assert text.startswith("# ")
    assert "离线下载是核心。" in text
    for marker in ("[[", "USR-01", "PRD_COMPLETE", "FD-01"):
        assert marker not in text
    assert "## 1 " in text


async def test_quality_has_four_separate_views(app: Any, client: AsyncClient) -> None:
    project_id = await create(app, client)
    early = (await client.get(f"/api/v3/projects/{project_id}/quality")).json()
    assert early["document_quality"]["value"] is None
    assert early["risks"]["value"] is None
    project_id = await to_document(app, client)
    await review(app, client, project_id)
    quality = (await client.get(f"/api/v3/projects/{project_id}/quality")).json()
    assert set(quality) == {
        "document_quality",
        "requirement_maturity",
        "implementation_readiness",
        "risks",
    }
    maturity = quality["requirement_maturity"]
    # The mock idea never names a scenario, so that core group stays empty.
    assert maturity["missing_core"] == ["使用场景"]
    assert maturity["value"] == 88  # 50 × 3/4 + 50 × 1
    assert quality["risks"]["blocking"] == 1
    assert "overall" not in str(quality)


# --- 17. jobs and SSE -------------------------------------------------------------


async def test_job_events_replay_after_disconnect(
    app: Any, client: AsyncClient
) -> None:
    project_id = await to_document(app, client)
    jobs = (await client.get(f"/api/v3/projects/{project_id}/jobs")).json()["items"]
    generate = next(j for j in jobs if j["kind"] == "generate")
    manager = app.state.jobs
    all_events = [
        e async for e in manager.subscribe(generate["id"], 0) if e is not None
    ]
    names = [e.event for e in all_events]
    assert names[0] == "job_started" and names[-1] == "job_succeeded"
    middle = all_events[len(all_events) // 2].sequence
    resumed = [
        e async for e in manager.subscribe(generate["id"], middle) if e is not None
    ]
    assert resumed and all(e.sequence > middle for e in resumed)
    assert resumed[-1].event == "job_succeeded"

    # Replay from the database once the in-memory buffer is gone (a restart).
    manager._buffers.pop(generate["id"], None)
    durable = manager.replay(generate["id"], 0)
    assert [e.event for e in durable if e.event == "section_done"]
    assert all(e.event != "section_delta" for e in durable)

    response = await client.get(
        f"/api/v3/jobs/{generate['id']}/events", headers={"Last-Event-ID": str(middle)}
    )
    assert response.status_code == 200
    assert "event: job_succeeded" in response.text
    assert f"id: {middle}\n" not in response.text


async def test_one_ai_task_per_project_and_restart_marks_jobs_failed(
    app: Any, client: AsyncClient, tmp_path: Path
) -> None:
    gateway(app).delay = 0.2
    response = await client.post("/api/v3/projects", json={"text": IDEA})
    project_id = response.json()["project"]["id"]
    busy = await client.post(f"/api/v3/projects/{project_id}/analyze")
    assert busy.status_code == 409
    await wait_job(app, response.json()["job"])

    from backend.v3.jobs import JobManager
    from backend.v3.models import Job, JobKind, JobStatus, now

    store = app.state.project_store
    store.insert(
        Job(
            id="orphan",
            project_id=project_id,
            kind=JobKind.REVIEW,
            status=JobStatus.RUNNING,
            trace_id="t",
            created_at=now(),
        )
    )
    restarted = JobManager(
        store=store, gateway=gateway(app), settings=app.state.settings
    )
    assert restarted.recover_interrupted() == ["orphan"]
    orphan = (await client.get("/api/v3/jobs/orphan")).json()
    assert orphan["status"] == "failed"
    assert orphan["error"]["code"] == "JOB_INTERRUPTED"
    await asyncio.sleep(0)


async def test_review_entry_imports_a_pasted_prd(app: Any, client: AsyncClient) -> None:
    text = (
        "# 打卡小程序\n\n## 1. 概述\n帮助用户养成习惯。\n\n"
        "## 2. 功能\n### 2.1 打卡\n每天打卡一次。"
    )
    response = await client.post(
        "/api/v3/projects", json={"text": text, "entry_mode": "review"}
    )
    assert response.json()["job"] is None
    project_id = response.json()["project"]["id"]
    imported = await sections(client, project_id)
    assert [(s["num"], s["title"]) for s in imported] == [
        ("1", "概述"),
        ("2", "功能"),
        ("2.1", "打卡"),
    ]
    assert all(s["origin"] == "human" for s in imported)
    result = await review(app, client, project_id)
    assert result["status"] == "succeeded"
