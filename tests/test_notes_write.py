import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apple_notes_mcp import server as m


class Writes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.backups = Path(self.tmp.name) / "backups"
        self.backend = m.Backend(
            ROOT / "fixtures/synthetic.json",
            folders=["folder-demo"],
            write_enabled=True,
            backup_dir=self.backups,
        )
        self.service = m.Service(self.backend)
        self.ident = "notes://fixture/a"

    def call(self, name, **args):
        return self.service.call("apple_notes_" + name, args)

    def token(self, ident=None):
        return self.call("prepare_edit", id=ident or self.ident)["version"]

    def test_create_append_edit_rename_restore(self):
        created = self.call(
            "create", folder_id="folder-demo", title="Synthetic test", text="Original content"
        )
        ident = created["id"]
        appended = self.call(
            "append", id=ident, expected_version=self.token(ident), text="Additional content"
        )
        self.assertIn(
            "Additional content", self.service.call("apple_notes_get", {"id": ident})["text"]
        )
        restored = self.call(
            "restore", id=ident, expected_version=self.token(ident), backup_id=appended["backup_id"]
        )
        self.assertNotIn(
            "Additional content", self.service.call("apple_notes_get", {"id": ident})["text"]
        )
        self.assertNotEqual(restored["backup_id"], appended["backup_id"])
        self.call(
            "edit",
            id=ident,
            expected_version=self.token(ident),
            content="<ul><li><b>Item</b></li></ul>",
            format="html",
        )
        self.call("rename", id=ident, expected_version=self.token(ident), title="New title")
        self.assertEqual(self.call("prepare_edit", id=ident)["title"], "New title")
        self.assertEqual(len(list(self.backups.iterdir())), 4)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in self.backups.iterdir()))

    def test_real_create_does_not_duplicate_notes_generated_title(self):
        backend = m.Backend(real=True, folders=["folder-demo"], write_enabled=True)
        service = m.Service(backend)
        with (
            patch.dict(os.environ, {"NOTES_ALLOW_WRITE": "1"}),
            patch.object(backend, "run", return_value={"created": True}) as run,
        ):
            service.call(
                "apple_notes_create",
                {"folder_id": "folder-demo", "title": "Unique title", "text": "Original body"},
            )
        self.assertEqual(run.call_args.kwargs["body_html"], "<div>Original body</div>")
        self.assertEqual(run.call_args.kwargs["title"], "Unique title")

    def test_stale_version_does_not_change_or_create_backup(self):
        old = self.token()
        self.backend.fixture["notes"][0]["text"] += " outside edit"
        before = copy.deepcopy(self.backend.fixture)
        with self.assertRaisesRegex(m.NotesError, "Version conflict"):
            self.call("append", id=self.ident, expected_version=old, text="new")
        self.assertEqual(self.backend.fixture, before)
        self.assertFalse(self.backups.exists())

    def test_locked_excluded_shared_attachment_and_scope_guards(self):
        for ident in ["notes://fixture/private", "notes://fixture/locked"]:
            with self.assertRaises(m.NotesError):
                self.token(ident)
        for operation, extra in [
            ("create", {"title": "x", "text": "y"}),
            ("move", {"id": self.ident, "expected_version": self.token()}),
        ]:
            with self.assertRaises(m.NotesError):
                self.call(operation, folder_id="folder-private", **extra)
        row = self.backend.fixture["notes"][0]
        row["shared"] = True
        with self.assertRaises(m.NotesError):
            self.call("rename", id=self.ident, expected_version=self.token(), title="x")
        row["shared"] = False
        row["attachment_count"] = 1
        with self.assertRaises(m.NotesError):
            self.call("append", id=self.ident, expected_version=self.token(), text="x")

    def test_empty_and_active_html_replacements_blocked(self):
        original = copy.deepcopy(self.backend.fixture)
        for content, fmt in [
            ("  \n\u200b", "text"),
            ("<div><br></div>", "html"),
            ("<script>alert(1)</script>", "html"),
            ('<img src="https://example.org/track">', "html"),
            ('<div onclick="x">text</div>', "html"),
            ("<b>unbalanced", "html"),
        ]:
            with self.assertRaises(m.NotesError):
                self.call(
                    "edit",
                    id=self.ident,
                    expected_version=self.token(),
                    content=content,
                    format=fmt,
                )
        self.assertEqual(original, self.backend.fixture)
        self.assertFalse(self.backups.exists())

    def test_backup_failure_prevents_mutation(self):
        before = copy.deepcopy(self.backend.fixture)
        with patch.object(
            self.service.writer, "backup", side_effect=OSError("synthetic storage failure")
        ):
            with self.assertRaises(OSError):
                self.call("append", id=self.ident, expected_version=self.token(), text="x")
        self.assertEqual(before, self.backend.fixture)

    def test_unsafe_backup_permissions_and_traversal_blocked(self):
        self.backups.mkdir(mode=0o755)
        self.backups.chmod(0o755)
        with self.assertRaises(m.NotesError):
            self.call("rename", id=self.ident, expected_version=self.token(), title="x")
        with self.assertRaises(m.NotesError):
            self.call(
                "restore", id=self.ident, expected_version=self.token(), backup_id="../runtime.key"
            )

    def test_restore_cannot_target_another_note(self):
        change = self.call("append", id=self.ident, expected_version=self.token(), text="extra")
        other = "notes://fixture/b"
        with self.assertRaises(m.NotesError):
            self.call(
                "restore",
                id=other,
                expected_version=self.token(other),
                backup_id=change["backup_id"],
            )

    def test_move_only_between_explicitly_allowed_folders(self):
        self.backend.folders.append("folder-private")
        result = self.call(
            "move", id=self.ident, expected_version=self.token(), folder_id="folder-private"
        )
        self.assertTrue(result["changed"])
        self.assertEqual(self.call("prepare_edit", id=self.ident)["folder_id"], "folder-private")

    def test_annotations_and_no_delete_or_default_write_exposure(self):
        self.assertEqual(len(self.service.tools), 14)
        for tool in self.service.tools:
            if tool["name"] in [
                "apple_notes_create",
                "apple_notes_append",
                "apple_notes_edit",
                "apple_notes_rename",
                "apple_notes_move",
                "apple_notes_restore",
            ]:
                self.assertFalse(tool["annotations"]["readOnlyHint"])
        for name in ["delete", "remove", "clear", "unlock", "shell", "run_script"]:
            with self.assertRaises(m.NotesError):
                self.call(name)
        read_only = m.Service(m.Backend(ROOT / "fixtures/synthetic.json", folders=["folder-demo"]))
        self.assertEqual(len(read_only.tools), 6)
        with self.assertRaises(m.NotesError):
            read_only.call(
                "apple_notes_create", {"folder_id": "folder-demo", "title": "x", "text": "y"}
            )

    def test_body_does_not_leak_through_metadata_or_unbounded_get(self):
        new = self.call("create", folder_id="folder-demo", title="plain", text="BODY_SENTINEL")
        metadata = self.service.call("apple_notes_list", {})
        self.assertNotIn("BODY_SENTINEL", json.dumps(metadata))
        self.assertNotIn("body_html", json.dumps(metadata))
        got = self.service.call("apple_notes_get", {"id": new["id"], "max_chars": 3})
        self.assertEqual(len(got["text"]), 3)
        self.assertNotIn("body_html", got)

    def test_real_write_requires_separate_runtime_gate(self):
        b = m.Backend(real=True, folders=["folder-demo"], write_enabled=True)
        with (
            patch.dict(os.environ, {"NOTES_ALLOW_REAL": "1"}, clear=True),
            patch.object(m.subprocess, "run") as run,
        ):
            with self.assertRaises(m.NotesError):
                m.Service(b).call(
                    "apple_notes_create", {"folder_id": "folder-demo", "title": "x", "text": "y"}
                )
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
