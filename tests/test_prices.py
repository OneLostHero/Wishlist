import json
import unittest
from datetime import datetime, timezone

from refresh_prices import Amazon, FetchError, amazon_identity, amazon_price, build_feed, shopify_price, usd_price


NOW = datetime(2026, 10, 11, 12, tzinfo=timezone.utc)
SHOP = "https://shop.test/products/book"
AMAZON = "https://www.amazon.com/dp/B08KG4QVCT/?tag=owner-20"


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.calls = []

    def json(self, url, payload=None, headers=None):
        self.calls.append((url, payload, headers))
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return reply


def variant(identifier, price, available=True):
    return {"id": identifier, "price": price, "available": available}


def offer(**changes):
    return {"condition": {"value": "New"}, "isBuyBoxWinner": True, "violatesMAP": False,
            "price": {"money": {"amount": 249.99, "currency": "USD"}},
            "availability": {"type": "IN_STOCK"}, **changes}


class PricesTest(unittest.TestCase):
    def test_shopify_currency_minor_units_and_exact_variant(self):
        client = FakeClient([{"currency": "CAD"}, {"variants": [variant(1, 10000), variant(2, 12050)]}])
        price = shopify_price(SHOP + "?variant=2", client)
        self.assertEqual(price["amount"], 120.5)
        self.assertEqual(price["currency"], "CAD")
        self.assertFalse(price["from"])
        self.assertEqual([call[0] for call in client.calls], ["https://shop.test/cart.js?currency=USD", SHOP + ".js?currency=USD"])

    def test_shopify_available_range_locale_and_sold_out_variant(self):
        product = {"variants": [variant(1, 100, False), variant(2, 2500), variant(3, 3500)]}
        client = FakeClient([{"currency": "USD"}, product])
        price = shopify_price("https://shop.test/en-us/products/book", client)
        self.assertEqual(price["amount"], 25)
        self.assertTrue(price["from"])
        self.assertEqual(client.calls[0][0], "https://shop.test/en-us/cart.js?currency=USD")
        for suffix, reason in (("?variant=1", "unavailable"), ("?variant=9", "variant_not_found")):
            with self.assertRaisesRegex(FetchError, reason):
                shopify_price(SHOP + suffix, FakeClient([{"currency": "USD"}, product]))

    def test_usd_offer_needs_no_conversion_and_foreign_offer_is_labelled(self):
        price = {"amount": 857, "currency": "CAD", "from": False}
        rate = {"base": "CAD", "quote": "USD", "rate": 0.70277, "date": "2026-10-09"}
        client, rates = FakeClient([rate]), {}
        native = {"amount": 600, "currency": "USD"}
        self.assertEqual(usd_price(native, client, rates, NOW), native)
        self.assertEqual(client.calls, [])
        converted = usd_price(price, client, rates, NOW)
        self.assertEqual(converted["amount"], 602.27)
        self.assertEqual(converted["currency"], "USD")
        self.assertTrue(converted["estimate"])
        self.assertEqual(converted["original_amount"], 857)
        self.assertEqual(converted["original_currency"], "CAD")
        self.assertEqual(converted["fx_date"], "2026-10-09")
        self.assertEqual(usd_price(price, client, rates, NOW), converted)
        self.assertEqual(len(client.calls), 1)

    def test_bad_exchange_rates_do_not_display_foreign_or_guessed_prices(self):
        price = {"amount": 100, "currency": "CAD"}
        rate = {"base": "CAD", "quote": "USD", "rate": 0.7, "date": "2026-10-09"}
        for changes in ({"date": "2026-09-01"}, {"date": "2026-10-12"}, {"date": "bad"},
                        {"base": "USD"}, {"quote": "CAD"}, {"rate": 0}, {"rate": "0.7"}):
            with self.assertRaises(FetchError):
                usd_price(price, FakeClient([{**rate, **changes}]), {}, NOW)
        feed = build_feed([{"name": "Mask", "link": SHOP, "price_source": "shopify"}],
                          FakeClient([{"currency": "CAD"}, {"variants": [variant(1, 85700)]}, FetchError("network_error")]),
                          env={}, clock=lambda: NOW)
        self.assertEqual(feed["items"][SHOP]["status"], "unavailable")
        self.assertNotIn("amount", feed["items"][SHOP])

    def test_invalid_prices_never_become_zero_or_guessed_currency(self):
        for price in (0, -1, "11900", None, float("nan")):
            with self.assertRaises(FetchError):
                shopify_price(SHOP, FakeClient([{"currency": "USD"}, {"variants": [variant(1, price)]}]))
        with self.assertRaises(FetchError):
            shopify_price(SHOP, FakeClient([{"currency": "$"}, {"variants": [variant(1, 100)]}]))

    def test_amazon_identity_and_restrictions(self):
        self.assertEqual(amazon_identity(AMAZON), ("B08KG4QVCT", "owner-20"))
        for link in (AMAZON.replace("amazon.com", "amazon.com.evil.test"), AMAZON.split("?")[0]):
            with self.assertRaises(FetchError):
                amazon_identity(link)
        result = amazon_price({"offersV2": {"listings": [offer()]}})
        self.assertEqual(result["amount"], 249.99)
        for change in ({"violatesMAP": True}, {"violatesMAP": None},
                       {"condition": {"value": "Used"}}, {"type": "SUBSCRIBE_AND_SAVE"},
                       {"dealDetails": {"accessType": "PRIME_EXCLUSIVE"}},
                       {"availability": {"type": "OUT_OF_STOCK"}}, {"price": None}):
            with self.assertRaisesRegex(FetchError, "no_public_offer"):
                amazon_price({"offersV2": {"listings": [offer(**change)]}})

    def test_amazon_token_reuse_request_and_asin_matching(self):
        correct = {"asin": "B08KG4QVCT", "offersV2": {"listings": [offer()]}}
        response = {"itemsResult": {"items": [{"asin": "B07YXR7KJ2"}, correct]}}
        client = FakeClient([{"access_token": "private-token"}, response, response])
        api = Amazon(client, {"AMAZON_CREATORS_CLIENT_ID": "private-id", "AMAZON_CREATORS_CLIENT_SECRET": "private-secret"})
        self.assertEqual(api.item("B08KG4QVCT", "owner-20"), correct)
        self.assertEqual(api.item("B08KG4QVCT", "owner-20"), correct)
        self.assertEqual(len(client.calls), 3)
        url, body, headers = client.calls[1]
        self.assertEqual(url, "https://creatorsapi.amazon/catalog/v1/getItems")
        self.assertEqual(body["condition"], "New")
        self.assertEqual(body["currencyOfPreference"], "USD")
        self.assertEqual(body["partnerTag"], "owner-20")
        self.assertEqual(headers["x-marketplace"], "www.amazon.com")
        self.assertEqual(headers["Authorization"], "Bearer private-token")

    def test_partial_failures_missing_credentials_and_legacy_rows(self):
        rows = [{"name": "Book", "link": SHOP, "price_source": "shopify"},
                {"name": "Amazon", "link": AMAZON, "price_source": "amazon"},
                {"name": "Legacy", "link": "https://example.test", "price": "$100"}]
        feed = build_feed(rows, FakeClient([{"currency": "USD"}, {"variants": [variant(1, 11900)]}]),
                          env={}, clock=lambda: NOW)
        self.assertEqual(feed["items"][SHOP]["amount"], 119)
        self.assertEqual(feed["items"][SHOP]["checked_at"], "2026-10-11T12:00:00Z")
        self.assertEqual(feed["items"][SHOP]["expires_at"], "2026-10-12T11:00:00Z")
        self.assertEqual(feed["items"][AMAZON]["reason"], "api_not_configured")
        self.assertNotIn("amount", feed["items"][AMAZON])
        self.assertEqual(len(feed["items"]), 2)
        failed = build_feed(rows[:1], FakeClient([FetchError("http_503")]), env={}, clock=lambda: NOW)
        self.assertEqual(failed["items"][SHOP]["status"], "unavailable")
        self.assertNotIn("amount", failed["items"][SHOP])

    def test_amazon_feed_never_contains_credentials_or_raw_response(self):
        item = {"asin": "B08KG4QVCT", "offersV2": {"listings": [offer()]}, "private_extra": "do-not-publish"}
        client = FakeClient([{"access_token": "private-token"}, {"itemsResult": {"items": [item]}}])
        feed = build_feed([{"name": "Pedal", "link": AMAZON, "price_source": "amazon"}], client,
                          env={"AMAZON_CREATORS_CLIENT_ID": "private-id", "AMAZON_CREATORS_CLIENT_SECRET": "private-secret"}, clock=lambda: NOW)
        self.assertEqual(feed["items"][AMAZON]["amount"], 249.99)
        for secret in ("private-id", "private-secret", "private-token", "do-not-publish"):
            self.assertNotIn(secret, json.dumps(feed))


if __name__ == "__main__":
    unittest.main()
