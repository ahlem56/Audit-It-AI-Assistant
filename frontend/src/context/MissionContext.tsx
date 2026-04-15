import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import {
  getMissions,
  getMission,
  getMissionObservations,
  getMissionReportPreview,
  createMission,
  createMissionFromExcel as createMissionFromExcelApi,
  updateMission,
  deleteMission as deleteMissionApi,
  uploadMissionExcel,
  updateMissionObservations,
  recalculateMissionPriorities,
  regenerateMissionReportPreview,
  exportMissionReportPptx,
  sendMissionAssistantMessage,
  getMissionFeedbacks,
  createMissionFeedback,
  updateMissionFeedbackStatus as updateMissionFeedbackStatusApi
} from '../services/api';
import type {
  AuditorFeedback,
  CreateFeedbackPayload,
  Mission,
  Observation,
  ParsedMissionContext,
  ReportPreview,
  ChatMessage,
  CreateMissionPayload,
  UpdateMissionPayload,
  AssistantMessagePayload
} from '../types';

interface MissionContextValue {
  // Missions
  missions: Mission[];
  activeMissionId: string | null;
  activeMission: Mission | null;
  loadingMissions: boolean;
  loadingMission: boolean;
  uploadState: { uploading: boolean; error: string | null };

  // Observations
  observations: Observation[];
  parsedMission: ParsedMissionContext | null;
  loadingObservations: boolean;

  // Report
  reportPreview: ReportPreview | null;
  loadingReport: boolean;

  // Chat
  chatHistory: ChatMessage[];
  loadingChat: boolean;

  // Feedback
  feedbackEntries: AuditorFeedback[];
  activeMissionFeedback: AuditorFeedback[];
  loadingFeedback: boolean;

  // Actions
  loadMissions: () => Promise<void>;
  setActiveMissionId: (id: string | null) => void;
  createNewMission: (payload: CreateMissionPayload) => Promise<Mission>;
  createMissionFromExcel: (file: File) => Promise<Mission>;
  deleteExistingMission: (missionId: string) => Promise<void>;
  updateActiveMission: (payload: UpdateMissionPayload) => Promise<void>;
  uploadExcel: (file: File) => Promise<void>;
  loadObservations: () => Promise<void>;
  updateObservations: (observations: Observation[]) => Promise<void>;
  recalculatePriorities: () => Promise<void>;
  loadReportPreview: () => Promise<void>;
  regenerateReportPreview: () => Promise<void>;
  exportReportPptx: () => Promise<Blob>;
  sendAssistantMessage: (payload: AssistantMessagePayload) => Promise<void>;
  loadFeedback: () => Promise<void>;
  submitFeedback: (payload: CreateFeedbackPayload) => Promise<AuditorFeedback | null>;
  updateFeedbackStatus: (feedbackId: string, status: AuditorFeedback['status']) => Promise<void>;
}

const MissionContext = createContext<MissionContextValue | undefined>(undefined);

export function MissionProvider({ children }: { children: ReactNode }) {
  const [missions, setMissions] = useState<Mission[]>([]);
  const [activeMissionId, setActiveMissionIdState] = useState<string | null>(() => {
    return localStorage.getItem('activeMissionId') || null;
  });
  const [activeMission, setActiveMission] = useState<Mission | null>(null);
  const [loadingMissions, setLoadingMissions] = useState(false);
  const [loadingMission, setLoadingMission] = useState(false);
  const [uploadState, setUploadState] = useState({ uploading: false, error: null as string | null });

  const [observations, setObservations] = useState<Observation[]>([]);
  const [parsedMission, setParsedMission] = useState<ParsedMissionContext | null>(null);
  const [loadingObservations, setLoadingObservations] = useState(false);

  const [reportPreview, setReportPreview] = useState<ReportPreview | null>(null);
  const [loadingReport, setLoadingReport] = useState(false);

  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [loadingChat, setLoadingChat] = useState(false);
  const [feedbackEntries, setFeedbackEntries] = useState<AuditorFeedback[]>([]);
  const [loadingFeedback, setLoadingFeedback] = useState(false);

  const loadMissions = async () => {
    setLoadingMissions(true);
    try {
      const data = await getMissions();
      setMissions(data);
    } catch (error) {
      console.error('Failed to load missions:', error);
      setMissions([]);
    } finally {
      setLoadingMissions(false);
    }
  };

  const setActiveMissionId = (id: string | null) => {
    setActiveMissionIdState(id);
    localStorage.setItem('activeMissionId', id || '');
    if (id) {
      loadActiveMission(id);
    } else {
      setActiveMission(null);
      setObservations([]);
      setParsedMission(null);
      setReportPreview(null);
      setChatHistory([]);
      setFeedbackEntries([]);
    }
  };

  const loadActiveMission = async (id: string) => {
    setLoadingMission(true);
    try {
      const mission = await getMission(id);
      setActiveMission(mission);
    } catch (error) {
      console.error('Failed to load mission:', error);
      setActiveMission(null);
    } finally {
      setLoadingMission(false);
    }
  };

  const createNewMission = async (payload: CreateMissionPayload): Promise<Mission> => {
    const newMission = await createMission(payload);
    setMissions(prev => [...prev, newMission]);
    return newMission;
  };

  const createMissionFromExcel = async (file: File): Promise<Mission> => {
    const newMission = await createMissionFromExcelApi(file);
    setMissions(prev => [...prev, newMission]);
    return newMission;
  };

  const deleteExistingMission = async (missionId: string) => {
    await deleteMissionApi(missionId);
    setMissions((prev) => prev.filter((mission) => mission.mission_id !== missionId));

    if (activeMissionId === missionId) {
      setActiveMissionId(null);
    }
  };

  const updateActiveMission = async (payload: UpdateMissionPayload) => {
    if (!activeMissionId) return;
    const updated = await updateMission(activeMissionId, payload);
    setActiveMission(updated);
    setMissions(prev => prev.map(m => m.mission_id === activeMissionId ? updated : m));
  };

  const uploadExcel = async (file: File) => {
    if (!activeMissionId) return;
    setUploadState({ uploading: true, error: null });
    try {
      await uploadMissionExcel(activeMissionId, file);
      await loadActiveMission(activeMissionId); // Refresh mission details
      await loadObservations(); // Refresh observations
      setUploadState({ uploading: false, error: null });
    } catch (error) {
      setUploadState({ uploading: false, error: error instanceof Error ? error.message : 'Upload failed' });
      throw error;
    }
  };

  const loadObservations = async () => {
    if (!activeMissionId) return;
    setLoadingObservations(true);
    try {
      const data = await getMissionObservations(activeMissionId);
      setParsedMission(data.mission);
      setObservations(data.observations);
    } catch (error) {
      console.error('Failed to load observations:', error);
      setParsedMission(null);
      setObservations([]);
    } finally {
      setLoadingObservations(false);
    }
  };

  const updateObservations = async (obs: Observation[]) => {
    if (!activeMissionId) return;
    try {
      await updateMissionObservations(activeMissionId, obs);
      setObservations(obs);
    } catch (error) {
      console.error('Failed to update observations:', error);
      throw error;
    }
  };

  const recalculatePriorities = async () => {
    if (!activeMissionId) return;
    try {
      const updated = await recalculateMissionPriorities(activeMissionId);
      setObservations(updated);
    } catch (error) {
      console.error('Failed to recalculate priorities:', error);
      throw error;
    }
  };

  const loadReportPreview = async () => {
    if (!activeMissionId) return;
    setLoadingReport(true);
    try {
      const data = await getMissionReportPreview(activeMissionId);
      setReportPreview(data);
    } catch (error) {
      console.error('Failed to load report preview:', error);
      setReportPreview(null);
    } finally {
      setLoadingReport(false);
    }
  };

  const regenerateReportPreview = async () => {
    if (!activeMissionId) return;
    setLoadingReport(true);
    try {
      const data = await regenerateMissionReportPreview(activeMissionId);
      setReportPreview(data);
    } catch (error) {
      console.error('Failed to regenerate report:', error);
      throw error;
    } finally {
      setLoadingReport(false);
    }
  };

  const exportReportPptx = async (): Promise<Blob> => {
    if (!activeMissionId) throw new Error('No active mission');
    return await exportMissionReportPptx(activeMissionId);
  };

  const sendAssistantMessage = async (payload: AssistantMessagePayload) => {
    if (!activeMissionId) return;
    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: payload.message.trim()
    };

    setChatHistory((current) => [...current, userMessage]);
    setLoadingChat(true);
    try {
      const response = await sendMissionAssistantMessage(activeMissionId, payload);
      setChatHistory((current) => [...current, response.message]);
    } catch (error) {
      setChatHistory((current) => current.filter((message) => message.id !== userMessage.id));
      console.error('Failed to send message:', error);
      throw error;
    } finally {
      setLoadingChat(false);
    }
  };

  const loadFeedback = async () => {
    if (!activeMissionId) {
      setFeedbackEntries([]);
      return;
    }

    setLoadingFeedback(true);
    try {
      const data = await getMissionFeedbacks(activeMissionId);
      setFeedbackEntries(data);
    } catch (error) {
      console.error('Failed to load feedback:', error);
      setFeedbackEntries([]);
    } finally {
      setLoadingFeedback(false);
    }
  };

  const submitFeedback = async (payload: CreateFeedbackPayload): Promise<AuditorFeedback | null> => {
    if (!activeMissionId) return null;

    const feedback = await createMissionFeedback(activeMissionId, payload);
    setFeedbackEntries((current) => [feedback, ...current]);
    return feedback;
  };

  const updateFeedbackStatus = async (feedbackId: string, status: AuditorFeedback['status']) => {
    if (!activeMissionId) return;

    const updated = await updateMissionFeedbackStatusApi(activeMissionId, feedbackId, status);
    setFeedbackEntries((current) =>
      current.map((entry) => (entry.feedback_id === feedbackId ? updated : entry))
    );
  };

  useEffect(() => {
    loadMissions();
  }, []);

  useEffect(() => {
    if (activeMissionId) {
      loadActiveMission(activeMissionId);
      loadObservations();
      loadReportPreview();
      loadFeedback();
    }
  }, [activeMissionId]);

  const activeMissionFeedback = activeMissionId
    ? feedbackEntries.filter((entry) => entry.mission_id === activeMissionId)
    : [];

  const value: MissionContextValue = {
    missions,
    activeMissionId,
    activeMission,
    loadingMissions,
    loadingMission,
    uploadState,
    observations,
    parsedMission,
    loadingObservations,
    reportPreview,
    loadingReport,
    chatHistory,
    loadingChat,
    feedbackEntries,
    activeMissionFeedback,
    loadingFeedback,
    loadMissions,
    setActiveMissionId,
    createNewMission,
    createMissionFromExcel,
    deleteExistingMission,
    updateActiveMission,
    uploadExcel,
    loadObservations,
    updateObservations,
    recalculatePriorities,
    loadReportPreview,
    regenerateReportPreview,
    exportReportPptx,
    sendAssistantMessage,
    loadFeedback,
    submitFeedback,
    updateFeedbackStatus
  };

  return (
    <MissionContext.Provider value={value}>
      {children}
    </MissionContext.Provider>
  );
}

export function useMissionContext() {
  const context = useContext(MissionContext);
  if (!context) {
    throw new Error('useMissionContext must be used within MissionProvider');
  }
  return context;
}
