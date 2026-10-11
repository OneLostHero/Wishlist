"""Wishlist with shared, persistent tentative claims. Python standard library only."""
import argparse
import csv
import hashlib
import json
import re
import secrets
import sqlite3
import unicodedata
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent


def item_statuses(root):
    result = {}
    with (root / "items.csv").open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            row = {key.strip(): (value or "").strip() for key, value in row.items() if key}
            name = row.get("name", "")
            if not name:
                continue
            normalized = re.sub(r"[\u0300-\u036f]", "", unicodedata.normalize("NFKD", name)).lower()
            base = "item-" + (re.sub(r"[^a-z0-9]+", "-", normalized).strip("-") or "gift")
            slug, suffix = base, 2
            while slug in result:
                slug, suffix = f"{base}-{suffix}", suffix + 1
            result[slug] = row.get("status", "")
    return result


def make_server(host, port, root=ROOT, database=None):
    root = Path(root)
    database = Path(database or root / ".wishlist" / "claims.sqlite3")
    database.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE IF NOT EXISTS claims (item TEXT PRIMARY KEY, token_hash TEXT NOT NULL)")

    class Handler(BaseHTTPRequestHandler):
        def json_response(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def read_claims(self):
            with closing(sqlite3.connect(database)) as db, db:
                return [row[0] for row in db.execute("SELECT item FROM claims ORDER BY item")]

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/claims":
                return self.json_response(200, {"claims": self.read_claims()})
            # Serve only public site files, never the database, repository or logs.
            public = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/index.html": ("index.html", "text/html; charset=utf-8"),
                      "/items.csv": ("items.csv", "text/csv; charset=utf-8"),
                      "/LICENSE": ("LICENSE", "text/plain; charset=utf-8")}
            if path not in public:
                return self.json_response(404, {"error": "Not found"})
            filename, mime = public[path]
            try:
                body = (root / filename).read_bytes()
            except OSError:
                return self.json_response(404, {"error": "Not found"})
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if urlsplit(self.path).path != "/api/claims":
                return self.json_response(404, {"error": "Not found"})
            origin = self.headers.get("Origin")
            if origin and (origin == "null" or urlsplit(origin).netloc != self.headers.get("Host")):
                return self.json_response(403, {"error": "Use the wishlist page to make changes."})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.json_response(415, {"error": "Expected JSON"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    raise ValueError()
                data = json.loads(self.rfile.read(length))
                item, token, action = data["item"], data["token"], data["action"]
                if not isinstance(item, str) or not isinstance(token, str) or not 32 <= len(token) <= 128 or action not in ("claim", "release"):
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                return self.json_response(400, {"error": "Invalid claim request"})
            statuses = item_statuses(root)
            if item not in statuses:
                return self.json_response(404, {"error": "This item is no longer on the wishlist."})
            if action == "claim" and statuses[item] in ("claimed", "bought"):
                return self.json_response(409, {"error": "This item is already claimed or bought."})
            digest = hashlib.sha256(token.encode()).hexdigest()
            with closing(sqlite3.connect(database)) as db, db:
                db.execute("BEGIN IMMEDIATE")
                existing = db.execute("SELECT token_hash FROM claims WHERE item = ?", (item,)).fetchone()
                if existing and not secrets.compare_digest(existing[0], digest):
                    return self.json_response(409 if action == "claim" else 403,
                                              {"error": "Someone else has marked this as possibly taken."})
                if action == "release":
                    db.execute("DELETE FROM claims WHERE item = ?", (item,))
                elif not existing:
                    db.execute("INSERT INTO claims VALUES (?, ?)", (item, digest))
            self.json_response(200, {"claims": self.read_claims()})

    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    with make_server(args.host, args.port) as server:
        print(f"Ryan's wishlist is running at http://{args.host}:{args.port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
