import type {
  Alert,
  AnalysisPayload,
  ComplianceState,
  FeatureFlag,
  ModelDiagnostics,
  MonitorStatus,
  OverlayOptions,
  RiskAreaState,
  RiskScore,
  RuntimeSettings,
  TimelineEvent,
} from "../api/types";

/**
 * Every event the Flask backend emits, and its payload shape.
 * Source: app/services/monitor_service.py + app/services/alert_state_service.py
 * (grep'd both files directly, not the old app.js).
 */
export interface ServerEvents {
  monitor_status: MonitorStatus;
  features_updated: { features: FeatureFlag[] };
  model_diagnostics: ModelDiagnostics;
  settings_updated: RuntimeSettings;
  overlay_updated: OverlayOptions;
  risk_area_updated: RiskAreaState;
  risk_score: RiskScore;
  timeline_event: TimelineEvent;
  compliance_state: ComplianceState;
  analysis: AnalysisPayload;
  active_alerts: { items: Alert[]; count: number };
  alert_created: Alert;
  alert: Alert; // legacy alias of alert_created, same payload
  alert_updated: Alert;
  alert_resolved: Alert;
}

export type ServerEventName = keyof ServerEvents;
