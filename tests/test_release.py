"""Portable package/CLI regressions; no real Notes calls."""

import contextlib
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from apple_notes_mcp import server as m

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def backend(self, **kwargs):
        return m.Backend(ROOT / "fixtures/synthetic.json", folders=["folder-demo"], **kwargs)

    def test_experimental_tools_are_separate_opt_in(self):
        ordinary = m.Service(self.backend(write_enabled=True))
        experimental = m.Service(self.backend(write_enabled=True, experimental_attachments=True))
        self.assertEqual(len(ordinary.tools), 14)
        self.assertEqual(len(experimental.tools), 17)
        report = ordinary.call("apple_notes_capabilities", {})
        self.assertFalse(report["experimental_attachments_enabled"])
        self.assertNotIn("add_attachment_bytes", report["supported"])
        with self.assertRaises(m.NotesError):
            ordinary.call("apple_notes_add_attachment", {})

    def test_local_consent_command_requires_explicit_real_gate(self):
        with (
            patch.object(sys, "argv", ["apple-notes-mcp", "--notes", "--request-automation"]),
            patch.dict(os.environ, {}, clear=True),
            patch.object(m, "automation_status") as access,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as e:
                m.main()
            self.assertEqual(e.exception.code, 2)
            access.assert_not_called()

    def test_explicit_consent_command_exits_without_serving(self):
        with (
            patch.object(sys, "argv", ["apple-notes-mcp", "--notes", "--request-automation"]),
            patch.dict(os.environ, {"NOTES_ALLOW_REAL": "1"}, clear=True),
            patch.object(m, "automation_status", return_value={"apple_event_status": 0}) as access,
            patch.object(m, "serve") as serve,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as e:
                m.main()
            self.assertEqual(e.exception.code, 0)
            access.assert_called_once_with(ask_user=True)
            serve.assert_not_called()

    def test_adapter_ships_inside_package(self):
        self.assertTrue((Path(m.__file__).parent / "adapter.js").is_file())


if __name__ == "__main__":
    unittest.main()
