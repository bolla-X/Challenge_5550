import { apiFetch } from "./client";
import type {
  AlertsResponse,
  Alert,
  EventsResponse,
  FeaturesResponse,
  ModelDiagnostics,
  OverlayOptions,
  PreflightResponse,
  RiskAreaState,
  RuntimeSettings,
  SettingsResponse,
  StatusResponse,
} from "./types";

// One function per Flask route, named after the route. See app/api/*.py.

export const getStatus = () => apiFetch<StatusResponse>("/status");
export const getPreflight = () => apiFetch<PreflightResponse>("/preflight");
export const startMonitor = () => apiFetch<StatusResponse>("/start", { method: "POST" });
export const stopMonitor = () => apiFetch<StatusResponse>("/stop", { method: "POST" });

export const getFeatures = () => apiFetch<FeaturesResponse>("/features");
export const patchFeatures = (features: Record<string, boolean>) =>
  apiFetch<FeaturesResponse>("/features", { method: "PATCH", body: JSON.stringify({ features }) });

export const listAlerts = (params: { limit?: number; severity?: string; status?: string } = {}) => {
  const query = new URLSearchParams();
  query.set("limit", String(params.limit ?? 50));
  if (params.severity) query.set("severity", params.severity);
  if (params.status) query.set("status", params.status);
  return apiFetch<AlertsResponse>(`/alerts?${query.toString()}`);
};
export const markFalsePositive = (alertId: number, reason?: string) =>
  apiFetch<{ alert: Alert }>(`/alerts/${alertId}/false-positive`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });

export const getModel = () => apiFetch<ModelDiagnostics>("/model");

export const getSettings = () => apiFetch<SettingsResponse>("/settings");
export const patchSettings = (updates: Partial<RuntimeSettings>) =>
  apiFetch<{ settings: RuntimeSettings }>("/settings", { method: "PATCH", body: JSON.stringify(updates) });

export const getOverlay = () => apiFetch<{ overlay: OverlayOptions }>("/overlay");
export const patchOverlay = (updates: Partial<OverlayOptions>) =>
  apiFetch<{ overlay: OverlayOptions }>("/overlay", { method: "PATCH", body: JSON.stringify(updates) });

export const getRiskArea = () => apiFetch<{ risk_area: RiskAreaState }>("/risk-area");
export const patchRiskArea = (payload: { name?: string; polygon: { x: number; y: number }[] }) =>
  apiFetch<{ risk_area: RiskAreaState }>("/risk-area", { method: "PATCH", body: JSON.stringify(payload) });

export const listEvents = (params: { limit?: number; eventType?: string; severity?: string } = {}) => {
  const query = new URLSearchParams();
  query.set("limit", String(params.limit ?? 80));
  if (params.eventType) query.set("event_type", params.eventType);
  if (params.severity) query.set("severity", params.severity);
  return apiFetch<EventsResponse>(`/events?${query.toString()}`);
};
