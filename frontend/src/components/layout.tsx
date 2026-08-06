import { useEffect, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";

export function Topbar() {
  const { mode, setMode, start, stop, connected, running } = useDashboardStore();
  const video = useVideoStatus();
  return (
    <header className="topbar">
      <div className="topbar-brand">
        <h1>VisionEPI</h1>
        <div className="topbar-status">
          <span className="status-dot-item">
            <span className="status-dot ok" /> backend
          </span>
          <span className="status-dot-item">
            <span className={`status-dot ${connected ? "ok" : "error"}`} /> conexão
          </span>
          <span className="status-dot-item">
            <span className={`status-dot ${running ? "ok" : "warn"}`} /> {running ? "monitorando" : "parado"}
          </span>
          <span className="status-dot-item">
            <span className={`status-dot ${video.status}`} /> {video.label}
          </span>
        </div>
      </div>
      <div className="topbar-actions">
        <div className="mode-toggle" role="group" aria-label="Modo de visualização">
          <button className={`segmented ${mode === "operator" ? "active" : ""}`.trim()} type="button" onClick={() => setMode("operator")}>
            Operador
          </button>
          <button className={`segmented ${mode === "technical" ? "active" : ""}`.trim()} type="button" onClick={() => setMode("technical")}>
            Técnico
          </button>
        </div>
        <button className="secondary" type="button" onClick={() => stop().catch((err) => console.error(err))}>
          Parar
        </button>
        <button type="button" id="startBtn" onClick={() => start().catch((err) => console.error(err))}>
          Iniciar
        </button>
      </div>
    </header>
  );
}

export function MessageBar() {
  const { message, hideMessage } = useDashboardStore();
  if (!message) return null;
  return (
    <section className={`message-bar ${message.tone === "warning" ? "" : message.tone}`.trim()} onClick={hideMessage} role="status">
      {message.text}
    </section>
  );
}

/** Video status derived the same way the old setVideoState() interval did:
 * fresh analysis -> ok, stale -> warn, very stale -> error. Recomputed every
 * second via a render tick since it must age even without new WS events. */
function useVideoStatus() {
  const running = useDashboardStore((s) => s.running);
  const lastAnalysisAt = useDashboardStore((s) => s.lastAnalysisAt);
  const [, forceTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);
  if (!running) return { status: "warn" as const, label: "parado" };
  if (!lastAnalysisAt) return { status: "warn" as const, label: "aguardando frame" };
  const age = Date.now() - lastAnalysisAt;
  if (age > 4500) return { status: "error" as const, label: "congelado" };
  if (age > 1800) return { status: "warn" as const, label: "instável" };
  return { status: "ok" as const, label: "recebendo" };
}

export function useVideoStreamLabel() {
  return useVideoStatus();
}
