def _occasion(api, name=None):
    occs = api.get("/api/occasions").json()["occasions"]
    if name:
        return next(o for o in occs if o["name"] == name)
    return occs[0]


def _recipient(api, occasion_id=None, **kw):
    oid = occasion_id or _occasion(api)["id"]
    r = api.post(f"/api/occasions/{oid}/recipients", json={"name": "Molly", "budget_pence": 30000, **kw})
    assert r.status_code == 201, r.text
    return r.json()["recipient"]


def _gift(api, rid, **kw):
    r = api.post(f"/api/recipients/{rid}/gifts", json={"description": "Lego set", **kw})
    assert r.status_code == 201, r.text
    return r.json()["gift"]


def test_fresh_install_has_this_years_christmas(api):
    occs = api.get("/api/occasions").json()["occasions"]
    assert len(occs) == 1 and occs[0]["kind"] == "christmas" and occs[0]["can_manage"] is True


def test_budget_tally(api):
    rec = _recipient(api)
    _gift(api, rec["id"], price_pence=12000, status="ordered")
    _gift(api, rec["id"], price_pence=4000, quantity=2, status="wrapped")
    g = _gift(api, rec["id"], price_pence=10000, my_share_pence=5000, status="delivered")
    assert g["cost_pence"] == 5000 and g["line_total_pence"] == 10000
    _gift(api, rec["id"], description="Maybe a scarf", price_pence=9000)  # idea

    t = api.get(f"/api/recipients/{rec['id']}").json()["recipient"]["totals"]
    assert (t["spent_pence"], t["planned_pence"], t["remaining_pence"]) == (25000, 34000, 5000)
    assert t["state"] == "under" and t["planned_state"] == "over"

    _gift(api, rec["id"], price_pence=4600, status="ordered")
    t = api.get(f"/api/recipients/{rec['id']}").json()["recipient"]["totals"]
    assert t["spent_pence"] == 29600 and t["state"] == "on"

    api.put("/api/settings", json={"budget_margin_pence": 0})
    assert api.get(f"/api/recipients/{rec['id']}").json()["recipient"]["totals"]["state"] == "under"


def test_gift_defaults_and_validation(api):
    rec = _recipient(api)
    g = _gift(api, rec["id"], link="www.example.com/thing")
    assert g["status"] == "idea" and g["priority"] == 2 and g["quantity"] == 1
    assert g["buyer"]["name"] == "admin"
    assert g["link"] == "https://www.example.com/thing"
    rid = rec["id"]
    for bad in ({"description": "  "}, {"description": "x", "link": "javascript:alert(1)"},
                {"description": "x", "price_pence": -1}, {"description": "x", "status": "lost"}):  # fmt: skip
        assert api.post(f"/api/recipients/{rid}/gifts", json=bad).status_code == 422

    r = api.patch(f"/api/gifts/{g['id']}", json={
        "status": "ordered", "retailer": "Argos", "tracking_number": "TRK123",
        "delivery_date": "2026-12-10", "hiding_place": "Loft", "priority": 1, "link": "",
    })  # fmt: skip
    g = r.json()["gift"]
    assert (g["status"], g["retailer"], g["delivery_date"], g["hiding_place"], g["priority"], g["link"]) == (
        "ordered",
        "Argos",
        "2026-12-10",
        "Loft",
        1,
        None,
    )
    assert api.delete(f"/api/gifts/{g['id']}").status_code == 200
    assert api.patch(f"/api/gifts/{g['id']}", json={"status": "wrapped"}).status_code == 404


def test_overview_lists_and_groups(api):
    oid = _occasion(api)["id"]
    cat = api.post("/api/categories", json={"name": "Kids"}).json()["category"]
    molly = _recipient(api, category_id=cat["id"])
    dad = _recipient(api, name="Dad", budget_pence=None)
    _gift(api, molly["id"], description="Low prio", priority=3)
    _gift(api, dad["id"], description="High prio", priority=1)
    _gift(api, molly["id"], description="Late", status="ordered", delivery_date="2026-12-20")
    _gift(api, dad["id"], description="Soon", status="ordered", delivery_date="2026-12-01")
    _gift(api, dad["id"], description="Undated", status="ordered")

    o = api.get(f"/api/occasions/{oid}/overview").json()
    assert [g["category"]["name"] if g["category"] else None for g in o["groups"]] == ["Kids", None]
    assert [x["description"] for x in o["to_order"]] == ["High prio", "Low prio"]
    assert [x["description"] for x in o["awaiting_delivery"]] == ["Soon", "Late", "Undated"]
    assert o["totals"]["budget_pence"] == 30000
    assert o["delete_impact"] == {"recipients": 2, "gifts": 5, "my_wishes": 0}

    api.delete(f"/api/categories/{cat['id']}")
    o = api.get(f"/api/occasions/{oid}/overview").json()
    assert len(o["groups"]) == 1 and o["groups"][0]["category"] is None


def test_people_are_linked_across_occasions(api):
    xmas = _occasion(api)
    rec = _recipient(api, notes="Size 7-8")
    pid = rec["person_id"]
    bday = api.post("/api/occasions", json={"kind": "birthday", "name": "Molly's birthday 2027",
                                            "date": "2027-03-14", "person_ids": [pid]}).json()["occasion"]  # fmt: skip
    b = api.get(f"/api/occasions/{bday['id']}/overview").json()
    b_rec = b["groups"][0]["recipients"][0]
    assert b_rec["person_id"] == pid and b_rec["notes"] == "Size 7-8"
    assert b_rec["budget_pence"] is None  # no copy source: a fresh budget

    # Editing notes in one occasion shows everywhere; budgets stay per occasion.
    api.patch(f"/api/recipients/{b_rec['id']}", json={"notes": "Size 9", "budget_pence": 5000})
    x_rec = api.get(f"/api/recipients/{rec['id']}").json()["recipient"]
    assert x_rec["notes"] == "Size 9" and x_rec["budget_pence"] == 30000

    people = api.get("/api/people").json()["people"]
    assert len(people) == 1
    assert {e["occasion"]["name"] for e in people[0]["entries"]} == {xmas["name"], "Molly's birthday 2027"}

    # Can't add the same person twice, can't delete a person who's still in occasions.
    assert api.post(f"/api/occasions/{bday['id']}/recipients", json={"person_id": pid}).status_code == 409
    assert api.delete(f"/api/people/{pid}").status_code == 409
    api.delete(f"/api/recipients/{b_rec['id']}")
    api.delete(f"/api/recipients/{rec['id']}")
    assert api.get("/api/people").json()["people"][0]["entries"] == []
    assert api.delete(f"/api/people/{pid}").status_code == 200


def test_legacy_columns_are_mirrored(api):
    """v0.1.0's recipients.name/notes/category_id keep matching the person."""
    from sqlalchemy import text

    from app.db import engine

    cat = api.post("/api/categories", json={"name": "Kids"}).json()["category"]
    rec = _recipient(api, notes="old")
    api.patch(f"/api/people/{rec['person_id']}", json={"name": "Molly B", "notes": "new", "category_id": cat["id"]})
    with engine.connect() as c:
        row = c.execute(text("SELECT name, notes, category_id FROM recipients WHERE id = :i"), {"i": rec["id"]}).one()
    assert tuple(row) == ("Molly B", "new", cat["id"])


def test_new_occasion_copy_options(api, second):
    src = _occasion(api)
    sam_id = next(u["id"] for u in api.get("/api/users/directory").json()["users"] if u["username"] == "sam")
    molly = _recipient(api, share_user_ids=[sam_id])
    dad = _recipient(api, name="Dad", budget_pence=5000)
    _gift(
        api, molly["id"], price_pence=5000, status="wrapped", tracking_number="X1", hiding_place="Loft", buyer_id=sam_id
    )
    # The source occasion stays active: creating never archives.
    body = {"kind": "christmas", "name": "Christmas 2027", "copy_from_id": src["id"],
            "person_ids": [molly["person_id"], dad["person_id"]]}  # fmt: skip

    full = api.post("/api/occasions", json={**body, "copy_gifts": True}).json()["occasion"]
    o = api.get(f"/api/occasions/{full['id']}/overview").json()
    recs = {r["name"]: r for g in o["groups"] for r in g["recipients"]}
    assert recs["Molly"]["budget_pence"] == 30000 and [p["name"] for p in recs["Molly"]["shared_with"]] == ["sam"]
    g = recs["Molly"]["gifts"][0]
    assert (g["status"], g["tracking_number"], g["hiding_place"], g["price_pence"]) == ("idea", None, None, 5000)
    assert g["buyer"]["name"] == "sam"

    bare = api.post(
        "/api/occasions", json={**body, "name": "Bare", "copy_budgets": False, "copy_sharing": False}
    ).json()
    o = api.get(f"/api/occasions/{bare['occasion']['id']}/overview").json()
    recs = {r["name"]: r for g in o["groups"] for r in g["recipients"]}
    assert recs["Molly"]["budget_pence"] is None and recs["Molly"]["shared_with"] == [] and recs["Molly"]["gifts"] == []

    actives = [x for x in api.get("/api/occasions").json()["occasions"] if not x["is_archived"]]
    assert len(actives) == 3

    # Only your own people can be added.
    sams = second.post("/api/people", json={"name": "Sam's mum"}).json()["person"]
    assert api.post("/api/occasions", json={"name": "x", "person_ids": [sams["id"]]}).status_code == 422


def test_occasion_privacy(api, second):
    """An occasion is visible to its creator and to people who can see someone in it."""
    mine = api.post("/api/occasions", json={"kind": "birthday", "name": "Ashley's birthday"}).json()["occasion"]
    assert all(o["name"] != "Ashley's birthday" for o in second.get("/api/occasions").json()["occasions"])
    assert second.get(f"/api/occasions/{mine['id']}/overview").status_code == 404

    theirs = second.post("/api/occasions", json={"kind": "birthday", "name": "Surprise for admin"}).json()["occasion"]
    assert api.get(f"/api/occasions/{theirs['id']}/overview").status_code == 404  # admins get no special access

    sam_id = next(u["id"] for u in api.get("/api/users/directory").json()["users"] if u["username"] == "sam")
    rec = _recipient(api, occasion_id=mine["id"], share_user_ids=[sam_id])
    assert any(o["name"] == "Ashley's birthday" for o in second.get("/api/occasions").json()["occasions"])
    shared = second.get(f"/api/recipients/{rec['id']}").json()
    assert shared["recipient"]["is_owner"] is False and shared["occasion"]["can_manage"] is False
    # Sharers can work on gifts and budget, not the person's details, sharing or the occasion itself.
    gift = _gift(api, rec["id"])
    assert second.patch(f"/api/gifts/{gift['id']}", json={"buyer_id": sam_id}).status_code == 200
    assert second.patch(f"/api/recipients/{rec['id']}", json={"budget_pence": 100}).status_code == 200
    assert second.patch(f"/api/recipients/{rec['id']}", json={"notes": "x"}).status_code == 403
    assert second.put(f"/api/recipients/{rec['id']}/shares", json={"user_ids": []}).status_code == 403
    assert second.delete(f"/api/recipients/{rec['id']}").status_code == 403
    for call in (lambda: second.post(f"/api/occasions/{mine['id']}/archive"),
                 lambda: second.patch(f"/api/occasions/{mine['id']}", json={"name": "x"}),
                 lambda: second.delete(f"/api/occasions/{mine['id']}")):  # fmt: skip
        assert call().status_code == 403
    outsider = api.post("/api/users", json={"username": "outsider"}).json()["user"]["id"]
    assert api.patch(f"/api/gifts/{gift['id']}", json={"buyer_id": outsider}).status_code == 422

    api.put(f"/api/recipients/{rec['id']}/shares", json={"user_ids": []})
    assert second.get(f"/api/recipients/{rec['id']}").status_code == 404
    assert second.get(f"/api/occasions/{mine['id']}/overview").status_code == 404


def test_archive_unarchive_read_only(api):
    oid = _occasion(api)["id"]
    rec = _recipient(api)
    gift = _gift(api, rec["id"])
    assert api.post(f"/api/occasions/{oid}/archive").json()["occasion"]["is_archived"] is True
    o = api.get(f"/api/occasions/{oid}/overview").json()
    assert o["read_only"] is True and o["groups"][0]["recipients"][0]["read_only"] is True
    assert api.patch(f"/api/recipients/{rec['id']}", json={"budget_pence": 1}).status_code == 409
    assert api.patch(f"/api/gifts/{gift['id']}", json={"status": "ordered"}).status_code == 409
    assert api.post(f"/api/recipients/{rec['id']}/gifts", json={"description": "x"}).status_code == 409
    assert api.post(f"/api/occasions/{oid}/recipients", json={"name": "New"}).status_code == 409

    assert api.post(f"/api/occasions/{oid}/unarchive").json()["occasion"]["is_archived"] is False
    assert api.patch(f"/api/gifts/{gift['id']}", json={"status": "ordered"}).status_code == 200


def test_delete_occasion_keeps_people(api):
    o = api.post("/api/occasions", json={"kind": "other", "name": "Leaving do"}).json()["occasion"]
    rec = _recipient(api, occasion_id=o["id"], name="Pat")
    _gift(api, rec["id"])
    assert (
        api.patch(f"/api/occasions/{o['id']}", json={"name": "Pat's leaving do", "date": "2027-01-31"}).json()[
            "occasion"
        ]["date"]
        == "2027-01-31"
    )
    assert api.delete(f"/api/occasions/{o['id']}").status_code == 200
    assert api.get(f"/api/occasions/{o['id']}/overview").status_code == 404
    assert api.get(f"/api/recipients/{rec['id']}").status_code == 404
    people = api.get("/api/people").json()["people"]
    assert [p["name"] for p in people] == ["Pat"] and people[0]["entries"] == []


def test_occasion_validation(api):
    assert api.post("/api/occasions", json={"name": " "}).status_code == 422
    assert api.post("/api/occasions", json={"name": "x", "kind": "wedding"}).status_code == 422
    assert api.post("/api/occasions/1/recipients", json={"name": ""}).status_code == 422


def test_categories_admin(api):
    a = api.post("/api/categories", json={"name": "Kids"}).json()["category"]
    b = api.post("/api/categories", json={"name": "Work"}).json()["category"]
    assert api.post("/api/categories", json={"name": "kids"}).status_code == 409
    r = api.put("/api/categories/order", json={"ids": [b["id"], a["id"]]})
    assert [c["name"] for c in r.json()["categories"]] == ["Work", "Kids"]
    assert api.patch(f"/api/categories/{a['id']}", json={"name": "Children"}).status_code == 200
    assert api.put("/api/categories/order", json={"ids": [a["id"]]}).status_code == 422


def test_occasions_sorted_by_date_with_christmas_inferred(api):
    from datetime import UTC, datetime

    year = datetime.now(UTC).year
    api.post("/api/occasions", json={"kind": "birthday", "name": "Later birthday", "date": f"{year + 1}-03-14"})
    api.post("/api/occasions", json={"kind": "other", "name": "Undated"})
    api.post("/api/occasions", json={"kind": "birthday", "name": "Soon birthday", "date": f"{year}-01-02"})
    names = [o["name"] for o in api.get("/api/occasions").json()["occasions"]]
    # The bootstrap "Christmas YYYY" has no date but sorts as 25 December.
    assert names == ["Soon birthday", f"Christmas {year}", "Later birthday", "Undated"]
