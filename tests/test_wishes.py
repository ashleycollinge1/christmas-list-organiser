def _occ(api, name=None):
    occs = api.get("/api/occasions").json()["occasions"]
    return next(o for o in occs if o["name"] == name) if name else occs[0]


def _wish(api, **kw):
    r = api.post("/api/wishes", json={"description": "Noise-cancelling headphones", **kw})
    assert r.status_code == 201, r.text
    return r.json()["wish"]


def test_first_wish_creates_me_and_defaults_to_anytime(api):
    assert api.get("/api/wishes").json()["me"] is None
    w = _wish(api, price_pence=24999, link="www.example.com/headphones")
    assert w["occasion"] is None and w["priority"] == 2 and w["quantity"] == 1 and w["archived"] is False
    assert w["link"] == "https://www.example.com/headphones"
    data = api.get("/api/wishes").json()
    assert data["me"]["name"] == "admin"
    people = api.get("/api/people").json()["people"]
    assert [(p["kind"], p["name"]) for p in people] == [("me", "admin")]


def test_totals_move_archive_restore(api):
    xmas = _occ(api)
    a = _wish(api, price_pence=1000, quantity=2)
    b = _wish(api, description="Book", price_pence=1299, occasion_id=xmas["id"], priority=1)
    _wish(api, description="Unpriced idea")
    t = api.get("/api/wishes").json()["totals"]
    assert t == {"count": 3, "total_pence": 3299, "unpriced": 1}

    # The occasion shows only its own wishes, and they never count as spending.
    o = api.get(f"/api/occasions/{xmas['id']}/overview").json()
    assert o["my_wishes"]["count"] == 1 and o["my_wishes"]["total_pence"] == 1299
    assert o["my_wishes"]["items"][0]["description"] == "Book"
    assert o["totals"]["spent_pence"] == 0 and o["totals"]["planned_pence"] == 0 and o["groups"] == []

    # Move Anytime -> Christmas, then archive and restore.
    assert (
        api.patch(f"/api/wishes/{a['id']}", json={"occasion_id": xmas["id"]}).json()["wish"]["occasion"]["id"]
        == xmas["id"]
    )
    assert api.patch(f"/api/wishes/{b['id']}", json={"archived": True}).json()["wish"]["archived"] is True
    assert api.get("/api/wishes").json()["totals"]["count"] == 2
    assert api.get(f"/api/occasions/{xmas['id']}/overview").json()["my_wishes"]["count"] == 1
    assert (
        api.patch(f"/api/wishes/{b['id']}", json={"archived": False, "occasion_id": None}).json()["wish"]["occasion"]
        is None
    )
    assert api.get("/api/wishes").json()["totals"]["count"] == 3


def test_deleting_an_occasion_moves_wishes_to_anytime(api):
    o = api.post("/api/occasions", json={"kind": "birthday", "name": "My birthday"}).json()["occasion"]
    w = _wish(api, occasion_id=o["id"])
    assert api.get(f"/api/occasions/{o['id']}/overview").json()["delete_impact"]["my_wishes"] == 1
    api.delete(f"/api/occasions/{o['id']}")
    after = api.get("/api/wishes").json()["wishes"]
    assert [x["id"] for x in after] == [w["id"]] and after[0]["occasion"] is None


def test_wishes_are_private(api, second):
    w = _wish(api)
    assert second.get("/api/wishes").json()["wishes"] == []
    assert second.patch(f"/api/wishes/{w['id']}", json={"description": "x"}).status_code == 404
    assert second.delete(f"/api/wishes/{w['id']}").status_code == 404
    # Can't file a wish under an occasion you can't see.
    assert second.post("/api/wishes", json={"description": "x", "occasion_id": _occ(api)["id"]}).status_code == 404


def test_me_rules(api):
    me = api.post("/api/people", json={"kind": "me", "name": "Ashley", "notes": "Medium, size 9 shoes"})
    assert me.status_code == 201 and me.json()["person"]["kind"] == "me"
    pid = me.json()["person"]["id"]
    assert api.post("/api/people", json={"kind": "me", "name": "Again"}).status_code == 409
    assert api.post("/api/people", json={"kind": "wizard", "name": "x"}).status_code == 422
    assert api.patch(f"/api/people/{pid}", json={"kind": "recipient"}).status_code == 422
    # Me isn't someone you buy for.
    oid = _occ(api)["id"]
    assert api.post(f"/api/occasions/{oid}/recipients", json={"person_id": pid}).status_code == 422
    assert api.post("/api/occasions", json={"name": "x", "person_ids": [pid]}).status_code == 422
    # The first wish uses the existing Me.
    _wish(api)
    assert api.get("/api/wishes").json()["me"]["id"] == pid
    assert api.delete(f"/api/people/{pid}").status_code == 409


def test_wish_validation(api):
    for bad in ({"description": " "}, {"description": "x", "link": "javascript:alert(1)"},
                {"description": "x", "price_pence": -5}, {"description": "x", "priority": 4},
                {"description": "x", "quantity": 0}):  # fmt: skip
        assert api.post("/api/wishes", json=bad).status_code == 422
    assert api.patch("/api/wishes/999", json={"description": "x"}).status_code == 404


def test_new_occasion_for_me_moves_chosen_wishes(api, second):
    keep, take1, take2 = (
        api.post("/api/wishes", json={"description": d}).json()["wish"]["id"] for d in ("Keep", "Take", "Also")
    )
    o = api.post("/api/occasions", json={"kind": "birthday", "name": "My birthday", "include_me": True,
                                         "wish_ids": [take1, take2]}).json()["occasion"]  # fmt: skip
    mine = api.get(f"/api/occasions/{o['id']}/overview").json()["my_wishes"]
    assert sorted(w["description"] for w in mine["items"]) == ["Also", "Take"] and mine["me"]["name"] == "admin"
    left = [w["description"] for w in api.get("/api/wishes").json()["wishes"] if w["occasion"] is None]
    assert left == ["Keep"] and keep

    # Me with no wishes yet still sets up your wish list, so the page can show it.
    fresh = second.post("/api/occasions", json={"name": "Sam's birthday", "include_me": True}).json()["occasion"]
    assert second.get(f"/api/occasions/{fresh['id']}/overview").json()["my_wishes"]["count"] == 0

    # Someone else's wishes can't be pulled in, and nothing is created when that fails.
    before = len(second.get("/api/occasions").json()["occasions"])
    r = second.post("/api/occasions", json={"name": "x", "include_me": True, "wish_ids": [keep]})
    assert r.status_code == 422 and len(second.get("/api/occasions").json()["occasions"]) == before


def test_home_list_includes_my_wish_summary(api):
    o = api.post("/api/occasions", json={"kind": "birthday", "name": "Mine", "include_me": True}).json()["occasion"]
    api.post("/api/wishes", json={"description": "A", "price_pence": 1500, "occasion_id": o["id"]})
    row = next(x for x in api.get("/api/occasions").json()["occasions"] if x["id"] == o["id"])
    assert row["people"] == 0 and row["my_wishes"] == {"count": 1, "total_pence": 1500, "unpriced": 0}
