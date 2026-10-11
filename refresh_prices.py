"""Fetch public wishlist prices at build time; Python standard library only.

Shopify Ajax product/cart APIs and Amazon Creators API (US, 3.1 credentials).
Secrets belong in the job environment. Never publish raw API responses or tokens.
"""
import argparse
import csv
import json
import math
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit, urlunsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parent
# Leave a margin below Amazon's 24-hour cache limit for browser expiry timers.
MAX_AGE = timedelta(hours=23)


def utc_now():
    return datetime.now(timezone.utc)


def timestamp(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


class FetchError(Exception):
    """A safe, non-sensitive error code for the public feed and build log."""


class Client:
    def __init__(self):
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def json(self, url, payload=None, headers=None):
        data = None if payload is None else json.dumps(payload).encode()
        request = Request(url, data=data, headers={
            "Accept": "application/json", "User-Agent": "RyansWishlist/1.0",
            **({"Content-Type": "application/json"} if data else {}), **(headers or {})})
        for attempt in range(3):
            try:
                with self.opener.open(request, timeout=20) as response:
                    raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise FetchError("invalid_response")
                return json.loads(raw)
            except HTTPError as error:
                code = error.code
                error.close()
                if code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise FetchError(f"http_{code}") from None
            except (URLError, TimeoutError, OSError):
                if attempt == 2:
                    raise FetchError("network_error") from None
            except (ValueError, UnicodeError):
                raise FetchError("invalid_response") from None
            time.sleep(2 ** attempt)


def valid_money(amount, currency):
    return (type(amount) in (int, float) and math.isfinite(amount) and amount > 0
            and isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency))


def shopify_price(link, client):
    url = urlsplit(link)
    match = re.fullmatch(r"(.*?)/products/([^/]+)/?", url.path)
    if url.scheme != "https" or not url.hostname or not match:
        raise FetchError("invalid_product_url")
    product_url = urlunsplit((url.scheme, url.netloc, url.path.rstrip("/") + ".js", "currency=USD", ""))
    # Request USD on BOTH routes: the currency query does not persist in cookies.
    # Read the returned currency, since not every shop supports USD.
    prefix = match[1].split("/collections/")[0]
    cart_url = urlunsplit((url.scheme, url.netloc, prefix + "/cart.js", "currency=USD", ""))
    currency = client.json(cart_url)["currency"]
    product = client.json(product_url)
    variants = product["variants"]
    variant_id = parse_qs(url.query).get("variant", [None])[0]
    if variant_id:
        variants = [v for v in variants if str(v["id"]) == variant_id]
        if not variants:
            raise FetchError("variant_not_found")
    available = [v for v in variants if v.get("available") is True]
    if available:
        variants = available
        availability = "available"
    elif variants and all(v.get("available") is False for v in variants):
        # Keep a sold-out wish's listed price, clearly paired with its stock status.
        availability = "out_of_stock"
    else:
        raise FetchError("unavailable")
    amounts = [v["price"] for v in variants]
    if not all(valid_money(amount, currency) for amount in amounts):
        raise FetchError("invalid_price")
    return {"amount": min(amounts) / 100, "currency": currency,
            "from": min(amounts) != max(amounts), "availability": availability}


def usd_price(price, client, rates, now):
    """Prefer the shop's USD offer; otherwise publish a dated USD estimate."""
    currency = price["currency"]
    if currency == "USD":
        return price
    if currency not in rates:
        rates[currency] = client.json(f"https://api.frankfurter.dev/v2/rate/{currency}/USD")
    rate = rates[currency]
    if (rate.get("base") != currency or rate.get("quote") != "USD"
            or not valid_money(rate.get("rate"), "USD")):
        raise FetchError("invalid_exchange_rate")
    try:
        age = (now.date() - date.fromisoformat(rate["date"])).days
    except (KeyError, TypeError, ValueError):
        raise FetchError("invalid_exchange_rate") from None
    # Allow weekends/holidays, but never silently use an old or future rate.
    if not 0 <= age <= 7:
        raise FetchError("stale_exchange_rate")
    amount = float((Decimal(str(price["amount"])) * Decimal(str(rate["rate"])))
                   .quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    if not valid_money(amount, "USD"):
        raise FetchError("invalid_exchange_rate")
    return {**price, "amount": amount, "currency": "USD", "estimate": True,
            "original_amount": price["amount"], "original_currency": currency,
            "fx_rate": rate["rate"], "fx_date": rate["date"]}


def amazon_identity(link):
    url = urlsplit(link)
    match = re.search(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:/|$)", url.path, re.I)
    tag = parse_qs(url.query).get("tag", [""])[0]
    if url.scheme != "https" or url.hostname not in ("amazon.com", "www.amazon.com") or not match or not tag:
        raise FetchError("invalid_amazon_link")
    return match[1].upper(), tag


class Amazon:
    def __init__(self, client, env):
        self.client, self.env, self.token = client, env, None

    def item(self, asin, tag):
        client_id = self.env.get("AMAZON_CREATORS_CLIENT_ID")
        secret = self.env.get("AMAZON_CREATORS_CLIENT_SECRET")
        if not client_id or not secret:
            raise FetchError("api_not_configured")
        if not self.token:
            self.token = self.client.json("https://api.amazon.com/auth/o2/token", {
                "grant_type": "client_credentials", "client_id": client_id,
                "client_secret": secret, "scope": "creatorsapi::default"})["access_token"]
        response = self.client.json("https://creatorsapi.amazon/catalog/v1/getItems", {
            "itemIds": [asin], "itemIdType": "ASIN", "marketplace": "www.amazon.com",
            "partnerTag": tag, "condition": "New", "currencyOfPreference": "USD",
            "resources": ["offersV2.listings." + name for name in
                          ("price", "availability", "condition", "isBuyBoxWinner", "violatesMAP", "type", "dealDetails")]
        }, {"Authorization": "Bearer " + self.token, "x-marketplace": "www.amazon.com"})
        # GetItems can partially fail or reorder results. Never associate by index.
        return next((item for item in (response.get("itemsResult") or {}).get("items", [])
                     if item.get("asin") == asin), {})


def amazon_price(item):
    listings = (item.get("offersV2") or {}).get("listings") or []
    for offer in sorted(listings, key=lambda o: not o.get("isBuyBoxWinner")):
        if offer.get("violatesMAP") is not False or (offer.get("condition") or {}).get("value") != "New":
            continue
        # Do not advertise a subscription, Prime-only, or short-lived deal as a normal price.
        if offer.get("type") or offer.get("dealDetails"):
            continue
        availability = (offer.get("availability") or {}).get("type", "").replace("_", "")
        if availability not in ("INSTOCK", "INSTOCKSCARCE", "PREORDER", "LEADTIME"):
            continue
        money = (offer.get("price") or {}).get("money") or {}
        if valid_money(money.get("amount"), money.get("currency")):
            return {"amount": money["amount"], "currency": money["currency"], "from": False,
                    "availability": "preorder" if availability == "PREORDER" else "available"}
    raise FetchError("no_public_offer")


def build_feed(rows, client=None, env=None, clock=utc_now):
    client = client or Client()
    amazon = Amazon(client, os.environ if env is None else env)
    rates = {}
    prices = {}
    for row in rows:
        source, link = row.get("price_source", "").strip(), row.get("link", "").strip()
        if source not in ("shopify", "amazon"):
            continue
        entry = {"source": source}
        try:
            if source == "shopify":
                result = shopify_price(link, client)
            else:
                asin, tag = amazon_identity(link)
                result = amazon_price(amazon.item(asin, tag))
                if result["currency"] != "USD":
                    raise FetchError("usd_offer_unavailable")
            result = usd_price(result, client, rates, clock())
            checked = clock()
            entry.update(result, status="ok", checked_at=timestamp(checked),
                         expires_at=timestamp(checked + MAX_AGE))
        except FetchError as error:
            entry.update(status="unavailable", reason=str(error))
        except (KeyError, TypeError, ValueError, AttributeError, InvalidOperation):
            entry.update(status="unavailable", reason="invalid_response")
        prices[link] = entry
        # Only known error codes and public item names; never log API responses.
        print(f"{row.get('name', 'Item')}: {entry['status']} ({entry.get('reason', source)})")
    return {"version": 1, "generated_at": timestamp(clock()), "items": prices}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=ROOT / "items.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "prices.json")
    args = parser.parse_args()
    with args.csv.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or "name" not in reader.fieldnames:
            raise SystemExit("The CSV must have a name column")
        rows = [{key.strip(): (value or "").strip() for key, value in row.items() if key}
                for row in reader if row.get("name", "").strip()]
    feed = build_feed(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(feed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
