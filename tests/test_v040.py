from tests.test_lists import _gift, _occasion, _recipient


def test_reorder_counts_as_spent_and_is_listed(api):
    oid = _occasion(api)["id"]
    rec = _recipient(api, budget_pence=10000)
    g = _gift(api, rec["id"], price_pence=3000, status="ordered", notes="Arrived smashed")
    _gift(api, rec["id"], description="Fine", price_pence=1000, status="delivered")
    assert api.patch(f"/api/gifts/{g['id']}", json={"status": "reorder"}).json()["gift"]["status"] == "reorder"
    t = api.get(f"/api/recipients/{rec['id']}").json()["recipient"]["totals"]
    assert t["spent_pence"] == 4000 and t["counts"]["reorder"] == 1
    o = api.get(f"/api/occasions/{oid}/overview").json()
    assert [x["description"] for x in o["needs_reorder"]] == ["Lego set"]
    assert o["awaiting_delivery"] == [] and o["totals"]["counts"]["delivered"] == 1
    # Problems sort before the rest of the list.
    assert [x["status"] for x in api.get(f"/api/recipients/{rec['id']}").json()["recipient"]["gifts"]] == [
        "reorder", "delivered"]  # fmt: skip


def test_bulk_gifts_status_move_delete(api, second):
    src = _occasion(api)
    rec = _recipient(api)
    a, b, c = (_gift(api, rec["id"], description=d) for d in ("A", "B", "C"))
    r = api.post("/api/gifts/bulk", json={"ids": [a["id"], b["id"]], "action": "status", "status": "ordered"})
    assert r.json()["count"] == 2
    statuses = {
        g["description"]: g["status"] for g in api.get(f"/api/recipients/{rec['id']}").json()["recipient"]["gifts"]
    }
    assert statuses == {"A": "ordered", "B": "ordered", "C": "idea"}

    # Move to an occasion Molly isn't in yet: her entry is created there.
    bday = api.post("/api/occasions", json={"kind": "birthday", "name": "Molly's birthday"}).json()["occasion"]
    api.post("/api/gifts/bulk", json={"ids": [a["id"], c["id"]], "action": "move", "occasion_id": bday["id"]})
    o = api.get(f"/api/occasions/{bday['id']}/overview").json()
    moved = o["groups"][0]["recipients"][0]
    assert moved["person_id"] == rec["person_id"] and sorted(g["description"] for g in moved["gifts"]) == ["A", "C"]
    assert [g["description"] for g in api.get(f"/api/recipients/{rec['id']}").json()["recipient"]["gifts"]] == ["B"]

    # All or nothing: one gift you can't see makes the whole request fail.
    sams = second.post("/api/occasions", json={"name": "Sam's"}).json()["occasion"]
    sr = second.post(f"/api/occasions/{sams['id']}/recipients", json={"name": "Pat"}).json()["recipient"]
    sg = _gift(second, sr["id"])
    assert api.post("/api/gifts/bulk", json={"ids": [b["id"], sg["id"]], "action": "delete"}).status_code == 404
    assert len(api.get(f"/api/recipients/{rec['id']}").json()["recipient"]["gifts"]) == 1

    # Archived occasions are read-only, as source or target.
    api.post(f"/api/occasions/{bday['id']}/archive")
    assert (
        api.post("/api/gifts/bulk", json={"ids": [b["id"]], "action": "move", "occasion_id": bday["id"]}).status_code
        == 409
    )
    assert api.post("/api/gifts/bulk", json={"ids": [a["id"]], "action": "delete"}).status_code == 409
    api.post(f"/api/occasions/{bday['id']}/unarchive")

    assert api.post("/api/gifts/bulk", json={"ids": [b["id"]], "action": "status", "status": "lost"}).status_code == 422
    assert api.post("/api/gifts/bulk", json={"ids": [b["id"]], "action": "explode"}).status_code == 422
    assert api.post("/api/gifts/bulk", json={"ids": [b["id"]], "action": "delete"}).json()["count"] == 1
    assert src  # source occasion untouched otherwise


def test_bulk_move_by_sharer_needs_existing_entry(api, second):
    sam_id = next(u["id"] for u in api.get("/api/users/directory").json()["users"] if u["username"] == "sam")
    rec = _recipient(api, share_user_ids=[sam_id])
    g = _gift(api, rec["id"])
    mine = second.post("/api/occasions", json={"name": "Sam's list"}).json()["occasion"]
    r = second.post("/api/gifts/bulk", json={"ids": [g["id"]], "action": "move", "occasion_id": mine["id"]})
    assert r.status_code == 403


def test_bulk_wishes(api, second):
    xmas = _occasion(api)
    ids = [api.post("/api/wishes", json={"description": d}).json()["wish"]["id"] for d in ("A", "B", "C")]
    api.post("/api/wishes/bulk", json={"ids": ids[:2], "action": "move", "occasion_id": xmas["id"]})
    api.post("/api/wishes/bulk", json={"ids": ids[1:], "action": "archive"})
    w = {x["description"]: x for x in api.get("/api/wishes").json()["wishes"]}
    assert (w["A"]["occasion"]["id"], w["A"]["archived"], w["B"]["archived"], w["C"]["occasion"]) == (
        xmas["id"],
        False,
        True,
        None,
    )
    api.post("/api/wishes/bulk", json={"ids": ids, "action": "restore"})
    api.post("/api/wishes/bulk", json={"ids": ids, "action": "move", "occasion_id": None})
    assert all(x["occasion"] is None and not x["archived"] for x in api.get("/api/wishes").json()["wishes"])
    assert second.post("/api/wishes/bulk", json={"ids": ids[:1], "action": "delete"}).status_code == 404
    assert api.post("/api/wishes/bulk", json={"ids": ids, "action": "delete"}).json()["count"] == 3
    assert api.get("/api/wishes").json()["wishes"] == []
