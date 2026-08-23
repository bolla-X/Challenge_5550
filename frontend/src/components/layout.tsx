import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useDashboardStore } from "../store/dashboardStore";

const EASE = [0.16, 1, 0.3, 1] as const; // matches tokens.css --ease
const EASE_IN = "easeIn" as const; // exits — tokens.css only has the ease-out curve above
// Exportado pra command-palette.tsx reaproveitar (não duplicar os 3 perfis
// e seus rótulos em dois arquivos).
export const MODES = [
  { key: "operator", label: "Operador" },
  { key: "technical", label: "Técnico" },
  { key: "supervisor", label: "Supervisor" },
] as const;

/** Ícone de alto-falante — traço grosso, sem preenchimento fino, pra ler
 * a distância num monitor de chão de fábrica. Riscado quando mudo, com
 * cor de aviso (mesma --danger dos status-dots) em vez de um cinza neutro:
 * "mudo" é um estado que precisa saltar aos olhos, não passar despercebido. */
function SpeakerIcon({ muted }: { muted: boolean }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 9v6h4l5 4V5L8 9H4z" fill="currentColor" stroke="none" />
      {muted ? <path d="M15.5 9.5l5 5M20.5 9.5l-5 5" /> : <path d="M16.5 8.5a5 5 0 0 1 0 7" />}
    </svg>
  );
}

export function MuteToggle() {
  const muted = useDashboardStore((s) => s.muted);
  const toggleMuted = useDashboardStore((s) => s.toggleMuted);
  return (
    <button
      type="button"
      className={`mute-toggle ${muted ? "muted" : ""}`.trim()}
      onClick={toggleMuted}
      aria-pressed={muted}
      aria-label={muted ? "Ativar som de alertas" : "Silenciar som de alertas"}
      title={muted ? "Som desligado" : "Som ligado"}
    >
      <SpeakerIcon muted={muted} />
    </button>
  );
}

// Seletor "simular setor" do Operador — existe só nessa fase de testes
// (sem login real ainda, ver conversa no chat). Escreve em operatorCam no
// store; quando o login chegar, isso vira derivado de sessão, não um
// <select> na topbar.
function OperatorCameraSimSelect() {
  const cameras = useDashboardStore((s) => s.cameras);
  const operatorCam = useDashboardStore((s) => s.operatorCam);
  const setOperatorCam = useDashboardStore((s) => s.setOperatorCam);
  return (
    <div className="sim-select-wrap" title="Simula qual câmera é 'do setor' deste Operador — provisório, some quando o login real existir.">
      <label htmlFor="operator-sim-select">simular setor</label>
      <select id="operator-sim-select" value={operatorCam} onChange={(e) => setOperatorCam(Number(e.target.value))}>
        {cameras.map((cam) => (
          <option key={cam.id} value={cam.id}>
            {cam.name}
          </option>
        ))}
      </select>
    </div>
  );
}

export function Topbar() {
  const { mode, setMode, start, stop, connected, running, setCommandPaletteOpen } = useDashboardStore();
  const video = useVideoStatus();
  const shouldReduceMotion = useReducedMotion();
  // Feedback de "seu clique registrou" durante a latência real do REST —
  // sem isso, Iniciar/Parar não dão nenhum sinal até a resposta chegar.
  const [pending, setPending] = useState<"start" | "stop" | null>(null);
  const runAction = (which: "start" | "stop", action: () => Promise<void>) => {
    setPending(which);
    action()
      .catch((err) => console.error(err))
      .finally(() => setPending(null));
  };
  return (
    <header className="topbar">
      <div className="topbar-inner">
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
            {/* Status do vídeo só é informação útil quando há stream — com
                running=false os dois dots diziam "parado" ao mesmo tempo. */}
            {running && (
              <span className="status-dot-item">
                <span className={`status-dot ${video.status}`} /> {video.label}
              </span>
            )}
          </div>
        </div>
        <div className="topbar-actions">
          {mode === "operator" && <OperatorCameraSimSelect />}
          <button type="button" className="secondary command-palette-trigger" onClick={() => setCommandPaletteOpen(true)}>
            Buscar <kbd>Ctrl K</kbd>
          </button>
          <MuteToggle />
          <div className="mode-toggle" role="group" aria-label="Modo de visualização">
            {MODES.map((item) => (
              <button key={item.key} className={`segmented ${mode === item.key ? "active" : ""}`.trim()} type="button" onClick={() => setMode(item.key)}>
                {/* Comunica que o clique produziu exatamente esse destaque —
                    a pílula desliza até o botão clicado em vez de trocar de
                    cor abruptamente em dois lugares ao mesmo tempo. */}
                {mode === item.key && (
                  <motion.span
                    className="segmented-pill"
                    layoutId="mode-pill"
                    transition={{ duration: shouldReduceMotion ? 0 : 0.2, ease: EASE }}
                  />
                )}
                <span className="segmented-label">{item.label}</span>
              </button>
            ))}
          </div>
          <button
            className={`secondary ${pending === "stop" ? "is-pending" : ""}`.trim()}
            type="button"
            disabled={pending !== null}
            onClick={() => runAction("stop", stop)}
          >
            {pending === "stop" ? "Parando…" : "Parar"}
          </button>
          <button
            type="button"
            id="startBtn"
            className={pending === "start" ? "is-pending" : ""}
            disabled={pending !== null}
            onClick={() => runAction("start", start)}
          >
            {pending === "start" ? "Iniciando…" : "Iniciar"}
          </button>
        </div>
      </div>
    </header>
  );
}

export function MessageBar() {
  const { message, hideMessage } = useDashboardStore();
  const shouldReduceMotion = useReducedMotion();
  return (
    <AnimatePresence initial={false}>
      {message && (
        <motion.section
          key={message.text}
          className={`message-bar ${message.tone === "warning" ? "" : message.tone}`.trim()}
          onClick={hideMessage}
          role="status"
          initial={shouldReduceMotion ? false : { opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={
            shouldReduceMotion
              ? { opacity: 0 }
              : { opacity: 0, height: 0, marginTop: 0, paddingTop: 0, paddingBottom: 0, transition: { duration: 0.15, ease: EASE_IN } }
          }
          transition={{ duration: shouldReduceMotion ? 0.001 : 0.2, ease: EASE }}
        >
          {message.text}
        </motion.section>
      )}
    </AnimatePresence>
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
