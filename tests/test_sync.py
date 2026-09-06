import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("dune", Path(__file__).resolve().parents[1] / "scripts/dune.py")
dune = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dune)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "query.sql").write_text("SELECT 2\n")
        self.query = {"id": 8626416, "file": "query.sql"}
        self.remote = {"query_id": 8626416, "owner": "programmablehq", "query_sql": "SELECT 1"}
        self.root_patch = patch.object(dune, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)

    def test_wrong_owner_never_writes(self):
        with patch.object(dune, "request", return_value={**self.remote, "owner": "someone_else"}) as request:
            with self.assertRaisesRegex(ValueError, "owner"):
                dune.sync("push", self.query, "programmablehq")
            self.assertEqual(request.call_count, 1)

    def test_private_query_cannot_be_imported(self):
        with patch.object(dune, "request", return_value={**self.remote, "is_private": True}):
            with self.assertRaisesRegex(ValueError, "public"):
                dune.sync("pull", self.query, "programmablehq")
        self.assertEqual((self.root / "query.sql").read_text(), "SELECT 2\n")

    def test_unchanged_query_does_not_write(self):
        with patch.object(dune, "request", return_value={**self.remote, "query_sql": "SELECT 2\n\n"}) as request:
            dune.sync("push", self.query, "programmablehq")
            self.assertEqual(request.call_count, 1)

    def test_external_edit_prevents_automatic_overwrite(self):
        with patch.object(dune, "request", return_value=self.remote) as request, \
             patch.object(dune, "previous_sql", return_value="SELECT 0"):
            with self.assertRaisesRegex(ValueError, "outside"):
                dune.sync("push", self.query, "programmablehq", "a" * 40)
            self.assertEqual(request.call_count, 1)

    def test_publish_requires_matching_readback(self):
        with patch.object(dune, "request", side_effect=[self.remote, {"query_id": 8626416}, self.remote]):
            with self.assertRaisesRegex(ValueError, "readback"):
                dune.sync("push", self.query, "programmablehq")

    def test_success_updates_only_sql_and_verifies(self):
        with patch.object(dune, "request", side_effect=[self.remote, {"query_id": 8626416},
                          {**self.remote, "query_sql": "SELECT 2\n"}]) as request:
            dune.sync("push", self.query, "programmablehq")
            self.assertEqual(request.call_args_list[1].args, (8626416, {"query_sql": "SELECT 2\n"}))


if __name__ == "__main__":
    unittest.main()
