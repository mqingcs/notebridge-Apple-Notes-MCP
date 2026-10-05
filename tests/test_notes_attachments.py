import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apple_notes_mcp import server as m
from apple_notes_mcp import writes as w
from apple_notes_mcp.attachments import MAX_BYTES


class Attachments(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.b = m.Backend(
            ROOT / "fixtures/synthetic.json",
            folders=["folder-demo"],
            write_enabled=True,
            experimental_attachments=True,
            backup_dir=Path(self.tmp.name) / "backups",
        )
        self.s = m.Service(self.b)
        self.id = "notes://fixture/a"

    def call(self, name, **args):
        return self.s.call("apple_notes_" + name, args)

    def ver(self):
        return self.call("prepare_edit", id=self.id)["version"]

    def add(self, data=b"synthetic attachment\n", filename="example.txt", **kwargs):
        return self.call(
            "add_attachment",
            id=self.id,
            expected_version=kwargs.get("expected_version", self.ver()),
            filename=filename,
            data_base64=base64.b64encode(data).decode(),
        )

    def test_add_list_read_roundtrip_and_metadata_backup(self):
        before = copy.deepcopy(self.b.fixture["notes"][0])
        a = self.add()
        r = self.call("get_attachment", id=self.id, attachment_id=a["attachment_id"])
        self.assertEqual(r["text"], "synthetic attachment\n")
        self.assertEqual(r["sha256"], hashlib.sha256(b"synthetic attachment\n").hexdigest())
        listed = self.call("list_attachments", id=self.id)
        self.assertEqual(listed["total"], 1)
        self.assertNotIn("data_base64", json.dumps(listed))
        self.assertEqual(before["text"], self.b.fixture["notes"][0]["text"])
        saved = json.loads(next(self.s.writer.backup_dir.glob("*.json")).read_text())
        self.assertEqual(saved["snapshot"]["attachment_count"], 0)
        self.assertFalse(a["removal_supported"])

    def test_second_add_preserves_first_and_paginates(self):
        a = self.add()
        b = self.add(b"second", "two.txt")
        p = self.call("list_attachments", id=self.id, limit=1)
        q = self.call("list_attachments", id=self.id, offset=p["next_offset"], limit=1)
        self.assertEqual(p["attachments"][0]["id"], a["attachment_id"])
        self.assertEqual(q["attachments"][0]["id"], b["attachment_id"])
        self.assertIsNone(q["next_offset"])
        self.assertEqual(
            self.call("get_attachment", id=self.id, attachment_id=a["attachment_id"])["bytes"], 21
        )

    def test_attachment_data_never_leaks_in_note_get_list_or_backup(self):
        self.add(b"UNIQUE_PRIVATE_ATTACHMENT_SENTINEL")
        self.add(b"other", "two.txt")
        self.assertNotIn("UNIQUE_PRIVATE_ATTACHMENT", json.dumps(self.call("get", id=self.id)))
        self.assertNotIn("data_base64", json.dumps(self.call("get", id=self.id)))
        self.assertNotIn("attachments", json.dumps(self.call("list")))
        for p in self.s.writer.backup_dir.glob("*.json"):
            self.assertNotIn("data_base64", p.read_text())
            self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o600)

    def test_filename_path_control_rejected(self):
        for name in ["../runtime.key", "/tmp/key", ".hidden", "x/y", "x\\y", "a:b", "\x00x", "  "]:
            with self.assertRaises(m.NotesError):
                self.add(filename=name)
        self.assertFalse(self.s.writer.backup_dir.exists())

    def test_invalid_empty_and_oversize_base64(self):
        for encoded in [
            "%%%%",
            "AAAA\n",
            "====",
            base64.b64encode(b"x" * (MAX_BYTES + 1)).decode(),
        ]:
            with self.assertRaises(m.NotesError):
                self.call(
                    "add_attachment",
                    id=self.id,
                    expected_version=self.ver(),
                    filename="x",
                    data_base64=encoded,
                )
        self.assertFalse(self.s.writer.backup_dir.exists())

    def test_read_bound_and_other_note_rejected(self):
        a = self.add()
        with self.assertRaises(m.NotesError):
            self.call("get_attachment", id=self.id, attachment_id=a["attachment_id"], max_bytes=1)
        with self.assertRaises(m.NotesError):
            self.call("get_attachment", id="notes://fixture/b", attachment_id=a["attachment_id"])

    def test_locked_shared_outside_scope(self):
        for ident in ["notes://fixture/private", "notes://fixture/locked"]:
            with self.assertRaises(m.NotesError):
                self.call("list_attachments", id=ident)
        self.b.fixture["notes"][0]["shared"] = True
        with self.assertRaises(m.NotesError):
            self.add()
        with self.assertRaises(m.NotesError):
            self.call("list_attachments", id=self.id)

    def test_stale_version_and_backup_failure_no_add(self):
        old = self.ver()
        self.add()
        with self.assertRaisesRegex(m.NotesError, "Version conflict"):
            self.add(expected_version=old)
        before = copy.deepcopy(self.b.fixture)
        with patch.object(self.s.writer, "backup", side_effect=OSError("full")):
            with self.assertRaises(OSError):
                self.add(b"more", "two.txt")
        self.assertEqual(before, self.b.fixture)

    def test_attachment_manifest_changes_version_even_same_count(self):
        self.add()
        old = self.ver()
        self.b.fixture["notes"][0]["attachments"][0]["modified_at"] = "changed"
        self.assertNotEqual(old, self.ver())

    def test_body_restore_and_edit_blocked_after_add(self):
        a = self.add()
        for name, extra in [
            ("restore", {"backup_id": a["backup_id"]}),
            ("edit", {"content": "new", "format": "text"}),
            ("append", {"text": "new"}),
        ]:
            with self.assertRaisesRegex(m.NotesError, "attachments"):
                self.call(name, id=self.id, expected_version=self.ver(), **extra)

    def test_private_transfer_cleanup_and_symlink_export_rejection(self):
        with self.s.attachments.temp() as tmp:
            self.assertEqual(stat.S_IMODE(Path(tmp).stat().st_mode), 0o700)
            f = Path(tmp) / "export"
            f.write_bytes(b"abc")
            self.assertEqual(self.s.attachments.read_export(f, 3), b"abc")
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
            with self.assertRaises(m.NotesError):
                self.s.attachments.read_export(f, 2)
            link = Path(tmp) / "link"
            link.symlink_to(f)
            with self.assertRaises(OSError):
                self.s.attachments.read_export(link, 3)
        self.assertFalse(Path(tmp).exists())

    def test_default_off_and_no_paths_or_delete_tools(self):
        readonly = m.Service(m.Backend(ROOT / "fixtures/synthetic.json", folders=["folder-demo"]))
        with self.assertRaises(m.NotesError):
            readonly.call("apple_notes_add_attachment", {})
        self.assertEqual(len(self.s.tools), 17)
        for t in self.s.tools:
            self.assertNotIn("file_path", t["inputSchema"]["properties"])
            self.assertNotIn("export_path", t["inputSchema"]["properties"])
        self.assertNotIn("apple_notes_delete_attachment", self.s.tool_map)

    def test_legacy_backup_hash_stays_compatible(self):
        snap = {
            "id": "x",
            "folder_id": "f",
            "title": "t",
            "modified_at": "now",
            "body_html": "b",
            "attachment_count": 0,
            "shared": False,
            "locked": False,
        }
        expected = hashlib.sha256(
            json.dumps(snap, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        self.assertEqual(w.version(snap), expected)

    def test_real_gate_before_any_attachment_transfer(self):
        service = m.Service(
            m.Backend(real=True, folders=["f"], write_enabled=True, experimental_attachments=True)
        )
        with patch.dict(os.environ, {}, clear=True), patch.object(service.backend, "run") as run:
            with self.assertRaises(m.NotesError):
                service.call("apple_notes_list_attachments", {"id": "x"})
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
