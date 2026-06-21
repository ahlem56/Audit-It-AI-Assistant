from __future__ import annotations

from app.agents.report_agent import generate_audit_report
from app.models.report_sections import DetailedFinding
from app.services.mission_service import load_mission_audit_input, save_mission_audit_input
from app.services.report_composer_service import recalculate_audit_input_priorities


def recalculate_mission_observation_priorities(
    mission_id: str,
    user_id: str,
    *,
    preserve_manual_overrides: bool = True,
) -> dict:
    audit_input = load_mission_audit_input(mission_id, user_id=user_id)
    if audit_input is None:
        raise ValueError(f"Mission '{mission_id}' audit input was not found.")

    report_result = generate_audit_report(
        f"Generate report for mission {mission_id}",
        None,
        audit_input,
    )

    raw_findings = report_result.get("structured_output", {}).get("detailed_findings", [])
    findings = [DetailedFinding.model_validate(item) for item in raw_findings]
    recalculated = recalculate_audit_input_priorities(
        audit_input,
        preserve_manual_overrides=preserve_manual_overrides,
        findings=findings,
    )
    save_mission_audit_input(mission_id, recalculated, user_id=user_id)

    return {
        "mission_id": mission_id,
        "observations": [observation.model_dump() for observation in recalculated.observations],
    }
