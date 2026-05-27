from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.models.audit_input import AuditObservation, MissionInfo, StructuredAuditInput
from app.services import export_service
from app.services import report_composer_service as composer


class ReportQualityEnrichmentTests(unittest.TestCase):
    def test_high_priority_finding_gets_structured_risk_and_auditable_recommendation(self) -> None:
        audit_input = StructuredAuditInput(
            mission=MissionInfo(
                mission_id="mission-quality",
                entite_auditee="Banque Zitouna",
                periode="FY2026",
                applications=["Temenos T24"],
            ),
            observations=[
                AuditObservation(
                    observation_id="OBS-001",
                    domaine_controle="Gestion des acces",
                    categorie_controle="Revocation des acces",
                    controle_ref="APD-01",
                    application="Temenos T24",
                    couche="Applicative",
                    titre_observation="Comptes utilisateurs T24 actifs apres cessation de contrat",
                    constat=(
                        "11 comptes utilisateurs T24 appartenant a des collaborateurs partis sont toujours actifs. "
                        "4 connexions post-depart ont ete confirmees, dont 2 sur comptes clients a fort encours."
                    ),
                    procedure_compensatoire=(
                        "La DRH adresse un email a la DSI lors des departs, sans accuse de reception ni suivi formel."
                    ),
                    commentaire_auditeur="Extraction T24 confirmee et comptes residuels identifies.",
                    responsables="RSSI / DRH / DSI",
                    statut_validation="validated",
                )
            ],
        )

        with patch.object(composer, "infer_observation_reasoning", return_value={}), patch.object(
            composer, "infer_priority_reasoning", return_value={}
        ):
            output = composer.compose_audit_report(audit_input)

        finding = output.detailed_findings[0]

        self.assertIn("comptes actifs après depart", finding.risk_scenario.lower())
        self.assertIn("cycle de vie des habilitations", finding.control_impact.lower())
        self.assertIn("rapprochement", finding.root_cause.lower())
        self.assertTrue(finding.aggravating_factors)
        self.assertIn("preuves attendues", " ".join(finding.recommendation_steps).lower())
        self.assertIn("mecanisme de suivi", " ".join(finding.recommendation_steps).lower())
        self.assertTrue(output.quality_gate.export_allowed)

    def test_export_helpers_do_not_emit_visible_truncation_marks(self) -> None:
        long_text = (
            "Mettre en place un rapprochement formalisé entre les mouvements RH et les comptes actifs applicatifs "
            "avec conservation des preuves, suivi des exceptions et revue périodique par les responsables habilités."
        )

        self.assertNotIn("...", export_service._truncate(long_text, 80))
        self.assertNotIn("...", export_service._wrap_cell_text(long_text, width=20, max_lines=2))
        self.assertNotIn("...", export_service._wrap_preserving_lines(long_text, width=20, max_lines=2))

        data = SimpleNamespace(
            detailed_recommendations=[
                SimpleNamespace(
                    reference="APD-01",
                    owner="DRH / DSI",
                    owners="",
                    priority="Critical",
                    immediate_action="Désactiver les comptes résiduels identifiés et documenter les exceptions maintenues temporairement.",
                    structural_action=long_text,
                    evidence_expected="Journal de désactivation, validation du responsable et résultat du rapprochement périodique.",
                    recommendation_steps=[],
                    recommendation=long_text,
                )
            ]
        )
        rows = export_service._build_recommendation_rows(data)
        self.assertEqual(len(rows[0]), 5)
        self.assertFalse(any("..." in cell for cell in rows[0]))

    def test_export_toc_includes_reference_report_sections(self) -> None:
        data = SimpleNamespace(detailed_findings=[SimpleNamespace()])
        toc = export_service._build_export_toc(data)

        self.assertEqual(
            toc,
            [
                "Cadre de notre intervention et démarche",
                "Synthèse générale",
                "Recommandations détaillées",
                "Annexes",
            ],
        )
        self.assertNotIn("Niveaux de priorité et critères de classification", toc)
        self.assertNotIn("Suivi des recommandations antérieures", toc)


if __name__ == "__main__":
    unittest.main()
