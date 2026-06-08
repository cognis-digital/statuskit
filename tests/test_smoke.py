"""Smoke tests for STATUSKIT. No network. Run: python -m pytest or unittest."""
import json
import os
import tempfile
import unittest

from statuskit import (
    StatusKit, StatusKitError, ComponentStatus, IncidentStatus, Impact,
    TOOL_NAME, TOOL_VERSION,
)
from statuskit.cli import main


DEMO = os.path.join(os.path.dirname(__file__), "..", "demos", "01-basic", "statuspage.json")


class TestCore(unittest.TestCase):
    def setUp(self):
        self.kit = StatusKit("Test")
        self.kit.add_component("api", "API")
        self.kit.add_component("web", "Web")

    def test_meta(self):
        self.assertEqual(TOOL_NAME, "statuskit")
        self.assertTrue(TOOL_VERSION)

    def test_overall_rolls_up_worst(self):
        self.assertEqual(self.kit.overall_status(), ComponentStatus.OPERATIONAL)
        self.kit.set_component_status("web", ComponentStatus.DEGRADED)
        self.kit.set_component_status("api", ComponentStatus.MAJOR)
        self.assertEqual(self.kit.overall_status(), ComponentStatus.MAJOR)

    def test_incident_status_follows_last_update(self):
        inc = self.kit.open_incident("i1", "Boom", Impact.MAJOR, ["api"])
        self.assertEqual(inc.status, IncidentStatus.INVESTIGATING)
        self.assertFalse(inc.resolved)
        self.kit.update_incident("i1", IncidentStatus.IDENTIFIED, "found it")
        self.kit.update_incident("i1", IncidentStatus.RESOLVED, "fixed")
        self.assertTrue(inc.resolved)
        self.assertIsNotNone(inc.resolved_at)
        self.assertIsNotNone(inc.duration_seconds())

    def test_cannot_update_resolved(self):
        self.kit.open_incident("i1", "Boom", Impact.MINOR, ["api"])
        self.kit.update_incident("i1", IncidentStatus.RESOLVED, "done")
        with self.assertRaises(StatusKitError):
            self.kit.update_incident("i1", IncidentStatus.MONITORING, "oops")

    def test_bad_inputs(self):
        with self.assertRaises(StatusKitError):
            self.kit.open_incident("i2", "x", "bogus-impact", ["api"])
        with self.assertRaises(StatusKitError):
            self.kit.open_incident("i3", "x", Impact.MAJOR, ["nope"])
        with self.assertRaises(StatusKitError):
            self.kit.subscribe("not-an-email")
        with self.assertRaises(StatusKitError):
            self.kit.add_component("api", "dup")

    def test_notify_targets_scoping(self):
        self.kit.open_incident("i1", "Boom", Impact.MAJOR, ["api"])
        self.kit.subscribe("all@x.com")
        self.kit.subscribe("api@x.com", ["api"])
        self.kit.subscribe("web@x.com", ["web"])
        targets = self.kit.notify_targets("i1")
        self.assertIn("all@x.com", targets)
        self.assertIn("api@x.com", targets)
        self.assertNotIn("web@x.com", targets)

    def test_uptime_counts_major_downtime(self):
        # An open major incident on 'api' should drop its uptime below 100.
        self.kit.open_incident("i1", "down", Impact.MAJOR, ["api"])
        up = self.kit.uptime(window_seconds=3600)
        self.assertLess(up["api"], 100.0)
        self.assertEqual(up["web"], 100.0)

    def test_roundtrip_from_dict(self):
        snap = self.kit.snapshot()
        kit2 = StatusKit.from_dict(json.loads(json.dumps(snap)))
        self.assertEqual(set(kit2.components), set(self.kit.components))


class TestDemoAndCli(unittest.TestCase):
    def test_demo_loads(self):
        kit = StatusKit.from_json_file(DEMO)
        self.assertEqual(kit.overall_status(), ComponentStatus.MAJOR)
        self.assertEqual(len(kit.active_incidents()), 1)
        targets = kit.notify_targets("inc-2026-002")
        self.assertIn("ops-all@example.com", targets)
        self.assertIn("api-team@example.com", targets)
        self.assertNotIn("cdn-watch@example.com", targets)

    def test_cli_status_nonzero_when_unhealthy(self):
        rc = main(["--format", "json", "status", DEMO])
        self.assertEqual(rc, 1)

    def test_cli_check_nonzero(self):
        self.assertEqual(main(["check", DEMO]), 1)

    def test_cli_uptime_ok(self):
        self.assertEqual(main(["--format", "json", "uptime", DEMO]), 0)

    def test_cli_healthy_page_zero(self):
        cfg = {"name": "ok", "components": [{"id": "a", "name": "A"}]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(cfg, fh)
            path = fh.name
        try:
            self.assertEqual(main(["status", path]), 0)
            self.assertEqual(main(["check", path]), 0)
        finally:
            os.unlink(path)

    def test_cli_bad_path(self):
        self.assertEqual(main(["status", "/no/such/file.json"]), 2)


if __name__ == "__main__":
    unittest.main()
