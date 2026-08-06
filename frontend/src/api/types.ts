/**
 * DTOs mirroring the Flask backend contract exactly as read from source
 * (not from the old app.js). Each type links back to the Python source of
 * truth so a payload shape change is traceable to one file.
 */

// ---- app/services/feature_manager.py: FeatureFlag.to_dict() -------------
export interface FeatureFlag {
  key: string;
  label: string;
  description: string;
  enabled: boolean;
  group: string;
}

// ---- app/models.py: Alert.to_dict() --------------------------------------
export interface Alert {
  id: number;
  key: string;
  rule: string;
  severity: "critical" | "high" | "medium" | "low" | "info" | string;
  message: string;
  feature: string | null;
  status: "active" | "resolved" | string;
  frame_ref: string | null;
  metadata: Record<string, unknown>;
  false_positive: boolean;
  occurrences: number;
  created_at: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  resolved_at: string | null;
}

// ---- app/models.py: EventLog.to_dict() -----------------------------------
export interface TimelineEvent {
  id: number;
  event_type: string;
  severity: string;
  message: string;
  subject: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
}

// ---- app/vision/schemas.py: BoundingBox.to_dict() ------------------------
export interface BoundingBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

// ---- app/vision/schemas.py: Detection.to_dict() --------------------------
export interface Detection {
  label: string;
  confidence: number;
  box: BoundingBox;
  class_id: number | null;
  category: string;
}

// ---- app/vision/schemas.py: PoseLandmark.to_dict() -----------------------
export interface PoseLandmark {
  name: string;
  x: number;
  y: number;
  z: number;
  visibility: number;
}

// ---- app/vision/schemas.py: PoseResult.to_dict() -------------------------
export interface PoseResult {
  found: boolean;
  landmarks: PoseLandmark[];
}

// ---- app/vision/schemas.py: FrameAnalysis.to_dict(), extended in --------
// ---- monitor_service.py._loop() with alerts/compliance/model ------------
export interface AnalysisPayload {
  detections: Detection[];
  pose: PoseResult;
  risk_events: Record<string, unknown>[];
  alerts: Alert[];
  alert_changes: Alert[];
  alert_resolved: Alert[];
  compliance: ComplianceState;
  model: ModelDiagnostics;
}

// ---- app/vision/yolo_ppe_detector.py: _build_diagnostics() ---------------
export interface ModelClassInfo {
  id: number | string;
  name: string;
  normalized: string;
}

export interface SupportedPpe {
  helmet: boolean;
  vest: boolean;
  gloves: boolean;
}

export interface ModelDiagnostics {
  model_path: string;
  confidence: number;
  device: string | null;
  classes: ModelClassInfo[];
  supported_ppe: SupportedPpe;
  person_supported: boolean;
  ppe_ready: boolean;
  multi_person_detection: boolean;
  max_detections: number;
  warning: string | null;
  error: string | null;
  ppe_feature_enabled?: boolean;
}

// ---- app/vision/person_compliance_matcher.py: build() --------------------
export interface PersonPpeCheck {
  key: string;
  status: "ok" | "missing" | "unsupported" | "disabled" | string;
  message: string;
  detections: Detection[];
  confidence: number;
}

export interface PersonRiskArea {
  status: "inside" | "outside" | string;
  message: string;
}

export interface PersonCompliance {
  id: string;
  label: string;
  confidence: number;
  box: BoundingBox;
  ppe: {
    helmet: PersonPpeCheck;
    vest: PersonPpeCheck;
    gloves: PersonPpeCheck;
  };
  risk_area?: PersonRiskArea;
}

// ---- app/services/compliance_service.py: build_state() -------------------
export interface PpeComplianceCard {
  key: string;
  label: string;
  status: "ok" | "missing" | "critical" | "warning" | "unsupported" | "waiting" | "disabled" | string;
  message: string;
  enabled: boolean;
  supported: boolean;
  detections: Detection[];
  active_alert: Alert | null;
}

export interface PoseComplianceState {
  enabled: boolean;
  status: "disabled" | "waiting" | "critical" | "warning" | "ok" | string;
  message: string;
  active_alert?: Alert;
}

export interface RiskAreaComplianceState {
  enabled: boolean;
  status: "disabled" | "warning" | "ok" | string;
  message: string;
  active_alert?: Alert;
}

export interface ComplianceState {
  person_present: boolean;
  person_count: number;
  people: PersonCompliance[];
  ppe: {
    helmet: PpeComplianceCard;
    vest: PpeComplianceCard;
    gloves: PpeComplianceCard;
  };
  pose: PoseComplianceState;
  risk_area: RiskAreaComplianceState;
  model: ModelDiagnostics;
  active_alerts: Alert[];
}

// ---- app/services/monitor_service.py: settings() -------------------------
export interface RuntimeSettings {
  video_source: string;
  target_fps: number;
  jpeg_quality: number;
  yolo_confidence: number;
  yolo_max_detections: number;
  multi_person_detection: boolean;
  alert_create_after_frames: number;
  alert_resolve_after_frames: number;
  cleanup_on_monitor_start: boolean;
  snapshot_enabled: boolean;
  snapshot_jpeg_quality: number;
  risk_area_name: string;
}

// ---- app/services/monitor_service.py: overlay_options --------------------
export interface OverlayOptions {
  boxes: boolean;
  labels: boolean;
  confidence: boolean;
  pose: boolean;
  risk_area: boolean;
}

// ---- app/services/monitor_service.py: risk_area_state() ------------------
export interface RiskAreaPoint {
  x: number;
  y: number;
}

export interface RiskAreaState {
  name: string;
  polygon: RiskAreaPoint[];
  enabled: boolean;
}

// ---- app/services/snapshot_service.py: info() (shape read via /status) --
export interface SnapshotInfo {
  enabled: boolean;
  snapshot_dir: string;
  jpeg_quality: number;
  [key: string]: unknown;
}

// ---- app/services/monitor_service.py: status() ---------------------------
export interface MonitorStatus {
  running: boolean;
  frame_counter: number;
  last_error: string | null;
  features: Record<string, FeatureFlag>;
  model: ModelDiagnostics;
  active_alerts: Alert[];
  cleanup: Record<string, unknown> | null;
  overlay: OverlayOptions;
  settings: RuntimeSettings;
  risk_area: RiskAreaState;
  snapshot: SnapshotInfo;
}

// ---- GET /status: {"system": "VisionEPI", ...status()} -------------------
export interface StatusResponse extends MonitorStatus {
  system: string;
}

// ---- app/services/monitor_service.py: preflight() ------------------------
export interface PreflightCheck {
  key: string;
  label: string;
  status: "ok" | "warning" | "error" | string;
  message: string;
}

export interface PreflightSummary {
  ok: number;
  warning: number;
  error: number;
}

export interface PreflightResponse {
  checks: PreflightCheck[];
  summary: PreflightSummary;
  can_start: boolean;
}

// ---- GET /features -> {features: FeatureFlag[]} --------------------------
export interface FeaturesResponse {
  features: FeatureFlag[];
}

// ---- GET /alerts -> {items: Alert[], count} ------------------------------
export interface AlertsResponse {
  items: Alert[];
  count: number;
}

// ---- GET /events -> {items: TimelineEvent[], count} ----------------------
export interface EventsResponse {
  items: TimelineEvent[];
  count: number;
}

// ---- GET /settings -> {settings, overlay} --------------------------------
export interface SettingsResponse {
  settings: RuntimeSettings;
  overlay: OverlayOptions;
}

// ---- app/services/risk_score_service.py: compute_risk_score() ------------
// Estatística sobre janela deslizante (contagem de alertas ponderada por
// severidade) — não é predição por IA/ML.
export type RiskLevel = "baixo" | "moderado" | "alto" | "critico";

export interface RiskFeatureScore {
  score: number;
  level: RiskLevel | string;
  alert_count: number;
}

export interface RiskScoreOverall extends RiskFeatureScore {
  driving_feature: string | null;
}

export interface RiskScore {
  window_minutes: number;
  overall: RiskScoreOverall;
  features: Record<string, RiskFeatureScore>;
  computed_at: string;
}

// ---- app/services/risk_score_service.py: compute_risk_trend() ------------
// Cada bucket é pontuado isoladamente (não é janela deslizante) — mostra a
// frequência daquela hora específica, não o /risk-score.overall.
export interface RiskTrendBucket {
  bucket_start: string;
  bucket_end: string;
  overall: { score: number; level: RiskLevel | string };
  features: Record<string, RiskFeatureScore>;
}

export interface RiskTrendResponse {
  hours: number;
  bucket_hours: number;
  buckets: RiskTrendBucket[];
}
