import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apple_notes_mcp import server as m


def fixture():
    return m.Backend(ROOT / "fixtures/synthetic.json", folders=["folder-demo"])


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = m.Service(fixture())

    def call(self, name, **args):
        return self.service.call(name, args)

    def test_metadata_no_body_locked_or_outside_scope(self):
        result = self.call("apple_notes_list")
        self.assertEqual(len(result["notes"]), 3)
        self.assertNotIn("text", json.dumps(result))
        self.assertNotIn("locked secret", json.dumps(result))
        self.assertNotIn("excluded note", json.dumps(result))
        self.assertEqual(result["source"], "synthetic")

    def test_pagination_same_timestamp_no_loss(self):
        result, ids = self.call("apple_notes_list", limit=1), []
        while True:
            ids.extend(x["id"] for x in result["notes"])
            if not result["next_cursor"]:
                break
            result = self.call("apple_notes_list", limit=1, cursor=result["next_cursor"])
        self.assertEqual(ids, ["notes://fixture/a", "notes://fixture/b", "notes://fixture/c"])

    def test_title_search_literal_unicode_and_empty(self):
        self.assertEqual(len(self.call("apple_notes_search", query="mcp")["notes"]), 2)
        self.assertEqual(len(self.call("apple_notes_search", query="计划")["notes"]), 1)
        self.assertEqual(self.call("apple_notes_search", query=".*")["notes"], [])
        self.assertEqual(self.call("apple_notes_search", query="里程碑")["notes"], [])
        self.assertEqual(self.call("search", query="missing"), {"results": []})

    def test_body_bounded_get_and_fetch(self):
        result = self.call("apple_notes_get", id="notes://fixture/a", max_chars=5)
        self.assertEqual(len(result["text"]), 5)
        self.assertTrue(result["truncated"])
        self.assertEqual(self.call("fetch", id="notes://fixture/a")["id"], "notes://fixture/a")
        self.assertEqual(len(self.call("search", query="MCP")["results"]), 2)

    def test_locked_outside_scope_and_unknown_id_denied(self):
        for ident in ("notes://fixture/locked", "notes://fixture/private", "absent"):
            with self.assertRaises(m.NotesError):
                self.call("apple_notes_get", id=ident)
        with self.assertRaises(m.NotesError):
            self.call("apple_notes_list", folder_id="folder-private")

    def test_invalid_arguments_rejected(self):
        for args in (
            {"limit": 0},
            {"limit": 51},
            {"limit": True},
            {"limit": "1"},
            {"body": True},
            {"limit": 1.5},
        ):
            with self.assertRaises(m.NotesError):
                self.service.call("apple_notes_list", args)
        for args in ({}, {"query": ""}, {"query": "x" * 513}, {"query": 1}):
            with self.assertRaises(m.NotesError):
                self.service.call("apple_notes_search", args)
        with self.assertRaises(m.NotesError):
            self.call("apple_notes_get", id="notes://fixture/a", max_chars=8001)

    def test_cursor_bound_to_query_and_scope(self):
        c = self.call("apple_notes_search", query="MCP", limit=1)["next_cursor"]
        with self.assertRaises(m.NotesError):
            self.call("apple_notes_search", query="different", cursor=c)
        for bad in ("?", "e30=", "a" * 4096):
            with self.assertRaises(m.NotesError):
                self.call("apple_notes_list", cursor=bad)

    def test_changes_boundary_and_next_watermark(self):
        r = self.call("apple_notes_changes", since="2026-09-10T12:00:00Z", limit=1)
        self.assertIsNone(r["next_since"])
        self.assertFalse(r["includes_deletions"])
        ids = []
        while True:
            ids.extend(x["id"] for x in r["notes"])
            if not r["next_cursor"]:
                break
            r = self.call(
                "apple_notes_changes",
                since="2026-09-10T12:00:00Z",
                limit=1,
                cursor=r["next_cursor"],
            )
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual(r["next_since"], r["as_of"])
        self.assertTrue(r["boundary_inclusive"])

    def test_changes_datetime_validation(self):
        for since in ("not-a-date", "2026-01-01", "2999-01-01T00:00:00Z"):
            with self.assertRaises(m.NotesError):
                self.call("apple_notes_changes", since=since)

    def test_write_tools_absent_and_rejected(self):
        self.assertEqual(len(m.TOOLS), 6)
        for t in m.TOOLS:
            self.assertTrue(t["annotations"]["readOnlyHint"])
            self.assertFalse(t["annotations"]["destructiveHint"])
        for name in ("apple_notes_create", "delete", "update", "unlock", "shell", "run_script"):
            with self.assertRaises(m.NotesError):
                self.call(name)

    def test_note_prompt_injection_is_plain_data(self):
        r = self.call("apple_notes_get", id="notes://fixture/c")
        self.assertIn("Ignore previous instructions", r["text"])
        self.assertEqual(len(m.TOOLS), 6)

    def test_default_real_gate_never_runs_subprocess(self):
        for b in (m.Backend(), m.Backend(real=True, folders=["folder-demo"])):
            with patch.dict(os.environ, {}, clear=True), patch.object(m.subprocess, "run") as run:
                with self.assertRaises(m.NotesError):
                    b.run("metadata")
                run.assert_not_called()

    def test_real_scope_and_permission_fail_closed(self):
        with (
            patch.dict(os.environ, {"NOTES_ALLOW_REAL": "1"}),
            patch.object(m.sys, "platform", "darwin"),
            patch.object(m, "automation_status", return_value={"apple_event_status": -1744}),
            patch.object(m.subprocess, "run") as run,
        ):
            for b in (m.Backend(real=True), m.Backend(real=True, folders=["folder-demo"])):
                with self.assertRaises(m.NotesError):
                    b.run("metadata")
            run.assert_not_called()

    def test_no_fixture_scope_returns_no_data(self):
        self.assertEqual(
            m.Service(m.Backend(ROOT / "fixtures/synthetic.json")).call("apple_notes_list", {})[
                "notes"
            ],
            [],
        )

    def test_jxa_backend_fixed_script_and_stdin_no_shell(self):
        with (
            patch.dict(os.environ, {"NOTES_ALLOW_REAL": "1"}),
            patch.object(m.sys, "platform", "darwin"),
            patch.object(m, "automation_status", return_value={"apple_event_status": 0}),
            patch.object(
                m.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "[]", "")
            ) as run,
        ):
            m.Backend(real=True, folders=["folder-demo"]).run("metadata")
            args, kw = run.call_args
            self.assertEqual(
                args[0],
                [
                    "/usr/bin/osascript",
                    "-l",
                    "JavaScript",
                    str(ROOT / "apple_notes_mcp/adapter.js"),
                ],
            )
            self.assertNotIn("shell", kw)
            self.assertEqual(json.loads(kw["input"])["folder_ids"], ["folder-demo"])

    def test_raw_private_diagnostics_never_forwarded(self):
        with (
            patch.dict(os.environ, {"NOTES_ALLOW_REAL": "1"}),
            patch.object(m.sys, "platform", "darwin"),
            patch.object(m, "automation_status", return_value={"apple_event_status": 0}),
            patch.object(
                m.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    [], 1, "PRIVATE_SENTINEL", "PRIVATE_SENTINEL"
                ),
            ),
        ):
            with self.assertRaises(m.NotesError) as e:
                m.Backend(real=True, folders=["folder-demo"]).run("metadata")
            self.assertNotIn("PRIVATE_SENTINEL", str(e.exception))


class ProtocolTests(unittest.TestCase):
    def request(self, ident, method, params=None):
        return {"jsonrpc": "2.0", "id": ident, "method": method, "params": params or {}}

    def test_lifecycle_version_capabilities_notifications(self):
        s = m.Service(fixture())
        self.assertIn("error", s.handle(self.request(1, "tools/list")))
        r = s.handle(
            self.request(
                2,
                "initialize",
                {
                    "protocolVersion": "unknown",
                    "clientInfo": {"name": "test", "version": "1"},
                    "capabilities": {},
                },
            )
        )
        self.assertEqual(r["result"]["protocolVersion"], m.VERSIONS[0])
        self.assertEqual(r["result"]["capabilities"], {"tools": {"listChanged": False}})
        self.assertIsNone(s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        self.assertEqual(len(s.handle(self.request(3, "tools/list"))["result"]["tools"]), 6)
        self.assertIn("error", s.handle(self.request(4, "initialize")))
        self.assertEqual(s.handle(self.request(5, "ping"))["result"], {})
        self.assertEqual(s.handle(self.request(6, "write"))["error"]["code"], -32601)

    def test_invalid_requests(self):
        for r in (
            [],
            None,
            {},
            {"jsonrpc": "1", "method": "ping"},
            {"jsonrpc": "2.0", "method": "ping", "id": True},
        ):
            self.assertEqual(m.Service(fixture()).handle(r)["error"]["code"], -32600)

    def test_subprocess_stdio_handshake_tools_calls_eof(self):
        requests = [
            self.request(
                1,
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "wire-test", "version": "1"},
                },
            ),
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            self.request(2, "tools/list"),
        ]
        for i, (name, args) in enumerate(
            [
                ("apple_notes_list", {}),
                ("apple_notes_search", {"query": "MCP"}),
                ("apple_notes_get", {"id": "notes://fixture/a"}),
                ("apple_notes_changes", {"since": "2026-09-10T12:00:00Z"}),
                ("search", {"query": "MCP"}),
                ("fetch", {"id": "notes://fixture/a"}),
                ("delete", {"id": "notes://fixture/a"}),
                ("fetch", {"id": "notes://fixture/locked"}),
            ],
            3,
        ):
            requests.append(self.request(i, "tools/call", {"name": name, "arguments": args}))
        r = subprocess.run(
            [
                sys.executable,
                "-m",
                "apple_notes_mcp",
                "--fixture",
                str(ROOT / "fixtures/synthetic.json"),
                "--allowed-folder",
                "folder-demo",
            ],
            input="\n".join(json.dumps(x) for x in requests) + "\n",
            text=True,
            capture_output=True,
            timeout=10,
            cwd=ROOT,
        )
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stderr, "")
        replies = [json.loads(line) for line in r.stdout.splitlines()]
        self.assertEqual(len(replies), 10)
        self.assertTrue(all(not x["result"]["isError"] for x in replies[2:8]))
        self.assertEqual(replies[8]["error"]["code"], -32602)
        self.assertTrue(replies[9]["result"]["isError"])
        self.assertNotIn("LOCKED_SENTINEL", r.stdout)
        self.assertNotIn("EXCLUDED_SENTINEL", r.stdout)

    def test_parse_error_and_oversized_frame_recovery(self):
        payload = (
            "{\nNaN\n"
            + "[" * 2000
            + "]" * 2000
            + "\n"
            + ("x" * (m.MAX_MESSAGE + 1))
            + "\n"
            + json.dumps(self.request(1, "ping"))
            + "\n"
        )
        r = subprocess.run(
            [sys.executable, "-m", "apple_notes_mcp"],
            input=payload,
            text=True,
            capture_output=True,
            timeout=10,
            cwd=ROOT,
        )
        replies = [json.loads(x) for x in r.stdout.splitlines()]
        codes = [x.get("error", {}).get("code") for x in replies]
        self.assertEqual(codes[:2], [-32700, -32700])
        # Python JSON parsers differ in their recursion limit: this valid JSON
        # array is either rejected during parsing or as a non-object RPC request.
        self.assertIn(codes[2], (-32700, -32600))
        self.assertEqual(codes[3:], [-32600, None])
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
