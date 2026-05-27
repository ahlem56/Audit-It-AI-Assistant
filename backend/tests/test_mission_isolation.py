from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services import mission_service
from app.services.retrieval_service import retrieve_documents


OWNER_MANAGER = {
    "user_id": "manager-1",
    "email": "manager.one@pwc.com",
    "role": "manager",
}
OTHER_MANAGER = {
    "user_id": "manager-2",
    "email": "manager.two@pwc.com",
    "role": "manager",
}
INVITED_AUDITOR = {
    "user_id": "auditor-1",
    "email": "auditor.one@pwc.com",
    "role": "auditor",
}
OUTSIDER_AUDITOR = {
    "user_id": "auditor-2",
    "email": "auditor.two@pwc.com",
    "role": "auditor",
}


class MissionIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.missions_dir = Path(self.temp_dir.name) / "missions"
        self.patches = [
            patch.object(mission_service, "AUTH_ENABLED", True),
            patch.object(mission_service, "MISSIONS_DIR", self.missions_dir),
            patch.object(mission_service, "azure_sql_enabled", return_value=False),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        self.temp_dir.cleanup()

    def _create_owned_mission(self) -> dict:
        return mission_service.create_mission(
            {
                "mission_id": "secure_mission",
                "name": "Secure Mission",
                "client_name": "Client A",
                "fiscal_year": "FY2026",
            },
            owner_user=OWNER_MANAGER,
        )

    def test_only_owner_or_invited_auditor_can_see_mission(self) -> None:
        self._create_owned_mission()
        mission_service.invite_auditor_to_mission(
            "secure_mission",
            INVITED_AUDITOR["email"],
            manager_user=OWNER_MANAGER,
        )

        self.assertIsNotNone(mission_service.get_mission("secure_mission", user=OWNER_MANAGER))
        self.assertIsNotNone(mission_service.get_mission("secure_mission", user=INVITED_AUDITOR))
        self.assertIsNone(mission_service.get_mission("secure_mission", user=OTHER_MANAGER))
        self.assertIsNone(mission_service.get_mission("secure_mission", user=OUTSIDER_AUDITOR))

    def test_other_manager_cannot_manage_or_delete_mission(self) -> None:
        self._create_owned_mission()

        with self.assertRaises(ValueError):
            mission_service.delete_mission("secure_mission", user=OTHER_MANAGER)

        self.assertIsNotNone(mission_service.get_mission("secure_mission", user=OWNER_MANAGER))

    def test_unscoped_retrieval_is_blocked_by_default(self) -> None:
        self.assertEqual(retrieve_documents("show all indexed audit evidence"), [])


if __name__ == "__main__":
    unittest.main()
