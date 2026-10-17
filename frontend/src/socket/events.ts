import type { Alert, AnalysisPayload, Incidente, ComplianceState, FeatureFlag, ModelDiagnostics, MonitorStatus, OverlayOptions, PreAlerta, RiskAreaState, RiskScore, RuntimeSettings, TimelineEvent } from "../api/types";

/** Alerta crítico sem reconhecimento (M7, app/services/escalonamento.py). Nível 1: supervisor; nível 2: TV e torre. */
export interface EventoDeEscalonamento {
  nivel: 1 | 2;
  papel: "supervisor" | "tv_torre";
  alerta_id: number;
  camera_id: number | null;
  regra: string | null;
  severidade: string | null;
  mensagem: string | null;
  segundos_sem_reconhecer: number;
  prazo_s: number;
  origem_do_prazo: "regra" | "configuracao";
  ts: string;
}

/**
 * Every event the Flask backend emits, and its payload shape.
 * Source: app/services/monitor_service.py + app/services/alert_state_service.py
 * (grep'd both files directly, not the old app.js).
 */
export interface ServerEvents {
  monitor_status: MonitorStatus;
  features_updated: { features: FeatureFlag[]; camera_id?: number | null };
  model_diagnostics: ModelDiagnostics;
  settings_updated: RuntimeSettings;
  overlay_updated: OverlayOptions;
  risk_area_updated: RiskAreaState;
  risk_score: RiskScore;
  timeline_event: TimelineEvent;
  compliance_state: ComplianceState;
  analysis: AnalysisPayload;
  active_alerts: { camera_id?: number | null; items: Alert[]; count: number; incidentes?: Incidente[] };
  incident_updated: Incidente;
  pre_alertas: { camera_id?: number | null; items: PreAlerta[] };
  alert_created: Alert;
  alert: Alert; // legacy alias of alert_created, same payload
  alert_updated: Alert;
  alert_resolved: Alert;
  escalonamento: EventoDeEscalonamento; // só a sala do parque (supervisão); o operador de setor não recebe
}

export type ServerEventName = keyof ServerEvents;
