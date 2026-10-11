# Ryan's wishlist

Ryan's wishlist: a personal gift list with a dark, grown-up gift-tag design. Item content lives in `items.csv`; shared "Possibly taken" marks are saved by `server.py` in a local SQLite database. The public site refreshes retailer prices during its scheduled deployment. No third-party dependencies. Requires Python 3.10 or later for the server and price updater.

Public wishlist: **https://onelosthero.github.io/Wishlist/**. The GitHub Pages version displays the list and owner-managed claimed statuses. Visitor marking is available when running the local Python server.

This is our own version of [Wishlist](https://github.com/Lickitysplitted/Wishlist) by **Lickitysplitted**. See [Credits & license](#credits--license).

## How to add / edit items

Edit `items.csv`, then refresh the local page. To update the public site, commit and push to `main`; the Publish wishlist workflow checks and deploys the site automatically. Change an item's `status` to `claimed` or `bought` to mark it publicly, or clear the field to make it available again.

### CSV columns

The header row must be line 1: `name,price,note,link,image,category,priority,status,price_source`. Columns after `image` are optional: existing five-column files still work, preserving their content and original order under the default sort. Columns are matched by header name, so order technically doesn't matter — but keep the standard order for sanity.

#### `name` (required)

The card title. Plain text, any characters. If it contains a comma, quote it.

- ✅ `Noise-cancelling headphones`
- ✅ `"Socks, wool, size M"` (comma → quoted)
- ❌ `Socks, wool, size M` unquoted — the commas split it into three columns and shift everything after it
- ❌ empty — the row is skipped

#### `price` (optional)

For manual prices (blank `price_source`), free text shown on the little gift tag exactly as written. Use **USD** for new manual numeric prices. Legacy manual text is preserved without trying to interpret or convert it. Price sorting uses the **first number** (including decimals and comma-grouped thousands); prices with no number go last within their availability group. An automatic source overrides this field and never falls back to an undated manual price.

- ✅ `~$120` · `$30–50` · `under $25` · `any amount`
- ✅ empty — the tag is simply omitted
- ❌ `$1,200` unquoted — the comma splits the field; write `"$1,200"`

#### `price_source` (optional)

- `shopify` — fetch the linked Shopify product using its public Ajax product API, requesting `currency=USD` on both product and cart routes and verifying the returned currency. Include `?variant=...` in the link to choose an exact variant (combine with `&currency=USD` for USD store links). Without a variant, the lowest available price is shown with “From” when available variants have different prices.
- `amazon` — fetch an Amazon.com `/dp/ASIN` or `/gp/product/ASIN` link through Amazon Creators API. The URL must include the Associates `tag`. Requires eligible API access and the two repository secrets described below. Only public, new-condition offers are displayed; restricted, membership, subscription and temporary deal prices are omitted.
- Blank — keep the original manual `price` behavior, including text such as `Varies by volume / edition`. Use this for a whole series, gift cards, or retailers without an integration.

Automatic prices are always displayed and sorted in **USD**, with a time checked. The store's own USD offer takes priority. If a Shopify store only returns another currency, the updater converts it using [Frankfurter's daily exchange-rate API](https://frankfurter.dev/) and marks the amount with `≈`, the store's currency and the rate date. Rates older than seven days, future dates, invalid responses or failed conversions hide the price instead of displaying another currency or guessing. No conversion is needed for the current mask ($600 USD) or civilization book ($119 USD), as checked on October 11, 2026. Amazon is explicitly requested in USD; unexpected foreign-currency Amazon offers are omitted.

If the source fails, is unavailable, or is too old, the card asks the visitor to check the store. No zero, guessed price, or stale manual price replaces a failed lookup. Future integrations belong in `refresh_prices.py`; a retailer URL alone does not guarantee that it exposes an accessible price feed.

#### `note` (optional)

Short description under the title: size, color, context. This is the field most likely to contain commas — quote it whenever in doubt.

- ✅ `"For the commute — any color but white."`
- ✅ `"He said ""no more mugs"" but here we are"` (literal quotes doubled)
- ❌ `For the commute, any color` unquoted — splits at the comma

#### `link` (optional)

Full URL to the product page. Becomes the "View item →" link; omitted if empty.

- ✅ `https://example.com/product/123`
- ✅ empty — card renders without a link
- ❌ `example.com/product/123` — no `https://`, so the product link is omitted
- ❌ `www.amazon.com/dp/XYZ` — same problem; always include the scheme

Amazon links use Ryan's Associates tracking ID, `onelosthero0d-20`. Preserve the `tag=onelosthero0d-20` query parameter when editing these URLs. All item links display "View item ↗"; tagged Amazon links retain `rel="sponsored noopener"` and the same destination on the photo and product link. Keep the affiliate disclosure above the list when publishing affiliate links.

#### `image` (optional)

Full URL to a photo. The full photo fits inside a 4:3 area at the top of the card; if the URL is broken the image is silently removed and the card renders text-only.

- ✅ `https://images.unsplash.com/photo-...?w=800&q=70`
- ✅ empty — text-only card (like the gift card example)
- ❌ `photo.jpg` or any relative path — images aren't stored in this repo, use a full URL
- ❌ a product *page* URL — must point at an actual image file, not the page containing it

#### `category` (optional)

Free text, shown above the title and used to build filter chips. Each distinct nonempty category gets a chip; spelling and capitalization matter.

- ✅ `Collectibles` · `Books` · `Home & hobbies`
- ✅ empty — shown under “All wishes”, without a category label
- ✅ `"Tools, parts & gear"` (comma → quoted)

#### `priority` (optional)

Controls the “Most wanted” sort. Ties keep their CSV order.

- ✅ `1` — most wanted, with a ribbon
- ✅ `2` or empty — normal priority (the default)
- ✅ `3` — nice to have
- ❌ other values — treated as `2`

#### `status` (optional)

Use a blank field, `claimed`, or `bought`. Claimed and bought items always follow available items in **every** sort, with a stamp and a greyscale photo. They have no "I might get this" button.

- ✅ empty — available
- ✅ `claimed` — someone has offered to get it
- ✅ `bought` — already purchased
- ❌ other values — treated as blank; use the lowercase values above

"I might get this" saves a shared **Possibly taken** mark and moves the item below available wishes. It does not send a text or change the CSV. The visitor can use "Undo my mark" in the same browser; an anonymous undo token is kept in local storage. Other visitors cannot undo that mark. If storage is blocked, undo works for the current visit only. Marks remain after server restarts and refresh for other visitors every 15 seconds or when they return to the tab. CSV `claimed` and `bought` statuses take precedence.

Back up `.wishlist/claims.sqlite3` to preserve visitor marks. This database and its anonymous tokens are excluded from Git and never served as public files. Names generate item IDs, so renaming an item changes its ID and does not carry its mark across. Clearing browser storage loses that visitor's undo token.

### Quoting rules (RFC 4180)

- Wrap a field in double quotes if it contains a comma, a double quote, or a line break: `"For the commute — any color but white."`
- Inside a quoted field, write a literal `"` as `""`: `"a ""quoted"" word"`
- One item per line; blank lines are ignored.
- Don't use single quotes for quoting — only `"` counts.

Example rows:

```csv
name,price,note,link,image,category,priority,status
Pour-over coffee kit,$30–50,"Kettle already owned — just the dripper and filters.",https://example.com/item,https://example.com/photo.jpg,Kitchen,1,
Bookstore gift card,any amount,"Always a safe bet — no photo needed.",https://example.com/card,,Books,2,
```

## Personalizing the page

Edit the `CONFIG` object at the top of `index.html`:

- `name` — the heading and browser title; defaults to `Ryan's wishlist`.
- `intro` — the short introduction beneath the heading (plain text).
- `contact` — optional `sms:+15551234567` or `mailto:you@example.com` for the header contact link. Blank by default. Gift buttons save a tentative mark and do not use this setting.
- `claimsAPI` — endpoint for visitor marking; automatically disabled on `*.github.io`, where statuses come from the CSV. Set it to an empty string for any other static host, or a hosted API URL when one is available. The local server uses `api/claims`.
- `shareURL` — your full public URL, including any path and trailing slash. Leave blank to share the current page URL.

The header has a wishlist copy button; each card has its own copy button with a `#item-name` anchor. Names generate the anchors, with suffixes for duplicates. Renaming an item changes its anchor. Copying uses `navigator.clipboard` on HTTPS or localhost, with a selectable-link fallback if clipboard access is unavailable.

Dark is the default even on a device set to light mode. Visitors can explicitly choose light with the theme button; that choice is stored in `localStorage`. If storage is blocked, the toggle works for the current visit. No external fonts, libraries, or build tools are required.

## Hosting

The public repository is [OneLostHero/Wishlist](https://github.com/OneLostHero/Wishlist), with GitHub Pages deploying via `.github/workflows/pages.yml`. The workflow publishes only `index.html`, `items.csv`, generated `prices.json` and `LICENSE`. Local databases, credentials, logs, server code and tests are not part of the website artifact.

GitHub Pages displays the list, category filters, sorting, themes, copy links and CSV `claimed`/`bought` stamps. Visitor marking buttons are hidden because Pages cannot run the claims API. Run `server.py` locally for shared tentative marks; those marks are not synchronized with the public CSV. Product photos load from their existing external URLs.

### Automatic price updates

The Publish wishlist workflow runs on pushes, manual dispatch, and at **00:23, 06:23, 12:23 and 18:23 UTC** daily. Each build fetches prices, then deploys the feed and page together. Prices are generated into an ignored file, never committed to Git history. GitHub's schedule can be delayed, and public-repository schedules can be disabled after 60 days without repository activity; check the Actions tab if updates stop and re-enable the workflow when needed.

The browser fetches the feed with caching disabled, refreshes it every 15 minutes while visible and when the tab regains focus, and hides expired values in long-open tabs. Each price expires after **23 hours**, leaving a margin below Amazon's 24-hour content caching limit. Source failures affect only that item and do not prevent the wishlist from publishing. A page with no feed still renders all items. The generated feed deliberately contains only public prices, timestamps, currency and a short status code.

As of October 11, 2026, the mask and civilization book have working Shopify feeds. Amazon's account page reports that this new Associates account is **not yet approved for Creators API**; its documentation also requires 10 qualifying sales in the past 30 days for product-data access. The Amazon integration is implemented and tested with sample responses, but cannot be tested live or activated until Amazon grants access. Amazon item links remain usable and preserve `tag=onelosthero0d-20`.

When eligible, generate North America **3.1** Creators API credentials and add these **GitHub Actions repository secrets**:

- `AMAZON_CREATORS_CLIENT_ID`
- `AMAZON_CREATORS_CLIENT_SECRET`

Then run **Actions → Publish wishlist → Run workflow**. The workflow already passes the secrets to the price updater, so no code change is needed. Never put credentials in the CSV, HTML, generated feed, repository variables or commits. This integration currently supports Amazon.com and USD. Amazon prices include a checked timestamp and the required price/content notices under “Price details.”

API references: [Shopify Ajax products](https://shopify.dev/docs/api/ajax/reference/product), [Amazon Creators API setup and eligibility](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/introduction), [Amazon HTTP requests](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/get-started/using-curl), [OffersV2](https://affiliate-program.amazon.com/creatorsapi/docs/en-us/api-reference/resources/offersV2), and [Amazon content policies](https://affiliate-program.amazon.com/help/operating/policies).

## Notes for AI assistants

- **Adding/removing/changing items → edit `items.csv` only.** Do not hardcode items into `index.html`.
- Edit `index.html` only for configuration, behavior, styling or layout changes.
- The CSV parser in `index.html` is RFC-4180-ish (quoted fields, `""` escapes, CRLF). Don't replace it with `split(",")`.
- Column headers are matched by name, so column order doesn't matter — but don't rename them without updating `index.html`.

## Previewing locally

`fetch()` doesn't work from `file://`, so open the page through a local server:

```sh
python refresh_prices.py
python server.py
# then visit http://localhost:8000
```

The updater fetches once for a local preview; the six-hour schedule runs on GitHub. The server binds to this computer only by default and stays running until stopped. To restart it, run the command above from this folder. For deliberate LAN access, use `python server.py --host 0.0.0.0` and open this computer's LAN address; configure HTTPS for use beyond local development. A localhost copy link only works on this computer.

## Verification

```sh
node tests/verify.cjs
python -m unittest discover -s tests -p 'test_*.py'
```

The Node checks cover current and legacy CSV rendering, filters, sorts, themes, tentative marks/undo, copy-link fallback, current/stale/failed price feeds, USD-only automatic prices, labelled conversions and price expiry in long-open tabs. Python checks cover Shopify currencies/variants, USD preference, exchange-rate dates and failures, Amazon offer restrictions and credential isolation, partial source failures, and the claims server's persistence, undo authorization and private-file isolation. Tests mock retailer responses; run `python refresh_prices.py` to check real source access. Node is only needed for checks, not to run the app.

## Credits & license

- Original project: [Wishlist](https://github.com/Lickitysplitted/Wishlist) by Lickitysplitted (Chris Hawkins). The page design, CSV format and parser, and most of this README come from that project.
- Modified by Promethean Robotics on 2026-10-11: rebranded the title, header, accent colour and footer, added the attribution credit, and rewrote the README intro.
- Modified by Ryan with Codex on 2026-10-11: configured personal branding, added the dark Gift Tag design, optional CSV metadata, filters, sorting, theme selection and gift/share controls. Preserved the original parser and owner-supplied item data.
- Licensed under the GNU General Public License v3.0, the same license as the original. See [`LICENSE`](LICENSE). Any redistribution, including the published Pages site, must keep the credit and the license.
