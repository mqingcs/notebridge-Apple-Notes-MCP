import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apple_notes_mcp import server as m


class TunnelHandshakeTests(unittest.TestCase):
    def setUp(self):
        self.service = m.Service(
            m.Backend(ROOT / "fixtures/synthetic.json", folders=["folder-demo"])
        )
        self.params = {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "tunnel-test", "version": "1"},
        }

    def request(self, method, params=None):
        return self.service.handle(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        )

    def test_duplicate_initialize_before_notification_preserves_gate(self):
        first = self.request("initialize", self.params)
        self.assertEqual(first, self.request("initialize", self.params))
        self.assertIn("error", self.request("tools/list"))
        self.service.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(len(self.request("tools/list")["result"]["tools"]), 6)

    def test_retry_ready_connection_does_not_revoke_readiness(self):
        self.request("initialize", self.params)
        self.service.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertIn("result", self.request("initialize", self.params))
        self.assertEqual(len(self.request("tools/list")["result"]["tools"]), 6)
        self.assertIn("error", self.request("initialize", {}))


if __name__ == "__main__":
    unittest.main()
