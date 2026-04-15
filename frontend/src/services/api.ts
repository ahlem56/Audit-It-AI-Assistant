import axios from 'axios';
import * as XLSX from 'xlsx';
import type {
  Mission,
  Observation,
  ParsedMissionContext,
  ReportPreview,
  ReportStructuredOutput,
  ReportCoveredControl,
  ReportControlMatrixEntry,
  ReportPrioritySummaryEntry,
  ReportKeyFigure,
  ReportApplicationDetail,
  ReportProcessSummary,
  ReportFinding,
  AssistantResponse,
  ChatMessage,
  CreateMissionPayload,
  UpdateMissionPayload,
  AssistantMessagePayload,
  PriorityLevel,
  PrioritySource,
  AuditorFeedback,
  CreateFeedbackPayload,
  ChatSource
} from '../types';

type ApiMission = {
  mission_id: string;
  name: string;
  client_name?: string;
  fiscal_year?: string;
  status?: Mission['status'];
  created_at: string;
  updated_at: string;
  uploaded_file_name?: string | null;
  parsing_status?: 'not_uploaded' | 'parsing' | 'parsed' | 'error';
  observations_count?: number;
  applications_count?: number;
  control_ids_count?: number;
};

type ApiObservation = {
  observation_id?: string;
  domaine_controle?: string;
  categorie_controle?: string;
  controle_ref?: string;
  application?: string;
  couche?: string;
  controle_attendu?: string;
  constat?: string;
  risque_associe?: string;
  procedure_compensatoire?: string;
  impact_potentiel?: string;
  cause_racine?: string;
  commentaire_auditeur?: string;
  population?: string;
  taille_echantillon?: string;
  nombre_exceptions?: string;
  responsables?: string;
  references_probantes?: string;
  statut_controle?: string;
  priority?: string | null;
  priority_justification?: string;
  priority_reason?: string;
  priority_source?: string;
  statut_validation?: string;
  recommandation_proposee?: string;
  titre_observation?: string;
  included_in_report?: boolean;
};

type ApiObservationsResponse = {
  mission_id?: string;
  mission?: {
    mission_id?: string;
    titre_mission?: string;
    entite_auditee?: string;
    type_mission?: string;
    periode?: string;
    intervenants?: string[];
    perimetre_intervention?: string;
    objectifs?: string[];
    date_rapport?: string;
    processus_couverts?: string[];
    applications?: string[];
  };
  observations?: ApiObservation[];
};

type ApiReportPreviewResponse = {
  agent?: string;
  request?: string;
  structured_output?: {
    cover_title?: string;
    cover_subtitle?: string;
    client_name?: string;
    report_period?: string;
    report_date?: string;
    confidentiality_notice?: string;
    table_of_contents?: string[];
    preamble?: string;
    objectives?: string[];
    stakeholders?: string[];
    scope_summary?: string;
    applications?: string[];
    application_details?: Array<Record<string, unknown>>;
    covered_processes?: string[];
    audit_approach?: string[];
    covered_controls?: Array<Record<string, unknown>>;
    control_matrix?: Array<Record<string, unknown>>;
    key_figures?: Array<Record<string, unknown>>;
    executive_summary?: string;
    general_synthesis?: string;
    conclusion?: string;
    executive_highlights?: string[];
    strengths?: string[];
    watch_points?: string[];
    maturity_level?: string;
    maturity_assessment?: string;
    priority_insight?: string;
    strategic_priorities?: string[];
    transversal_initiatives?: string[];
    process_summaries?: Array<Record<string, unknown>>;
    priority_summary?: Array<Record<string, unknown>>;
    detailed_findings?: Array<{
      observation_id?: string;
      title?: string;
      reference?: string;
      domain?: string;
      category?: string;
      application?: string;
      layer?: string;
      owners?: string;
      expected_control?: string;
      finding?: string;
      compensating_procedure?: string;
      risk_impact?: string;
      impact_detail?: string;
      root_cause?: string;
      recommendation?: string;
      recommendation_objective?: string;
      recommendation_steps?: string[];
      priority?: string;
      priority_justification?: string;
      auditor_comment?: string;
      management_summary?: string;
    }>;
    detailed_recommendations?: Array<Record<string, unknown>>;
    prior_recommendations_follow_up?: string[];
    appendices?: string[];
  };
  answer?: string;
};

type ApiAssistantMessage = {
  id?: string;
  role?: 'user' | 'assistant';
  content?: string;
  message?: string;
  text?: string;
};

type ApiChatSource = {
  source_id?: string;
  document_name?: string;
  chunk_id?: number | null;
  score?: number | null;
  excerpt?: string | null;
};

type ApiChatResponse = {
  agent?: string;
  question?: string;
  answer?: string;
  sources?: ApiChatSource[];
  plan?: {
    needs_multi_hop?: boolean;
    retrieval_steps?: string[];
    comparison_required?: boolean;
    final_task?: string;
  };
  retrieval_evaluations?: Record<
    string,
    {
      relevant?: boolean;
      sufficient?: boolean;
      reason?: string;
      retry_step?: string | null;
    }
  >;
};

type ApiFeedback = {
  feedback_id?: string;
  mission_id?: string;
  created_at?: string;
  author?: string | null;
  scope?: 'mission' | 'report' | 'observation' | null;
  target_id?: string | null;
  rating?: number | null;
  sentiment?: 'positive' | 'neutral' | 'negative' | null;
  categories?: string[] | null;
  comment?: string | null;
  requires_action?: boolean | null;
  status?: 'pending' | 'reviewed' | 'resolved' | null;
};

type ApiFeedbackListResponse = {
  mission_id?: string;
  feedbacks?: ApiFeedback[];
};

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' }
});

function handleApiError(error: any): Error {
  console.error('API Error:', error);

  if (!error.response && (error.code === 'ERR_NETWORK' || error.message?.includes('Network Error') || error.message?.includes('CORS'))) {
    return new Error('API request failed. Make sure the backend is running and the Vite dev server was restarted.');
  }

  if (error.response?.status >= 500) {
    return new Error('Server error. Please try again later.');
  }
  if (error.response?.status === 404) {
    return new Error('Resource not found.');
  }
  if (error.response?.status === 400) {
    return new Error(error.response.data?.detail || 'Invalid request.');
  }

  return new Error(error.message || 'Unexpected API error.');
}

function normalizePriority(priority?: string | null): PriorityLevel {
  const normalized = String(priority ?? '').trim().toLowerCase();
  if (normalized === 'critical') return 'Critical';
  if (normalized === 'high') return 'High';
  if (normalized === 'medium') return 'Medium';
  return 'Low';
}

function normalizePrioritySource(source?: string | null): PrioritySource {
  if (source === 'manual_override') return 'manual_override';
  if (source === 'generated_pipeline') return 'generated_pipeline';
  if (!source) return '';
  return 'system';
}

function normalizeObservationStatus(status?: string | null): Observation['status'] {
  return String(status ?? '').trim().toLowerCase() === 'validated' ? 'Validated' : 'Draft';
}

function mapMission(apiMission: ApiMission): Mission {
  return {
    mission_id: apiMission.mission_id,
    name: apiMission.name,
    client: apiMission.client_name ?? '',
    fiscal_year: apiMission.fiscal_year ?? '',
    created_at: apiMission.created_at,
    updated_at: apiMission.updated_at,
    status: apiMission.status ?? 'Draft',
    parsing_status: apiMission.parsing_status,
    observations_count: apiMission.observations_count ?? 0,
    applications_count: apiMission.applications_count ?? 0,
    control_ids_count: apiMission.control_ids_count ?? 0,
    current_file: apiMission.uploaded_file_name
      ? {
          name: apiMission.uploaded_file_name,
          size: ''
        }
      : undefined,
    summary: '',
    key_findings: []
  };
}

function mapObservation(apiObservation: ApiObservation, index: number): Observation {
  return {
    id: apiObservation.observation_id || `obs-${index + 1}`,
    observation_id: apiObservation.observation_id || `obs-${index + 1}`,
    domain: apiObservation.domaine_controle || '',
    domaine_controle: apiObservation.domaine_controle || '',
    category: apiObservation.categorie_controle || '',
    categorie_controle: apiObservation.categorie_controle || '',
    control_id: apiObservation.controle_ref || '',
    controle_ref: apiObservation.controle_ref || '',
    application: apiObservation.application || '',
    layer: apiObservation.couche || '',
    couche: apiObservation.couche || '',
    title: apiObservation.titre_observation || '',
    titre_observation: apiObservation.titre_observation || '',
    expected_control: apiObservation.controle_attendu || '',
    controle_attendu: apiObservation.controle_attendu || '',
    finding: apiObservation.constat || apiObservation.titre_observation || '',
    constat: apiObservation.constat || '',
    risk: apiObservation.risque_associe || '',
    risque_associe: apiObservation.risque_associe || '',
    compensating_procedure: apiObservation.procedure_compensatoire || '',
    procedure_compensatoire: apiObservation.procedure_compensatoire || '',
    impact: apiObservation.impact_potentiel || '',
    impact_potentiel: apiObservation.impact_potentiel || '',
    root_cause: apiObservation.cause_racine || '',
    cause_racine: apiObservation.cause_racine || '',
    comments: apiObservation.commentaire_auditeur || '',
    commentaire_auditeur: apiObservation.commentaire_auditeur || '',
    population: apiObservation.population || '',
    sample_size: apiObservation.taille_echantillon || '',
    taille_echantillon: apiObservation.taille_echantillon || '',
    exception_count: apiObservation.nombre_exceptions || '',
    nombre_exceptions: apiObservation.nombre_exceptions || '',
    owners: apiObservation.responsables || '',
    responsables: apiObservation.responsables || '',
    evidence_references: apiObservation.references_probantes || '',
    references_probantes: apiObservation.references_probantes || '',
    control_status: apiObservation.statut_controle || '',
    statut_controle: apiObservation.statut_controle || '',
    priority: apiObservation.priority ? normalizePriority(apiObservation.priority) : null,
    priority_justification: apiObservation.priority_justification || '',
    priority_reason: apiObservation.priority_reason || '',
    priority_source: normalizePrioritySource(apiObservation.priority_source),
    status: normalizeObservationStatus(apiObservation.statut_validation),
    statut_validation: apiObservation.statut_validation || '',
    recommendation: apiObservation.recommandation_proposee || ''
    ,
    recommandation_proposee: apiObservation.recommandation_proposee || '',
    included_in_report: apiObservation.included_in_report ?? true
  };
}

function mapParsedMissionContext(apiMission?: ApiObservationsResponse['mission']): ParsedMissionContext | null {
  if (!apiMission) return null;

  return {
    mission_id: apiMission.mission_id || '',
    titre_mission: apiMission.titre_mission || '',
    entite_auditee: apiMission.entite_auditee || '',
    type_mission: apiMission.type_mission || '',
    periode: apiMission.periode || '',
    intervenants: Array.isArray(apiMission.intervenants) ? apiMission.intervenants : [],
    perimetre_intervention: apiMission.perimetre_intervention || '',
    objectifs: Array.isArray(apiMission.objectifs) ? apiMission.objectifs : [],
    date_rapport: apiMission.date_rapport || '',
    processus_couverts: Array.isArray(apiMission.processus_couverts) ? apiMission.processus_couverts : [],
    applications: Array.isArray(apiMission.applications) ? apiMission.applications : []
  };
}

function toApiObservation(observation: Observation): ApiObservation {
  return {
    observation_id: observation.observation_id || observation.id,
    domaine_controle: observation.domaine_controle || observation.domain,
    categorie_controle: observation.categorie_controle || observation.category,
    controle_ref: observation.controle_ref || observation.control_id,
    application: observation.application,
    couche: observation.couche || observation.layer,
    titre_observation: observation.titre_observation || observation.title,
    controle_attendu: observation.controle_attendu || observation.expected_control,
    constat: observation.constat || observation.finding,
    risque_associe: observation.risque_associe || observation.risk,
    procedure_compensatoire: observation.procedure_compensatoire || observation.compensating_procedure,
    impact_potentiel: observation.impact_potentiel || observation.impact,
    cause_racine: observation.cause_racine || observation.root_cause,
    commentaire_auditeur: observation.commentaire_auditeur || observation.comments,
    population: observation.population,
    taille_echantillon: observation.taille_echantillon || observation.sample_size,
    nombre_exceptions: observation.nombre_exceptions || observation.exception_count,
    responsables: observation.responsables || observation.owners,
    references_probantes: observation.references_probantes || observation.evidence_references,
    statut_controle: observation.statut_controle || observation.control_status,
    priority: observation.priority,
    priority_justification: observation.priority_justification,
    priority_reason: observation.priority_reason,
    priority_source: observation.priority_source,
    statut_validation: observation.statut_validation || observation.status,
    recommandation_proposee: observation.recommandation_proposee || observation.recommendation,
    included_in_report: observation.included_in_report
  };
}

function normalizeChatMessages(payload: any): ChatMessage[] {
  const rawMessages = Array.isArray(payload?.messages)
    ? payload.messages
    : Array.isArray(payload)
    ? payload
    : payload?.response
    ? [{ role: 'assistant', content: String(payload.response) }]
    : payload?.answer
    ? [{ role: 'assistant', content: String(payload.answer) }]
    : payload?.message
    ? [{ role: 'assistant', content: String(payload.message) }]
    : [];

  return rawMessages.map((message: ApiAssistantMessage, index: number) => ({
    id: message.id || `msg-${Date.now()}-${index}`,
    role: message.role === 'user' ? 'user' : 'assistant',
    content: message.content || message.message || message.text || ''
  }));
}

function mapChatSources(sources?: ApiChatSource[] | null): ChatSource[] {
  if (!Array.isArray(sources)) return [];

  return sources.map((source, index) => ({
    source_id: source.source_id || `Source ${index + 1}`,
    document_name: source.document_name || 'Unknown document',
    chunk_id: typeof source.chunk_id === 'number' ? source.chunk_id : null,
    score: typeof source.score === 'number' ? source.score : null,
    excerpt: source.excerpt || null
  }));
}

function buildQuestionFromHistory(payload: AssistantMessagePayload): string {
  const latestMessage = payload.message.trim();
  const previousMessages = payload.history.filter(
    (message) => !(message.role === 'user' && message.content.trim() === latestMessage)
  );

  if (previousMessages.length === 0) return latestMessage;

  const historyText = previousMessages
    .map((message) => `${message.role === 'assistant' ? 'Assistant' : 'User'}: ${message.content}`)
    .join('\n\n');

  return `Conversation context:\n${historyText}\n\nCurrent question:\n${latestMessage}`;
}

function buildPriorityDistribution(observations: Observation[]): Record<PriorityLevel, number> {
  return observations.reduce(
    (accumulator, observation) => {
      accumulator[observation.priority] += 1;
      return accumulator;
    },
    { Critical: 0, High: 0, Medium: 0, Low: 0 }
  );
}

function extractFiscalYearValue(value?: string | null): string {
  const text = String(value ?? '').trim();
  if (!text) return '';

  const fyMatch = text.match(/\bFY\s*[- ]?\s*(\d{2,4})\b/i);
  if (fyMatch) return `FY${fyMatch[1].slice(-2)}`;

  const years = [...text.matchAll(/\b(20\d{2})\b/g)].map((match) => match[1]);
  if (years.length > 0) return `FY${years[years.length - 1].slice(-2)}`;

  return text;
}

function mapReportPreview(response: ApiReportPreviewResponse): ReportPreview {
  const structuredOutput = response.structured_output;
  const toStringArray = (value: unknown): string[] =>
    Array.isArray(value) ? value.map((item) => String(item ?? '').trim()).filter(Boolean) : [];

  const toRecordArray = (value: unknown): Record<string, unknown>[] => (Array.isArray(value) ? value : []);

  const mapCoveredControls = (value: unknown): ReportCoveredControl[] =>
    toRecordArray(value).map((item) => ({
      reference: String(item.reference ?? ''),
      process: String(item.process ?? ''),
      description: String(item.description ?? ''),
      test_procedure: String(item.test_procedure ?? '')
    }));

  const mapControlMatrix = (value: unknown): ReportControlMatrixEntry[] =>
    toRecordArray(value).map((item) => ({
      reference: String(item.reference ?? ''),
      process: String(item.process ?? ''),
      control_description: String(item.control_description ?? ''),
      application_statuses:
        item.application_statuses && typeof item.application_statuses === 'object'
          ? Object.fromEntries(
              Object.entries(item.application_statuses as Record<string, unknown>).map(([key, entryValue]) => [
                key,
                String(entryValue ?? '')
              ])
            )
          : {},
      overall_priority: String(item.overall_priority ?? '')
    }));

  const mapKeyFigures = (value: unknown): ReportKeyFigure[] =>
    toRecordArray(value).map((item) => ({
      label: String(item.label ?? ''),
      value: String(item.value ?? ''),
      commentary: String(item.commentary ?? '')
    }));

  const mapApplicationDetails = (value: unknown): ReportApplicationDetail[] =>
    toRecordArray(value).map((item) => ({
      name: String(item.name ?? item.application ?? item.nom_application ?? ''),
      description: String(item.description ?? ''),
      operating_system: String(item.operating_system ?? item.systeme_exploitation ?? ''),
      database: String(item.database ?? item.base_de_donnees ?? ''),
      provider: String(item.provider ?? item.prestataire ?? '')
    }));

  const mapProcessSummaries = (value: unknown): ReportProcessSummary[] =>
    toRecordArray(value).map((item) => ({
      process_code: String(item.process_code ?? ''),
      process_name: String(item.process_name ?? ''),
      observation_count: Number(item.observation_count ?? 0),
      applications: toStringArray(item.applications),
      strengths: toStringArray(item.strengths),
      watch_points: toStringArray(item.watch_points)
    }));

  const mapPrioritySummary = (value: unknown): ReportPrioritySummaryEntry[] =>
    toRecordArray(value).map((item) => ({
      priority: String(item.priority ?? ''),
      count: Number(item.count ?? 0),
      percentage: Number(item.percentage ?? 0)
    }));

  const mapFindings = (value: unknown): ReportFinding[] =>
    toRecordArray(value).map((item) => ({
      observation_id: String(item.observation_id ?? ''),
      reference: String(item.reference ?? ''),
      domain: String(item.domain ?? ''),
      category: String(item.category ?? ''),
      application: String(item.application ?? ''),
      layer: String(item.layer ?? ''),
      owners: String(item.owners ?? ''),
      title: String(item.title ?? ''),
      expected_control: String(item.expected_control ?? ''),
      finding: String(item.finding ?? ''),
      compensating_procedure: String(item.compensating_procedure ?? ''),
      risk_impact: String(item.risk_impact ?? ''),
      impact_detail: String(item.impact_detail ?? ''),
      root_cause: String(item.root_cause ?? ''),
      recommendation: String(item.recommendation ?? ''),
      recommendation_objective: String(item.recommendation_objective ?? ''),
      recommendation_steps: toStringArray(item.recommendation_steps),
      priority: String(item.priority ?? ''),
      priority_justification: String(item.priority_justification ?? ''),
      auditor_comment: String(item.auditor_comment ?? ''),
      management_summary: String(item.management_summary ?? '')
    }));

  const normalizedStructuredOutput: ReportStructuredOutput = {
    cover_title: String(structuredOutput?.cover_title ?? ''),
    cover_subtitle: String(structuredOutput?.cover_subtitle ?? ''),
    client_name: String(structuredOutput?.client_name ?? ''),
    report_period: String(structuredOutput?.report_period ?? ''),
    report_date: String(structuredOutput?.report_date ?? ''),
    confidentiality_notice: String(structuredOutput?.confidentiality_notice ?? ''),
    table_of_contents: toStringArray(structuredOutput?.table_of_contents),
    preamble: String(structuredOutput?.preamble ?? ''),
    objectives: toStringArray(structuredOutput?.objectives),
    stakeholders: toStringArray(structuredOutput?.stakeholders),
    scope_summary: String(structuredOutput?.scope_summary ?? ''),
    applications: toStringArray(structuredOutput?.applications),
    application_details: mapApplicationDetails(structuredOutput?.application_details),
    covered_processes: toStringArray(structuredOutput?.covered_processes),
    audit_approach: toStringArray(structuredOutput?.audit_approach),
    covered_controls: mapCoveredControls(structuredOutput?.covered_controls),
    control_matrix: mapControlMatrix(structuredOutput?.control_matrix),
    key_figures: mapKeyFigures(structuredOutput?.key_figures),
    executive_highlights: toStringArray(structuredOutput?.executive_highlights),
    strengths: toStringArray(structuredOutput?.strengths),
    watch_points: toStringArray(structuredOutput?.watch_points),
    maturity_level: String(structuredOutput?.maturity_level ?? ''),
    maturity_assessment: String(structuredOutput?.maturity_assessment ?? ''),
    priority_insight: String(structuredOutput?.priority_insight ?? ''),
    strategic_priorities: toStringArray(structuredOutput?.strategic_priorities),
    transversal_initiatives: toStringArray(structuredOutput?.transversal_initiatives),
    process_summaries: mapProcessSummaries(structuredOutput?.process_summaries),
    general_synthesis: String(structuredOutput?.general_synthesis ?? ''),
    priority_summary: mapPrioritySummary(structuredOutput?.priority_summary),
    detailed_findings: mapFindings(structuredOutput?.detailed_findings),
    detailed_recommendations: mapFindings(structuredOutput?.detailed_recommendations),
    prior_recommendations_follow_up: toStringArray(structuredOutput?.prior_recommendations_follow_up),
    appendices: toStringArray(structuredOutput?.appendices),
    executive_summary: String(structuredOutput?.executive_summary ?? ''),
    conclusion: String(structuredOutput?.conclusion ?? '')
  };

  return {
    agent: response.agent,
    request: response.request,
    answer: response.answer || '',
    structured_output: normalizedStructuredOutput
  };
}

function mapFeedback(apiFeedback: ApiFeedback): AuditorFeedback {
  const normalizedRating = Number(apiFeedback.rating);
  const rating =
    normalizedRating >= 1 && normalizedRating <= 5 ? (normalizedRating as AuditorFeedback['rating']) : undefined;

  return {
    feedback_id: apiFeedback.feedback_id || '',
    mission_id: apiFeedback.mission_id || '',
    created_at: apiFeedback.created_at || '',
    author: apiFeedback.author || undefined,
    scope: apiFeedback.scope || undefined,
    target_id: apiFeedback.target_id || undefined,
    rating,
    sentiment: apiFeedback.sentiment || undefined,
    categories: Array.isArray(apiFeedback.categories)
      ? (apiFeedback.categories.filter(Boolean) as AuditorFeedback['categories'])
      : [],
    comment: apiFeedback.comment || undefined,
    requires_action: Boolean(apiFeedback.requires_action),
    status: apiFeedback.status || 'pending'
  };
}

export async function getMissions(): Promise<Mission[]> {
  try {
    const response = await api.get<ApiMission[]>('/missions');
    return response.data.map(mapMission);
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function createMission(payload: CreateMissionPayload): Promise<Mission> {
  try {
    const response = await api.post<ApiMission>('/missions', {
      mission_id: payload.mission_id,
      name: payload.name,
      client_name: payload.client,
      fiscal_year: payload.fiscal_year
    });
    return mapMission(response.data);
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function createMissionFromExcel(file: File): Promise<Mission> {
  try {
    const workbook = XLSX.read(await file.arrayBuffer(), { type: 'array' });
    const normalize = (value: unknown) =>
      String(value ?? '')
        .trim()
        .toLowerCase()
        .replace(/[_-]+/g, ' ')
        .replace(/\s+/g, ' ');

    const getCellString = (value: unknown) => {
      const result = String(value ?? '').trim();
      return result.length > 0 ? result : null;
    };

    const missionSheetName =
      workbook.SheetNames.find((sheetName) => normalize(sheetName) === 'mission') ||
      workbook.SheetNames.find((sheetName) => normalize(sheetName).includes('mission'));

    if (!missionSheetName) {
      throw new Error('No mission sheet found in workbook.');
    }

    const missionSheet = workbook.Sheets[missionSheetName];
    const rows = XLSX.utils.sheet_to_json(missionSheet, { header: 1, blankrows: false }) as unknown[][];

    const expectedHeaders = {
      missionId: ['id mission', 'mission id'],
      name: ['titre mission', 'mission name', 'name'],
      client: ['entité auditée', 'entite auditee', 'client', 'client name'],
      fiscalYear: ['période', 'periode', 'fiscal year', 'fiscal_year', 'fy']
    } as const;

    const findHeaderRowIndex = () =>
      rows.findIndex((row) => {
        const normalizedCells = row.map((cell) => normalize(cell)).filter(Boolean);
        return (
          expectedHeaders.name.some((header) => normalizedCells.includes(header)) &&
          expectedHeaders.client.some((header) => normalizedCells.includes(header)) &&
          expectedHeaders.fiscalYear.some((header) => normalizedCells.includes(header))
        );
      });

    const headerRowIndex = findHeaderRowIndex();
    if (headerRowIndex === -1) {
      throw new Error('Mission sheet headers not found in workbook.');
    }

    const headerRow = rows[headerRowIndex].map((cell) => normalize(cell));
    const valueRow = rows.slice(headerRowIndex + 1).find((row) => row.some((cell) => getCellString(cell)));

    if (!valueRow) {
      throw new Error('Mission sheet values not found in workbook.');
    }

    const findValueByHeaders = (headers: readonly string[]) => {
      const columnIndex = headerRow.findIndex((header) => headers.includes(header));
      if (columnIndex === -1) return null;
      return getCellString(valueRow[columnIndex]);
    };

    const missionId = findValueByHeaders(expectedHeaders.missionId);
    const name = findValueByHeaders(expectedHeaders.name);
    const client = findValueByHeaders(expectedHeaders.client);
    const fiscalYear = extractFiscalYearValue(findValueByHeaders(expectedHeaders.fiscalYear));

    if (!name || !client || !fiscalYear) {
      throw new Error(
        `Missing required mission data. Please include mission name, client, and fiscal year in the workbook. Found: name=${name ?? 'null'}, client=${client ?? 'null'}, fiscal_year=${fiscalYear ?? 'null'}`
      );
    }

    const mission = await createMission({
      mission_id: missionId ?? undefined,
      name: String(name),
      client: String(client),
      fiscal_year: String(fiscalYear)
    });

    await uploadMissionExcel(mission.mission_id, file);
    return await getMission(mission.mission_id);
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function getMission(missionId: string): Promise<Mission> {
  try {
    const response = await api.get<ApiMission>(`/missions/${missionId}`);
    return mapMission(response.data);
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function updateMission(missionId: string, payload: UpdateMissionPayload): Promise<Mission> {
  try {
    const response = await api.put<ApiMission>(`/missions/${missionId}`, {
      name: payload.name,
      client_name: payload.client,
      fiscal_year: payload.fiscal_year
    });
    return mapMission(response.data);
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function deleteMission(missionId: string): Promise<{ deleted: string }> {
  try {
    const response = await api.delete<{ deleted: string }>(`/missions/${missionId}`);
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function uploadMissionExcel(missionId: string, file: File): Promise<void> {
  try {
    const form = new FormData();
    form.append('file', file);
    await api.post('/upload', form, {
      params: { mission_id: missionId },
      headers: { 'Content-Type': 'multipart/form-data' }
    });
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function getMissionObservations(
  missionId: string
): Promise<{ mission: ParsedMissionContext | null; observations: Observation[] }> {
  try {
    const response = await api.get<ApiObservation[] | ApiObservationsResponse>(`/missions/${missionId}/observations`);
    const data = Array.isArray(response.data)
      ? response.data
      : Array.isArray(response.data?.observations)
      ? response.data.observations
      : [];
    const mission = Array.isArray(response.data) ? null : mapParsedMissionContext(response.data?.mission);
    return {
      mission,
      observations: data.map(mapObservation)
    };
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function updateMissionObservations(missionId: string, observations: Observation[]): Promise<void> {
  try {
    await api.put(`/missions/${missionId}/observations`, {
      observations: observations.map(toApiObservation),
      preserve_manual_overrides: true
    });
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function recalculateMissionPriorities(missionId: string): Promise<Observation[]> {
  try {
    const response = await api.post<{ observations?: ApiObservation[] }>(`/missions/${missionId}/observations/recalculate-priorities`);
    const data = Array.isArray(response.data?.observations) ? response.data.observations : [];
    return data.map(mapObservation);
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function getMissionReportPreview(missionId: string): Promise<ReportPreview> {
  try {
    const response = await api.get<ApiReportPreviewResponse>(`/missions/${missionId}/report-preview`);
    return mapReportPreview(response.data);
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function regenerateMissionReportPreview(missionId: string): Promise<ReportPreview> {
  try {
    const response = await api.post<ApiReportPreviewResponse>(`/missions/${missionId}/report-preview/regenerate`);
    return mapReportPreview(response.data);
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function exportMissionReportPptx(missionId: string): Promise<Blob> {
  try {
    const response = await api.get(`/missions/${missionId}/export-report`, { responseType: 'blob' });
    return response.data;
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function sendMissionAssistantMessage(missionId: string, payload: AssistantMessagePayload): Promise<AssistantResponse> {
  try {
    const response = await api.post<ApiChatResponse>('/chat', {
      question: buildQuestionFromHistory(payload),
      mission_id: missionId
    });

    return {
      message: {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: response.data?.answer || 'No answer returned by the backend.',
        sources: mapChatSources(response.data?.sources),
        agent: response.data?.agent || 'qa_agent'
      }
    };
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function getMissionFeedbacks(missionId: string): Promise<AuditorFeedback[]> {
  try {
    const response = await api.get<ApiFeedbackListResponse>(`/missions/${missionId}/feedbacks`);
    const feedbacks = Array.isArray(response.data?.feedbacks) ? response.data.feedbacks : [];
    return feedbacks.map(mapFeedback);
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function createMissionFeedback(missionId: string, payload: CreateFeedbackPayload): Promise<AuditorFeedback> {
  try {
    const response = await api.post<ApiFeedback>(`/missions/${missionId}/feedbacks`, payload);
    return mapFeedback(response.data);
  } catch (error) {
    throw handleApiError(error);
  }
}

export async function updateMissionFeedbackStatus(
  missionId: string,
  feedbackId: string,
  status: AuditorFeedback['status']
): Promise<AuditorFeedback> {
  try {
    const response = await api.patch<ApiFeedback>(`/missions/${missionId}/feedbacks/${feedbackId}`, { status });
    return mapFeedback(response.data);
  } catch (error) {
    throw handleApiError(error);
  }
}
