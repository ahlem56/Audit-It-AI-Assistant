from __future__ import annotations

import unittest
from unittest.mock import patch

from app.agents.qa_agent import answer_mission_question
from app.models.audit_input import ApplicationScope, AuditObservation, MissionInfo, StructuredAuditInput
from app.services.intent_classifier import classify_intent


class ChatIntentRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.audit_input = StructuredAuditInput(
            mission=MissionInfo(
                applications=["Temenos T24", "IBS OpenBanking"],
                application_details=[
                    ApplicationScope(name="Temenos T24", provider="Interne"),
                    ApplicationScope(name="IBS OpenBanking", provider="IBS Group"),
                ],
            ),
            observations=[
                AuditObservation(
                    observation_id="OBS-001",
                    controle_ref="APD-01",
                    application="Temenos T24",
                    titre_observation="Comptes actifs apres depart",
                    priority="Critical",
                    priority_justification="Des operations post-depart ont ete relevees",
                ),
                AuditObservation(
                    observation_id="OBS-005",
                    controle_ref="APD-03",
                    application="Amplitude",
                    titre_observation="Recertification absente",
                    priority="Critical",
                ),
                AuditObservation(
                    observation_id="OBS-006",
                    domaine_controle="Gestion des acces",
                    controle_ref="APD-04",
                    application="IBS OpenBanking",
                    titre_observation="Politique de mots de passe insuffisante",
                ),
                AuditObservation(
                    observation_id="OBS-013",
                    domaine_controle="Operations informatiques",
                    controle_ref="CO-04",
                    application="IBS OpenBanking",
                    titre_observation="Correctifs critiques en retard",
                ),
            ]
        )

    def test_single_observation_priority_question_uses_direct_answer(self) -> None:
        result = answer_mission_question("Pourquoi OBS-001 est-elle Critical ?", self.audit_input)
        self.assertIsNotNone(result)
        self.assertIn("OBS-001", result["answer"])

    def test_recommendation_question_is_not_replaced_by_priority_answer(self) -> None:
        result = answer_mission_question(
            "Propose un plan d'action concret pour OBS-001 avec responsable et echeance.",
            self.audit_input,
        )
        self.assertIsNone(result)

    def test_comparison_is_not_replaced_by_first_observation_answer(self) -> None:
        result = answer_mission_question(
            "Compare les risques de OBS-001 et OBS-005. Laquelle traiter en premier ?",
            self.audit_input,
        )
        self.assertIsNone(result)

    def test_analytical_requests_are_qa_without_calling_llm(self) -> None:
        questions = [
            "Liste les observations relatives a IBS OpenBanking avec leur reference.",
            "Quelles observations impliquent un prestataire externe ?",
            "Prepare un plan de remediation sur 30, 60 et 90 jours pour cette mission.",
        ]
        with patch("app.services.intent_classifier.get_chat_llm") as get_llm:
            for question in questions:
                self.assertEqual("qa", classify_intent(question))
        get_llm.assert_not_called()

    def test_explicit_report_generation_still_routes_to_report(self) -> None:
        self.assertEqual("report", classify_intent("Genere un rapport d'audit complet."))

    def test_history_does_not_retrigger_old_top_risks_question(self) -> None:
        question = (
            "Conversation context:\nUser: Summarize the top risks in this mission.\n\n"
            "Current question:\nQuel utilisateur a effectue les operations post-depart dans T24 ?"
        )
        result = answer_mission_question(question, self.audit_input)
        self.assertIsNotNone(result)
        self.assertIn("aucun nom", result["answer"])
        self.assertNotIn("top risks", result["answer"])
        self.assertEqual("qa", classify_intent(question))

    def test_application_listing_is_calculated_from_mission_data(self) -> None:
        result = answer_mission_question(
            "Liste les observations relatives a IBS OpenBanking avec leur reference de controle.",
            self.audit_input,
        )
        self.assertIsNotNone(result)
        self.assertIn("2 observations", result["answer"])
        self.assertIn("OBS-006 | APD-04", result["answer"])
        self.assertIn("OBS-013 | CO-04", result["answer"])
        self.assertEqual(2, len(result["sources"]))

    def test_remediation_plan_is_built_without_llm(self) -> None:
        report_result = {
            "structured_output": {
                "detailed_findings": [
                    {
                        "observation_id": "OBS-001",
                        "priority": "Critical",
                        "immediate_action": "Desactiver les comptes residuels",
                        "owner": "RSSI / DRH / DSI",
                        "evidence_expected": "tickets de desactivation et validation",
                    }
                ]
            }
        }
        result = answer_mission_question(
            "Prepare un plan de remediation sur 30, 60 et 90 jours pour cette mission.",
            self.audit_input,
            report_result,
        )
        self.assertIsNotNone(result)
        self.assertIn("Sous 30 jours", result["answer"])
        self.assertIn("Sous 60 jours", result["answer"])
        self.assertIn("Sous 90 jours", result["answer"])
        self.assertIn("Desactiver les comptes residuels", result["answer"])

    def test_post_departure_identity_is_not_invented(self) -> None:
        self.audit_input.observations[0].constat = (
            "11 comptes sont restes actifs et 4 ont realise des operations apres le depart."
        )
        result = answer_mission_question(
            "Quel utilisateur a effectue les operations post-depart dans T24 ?",
            self.audit_input,
        )
        self.assertIsNotNone(result)
        self.assertIn("aucun nom", result["answer"])
        self.assertIn("impossible", result["answer"])
        self.assertEqual(1, len(result["sources"]))


if __name__ == "__main__":
    unittest.main()
