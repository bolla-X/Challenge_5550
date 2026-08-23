import { ROLE_ACCESS, useDashboardStore } from "../store/dashboardStore";
import type { CameraFeatureSet, CameraMock } from "../api/types";

const CAMERA_FEATURE_ORDER: (keyof CameraFeatureSet)[] = ["helmet", "vest", "gloves", "pose", "falls", "posture", "risk_area"];
const CAMERA_FEATURE_LABELS: Record<keyof CameraFeatureSet, string> = {
  helmet: "Capacete",
  vest: "Colete",
  gloves: "Luvas",
  pose: "Pose",
  falls: "Quedas",
  posture: "Postura",
  risk_area: "Área de risco",
};

// Backend ainda é single-source (ver conversa: "usa os modelos que já tem,
// mesma câmera em todos por enquanto") — /video_feed sempre serve a mesma
// câmera física, então toda card "online" do mock aponta pra ela. Troca
// por thumbnail por camera_id assim que o backend suportar multi-source.
function CameraOfflineIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3l18 18M9 7h6l2 3h2a1 1 0 0 1 1 1v7a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1v-4M4 7h1" />
      <circle cx="12" cy="14" r="3" />
    </svg>
  );
}

function CameraCard({
  camera,
  onConfigure,
  canConfigure,
  running,
}: {
  camera: CameraMock;
  onConfigure: (id: number) => void;
  canConfigure: boolean;
  running: boolean;
}) {
  const cardCls = ["cam-card", camera.status === "offline" ? "warn" : camera.alerts.some((a) => a.sev === "critical") ? "error" : ""]
    .filter(Boolean)
    .join(" ");
  const statText =
    camera.status === "offline"
      ? "reconectando…"
      : `${camera.alerts.length} alerta${camera.alerts.length === 1 ? "" : "s"} ativo${camera.alerts.length === 1 ? "" : "s"}`;

  return (
    <div className={cardCls}>
      {camera.status === "offline" ? (
        <div className="cam-frame offline">
          <CameraOfflineIcon />
          <span>Sem sinal — verificar fonte</span>
        </div>
      ) : running ? (
        <div className="cam-frame">
          <span className="cam-live-tag">
            <span className="status-dot ok" /> recebendo
          </span>
          {camera.alerts.length > 0 && (
            <span className="cam-alert-tag">
              {camera.alerts.length} alerta{camera.alerts.length > 1 ? "s" : ""}
            </span>
          )}
          <img src="/video_feed" alt={camera.name} />
        </div>
      ) : (
        <div className="cam-frame offline">
          <span>Monitoramento parado</span>
        </div>
      )}
      <div className="cam-body">
        <div className="cam-title-row">
          <h3>
            <span className={`status-dot ${camera.status === "offline" ? "warn" : "ok"}`} /> {camera.name}
          </h3>
        </div>
        <div className="cam-location">
          {camera.location} · {camera.source_type} {camera.source}
        </div>
        {canConfigure && (
          <div className="cam-conn-row">
            <span>
              latência: <b>{camera.connectivity.latency_ms !== null ? `${camera.connectivity.latency_ms}ms` : "—"}</b>
            </span>
            <span>
              uptime: <b>{camera.connectivity.uptime_pct}%</b>
            </span>
            <span>
              reconectou: <b>{camera.connectivity.last_reconnect}</b>
            </span>
          </div>
        )}
        <div className="cam-feature-chips">
          {CAMERA_FEATURE_ORDER.map((key) => (
            <span key={key} className={`cam-chip ${camera.features[key] ? "on" : ""}`.trim()}>
              {CAMERA_FEATURE_LABELS[key]}
            </span>
          ))}
        </div>
        <div className="cam-footer">
          <span className="cam-footer-stat" style={{ color: camera.status === "offline" ? "var(--warning)" : camera.alerts.length ? "var(--danger)" : "var(--muted)" }}>
            {statText}
          </span>
          <button type="button" className="cam-configure" onClick={() => onConfigure(camera.id)}>
            {canConfigure ? "Configurar" : "Ver"}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
              <path d="M9 6l6 6-6 6" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Grid de câmeras — tela inicial de Técnico/Supervisor (mock, ver
 * mockCameras.ts). Operador nunca chega aqui (ver setMode no store, que
 * trava screen="kiosk" pro Operador).
 */
export function CameraGrid() {
  const cameras = useDashboardStore((s) => s.cameras);
  const mode = useDashboardStore((s) => s.mode);
  const running = useDashboardStore((s) => s.running);
  const setCamId = useDashboardStore((s) => s.setCamId);
  const setScreen = useDashboardStore((s) => s.setScreen);
  const access = ROLE_ACCESS[mode];

  const openFocus = (id: number) => {
    setCamId(id);
    setScreen("focus");
  };

  return (
    <div className="camera-grid">
      {cameras.map((camera) => (
        <CameraCard key={camera.id} camera={camera} onConfigure={openFocus} canConfigure={access.canConfigure} running={running} />
      ))}
      {access.canConfigure && (
        <div className="cam-add-card" role="button" tabIndex={0} onClick={() => alert("Formulário de cadastro de nova câmera (mock, ainda não implementado).")}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <path d="M12 5v14M5 12h14" />
          </svg>
          <span>Adicionar câmera</span>
        </div>
      )}
    </div>
  );
}
