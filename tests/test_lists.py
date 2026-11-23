def _recipient(api, **kw):
    r = api.post("/api/recipients", json={"name": "Molly", "budget_pence": 30000, **kw})
    assert r.status_code == 201, r.text
    return r.json()["recipient"]


def _gift(api, rid, **kw):
    r = api.post(f"/api/recipients/{rid}/gifts", json={"description": "Lego set", **kw})
    assert r.status_code == 201, r.text
    return r.json()["gift"]


def test_budget_tally(api):
    rec = _recipient(api)
    _gift(api, rec["id"], price_pence=12000, status="ordered")
    _gift(api, rec["id"], price_pence=4000, quantity=2, status="wrapped")
    g = _gift(api, rec["id"], price_pence=10000, my_share_pence=5000, status="delivered")
    assert g["cost_pence"] == 5000 and g["line_total_pence"] == 10000
    _gift(api, rec["id"], description="Maybe a scarf", price_pence=9000)  # idea

    t = api.get(f"/api/recipients/{rec['id']}").json()["recipient"]["totals"]
    assert t["spent_pence"] == 25000
    assert t["planned_pence"] == 34000
    assert t["remaining_pence"] == 5000
    assert t["state"] == "under"
    assert t["planned_state"] == "over"

    # Within the default +/- GBP 5 margin counts as "on budget".
    _gift(api, rec["id"], price_pence=4600, status="ordered")
    t = api.get(f"/api/recipients/{rec['id']}").json()["recipient"]["totals"]
    assert t["spent_pence"] == 29600 and t["state"] == "on"

    api.put("/api/settings", json={"budget_margin_pence": 0})
    t = api.get(f"/api/recipients/{rec['id']}").json()["recipient"]["totals"]
    assert t["state"] == "under"


def test_gift_defaults_and_validation(api):
    rec = _recipient(api)
    g = _gift(api, rec["id"], link="www.example.com/thing")
    assert g["status"] == "idea" and g["priority"] == 2 and g["quantity"] == 1
    assert g["buyer"]["name"] == "admin"
    assert g["link"] == "https://www.example.com/thing"
    rid = rec["id"]
    assert api.post(f"/api/recipients/{rid}/gifts", json={"description": "  "}).status_code == 422
    assert (
        api.post(f"/api/recipients/{rid}/gifts", json={"description": "x", "link": "javascript:alert(1)"}).status_code
        == 422
    )
    assert api.post(f"/api/recipients/{rid}/gifts", json={"description": "x", "price_pence": -1}).status_code == 422
    assert api.post(f"/api/recipients/{rid}/gifts", json={"description": "x", "status": "lost"}).status_code == 422

    r = api.patch(
        f"/api/gifts/{g['id']}",
        json={
            "status": "ordered",
            "retailer": "Argos",
            "tracking_number": "TRK123",
            "delivery_date": "2026-12-10",
            "hiding_place": "Loft",
            "priority": 1,
            "link": "",
        },
    )
    assert r.status_code == 200
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
    cat = api.post("/api/categories", json={"name": "Kids"}).json()["category"]
    molly = _recipient(api, category_id=cat["id"])
    dad = _recipient(api, name="Dad", budget_pence=None)
    _gift(api, molly["id"], description="Low prio", priority=3)
    _gift(api, dad["id"], description="High prio", priority=1)
    _gift(api, molly["id"], description="Late", status="ordered", delivery_date="2026-12-20")
    _gift(api, dad["id"], description="Soon", status="ordered", delivery_date="2026-12-01")
    _gift(api, dad["id"], description="Undated", status="ordered")

    o = api.get("/api/overview").json()
    assert [g["category"]["name"] if g["category"] else None for g in o["groups"]] == ["Kids", None]
    assert [x["description"] for x in o["to_order"]] == ["High prio", "Low prio"]
    assert [x["description"] for x in o["awaiting_delivery"]] == ["Soon", "Late", "Undated"]
    assert o["awaiting_delivery"][0]["recipient_name"] == "Dad"
    assert o["totals"]["budget_pence"] == 30000

    # Deleting the category leaves recipients uncategorised.
    api.delete(f"/api/categories/{cat['id']}")
    o = api.get("/api/overview").json()
    assert len(o["groups"]) == 1 and o["groups"][0]["category"] is None


def test_recipients_are_private_unless_shared(api, second):
    rec = _recipient(api)
    gift = _gift(api, rec["id"])
    assert second.get(f"/api/recipients/{rec['id']}").status_code == 404
    assert second.patch(f"/api/gifts/{gift['id']}", json={"status": "ordered"}).status_code == 404
    assert second.get("/api/overview").json()["groups"] == []

    # Admins get no special access to other users' recipients either.
    theirs = _recipient(second, name="Secret for admin")
    assert api.get(f"/api/recipients/{theirs['id']}").status_code == 404

    sam_id = next(u["id"] for u in api.get("/api/users/directory").json()["users"] if u["username"] == "sam")
    r = api.put(f"/api/recipients/{rec['id']}/shares", json={"user_ids": [sam_id]})
    assert r.status_code == 200 and [p["name"] for p in r.json()["recipient"]["shared_with"]] == ["sam"]

    shared = second.get(f"/api/recipients/{rec['id']}").json()["recipient"]
    assert shared["is_owner"] is False
    assert second.patch(f"/api/gifts/{gift['id']}", json={"buyer_id": sam_id}).status_code == 200
    # Only the owner can delete or re-share.
    assert second.delete(f"/api/recipients/{rec['id']}").status_code == 403
    assert second.put(f"/api/recipients/{rec['id']}/shares", json={"user_ids": []}).status_code == 403

    # Buyers must have access to the recipient.
    outsider = api.post("/api/users", json={"username": "outsider"}).json()["user"]["id"]
    assert api.patch(f"/api/gifts/{gift['id']}", json={"buyer_id": outsider}).status_code == 422

    api.put(f"/api/recipients/{rec['id']}/shares", json={"user_ids": []})
    assert second.get(f"/api/recipients/{rec['id']}").status_code == 404


def test_seasons_archive_copy_and_read_only(api):
    cat = api.post("/api/categories", json={"name": "Family"}).json()["category"]
    rec = _recipient(api, category_id=cat["id"], notes="Size M")
    _gift(api, rec["id"], price_pence=5000, status="wrapped", tracking_number="X1", hiding_place="Loft")
    old_season = api.get("/api/overview").json()["season"]

    r = api.post("/api/seasons", json={"name": "Christmas 2027", "copy_recipients": True, "copy_gifts": True})
    assert r.status_code == 201
    o = api.get("/api/overview").json()
    assert o["season"]["name"] == "Christmas 2027" and o["read_only"] is False
    new_rec = o["groups"][0]["recipients"][0]
    assert (new_rec["name"], new_rec["budget_pence"], new_rec["notes"], new_rec["category"]["name"]) == (
        "Molly",
        30000,
        "Size M",
        "Family",
    )
    g = new_rec["gifts"][0]
    assert g["status"] == "idea" and g["tracking_number"] is None and g["hiding_place"] is None
    assert g["price_pence"] == 5000

    # The old season is archived and read-only.
    old = api.get(f"/api/overview?season_id={old_season['id']}").json()
    assert old["read_only"] is True
    old_rec = old["groups"][0]["recipients"][0]
    assert old_rec["gifts"][0]["status"] == "wrapped"
    assert api.patch(f"/api/recipients/{old_rec['id']}", json={"name": "x"}).status_code == 409
    assert api.post(f"/api/recipients/{old_rec['id']}/gifts", json={"description": "x"}).status_code == 409

    seasons = api.get("/api/seasons").json()["seasons"]
    assert [s["is_archived"] for s in seasons] == [False, True]

    # Without copying, the new season starts empty.
    api.post("/api/seasons", json={"name": "Christmas 2028", "copy_recipients": False})
    assert api.get("/api/overview").json()["groups"] == []

    # Re-activating an archived season.
    assert api.post(f"/api/seasons/{old_season['id']}/activate").status_code == 200
    assert api.get("/api/overview").json()["season"]["id"] == old_season["id"]


def test_categories_admin(api):
    a = api.post("/api/categories", json={"name": "Kids"}).json()["category"]
    b = api.post("/api/categories", json={"name": "Work"}).json()["category"]
    assert api.post("/api/categories", json={"name": "kids"}).status_code == 409
    r = api.put("/api/categories/order", json={"ids": [b["id"], a["id"]]})
    assert [c["name"] for c in r.json()["categories"]] == ["Work", "Kids"]
    assert api.patch(f"/api/categories/{a['id']}", json={"name": "Children"}).status_code == 200
    assert api.put("/api/categories/order", json={"ids": [a["id"]]}).status_code == 422
