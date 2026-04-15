from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ApplicationScope(BaseModel):
    name: str = ""
    description: str = ""
    operating_system: str = ""
    database: str = ""
    provider: str = ""


class MissionInfo(BaseModel):
    mission_id: str = ""
    titre_mission: str = ""
    entite_auditee: str = ""
    type_mission: str = ""
    periode: str = ""
    intervenants: list[str] = Field(default_factory=list)
    perimetre_intervention: str = ""
    objectifs: list[str] = Field(default_factory=list)
    date_rapport: str = ""
    processus_couverts: list[str] = Field(default_factory=list)
    applications: list[str] = Field(default_factory=list)
    application_details: list[ApplicationScope] = Field(default_factory=list)


class AuditObservation(BaseModel):
    observation_id: str = ""
    domaine_controle: str = ""
    categorie_controle: str = ""
    controle_ref: str = ""
    application: str = ""
    couche: str = ""
    titre_observation: str = ""
    controle_attendu: str = ""
    constat: str = ""
    risque_associe: str = ""
    procedure_compensatoire: str = ""
    impact_potentiel: str = ""
    cause_racine: str = ""
    recommandation_proposee: str = ""
    commentaire_auditeur: str = ""
    population: str = ""
    taille_echantillon: str = ""
    nombre_exceptions: str = ""
    responsables: str = ""
    references_probantes: str = ""
    statut_controle: str = ""
    statut_validation: str = ""
    priority: Optional[str] = None
    priority_justification: str = ""
    priority_reason: str = ""
    priority_source: str = ""
    included_in_report: bool = True


class StructuredAuditInput(BaseModel):
    mission: MissionInfo = Field(default_factory=MissionInfo)
    observations: list[AuditObservation] = Field(default_factory=list)
