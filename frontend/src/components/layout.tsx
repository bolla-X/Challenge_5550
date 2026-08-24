import { useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useDashboardStore } from "../store/dashboardStore";

const EASE = [0.16, 1, 0.3, 1] as const; // matches tokens.css --ease
const EASE_IN = "easeIn" as const; // exits — tokens.css only has the ease-out curve above

const ROTULO_DO_PAPEL: Record<string, string> = {
  operator: "Operador",
  technical: "Técnico",
  supervisor: "Supervisor",
};

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

/** Aviso para o Operador cuja conta ainda não tem setor atribuído.
 *
 * O backend não entrega câmera nenhuma nesse estado (ver camera_scope em
 * app/utils/auth.py), então não há o que escolher — o que cabe aqui é dizer
 * a quem pedir. O seletor que existia antes prometia uma escolha que o
 * servidor recusaria.
 */
function OperadorSemSetor() {
  const user = useDashboardStore((s) => s.user);
  if (user?.camera_id != null) return null;
  return (
    <div className="sim-select-wrap" role="status">
      <label>sem setor</label>
      <span title="Peça ao supervisor para atribuir a câmera do seu setor.">peça ao supervisor</span>
    </div>
  );
}

/** Quem está logado + sair. Substitui o seletor de perfil da topbar. */
function UserMenu() {
  const user = useDashboardStore((s) => s.user);
  const logout = useDashboardStore((s) => s.logout);
  const [saindo, setSaindo] = useState(false);
  if (!user) return null;

  return (
    <div className="user-menu">
      <div className="user-menu-info">
        <strong>{user.name}</strong>
        <span>{ROTULO_DO_PAPEL[user.role] ?? user.role}</span>
      </div>
      <button
        type="button"
        className="secondary small"
        disabled={saindo}
        onClick={() => {
          setSaindo(true);
          logout().finally(() => setSaindo(false));
        }}
      >
        {saindo ? "Saindo…" : "Sair"}
      </button>
    </div>
  );
}

export function Topbar() {
  const { mode, start, stop, connected, running, setCommandPaletteOpen } = useDashboardStore();
  const video = useVideoStatus();
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
          {mode === "operator" && <OperadorSemSetor />}
          <button type="button" className="secondary command-palette-trigger" onClick={() => setCommandPaletteOpen(true)}>
            Buscar <kbd>Ctrl K</kbd>
          </button>
          <MuteToggle />
          {/* O seletor de perfil virou identidade: o modo agora É o papel da
              pessoa logada, não um botão. Trocar de perfil exige outra conta —
              é o ponto de ter autenticação de verdade. */}
          <UserMenu />
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
  const video = useDashboardStore((s) => s.videoStream);
  const [, forceTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);
  if (!running) return { status: "warn" as const, label: "parado" };

  // O backend sabe o estado real da captura (VideoStream.status()). Quando ele
  // chega, vale mais que a heurística de idade do frame abaixo: "reconectando,
  // 3ª tentativa" diz o que "congelado" não dizia.
  if (video) {
    if (video.state === "unavailable") {
      return { status: "error" as const, label: `sem sinal — nova tentativa em ${Math.ceil(video.seconds_until_retry)}s` };
    }
    if (video.state === "reconnecting") {
      return { status: "error" as const, label: `reconectando (tentativa ${video.reconnect_attempts + 1})` };
    }
  }

  if (!lastAnalysisAt) return { status: "warn" as const, label: "aguardando frame" };
  const age = Date.now() - lastAnalysisAt;
  if (age > 4500) return { status: "error" as const, label: "congelado" };
  if (age > 1800) return { status: "warn" as const, label: "instável" };
  return { status: "ok" as const, label: "recebendo" };
}

export function useVideoStreamLabel() {
  return useVideoStatus();
}