#!/usr/bin/env python3
"""Exercise stdio with synthetic data only; never contacts Apple Notes."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--installed", action="store_true", help="Run outside checkout to verify installed package"
    )
    args = p.parse_args()
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "synthetic-smoke", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    for i, (name, arguments) in enumerate(
        [
            ("apple_notes_list", {"limit": 1}),
            ("apple_notes_search", {"query": "MCP", "limit": 1}),
            ("apple_notes_get", {"id": "notes://fixture/a", "max_chars": 100}),
        ],
        3,
    ):
        requests.append(
            {
                "jsonrpc": "2.0",
                "id": i,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
        )
    with tempfile.TemporaryDirectory() as tmp:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "apple_notes_mcp",
                "--fixture",
                str(ROOT / "fixtures/synthetic.json"),
                "--allowed-folder",
                "folder-demo",
            ],
            cwd=tmp if args.installed else ROOT,
            input="\n".join(json.dumps(x) for x in requests) + "\n",
            text=True,
            capture_output=True,
            timeout=15,
        )
    if result.returncode:
        raise SystemExit("Synthetic server exited unsuccessfully (diagnostics not echoed).")
    replies = [json.loads(x) for x in result.stdout.splitlines()]
    assert len(replies) == 5
    assert len(replies[1]["result"]["tools"]) == 6
    assert all(not r["result"]["isError"] for r in replies[2:])
    listed, searched, got = [r["result"]["structuredContent"] for r in replies[2:]]
    assert listed["source"] == searched["source"] == "synthetic"
    assert len(listed["notes"]) == len(searched["notes"]) == 1
    assert got["id"] == "notes://fixture/a" and not got["truncated"]
    print(
        json.dumps(
            {
                "ok": True,
                "mode": "synthetic",
                "installed": args.installed,
                "tools": 6,
                "list_count": 1,
                "search_count": 1,
                "get_chars": len(got["text"]),
            }
        )
    )


if __name__ == "__main__":
    main()
