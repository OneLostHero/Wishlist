# Wishlist

A gift wishlist rendered as a card grid on GitHub Pages. All content lives in `items.csv` — `index.html` fetches and renders it in the browser. No build step, no dependencies.

## How to add / edit items

Edit `items.csv`, commit, push. GitHub Pages redeploys automatically (give it a minute).

### CSV columns

The header row must be line 1: `name,price,note,link,image`. Columns are matched by header name, so order technically doesn't matter — but keep the standard order for sanity.

#### `name` (required)

The card title. Plain text, any characters. If it contains a comma, quote it.

- ✅ `Noise-cancelling headphones`
- ✅ `"Socks, wool, size M"` (comma → quoted)
- ❌ `Socks, wool, size M` unquoted — the commas split it into three columns and shift everything after it
- ❌ empty — renders a card with no title

#### `price` (optional)

Free text, shown on the little gift tag. It is **not** parsed as a number, so anything readable works.

- ✅ `~$120` · `$30–50` · `under $25` · `any amount`
- ✅ empty — the tag is simply omitted
- ❌ `$1,200` unquoted — the comma splits the field; write `"$1,200"`

#### `note` (optional)

Short description under the title: size, color, context. This is the field most likely to contain commas — quote it whenever in doubt.

- ✅ `"For the commute — any color but white."`
- ✅ `"He said ""no more mugs"" but here we are"` (literal quotes doubled)
- ❌ `For the commute, any color` unquoted — splits at the comma

#### `link` (optional)

Full URL to the product page. Becomes the "View item →" link; omitted if empty.

- ✅ `https://example.com/product/123`
- ✅ empty — card renders without a link
- ❌ `example.com/product/123` — no `https://`, so the browser treats it as a relative path on the wishlist site and the link 404s
- ❌ `www.amazon.com/dp/XYZ` — same problem; always include the scheme

#### `image` (optional)

Full URL to a photo. Shown as a 4:3 cover image at the top of the card; if the URL is broken the image is silently removed and the card renders text-only.

- ✅ `https://images.unsplash.com/photo-...?w=800&q=70`
- ✅ empty — text-only card (like the gift card example)
- ❌ `photo.jpg` or any relative path — images aren't stored in this repo, use a full URL
- ❌ a product *page* URL — must point at an actual image file, not the page containing it

### Quoting rules (RFC 4180)

- Wrap a field in double quotes if it contains a comma, a double quote, or a line break: `"For the commute — any color but white."`
- Inside a quoted field, write a literal `"` as `""`: `"a ""quoted"" word"`
- One item per line; blank lines are ignored.
- Don't use single quotes for quoting — only `"` counts.

Example rows:

```csv
Pour-over coffee kit,$30–50,"Kettle already owned — just the dripper and filters.",https://example.com/item,https://example.com/photo.jpg
Bookstore gift card,any amount,"Always a safe bet — no photo needed.",https://example.com/card,
```

## Notes for AI assistants

- **Adding/removing/changing items → edit `items.csv` only.** Do not hardcode items into `index.html`.
- Edit `index.html` only for styling or layout changes.
- The CSV parser in `index.html` is RFC-4180-ish (quoted fields, `""` escapes, CRLF). Don't replace it with `split(",")`.
- Column headers are matched by name, so column order doesn't matter — but don't rename them without updating `index.html`.

## Previewing locally

`fetch()` doesn't work from `file://`, so open the page through a local server:

```sh
python -m http.server
# then visit http://localhost:8000
```
