import csv
import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import ROOT, make_server


class ClaimsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ("index.html", "items.csv", "LICENSE"):
            shutil.copyfile(ROOT / name, self.root / name)
        self.start_server()

    def start_server(self):
        self.server = make_server("127.0.0.1", 0, self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def tearDown(self):
        self.stop_server()
        self.temp.cleanup()

    def request(self, path="/api/claims", action=None, token="a" * 64, origin=None):
        headers = {}
        body = None
        if action:
            body = json.dumps({"item": "item-majora-s-mask-wooden-replica", "token": token, "action": action}).encode()
            headers["Content-Type"] = "application/json"
        if origin:
            headers["Origin"] = origin
        try:
            response = urlopen(Request(self.url + path, data=body, headers=headers), timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.read()

    def test_shared_claim_persistence_conflict_and_undo(self):
        self.assertEqual(json.loads(self.request()[1]), {"claims": []})
        self.assertEqual(self.request(action="claim")[0], 200)
        # Retrying the same visitor's request is safe.
        self.assertEqual(self.request(action="claim")[0], 200)
        self.assertEqual(self.request(action="claim", token="b" * 64)[0], 409)
        self.assertEqual(self.request(action="release", token="b" * 64)[0], 403)
        self.stop_server()
        self.start_server()
        self.assertEqual(json.loads(self.request()[1]), {"claims": ["item-majora-s-mask-wooden-replica"]})
        self.assertEqual(self.request(action="release")[0], 200)
        self.assertEqual(json.loads(self.request()[1]), {"claims": []})

    def test_private_files_cross_origin_and_csv_status(self):
        for path in ("/.git/config", "/.wishlist/claims.sqlite3", "/server.py", "/../README.md"):
            self.assertEqual(self.request(path)[0], 404)
        self.assertEqual(self.request(action="claim", origin="https://unrelated.test")[0], 403)
        self.assertEqual(self.request(action="claim", token="short")[0], 400)
        self.assertEqual(self.request("/")[0], 200)
        with (self.root / "items.csv").open(encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            fields, items = reader.fieldnames, list(reader)
        next(item for item in items if item["name"] == "Majora's Mask wooden replica")["status"] = "bought"
        with (self.root / "items.csv").open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fields)
            writer.writeheader()
            writer.writerows(items)
        self.assertEqual(self.request(action="claim")[0], 409)


if __name__ == "__main__":
    unittest.main()
