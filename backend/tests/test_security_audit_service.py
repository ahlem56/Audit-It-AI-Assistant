from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import security_audit_service


class SecurityAuditServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.audit_log_path = Path(self.temp_dir.name) / "security_audit_events.jsonl"
        self.patches = [
            patch.object(security_audit_service, "AUDIT_LOG_PATH", self.audit_log_path),
            patch.object(security_audit_service, "azure_sql_enabled", return_value=False),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def test_events_are_hash_chained_and_verifiable(self) -> None:
        user = {"user_id": "user-1", "email": "auditor@pwc.com", "organization": "PwC"}

        first = security_audit_service.log_security_event(
            action="MISSION_VIEWED",
            user=user,
            mission_id="mission-1",
            resource_type="mission",
            resource_id="mission-1",
        )
        second = security_audit_service.log_security_event(
            action="AI_ANSWER_GENERATED",
            user=user,
            mission_id="mission-1",
            resource_type="chat",
            resource_id="mission-1",
        )

        events = security_audit_service.list_security_events()

        self.assertEqual(events[0]["event_id"], second["event_id"])
        self.assertEqual(events[1]["event_id"], first["event_id"])
        self.assertEqual(second["previous_hash"], first["hash"])
        self.assertTrue(security_audit_service.verify_event_chain(events)["valid"])

    def test_tampering_invalidates_chain(self) -> None:
        user = {"user_id": "user-1", "email": "auditor@pwc.com", "organization": "PwC"}
        security_audit_service.log_security_event(action="FILE_UPLOADED", user=user, mission_id="mission-1")
        events = security_audit_service.list_security_events()
        events[0]["action"] = "MISSION_VIEWED"

        result = security_audit_service.verify_event_chain(events)

        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "Event hash mismatch.")


if __name__ == "__main__":
    unittest.main()
