from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.models.audit_input import AuditObservation, MissionInfo, StructuredAuditInput
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

    def test_application_count_prefers_mission_scope(self) -> None:
        audit_input = StructuredAuditInput(
            mission=MissionInfo(
                applications=[
                    "Temenos T24",
                    "Amplitude (Sopra)",
                    "SWIFT Alliance",
                    "IBS OpenBanking",
                    "HR Access",
                ]
            ),
            observations=[
                AuditObservation(application="Temenos T24", controle_ref="AC-01"),
                AuditObservation(application="HR Access", controle_ref="AC-02"),
                AuditObservation(application="Temenos T24 / Oracle 19c", controle_ref="AC-03"),
                AuditObservation(application="SWIFT Alliance", controle_ref="AC-04"),
                AuditObservation(application="Amplitude (Sopra)", controle_ref="AC-05"),
                AuditObservation(application="IBS OpenBanking", controle_ref="AC-06"),
                AuditObservation(application="Temenos T24 / Red Hat Linux 8", controle_ref="AC-07"),
            ],
        )

        stats = mission_service._audit_stats(audit_input)

        self.assertEqual(stats["applications_count"], 5)

    def test_parsed_source_data_completes_workbook_step_without_filename_metadata(self) -> None:
        self._create_owned_mission()
        audit_input = StructuredAuditInput(
            mission=MissionInfo(mission_id="secure_mission", entite_auditee="Client A"),
            observations=[
                AuditObservation(
                    observation_id="OBS-001",
                    controle_ref="AC-01",
                    application="ERP",
                    statut_validation="validated",
                )
            ],
        )

        mission_service.save_mission_audit_input(
            "secure_mission",
            audit_input,
            user_id=OWNER_MANAGER["user_id"],
        )
        mission = mission_service.get_mission("secure_mission", user=OWNER_MANAGER)

        workbook_step = next(step for step in mission["workflow"]["steps"] if step["key"] == "workbook_uploaded")
        self.assertEqual(workbook_step["state"], "completed")


if __name__ == "__main__":
    unittest.main()
