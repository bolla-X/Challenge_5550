import { create } from "zustand";
import { devtools } from "zustand/middleware";
import { socket } from "../socket/client";
import type { ServerEventName, ServerEvents } from "../socket/events";
import {
  getFeatures,
  getOverlay,
  getRiskArea,
  getSettings,
  getStatus,
  listAlerts,
  listEvents,
  markFalsePositive as apiMarkFalsePositive,
  patchFeatures as apiPatchFeatures,
  patchOverlay as apiPatchOverlay,
  patchRiskArea as apiPatchRiskArea,
  patchSettings as apiPatchSettings,
  startMonitor,
  stopMonitor,
} from "../api/endpoints";
import type {
  Alert,
  ComplianceState,
  Detection,
  FeatureFlag,
  ModelDiagnostics,
  OverlayOptions,
  PoseResult,
  RiskAreaState,
  RuntimeSettings,
  TimelineEvent,
} from "../api/types";

export type ViewMode = "operator" | "technical";

interface DashboardState {
  // connection
  connected: boolean;
  mode: ViewMode;

  // monitor
  running: boolean;
  frameCounter: number;
  lastError: string | null;

  // domain slices, each owned by exactly one socket event / REST call
  features: FeatureFlag[];
  overlay: OverlayOptions | null;
  settings: RuntimeSettings | null;
  riskArea: RiskAreaState | null;
  model: ModelDiagnostics | null;
  compliance: ComplianceState | null;
  activeAlerts: Alert[];
  alertHistory: Alert[];
  timeline: TimelineEvent[];
  message: { text: string; tone: "ok" | "warning" | "error" } | null;
  lastAnalysisAt: number | null;
  wsFrameCounter: number;
  fps: number;
  lastDetections: Detection[];
  lastPose: PoseResult | null;

  // Local-only UI state for the risk-area canvas editor (not server state —
  // riskArea above holds the saved polygon; this is the in-progress draft).
  riskEditorActive: boolean;
  riskEditorPoints: { x: number; y: number }[];
  toggleRiskEditor: () => void;
  clearRiskEditorPoints: () => void;
  addRiskEditorPoint: (point: { x: number; y: number }) => void;
  resetRiskEditorFromServer: () => void;

  // actions
  setMode: (mode: ViewMode) => void;
  showMessage: (text: string, tone?: "ok" | "warning" | "error") => void;
  hideMessage: () => void;
  bootstrap: () => Promise<void>;
  start: () => Promise<void>;
  stop: () => Promise<void>;
  updateFeatures: (updates: Record<string, boolean>) => Promise<void>;
  updateOverlay: (updates: Partial<OverlayOptions>) => Promise<void>;
  updateSettings: (updates: Partial<RuntimeSettings>) => Promise<void>;
  updateRiskArea: (payload: { name?: string; polygon: { x: number; y: number }[] }) => Promise<void>;
  markFalsePositive: (alertId: number, reason?: string) => Promise<void>;
}

const MAX_TIMELINE = 90;
const MAX_HISTORY = 80;
// Matches the original app.js's state.fpsSamples: 20-sample moving average,
// not an instantaneous delta (too noisy for diagnostic use in Técnico mode).
// Module-level, not store state — it's a rolling accumulator, not something
// any component reads directly (only the derived `fps` average is exposed).
const FPS_SAMPLE_WINDOW = 20;
const fpsSamples: number[] = [];

export const useDashboardStore = create<DashboardState>()(
  devtools(
    (set) => ({
      connected: socket.connected,
      mode: "operator",

      running: false,
      frameCounter: 0,
      lastError: null,

      features: [],
      overlay: null,
      settings: null,
      riskArea: null,
      model: null,
      compliance: null,
      activeAlerts: [],
      alertHistory: [],
      timeline: [],
      message: null,
      lastAnalysisAt: null,
      wsFrameCounter: 0,
      fps: 0,
      lastDetections: [],
      lastPose: null,

      riskEditorActive: false,
      riskEditorPoints: [],
      toggleRiskEditor: () => set((state) => ({ riskEditorActive: !state.riskEditorActive }), false, "toggleRiskEditor"),
      clearRiskEditorPoints: () => set({ riskEditorPoints: [] }, false, "clearRiskEditorPoints"),
      addRiskEditorPoint: (point) =>
        set((state) => ({ riskEditorPoints: [...state.riskEditorPoints, point] }), false, "addRiskEditorPoint"),
      resetRiskEditorFromServer: () =>
        set(
          (state) => ({ riskEditorPoints: (state.riskArea?.polygon || []).map((p) => ({ x: p.x, y: p.y })) }),
          false,
          "resetRiskEditorFromServer",
        ),

      setMode: (mode) => set({ mode }, false, "setMode"),
      showMessage: (text, tone = "warning") => set({ message: { text, tone } }, false, "showMessage"),
      hideMessage: () => set({ message: null }, false, "hideMessage"),

      bootstrap: async () => {
        const [status, featuresRes, settingsRes, overlayRes, riskAreaRes, eventsRes, alertsRes] = await Promise.all([
          getStatus(),
          getFeatures(),
          getSettings(),
          getOverlay(),
          getRiskArea(),
          listEvents({ limit: 80, eventType: "alert_resolved" }),
          listAlerts({ limit: 50 }),
        ]);
        set(
          {
            running: status.running,
            frameCounter: status.frame_counter,
            lastError: status.last_error,
            model: status.model,
            activeAlerts: status.active_alerts,
            features: featuresRes.features,
            settings: settingsRes.settings,
            overlay: overlayRes.overlay,
            riskArea: riskAreaRes.risk_area,
            timeline: eventsRes.items,
            alertHistory: alertsRes.items,
            riskEditorPoints: (riskAreaRes.risk_area.polygon || []).map((p) => ({ x: p.x, y: p.y })),
          },
          false,
          "bootstrap",
        );
      },

      start: async () => {
        const status = await startMonitor();
        set({ running: status.running, frameCounter: status.frame_counter }, false, "start");
      },
      stop: async () => {
        const status = await stopMonitor();
        set({ running: status.running }, false, "stop");
      },
      updateFeatures: async (updates) => {
        const res = await apiPatchFeatures(updates);
        set({ features: res.features }, false, "updateFeatures");
      },
      updateOverlay: async (updates) => {
        const res = await apiPatchOverlay(updates);
        set({ overlay: res.overlay }, false, "updateOverlay");
      },
      updateSettings: async (updates) => {
        const res = await apiPatchSettings(updates);
        set({ settings: res.settings, message: { text: "Configurações runtime salvas.", tone: "ok" } }, false, "updateSettings");
      },
      updateRiskArea: async (payload) => {
        try {
          const res = await apiPatchRiskArea(payload);
          set({ riskArea: res.risk_area, message: { text: "Área de risco atualizada no backend.", tone: "ok" } }, false, "updateRiskArea");
        } catch (error) {
          set({ message: { text: error instanceof Error ? error.message : "Falha ao salvar área de risco.", tone: "error" } }, false, "updateRiskArea:error");
          throw error;
        }
      },
      markFalsePositive: async (alertId, reason) => {
        try {
          const res = await apiMarkFalsePositive(alertId, reason);
          resolveAlert(res.alert);
          set({ message: { text: "Alerta marcado como falso positivo.", tone: "ok" } }, false, "markFalsePositive");
        } catch (error) {
          set({ message: { text: error instanceof Error ? error.message : "Falha ao marcar falso positivo.", tone: "error" } }, false, "markFalsePositive:error");
        }
      },
    }),
    { name: "visionepi-dashboard" },
  ),
);

/** Shared by the alert_resolved socket handler and the false-positive REST action. */
function resolveAlert(alert: Alert) {
  useDashboardStore.setState(
    (state) => ({
      activeAlerts: state.activeAlerts.filter((item) => item.id !== alert.id),
      alertHistory: [alert, ...state.alertHistory.filter((item) => item.id !== alert.id)].slice(0, MAX_HISTORY),
    }),
    false,
    "resolveAlert",
  );
}

function upsertActiveAlert(alert: Alert) {
  if (alert.status === "resolved") return;
  useDashboardStore.setState(
    (state) => ({
      activeAlerts: [...state.activeAlerts.filter((item) => item.id !== alert.id), alert],
    }),
    false,
    "upsertActiveAlert",
  );
}

/**
 * Wires every Socket.IO event the backend emits to a store update.
 * Call once at app root (see main.tsx). Logs each event so the checkpoint
 * ("quero ver os eventos chegando") is visible without needing the Redux
 * DevTools extension installed.
 */
export function subscribeToServerEvents(): () => void {
  const set = useDashboardStore.setState;
  // Track exact handler references: socket.off(event) with no handler wipes
  // every listener for that event, which breaks under React 18 StrictMode's
  // dev-only double-invoke (mount -> cleanup -> mount) — the first mount's
  // cleanup would delete the second mount's listeners too.
  const teardown: Array<() => void> = [];

  function on<K extends ServerEventName>(event: K, handler: (payload: ServerEvents[K]) => void) {
    const wrapped = (payload: ServerEvents[K]) => {
      console.log(`[ws] ${event}`, payload);
      handler(payload);
    };
    // TS can't prove `wrapped`'s type lines up with the overloaded, K-indexed
    // `Socket#on` signature when K is itself generic (a known TS limitation
    // with higher-order generics against overloads) — every call site below
    // is a concrete, correctly-typed K, so this cast is safe.
    (socket.on as (event: K, handler: (payload: ServerEvents[K]) => void) => void)(event, wrapped);
    teardown.push(() => (socket.off as (event: K, handler: (payload: ServerEvents[K]) => void) => void)(event, wrapped));
  }

  const onConnect = () => {
    console.log("[ws] connect");
    set({ connected: true }, false, "ws:connect");
  };
  const onDisconnect = () => {
    console.log("[ws] disconnect");
    set({ connected: false }, false, "ws:disconnect");
  };
  socket.on("connect", onConnect);
  socket.on("disconnect", onDisconnect);
  teardown.push(() => socket.off("connect", onConnect), () => socket.off("disconnect", onDisconnect));

  on("monitor_status", (status) =>
    set(
      {
        running: status.running,
        frameCounter: status.frame_counter,
        lastError: status.last_error,
        model: status.model,
        activeAlerts: status.active_alerts,
        overlay: status.overlay,
        settings: status.settings,
        riskArea: status.risk_area,
      },
      false,
      "ws:monitor_status",
    ),
  );
  on("features_updated", (payload) => set({ features: payload.features }, false, "ws:features_updated"));
  on("model_diagnostics", (model) => {
    set({ model }, false, "ws:model_diagnostics");
    if (model.warning) useDashboardStore.getState().showMessage(model.warning, model.error ? "error" : "warning");
    else useDashboardStore.getState().hideMessage();
  });
  on("settings_updated", (settings) => set({ settings }, false, "ws:settings_updated"));
  on("overlay_updated", (overlay) => set({ overlay }, false, "ws:overlay_updated"));
  on("risk_area_updated", (riskArea) => set({ riskArea }, false, "ws:risk_area_updated"));
  on("compliance_state", (compliance) => set({ compliance }, false, "ws:compliance_state"));
  on("active_alerts", (payload) => set({ activeAlerts: payload.items }, false, "ws:active_alerts"));
  on("analysis", (payload) =>
    set(
      (state) => {
        const now = Date.now();
        if (state.lastAnalysisAt) {
          const delta = Math.max(1, now - state.lastAnalysisAt);
          fpsSamples.push(1000 / delta);
          if (fpsSamples.length > FPS_SAMPLE_WINDOW) fpsSamples.shift();
        }
        const fps = fpsSamples.length ? fpsSamples.reduce((a, b) => a + b, 0) / fpsSamples.length : state.fps;
        return {
          compliance: payload.compliance,
          model: payload.model,
          activeAlerts: payload.alerts,
          lastAnalysisAt: now,
          wsFrameCounter: state.wsFrameCounter + 1,
          fps,
          lastDetections: payload.detections,
          lastPose: payload.pose,
        };
      },
      false,
      "ws:analysis",
    ),
  );
  on("timeline_event", (event) =>
    set((state) => ({ timeline: [event, ...state.timeline].slice(0, MAX_TIMELINE) }), false, "ws:timeline_event"),
  );
  on("alert_created", upsertActiveAlert);
  on("alert", upsertActiveAlert); // legacy alias, same payload as alert_created
  on("alert_updated", upsertActiveAlert);
  on("alert_resolved", resolveAlert);

  if (!socket.connected) socket.connect();

  return () => teardown.forEach((fn) => fn());
}
