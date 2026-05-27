export type MissionStatus = 'Draft' | 'Ready' | 'Finalized';
export type MissionWorkflowStepState = 'completed' | 'in_progress' | 'coming_next';

export interface MissionWorkflowStep {
  key: string;
  label: string;
  state: MissionWorkflowStepState;
  status_label: string;
  description: string;
}

export interface MissionWorkflow {
  steps: MissionWorkflowStep[];
  next_best_action: string;
  validated_observations_count: number;
  total_observations_count: number;
  report_generated: boolean;
  exported_at?: string | null;
}

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
  report_generated_at?: string | null;
  exported_at?: string | null;
  owner_email?: string;
  invited_auditor_emails: string[];
  workflow?: MissionWorkflow;
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

export interface TraceabilitySource {
  source_id: string;
  document_name: string;
  source_type: string;
  excerpt: string;
}

export interface FindingTraceability {
  observation_source_id: string;
  original_reference: string;
  resolved_reference: string;
  fields_used: string[];
  source_documents: TraceabilitySource[];
  heuristic_rules_triggered: string[];
  confidence_score: number;
  priority_justification: string;
  priority_decision_mode: string;
  recommendation_decision_mode: string;
  agent: string;
  generated_at: string;
  report_version: string;
}

export interface ReportFinding {
  observation_id: string;
  original_reference?: string;
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
  risk_scenario: string;
  impact_detail: string;
  business_impact: string;
  control_impact: string;
  compliance_impact: string;
  root_cause: string;
  aggravating_factors: string[];
  recommendation: string;
  recommendation_objective: string;
  immediate_action: string;
  structural_action: string;
  owner: string;
  evidence_expected: string;
  follow_up_mechanism: string;
  recommendation_steps: string[];
  priority: string;
  priority_justification: string;
  auditor_comment: string;
  management_summary: string;
  traceability: FindingTraceability;
}

export type QualityIssueSeverity = 'blocking' | 'warning';

export interface ReportQualityIssue {
  rule_id: string;
  severity: QualityIssueSeverity;
  title: string;
  message: string;
  recommendation: string;
  affected_observation_ids: string[];
  affected_applications: string[];
  affected_section: string;
  score_impact: number;
}

export interface ReportQualityGateResult {
  readiness_score: number;
  export_allowed: boolean;
  blocking_issues_count: number;
  warning_issues_count: number;
  summary: string;
  issues: ReportQualityIssue[];
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
  quality_gate: ReportQualityGateResult;
}

export interface ReportPreview {
  agent?: string;
  request?: string;
  answer: string;
  structured_output: ReportStructuredOutput;
}

export interface MissionQualityGateResult extends ReportQualityGateResult {
  mission_id: string;
}

export interface ReportEmailDefaults {
  to_email: string;
  subject: string;
  body: string;
}

export interface SendReportEmailPayload {
  to_email: string;
  subject: string;
  body: string;
}

export interface SendReportEmailResult {
  mission_id: string;
  sent_to: string;
  subject: string;
  filename: string;
  status: string;
}

export type NotificationType =
  | 'mission_assigned'
  | 'mission_status_changed'
  | 'observation_created'
  | 'report_generated'
  | 'report_finalized';

export interface NotificationItem {
  notification_id: string;
  recipient_email: string;
  type: NotificationType | string;
  title: string;
  message: string;
  mission_id?: string | null;
  related_entity_type?: string | null;
  related_entity_id?: string | null;
  is_read: boolean;
  created_at: string;
  read_at?: string | null;
}

export interface SecurityAuditEvent {
  event_id: string;
  timestamp: string;
  user_id: string;
  user_email: string;
  organization_id: string;
  mission_id: string;
  action: string;
  resource_type: string;
  resource_id: string;
  ip_address: string;
  user_agent: string;
  status: string;
  metadata_json: Record<string, unknown>;
  hash: string;
  previous_hash: string;
}

export interface SecurityAuditChainStatus {
  valid: boolean;
  checked_events: number;
  reason: string;
}

export interface SecurityAuditEventsResponse {
  events: SecurityAuditEvent[];
  chain: SecurityAuditChainStatus;
}

export interface AuthUser {
  user_id: string;
  email: string;
  first_name: string;
  last_name: string;
  display_name: string;
  organization: string;
  job_title: string;
  role: string;
  auth_provider: string;
  last_login_at?: string | null;
  profile_image_url?: string | null;
}

export interface AuthConfig {
  enabled: boolean;
  provider: string;
  login_url?: string | null;
  signup_url?: string | null;
  logout_url?: string | null;
  password_sign_in_enabled: boolean;
  microsoft_sign_in_enabled: boolean;
}

export interface AuthSession {
  authenticated: boolean;
  auth_enabled: boolean;
  user?: AuthUser | null;
}

export interface LogoutResult {
  logged_out: boolean;
  logout_url?: string | null;
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

export interface M365DriveItem {
  id: string;
  name: string;
  size?: number;
  webUrl?: string;
  file?: {
    mimeType?: string;
  };
  folder?: {
    childCount?: number;
  };
  parentReference?: {
    driveId?: string;
    id?: string;
    path?: string;
  };
  lastModifiedDateTime?: string;
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

export type FeedbackScope = 'report' | 'observation';

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
}
