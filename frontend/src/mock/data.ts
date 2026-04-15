import type { ChatMessage, Mission, Observation } from '../types';

export const mockMission: Mission = {
  mission_id: 'PWCFY25-001',
  name: 'Paref FY25',
  client: 'Paref Immobilier',
  fiscal_year: 'FY25',
  created_at: '2025-10-02',
  updated_at: '2026-03-15',
  status: 'Draft',
  current_file: {
    name: 'ITGC_Risk_Dashboard.xlsx',
    size: '2.4 MB'
  },
  summary: 'The mission is focused on ITGC controls for SAP, Oracle, and Active Directory environments, with stronger scrutiny on critical segregation-of-duty risks and access management procedures.',
  key_findings: [
    'Critical user provisioning gaps in Oracle workflows.',
    'High risk around SAP change management controls.',
    'Medium risk due to missing Active Directory review documentation.'
  ]
};

function createMockObservation(base: {
  id: string;
  controlId: string;
  application: string;
  finding: string;
  compensatingProcedure: string;
  comments: string;
  priority: Observation['priority'];
  priorityReason: string;
  recommendation: string;
}): Observation {
  return {
    id: base.id,
    observation_id: base.id,
    domain: '',
    domaine_controle: '',
    category: '',
    categorie_controle: '',
    control_id: base.controlId,
    controle_ref: base.controlId,
    application: base.application,
    layer: '',
    couche: '',
    title: '',
    titre_observation: '',
    expected_control: '',
    controle_attendu: '',
    finding: base.finding,
    constat: base.finding,
    risk: '',
    risque_associe: '',
    compensating_procedure: base.compensatingProcedure,
    procedure_compensatoire: base.compensatingProcedure,
    impact: '',
    impact_potentiel: '',
    root_cause: '',
    cause_racine: '',
    comments: base.comments,
    commentaire_auditeur: base.comments,
    population: '',
    sample_size: '',
    taille_echantillon: '',
    exception_count: '',
    nombre_exceptions: '',
    owners: '',
    responsables: '',
    evidence_references: '',
    references_probantes: '',
    control_status: '',
    statut_controle: '',
    status: 'Draft',
    statut_validation: 'Draft',
    priority: base.priority,
    priority_justification: '',
    priority_reason: base.priorityReason,
    priority_source: 'system',
    recommendation: base.recommendation,
    recommandation_proposee: base.recommendation,
    included_in_report: true
  };
}

export const mockObservations: Observation[] = [
  createMockObservation({
    id: 'obs-001',
    controlId: 'SAP-AC-001',
    application: 'SAP',
    finding: 'Access reviews are not consistently completed for privileged SAP accounts.',
    compensatingProcedure: 'Implement quarterly access certifications and track completion dates.',
    comments: 'Recent audit sample showed 4 unresolved accounts.',
    priority: 'Critical',
    priorityReason: 'privileged access risk',
    recommendation: 'Formalise a SAP privileged access review process and remediate exceptions immediately.'
  }),
  createMockObservation({
    id: 'obs-002',
    controlId: 'ORCL-SEG-005',
    application: 'Oracle',
    finding: 'Segregation of duties matrix is not aligned with current Oracle administrator roles.',
    compensatingProcedure: 'Update the SoD matrix and reconcile against active role assignments.',
    comments: 'Matrix update pending since last quarter.',
    priority: 'High',
    priorityReason: 'role conflict detected',
    recommendation: 'Review administrator roles and separate conflicting duties by design.'
  }),
  createMockObservation({
    id: 'obs-003',
    controlId: 'AD-ACC-010',
    application: 'Active Directory',
    finding: 'Temporary accounts remain enabled beyond approved expiration dates.',
    compensatingProcedure: 'Enforce automatic deactivation for temporary accounts after approval windows.',
    comments: 'Several accounts active for >30 days.',
    priority: 'Medium',
    priorityReason: 'stale temporary accounts',
    recommendation: 'Create a workflow for temporary account expiration and monitor expiries.'
  })
];

export const mockChatHistory: ChatMessage[] = [
  {
    id: 'chat-1',
    role: 'assistant',
    content: "Bienvenue dans la mission Paref FY25. Je peux vous aider a analyser les observations et construire un rapport de conformite ITGC."
  }
];
