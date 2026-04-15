export type MissionStatus = 'Draft' | 'Ready' | 'Finalized';

export type PriorityLevel = 'Critical' | 'High' | 'Medium' | 'Low';

export type PrioritySource = 'system' | 'manual_override' | 'generated_pipeline' | '';

export interface Observation {
  id: string;
  observation_id: string;
  domain: string;
  domaine_controle: string;
  category: string;
  categorie_controle: string;
  control_id: string;
  controle_ref: string;
  application: string;
  layer: string;
  couche: string;
  title: string;
  titre_observation: string;
  expected_control: string;
  controle_attendu: string;
  finding: string;
  constat: string;
  risk: string;
  risque_associe: string;
  compensating_procedure: string;
  procedure_compensatoire: string;
  impact: string;
  impact_potentiel: string;
  root_cause: string;
  cause_racine: string;
  comments: string;
  commentaire_auditeur: string;
  population: string;
  sample_size: string;
  taille_echantillon: string;
  exception_count: string;
  nombre_exceptions: string;
  owners: string;
  responsables: string;
  evidence_references: string;
  references_probantes: string;
  control_status: string;
  statut_controle: string;
  status: string;
  statut_validation: string;
  priority: PriorityLevel | null;
  priority_justification: string;
  priority_reason: string;
  priority_source: PrioritySource;
  recommendation: string;
  recommandation_proposee: string;
  included_in_report: boolean;
}

export interface Mission {
  mission_id: string;
  name: string;
  client: string;
  fiscal_year: string;
  created_at: string;
  updated_at: string;
  status: MissionStatus;
  parsing_status?: 'not_uploaded' | 'parsing' | 'parsed' | 'error';
  observations_count?: number;
  applications_count?: number;
  control_ids_count?: number;
  current_file?: {
    name: string;
    size: string;
  };
  summary: string;
  key_findings: string[];
}

export interface ParsedMissionContext {
  mission_id: string;
  titre_mission: string;
  entite_auditee: string;
  type_mission: string;
  periode: string;
  intervenants: string[];
  perimetre_intervention: string;
  objectifs: string[];
  date_rapport: string;
  processus_couverts: string[];
  applications: string[];
}

export interface ReportCoveredControl {
  reference: string;
  process: string;
  description: string;
  test_procedure: string;
}

export interface ReportControlMatrixEntry {
  reference: string;
  process: string;
  control_description: string;
  application_statuses: Record<string, string>;
  overall_priority: string;
}

export interface ReportPrioritySummaryEntry {
  priority: string;
  count: number;
  percentage: number;
}

export interface ReportKeyFigure {
  label: string;
  value: string;
  commentary: string;
}

export interface ReportApplicationDetail {
  name: string;
  description: string;
  operating_system: string;
  database: string;
  provider: string;
}

export interface ReportProcessSummary {
  process_code: string;
  process_name: string;
  observation_count: number;
  applications: string[];
  strengths: string[];
  watch_points: string[];
}

export interface ReportFinding {
  observation_id: string;
  reference: string;
  domain: string;
  category: string;
  application: string;
  layer: string;
  owners: string;
  title: string;
  expected_control: string;
  finding: string;
  compensating_procedure: string;
  risk_impact: string;
  impact_detail: string;
  root_cause: string;
  recommendation: string;
  recommendation_objective: string;
  recommendation_steps: string[];
  priority: string;
  priority_justification: string;
  auditor_comment: string;
  management_summary: string;
}

export interface ReportStructuredOutput {
  cover_title: string;
  cover_subtitle: string;
  client_name: string;
  report_period: string;
  report_date: string;
  confidentiality_notice: string;
  table_of_contents: string[];
  preamble: string;
  objectives: string[];
  stakeholders: string[];
  scope_summary: string;
  applications: string[];
  application_details: ReportApplicationDetail[];
  covered_processes: string[];
  audit_approach: string[];
  covered_controls: ReportCoveredControl[];
  control_matrix: ReportControlMatrixEntry[];
  key_figures: ReportKeyFigure[];
  executive_highlights: string[];
  strengths: string[];
  watch_points: string[];
  maturity_level: string;
  maturity_assessment: string;
  priority_insight: string;
  strategic_priorities: string[];
  transversal_initiatives: string[];
  process_summaries: ReportProcessSummary[];
  general_synthesis: string;
  priority_summary: ReportPrioritySummaryEntry[];
  detailed_findings: ReportFinding[];
  detailed_recommendations: ReportFinding[];
  prior_recommendations_follow_up: string[];
  appendices: string[];
  executive_summary: string;
  conclusion: string;
}

export interface ReportPreview {
  agent?: string;
  request?: string;
  answer: string;
  structured_output: ReportStructuredOutput;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: ChatSource[];
  agent?: string;
}

export interface AssistantResponse {
  message: ChatMessage;
}

export interface CreateMissionPayload {
  mission_id?: string;
  name: string;
  client: string;
  fiscal_year: string;
}

export interface UpdateMissionPayload {
  name?: string;
  client?: string;
  fiscal_year?: string;
  summary?: string;
  key_findings?: string[];
}

export interface AssistantMessagePayload {
  message: string;
  history: ChatMessage[];
}

export interface ChatSource {
  source_id: string;
  document_name: string;
  chunk_id: number | null;
  score: number | null;
  excerpt: string | null;
}

export type FeedbackScope = 'mission' | 'report' | 'observation';

export type FeedbackSentiment = 'positive' | 'neutral' | 'negative';

export type FeedbackCategory =
  | 'report_quality'
  | 'priority_logic'
  | 'recommendations'
  | 'ppt_design'
  | 'data_accuracy'
  | 'missing_content'
  | 'usability';

export type FeedbackStatus = 'pending' | 'reviewed' | 'resolved';

export interface AuditorFeedback {
  feedback_id: string;
  mission_id: string;
  created_at: string;
  author?: string;
  scope?: FeedbackScope;
  target_id?: string;
  rating?: 1 | 2 | 3 | 4 | 5;
  sentiment?: FeedbackSentiment;
  categories: FeedbackCategory[];
  comment?: string;
  requires_action: boolean;
  status: FeedbackStatus;
}

export interface CreateFeedbackPayload {
  scope?: FeedbackScope;
  target_id?: string;
  rating?: 1 | 2 | 3 | 4 | 5;
  sentiment?: FeedbackSentiment;
  categories: FeedbackCategory[];
  comment?: string;
  requires_action: boolean;
  author?: string;
}
