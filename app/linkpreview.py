"""Read a product page to suggest a name and price for a wish.

The server fetches whatever URL a signed-in user gives it, so this is guarded
against server-side request forgery:

- only http/https, on the standard ports;
- every hostname is resolved and refused if *any* address is private, loopback,
  link-local, multicast or otherwise non-public (cloud metadata, the Docker
  network, your LAN). This is checked again on every redirect, which are
  followed by hand (at most 5);
- short timeouts, HTML only, and at most 2 MB is read;
- no cookies or credentials are sent.

Many shops block automated requests; callers treat failure as "no suggestion".
"""

from __future__ import annotations

import contextlib
import html
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
TIMEOUT = httpx.Timeout(8.0, connect=4.0)
# A mainstream browser UA: many shops serve an error page to obviously automated clients.
USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)
URL_IN_TEXT = re.compile(r"https?://[^\s<>\"']+", re.I)


class PreviewError(Exception):
    """A URL we won't or can't read. The message is safe to show to the user."""


@dataclass
class Preview:
    url: str
    title: str | None = None
    price_pence: int | None = None
    currency: str | None = None
    site: str | None = None

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "title": self.title,
            "price_pence": self.price_pence,
            "currency": self.currency,
            "site": self.site,
        }


def extract_url(text: str | None) -> str | None:
    """The first http(s) URL in shared text ("Check this out https://…"), or the text if it's a bare URL."""
    if not text:
        return None
    text = text.strip()
    m = URL_IN_TEXT.search(text)
    if m:
        return m.group(0).rstrip(").,;!?")
    if " " not in text and "." in text:
        return "https://" + text
    return None


# ---------------------------------------------------------------------------- URL safety


def _public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not (ip.is_multicast or ip.is_reserved)


def check_url(url: str, resolve=socket.getaddrinfo) -> str:
    """Raise PreviewError unless url is http(s) to a public host on a normal port."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise PreviewError("Only http and https links can be read.")
    host = parts.hostname
    if not host:
        raise PreviewError("That doesn't look like a web link.")
    if parts.username or parts.password:
        raise PreviewError("Links with a username or password can't be read.")
    try:
        port = parts.port
    except ValueError as exc:
        raise PreviewError("That link has an invalid port.") from exc
    if port not in (None, 80, 443):
        raise PreviewError("Only links on the standard web ports can be read.")
    try:
        infos = resolve(host, port or (443 if parts.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as exc:
        raise PreviewError("Couldn't find that website.") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses:
        raise PreviewError("Couldn't find that website.")
    for addr in addresses:
        if not _public(ipaddress.ip_address(addr.split("%")[0])):
            raise PreviewError("That link points to a private or local address, so it won't be read.")
    return url


# ---------------------------------------------------------------------------- fetching


def fetch_html(url: str, client: httpx.Client | None = None, resolve=socket.getaddrinfo) -> tuple[str, str]:
    """GET url (following redirects safely). Returns (final_url, html)."""
    own = client is None
    client = client or httpx.Client(
        timeout=TIMEOUT,
        follow_redirects=False,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            "Accept-Language": "en-GB,en;q=0.9",
        },
    )
    try:
        for _ in range(MAX_REDIRECTS + 1):
            check_url(url, resolve)
            with client.stream("GET", url) as resp:
                if resp.is_redirect:
                    location = resp.headers.get("location")
                    if not location:
                        raise PreviewError("That website sent a broken redirect.")
                    url = urljoin(url, location)
                    continue
                if resp.status_code >= 400:
                    raise PreviewError(f"That website refused the request ({resp.status_code}).")
                ctype = resp.headers.get("content-type", "")
                if "html" not in ctype.lower():
                    raise PreviewError("That link isn't a web page.")
                body = bytearray()
                for chunk in resp.iter_bytes():
                    body.extend(chunk)
                    if len(body) >= MAX_BYTES:
                        del body[MAX_BYTES:]
                        break
                return url, body.decode(resp.encoding or "utf-8", errors="replace")
        raise PreviewError("That link redirects too many times.")
    except httpx.TimeoutException as exc:
        raise PreviewError("That website took too long to respond.") from exc
    except httpx.HTTPError as exc:
        raise PreviewError("Couldn't reach that website.") from exc
    finally:
        if own:
            client.close()


# ---------------------------------------------------------------------------- parsing


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.ld: list[str] = []
        self.title = ""
        self._in_title = False
        self._in_ld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if key and "content" in a and key not in self.meta:
                self.meta[key] = a["content"]
        elif tag == "title" and not self.title:
            self._in_title = True
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in_ld = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self._in_title = False
        elif tag == "script" and self._in_ld:
            self.ld.append("".join(self._buf))
            self._in_ld = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_ld:
            self._buf.append(data)


def _walk_products(node):
    """Yield every schema.org Product in a JSON-LD blob (handles @graph and lists)."""
    if isinstance(node, list):
        for item in node:
            yield from _walk_products(item)
    elif isinstance(node, dict):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if any(isinstance(t, str) and t.lower() in ("product", "productgroup") for t in types):
            yield node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                yield from _walk_products(node[key])


def _offer_price(offers) -> tuple[str | None, str | None]:
    if isinstance(offers, list):
        for o in offers:
            p, c = _offer_price(o)
            if p:
                return p, c
        return None, None
    if not isinstance(offers, dict):
        return None, None
    price = offers.get("price") or offers.get("lowPrice")
    spec = offers.get("priceSpecification")
    if price is None and isinstance(spec, dict):
        price = spec.get("price")
    currency = offers.get("priceCurrency") or (spec.get("priceCurrency") if isinstance(spec, dict) else None)
    return (str(price) if price is not None else None), currency


def to_pence(value: str | None) -> int | None:
    if not value:
        return None
    cleaned = re.sub(r"[^\d.,]", "", str(value))
    if not cleaned:
        return None
    # "1,299.99" / "1299,99" / "1.299,99"
    if "," in cleaned and "." in cleaned:
        cleaned = (
            cleaned.replace(",", "")
            if cleaned.rfind(".") > cleaned.rfind(",")
            else cleaned.replace(".", "").replace(",", ".")
        )
    elif "," in cleaned:
        head, _, tail = cleaned.rpartition(",")
        cleaned = f"{head.replace(',', '')}.{tail}" if len(tail) == 2 else cleaned.replace(",", "")
    try:
        pence = round(float(cleaned) * 100)
    except ValueError:
        return None
    return pence if 0 <= pence <= 10_000_000 else None


def _clean_title(title: str | None, site: str | None) -> str | None:
    if not title:
        return None
    t = re.sub(r"\s+", " ", html.unescape(title)).strip()
    # Drop a trailing " | Shop" / " - Shop" / " : Amazon.co.uk" site suffix.
    parts = re.split(r"\s+[|\-–—:]\s+", t)
    if len(parts) > 1:
        last = parts[-1].lower()
        if (site and site.lower() in last) or re.search(r"\.(co\.uk|com|uk)$", last) or len(parts[-1]) <= 25:
            t = " - ".join(parts[:-1]) if len(parts) > 2 else parts[0]
    t = re.sub(r"^(Buy|Shop)\s+", "", t, flags=re.I).strip()
    return t[:200] or None


def parse(url: str, page: str) -> Preview:
    c = _Collector()
    with contextlib.suppress(Exception):  # malformed HTML: use whatever was collected
        c.feed(page)
        c.close()  # flush text still buffered at the end of a truncated page
    m = c.meta
    site = m.get("og:site_name") or (urlsplit(url).hostname or "").removeprefix("www.")
    title = None
    price = currency = None
    for blob in c.ld:
        try:
            data = json.loads(blob)
        except ValueError:
            continue
        for product in _walk_products(data):
            title = title or product.get("name")
            if price is None:
                price, currency = _offer_price(product.get("offers"))
    title = title or m.get("og:title") or m.get("twitter:title") or c.title
    if price is None:
        price = m.get("product:price:amount") or m.get("og:price:amount") or m.get("price")
        currency = m.get("product:price:currency") or m.get("og:price:currency") or m.get("pricecurrency")
    pence = to_pence(price)
    currency = (currency or "").strip().upper() or None
    # Only suggest prices we know (or can safely assume) are in pounds.
    host = (urlsplit(url).hostname or "").lower()
    if currency is None and ("£" in str(price or "") or host.endswith(".uk")):
        currency = "GBP"
    if currency != "GBP":
        pence = None
    return Preview(url=url, title=_clean_title(title, site), price_pence=pence, currency=currency, site=site or None)


def name_from_url(url: str) -> str | None:
    """Best guess at a product name from the link itself, for sites that block reading.

    "…/Sony-WH-1000XM5-Cancelling-Headphones/dp/B09…" -> "Sony WH 1000XM5 Cancelling Headphones".
    """
    from urllib.parse import unquote

    best = None
    for seg in urlsplit(url).path.split("/"):
        seg = unquote(seg).rsplit(".", 1)[0] if "." in seg[-6:] else unquote(seg)
        words = [w for w in re.split(r"[-_+]+", seg) if w]
        # Wordy segments only: skip IDs, SKUs and short path parts.
        alpha = [w for w in words if re.search(r"[A-Za-z]{2,}", w)]
        if len(alpha) >= 2 and len(" ".join(words)) >= 8 and (best is None or len(words) > len(best)):
            best = words
    if not best:
        return None
    text = " ".join(best)
    return (text.capitalize() if text.islower() else text[0].upper() + text[1:])[:200]


def preview(url: str, client: httpx.Client | None = None, resolve=socket.getaddrinfo) -> Preview:
    final_url, page = fetch_html(url, client=client, resolve=resolve)
    result = parse(final_url, page)
    result.url = url
    return result
