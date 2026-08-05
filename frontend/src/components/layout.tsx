import { useEffect, useState } from "react";
import { useDashboardStore } from "../store/dashboardStore";

export function TopBar() {
  const { mode, setMode, start, stop } = useDashboardStore();
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">VE</div>
        <div>
          <h1>VisionEPI</h1>
          <p>Console de monitoramento: EPIs, postura, quedas, área de risco.</p>
        </div>
      </div>
      <div className="top-actions">
        <div className="mode-toggle" role="group" aria-label="Modo de visualização">
          <button className={`segmented ${mode === "operator" ? "active" : ""}`.trim()} type="button" onClick={() => setMode("operator")}>
            Operador
          </button>
          <button className={`segmented ${mode === "technical" ? "active" : ""}`.trim()} type="button" onClick={() => setMode("technical")}>
            Técnico
          </button>
        </div>
        <button type="button" id="startBtn" onClick={() => start().catch((err) => console.error(err))}>
          Iniciar
        </button>
        <button className="secondary" type="button" onClick={() => stop().catch((err) => console.error(err))}>
          Parar
        </button>
      </div>
    </header>
  );
}

export function MessageBar() {
  const { message, hideMessage } = useDashboardStore();
  if (!message) return <section className="message-bar hidden" />;
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

export function StatusRibbon() {
  const { connected, running, frameCounter, wsFrameCounter, fps } = useDashboardStore();
  const video = useVideoStatus();
  return (
    <section className="status-grid" aria-label="Status do sistema">
      <article className="status-card ok">
        <span>Backend</span>
        <strong>Online</strong>
      </article>
      <article className={`status-card ${connected ? "ok" : "error"}`}>
        <span>WebSocket</span>
        <strong>{connected ? "Conectado" : "Desconectado"}</strong>
      </article>
      <article className={`status-card ${running ? "ok" : "warn"}`}>
        <span>Monitor</span>
        <strong>{running ? "Ativo" : "Parado"}</strong>
      </article>
      <article className={`status-card ${video.status}`}>
        <span>Vídeo</span>
        <strong>{video.label}</strong>
      </article>
      <article className="status-card technical-only">
        <span>Frames</span>
        <strong>{frameCounter || wsFrameCounter}</strong>
      </article>
      <article className="status-card technical-only">
        <span>FPS visual</span>
        <strong>{fps.toFixed(1)}</strong>
      </article>
    </section>
  );
}
