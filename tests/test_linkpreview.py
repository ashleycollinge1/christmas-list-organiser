import socket

import httpx
import pytest

from app import linkpreview as lp


def fake_resolver(mapping):
    def resolve(host, port, proto=0):
        if host not in mapping:
            raise socket.gaierror("unknown host")
        return [(socket.AF_INET, socket.SOCK_STREAM, proto, "", (addr, port)) for addr in mapping[host]]

    return resolve


PUBLIC = fake_resolver({"shop.example.co.uk": ["93.184.216.34"], "shop.example.com": ["93.184.216.34"],
                        "evil.example.com": ["93.184.216.34"], "internal.example.com": ["10.0.0.5"]})  # fmt: skip


# ---------------------------------------------------------------- parsing

JSON_LD = """<html><head><title>Lego Orchid | Big Shop</title>
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"BreadcrumbList"},
{"@type":"Product","name":"LEGO Icons Orchid 10311","offers":{"@type":"Offer","price":"39.99","priceCurrency":"GBP"}}]}
</script></head></html>"""

OPEN_GRAPH = """<html><head><meta property="og:site_name" content="Argos">
<meta property="og:title" content="Sony WH-1000XM5 Headphones - Black | Argos">
<meta property="product:price:amount" content="279.00"><meta property="product:price:currency" content="GBP">
</head></html>"""


def test_parses_json_ld_product():
    p = lp.parse("https://shop.example.com/orchid", JSON_LD)
    assert (p.title, p.price_pence, p.currency) == ("LEGO Icons Orchid 10311", 3999, "GBP")


def test_parses_open_graph_and_strips_site_suffix():
    p = lp.parse("https://www.argos.co.uk/x", OPEN_GRAPH)
    assert p.title == "Sony WH-1000XM5 Headphones - Black"
    assert p.price_pence == 27900 and p.site == "Argos"


def test_title_only_page():
    p = lp.parse("https://blog.example.com/post", "<title>  Handmade   mug : Etsy UK </title>")
    assert p.title == "Handmade mug" and p.price_pence is None


def test_only_pounds_are_suggested():
    usd = (
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"X","offers":{"price":"10","priceCurrency":"USD"}}</script>'
    )
    assert lp.parse("https://shop.example.com/x", usd).price_pence is None
    # No currency given: assume pounds only on a .uk shop or with a £ sign.
    bare = '<meta itemprop="price" content="12.50">'
    assert lp.parse("https://shop.example.co.uk/x", bare).price_pence == 1250
    assert lp.parse("https://shop.example.com/x", bare).price_pence is None
    assert lp.parse("https://shop.example.com/x", '<meta itemprop="price" content="£8">').price_pence == 800


TO_PENCE = [("1,299.99", 129999), ("1299,99", 129999), ("1.299,99", 129999),
            ("£24", 2400), ("abc", None), ("", None), ("12,500", 1250000)]  # fmt: skip


@pytest.mark.parametrize(("raw", "pence"), TO_PENCE)
def test_to_pence(raw, pence):
    assert lp.to_pence(raw) == pence


def test_malformed_html_does_not_crash():
    assert lp.parse("https://x.example.com", "<html><title>Ok<script type='application/ld+json'>{bad").title


@pytest.mark.parametrize(("text", "url"), [
    ("https://amzn.eu/d/abc", "https://amzn.eu/d/abc"),
    ("Check this out! https://www.argos.co.uk/product/123.", "https://www.argos.co.uk/product/123"),
    ("example.com/thing", "https://example.com/thing"),
    ("no link here", None), (None, None),
])  # fmt: skip
def test_extract_url(text, url):
    assert lp.extract_url(text) == url


# ---------------------------------------------------------------- SSRF guard


PRIVATE = ["127.0.0.1", "10.1.2.3", "192.168.1.10", "172.17.0.2", "169.254.169.254",
           "100.64.0.1", "0.0.0.0", "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1"]  # fmt: skip


@pytest.mark.parametrize("addr", PRIVATE)
def test_private_addresses_refused(addr):
    with pytest.raises(lp.PreviewError, match="private or local"):
        lp.check_url("https://sneaky.example.com/", fake_resolver({"sneaky.example.com": [addr]}))


def test_any_private_address_refuses_the_host():
    resolve = fake_resolver({"mixed.example.com": ["93.184.216.34", "127.0.0.1"]})
    with pytest.raises(lp.PreviewError):
        lp.check_url("https://mixed.example.com/", resolve)


@pytest.mark.parametrize("url", ["ftp://shop.example.com/x", "file:///etc/passwd", "http://shop.example.com:8080/",
                                 "http://user:pw@shop.example.com/", "https:///nohost"])  # fmt: skip
def test_bad_urls_refused(url):
    with pytest.raises(lp.PreviewError):
        lp.check_url(url, PUBLIC)


def test_public_url_allowed():
    assert lp.check_url("https://shop.example.com/x", PUBLIC) == "https://shop.example.com/x"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def test_fetch_follows_safe_redirects_and_reads_html():
    def handler(req):
        if req.url.path == "/short":
            return httpx.Response(301, headers={"location": "https://shop.example.co.uk/real"})
        return httpx.Response(200, headers={"content-type": "text/html"}, text=JSON_LD)

    p = lp.preview("https://shop.example.com/short", client=_client(handler), resolve=PUBLIC)
    assert p.title == "LEGO Icons Orchid 10311" and p.url == "https://shop.example.com/short"


def test_redirect_to_private_address_refused():
    def handler(req):
        return httpx.Response(302, headers={"location": "http://internal.example.com/admin"})

    with pytest.raises(lp.PreviewError, match="private or local"):
        lp.fetch_html("https://evil.example.com/", client=_client(handler), resolve=PUBLIC)


def test_non_html_and_errors():
    pdf = _client(lambda r: httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF"))
    with pytest.raises(lp.PreviewError, match="isn't a web page"):
        lp.fetch_html("https://shop.example.com/x.pdf", client=pdf, resolve=PUBLIC)
    blocked = _client(lambda r: httpx.Response(503, headers={"content-type": "text/html"}))
    with pytest.raises(lp.PreviewError, match="refused"):
        lp.fetch_html("https://shop.example.com/", client=blocked, resolve=PUBLIC)
    loop = _client(lambda r: httpx.Response(302, headers={"location": "/again"}))
    with pytest.raises(lp.PreviewError, match="too many"):
        lp.fetch_html("https://shop.example.com/", client=loop, resolve=PUBLIC)


def test_reads_at_most_the_size_limit(monkeypatch):
    monkeypatch.setattr(lp, "MAX_BYTES", 1000)
    big = _client(lambda r: httpx.Response(200, headers={"content-type": "text/html"}, content=b"a" * 50_000))
    _, page = lp.fetch_html("https://shop.example.com/", client=big, resolve=PUBLIC)
    assert len(page) < 50_000


# ---------------------------------------------------------------- endpoints


def test_preview_endpoint(api, monkeypatch):
    from app.routers import wishes

    monkeypatch.setattr(
        lp, "preview", lambda url: lp.Preview(url=url, title="Orchid", price_pence=3999, currency="GBP")
    )
    r = api.get("/api/wishes/preview", params={"text": "Look https://shop.example.com/orchid"}).json()
    assert r["error"] is None and r["preview"]["title"] == "Orchid" and r["preview"]["url"].endswith("/orchid")

    def refuse(url):
        raise lp.PreviewError("That website refused the request (503).")

    monkeypatch.setattr(lp, "preview", refuse)
    r = api.get("/api/wishes/preview", params={"url": "https://shop.example.com/x"}).json()
    assert r["error"].startswith("That website refused") and r["preview"]["url"] == "https://shop.example.com/x"
    assert api.get("/api/wishes/preview", params={"text": "nothing"}).status_code == 422

    wishes.preview_limit._hits.clear()
    monkeypatch.setattr(wishes.preview_limit, "limit", 2)
    codes = [api.get("/api/wishes/preview", params={"url": "https://shop.example.com/x"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    wishes.preview_limit._hits.clear()


def test_preview_needs_login(client):
    assert client.get("/api/wishes/preview", params={"url": "https://example.com"}).status_code == 401


def test_share_redirects_to_form(client):
    r = client.get("/share", params={"text": "Want this https://shop.example.com/a?b=1&c=2"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/#/add?url=https%3A%2F%2Fshop.example.com%2Fa%3Fb%3D1%26c%3D2"
    assert client.get("/share", follow_redirects=False).headers["location"] == "/#/add?url="


@pytest.mark.parametrize(("url", "name"), [
    ("https://www.johnlewis.com/lego-icons-10311-orchid/p5765185", "Lego icons 10311 orchid"),
    ("https://www.amazon.co.uk/Sony-WH-1000XM5-Cancelling-Headphones/dp/B09XS7JWHH/ref=sr_1_1",
     "Sony WH 1000XM5 Cancelling Headphones"),
    ("https://www.etsy.com/uk/listing/1234/personalised-wooden-name-puzzle", "Personalised wooden name puzzle"),
    ("https://www.argos.co.uk/product/9576658", None),
    ("https://amzn.eu/d/abc123", None),
])  # fmt: skip
def test_name_from_url(url, name):
    assert lp.name_from_url(url) == name


def test_blocked_page_falls_back_to_name_from_link(api, monkeypatch):
    def refuse(url):
        raise lp.PreviewError("That website refused the request (403).")

    monkeypatch.setattr(lp, "preview", refuse)
    r = api.get("/api/wishes/preview", params={"url": "https://www.johnlewis.com/lego-icons-10311-orchid/p5765185"})
    body = r.json()
    assert body["guessed"] is True and body["preview"]["title"] == "Lego icons 10311 orchid"
