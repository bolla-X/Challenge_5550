import { apiFetch } from "./client";
import type { AuthUser } from "./types";
import type {
  AlertsResponse,
  Alert,
  CameraDiscoveryResponse,
  CameraFeatureSet,
  CameraRecord,
  CamerasResponse,
  EventsResponse,
  FeaturesResponse,
  ModelDiagnostics,
  MonitorStatus,
  OverlayOptions,
  PreflightResponse,
  RiskAreaState,
  RiskScore,
  RiskTrendResponse,
  RuntimeSettings,
  SettingsResponse,
  StatusResponse,
} from "./types";

// One function per Flask route, named after the route. See app/api/*.py.

// ---- autenticação (sessão em cookie HttpOnly; não há token no JS) -------
export const getMe = () => apiFetch<{ user: AuthUser | null }>("/api/auth/me");
export const login = (email: string, password: string) =>
  apiFetch<{ user: AuthUser }>("/api/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
export const logout = () => apiFetch<{ ok: boolean }>("/api/auth/logout", { method: "POST" });

export const getStatus = () => apiFetch<StatusResponse>("/status");
export const getPreflight = () => apiFetch<PreflightResponse>("/preflight");
export const startMonitor = () => apiFetch<StatusResponse>("/start", { method: "POST" });
export const stopMonitor = () => apiFetch<StatusResponse>("/stop", { method: "POST" });

export const getFeatures = () => apiFetch<FeaturesResponse>("/features");
export const patchFeatures = (features: Record<string, boolean>) =>
  apiFetch<FeaturesResponse>("/features", { method: "PATCH", body: JSON.stringify({ features }) });

// ---- controle por câmera (Fase A, Passo 5/6 — ver app/api/cameras.py) ----
// Mesmo shape de resposta do /status legado (MonitorStatus), só que
// escopado a uma câmera. video_feed não tem função própria aqui — é usado
// direto como `src` de <img>, não faz sentido "buscar" um MJPEG via fetch.
export const getCameraStatus = (cameraId: number) => apiFetch<MonitorStatus>(`/api/cameras/${cameraId}/status`);
export const startCamera = (cameraId: number) => apiFetch<MonitorStatus>(`/api/cameras/${cameraId}/start`, { method: "POST" });
export const stopCamera = (cameraId: number) => apiFetch<MonitorStatus>(`/api/cameras/${cameraId}/stop`, { method: "POST" });

// ---- CRUD de câmeras (ver app/api/cameras.py) ---------------------------
export const listCameras = () => apiFetch<CamerasResponse>("/api/cameras");
export const createCamera = (payload: {
  name: string;
  location?: string | null;
  source_type: "USB" | "RTSP" | "Arquivo";
  source: string;
  fps?: number;
  width?: number;
  height?: number;
  features?: Partial<CameraFeatureSet>;
}) => apiFetch<CameraRecord>("/api/cameras", { method: "POST", body: JSON.stringify(payload) });
export const updateCamera = (
  cameraId: number,
  payload: Partial<{
    name: string;
    location: string | null;
    source_type: "USB" | "RTSP" | "Arquivo";
    source: string;
    fps: number;
    width: number;
    height: number;
    rotation: 0 | 90 | 180 | 270;
    enabled: boolean;
    features: Partial<CameraFeatureSet>;
  }>,
) => apiFetch<CameraRecord>(`/api/cameras/${cameraId}`, { method: "PUT", body: JSON.stringify(payload) });
export const deleteCamera = (cameraId: number) => apiFetch<{ deleted: boolean; id: number }>(`/api/cameras/${cameraId}`, { method: "DELETE" });

// Testa de verdade quais índices USB respondem agora — ver docstring de
// discover_cameras() no backend. maxIndex vira ?max_index=N.
export const discoverCameras = (maxIndex = 5) => apiFetch<CameraDiscoveryResponse>(`/api/cameras/discover?max_index=${maxIndex}`);

export const listAlerts = (
  params: { limit?: number; severity?: string; status?: string; cameraId?: number | null; feature?: string } = {},
) => {
  const query = new URLSearchParams();
  query.set("limit", String(params.limit ?? 50));
  if (params.severity) query.set("severity", params.severity);
  if (params.status) query.set("status", params.status);
  if (params.cameraId != null) query.set("camera_id", String(params.cameraId));
  if (params.feature) query.set("feature", params.feature);
  return apiFetch<AlertsResponse>(`/alerts?${query.toString()}`);
};

// Ações em lote. Apagar só alcança alertas JÁ resolvidos (o backend recusa o resto).
const comCamera = (cameraId?: number | null) => (cameraId != null ? `?camera_id=${cameraId}` : "");
export const acknowledgeAllAlerts = (cameraId?: number | null) =>
  apiFetch<{ acknowledged: number }>(`/alerts/acknowledge-all${comCamera(cameraId)}`, { method: "POST" });
export const resolveActiveAlerts = (cameraId?: number | null) =>
  apiFetch<{ active_before: number; silencio_s: number; pedidos: number[]; resolvidos_direto: number }>(
    `/alerts/resolve-active${comCamera(cameraId)}`,
    { method: "POST" },
  );
export const deleteResolvedAlerts = (params: { cameraId?: number | null; olderThanDays?: number } = {}) => {
  const query = new URLSearchParams();
  if (params.cameraId != null) query.set("camera_id", String(params.cameraId));
  if (params.olderThanDays != null) query.set("older_than_days", String(params.olderThanDays));
  const qs = query.toString();
  return apiFetch<{ deleted: number; evidence_files_removed: number }>(`/alerts/resolved${qs ? `?${qs}` : ""}`, {
    method: "DELETE",
  });
};
export const markFalsePositive = (alertId: number, reason?: string) =>
  apiFetch<{ alert: Alert }>(`/alerts/${alertId}/false-positive`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
// "Avisei o colaborador": registra na linha do tempo quem tratou o alerta em
// campo, sem resolvê-lo (a detecção é quem resolve). Ver acknowledge_alert()
// em app/api/alerts.py.
export const acknowledgeAlert = (alertId: number, note?: string) =>
  apiFetch<{ alert: Alert }>(`/alerts/${alertId}/acknowledge`, {
    method: "POST",
    body: JSON.stringify({ note }),
  });

export const getModel = () => apiFetch<ModelDiagnostics>("/model");
export const getRiskScore = () => apiFetch<RiskScore>("/risk-score");
export const getRiskTrend = (hours = 24) => apiFetch<RiskTrendResponse>(`/risk-score/trend?hours=${hours}`);

export const getSettings = () => apiFetch<SettingsResponse>("/settings");
export const patchSettings = (updates: Partial<RuntimeSettings>) =>
  apiFetch<{ settings: RuntimeSettings }>("/settings", { method: "PATCH", body: JSON.stringify(updates) });

export const getOverlay = () => apiFetch<{ overlay: OverlayOptions }>("/overlay");
export const patchOverlay = (updates: Partial<OverlayOptions>) =>
  apiFetch<{ overlay: OverlayOptions }>("/overlay", { method: "PATCH", body: JSON.stringify(updates) });

// Com camId, usa a rota POR CÂMERA (zona própria de cada câmera). Sem camId cai
// na rota legada, que opera sobre a câmera padrão.
export const getRiskArea = (camId?: number | null) =>
  apiFetch<{ risk_area: RiskAreaState }>(camId != null ? `/api/cameras/${camId}/risk-area` : "/risk-area");
export const patchRiskArea = (payload: { name?: string; polygon: { x: number; y: number }[] }, camId?: number | null) =>
  apiFetch<{ risk_area: RiskAreaState }>(camId != null ? `/api/cameras/${camId}/risk-area` : "/risk-area", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });

export const listEvents = (params: { limit?: number; eventType?: string; severity?: string } = {}) => {
  const query = new URLSearchParams();
  query.set("limit", String(params.limit ?? 80));
  if (params.eventType) query.set("event_type", params.eventType);
  if (params.severity) query.set("severity", params.severity);
  return apiFetch<EventsResponse>(`/events?${query.toString()}`);
};
